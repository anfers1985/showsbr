"""
ShowsBR — Agente Publicador de Shows
Lê a aba Aprovados do Google Sheets e atualiza os JSONs em public/data/shows/.
Roda via GitHub Actions a cada 2 horas.
"""

import os
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

# data/ agora fica dentro de public/ para o Cloudflare Pages servir os JSONs
DATA_DIR = Path('public/data/shows')

# Mapeamento fixo de colunas por ÍNDICE (evita problema de cabeçalho duplicado)
# Deve corresponder exatamente à ordem das colunas na planilha
COL = {
    'id': 0,           # A
    'artista': 1,      # B
    'evento': 2,       # C  (Artista/Evento)
    'descricao': 3,    # D
    'genero': 4,       # E
    'data': 5,         # F  (Data do show — DD/MM/AAAA)
    'horario': 6,      # G
    'local': 7,        # H
    'endereco': 8,     # I
    'cidade': 9,       # J
    'estado': 10,      # K
    'organizador': 11, # L
    'cnpj': 12,        # M
    'valores': 13,     # N
    'gratuito': 14,    # O
    'link_compra': 15, # P
    'cupom': 16,       # Q
    'fonte': 17,       # R
    'data_coleta': 18, # S  (Data Coleta)
}


def conectar_sheets():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    sheets_id = os.environ.get('SHEETS_ID')
    if not creds_json or not sheets_id:
        raise ValueError('GOOGLE_CREDENTIALS e SHEETS_ID devem estar configurados.')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(sheets_id)


def ler_aprovados(aba):
    """
    Usa get_all_values() (retorna lista de listas) em vez de get_all_records()
    para evitar o erro de cabeçalho duplicado do gspread.
    Pula a linha 1 (cabeçalhos).
    """
    todas = aba.get_all_values()
    if len(todas) <= 1:
        log.info('Aba Aprovados vazia ou só com cabeçalho.')
        return []
    linhas = todas[1:]  # remove cabeçalho
    log.info(f'{len(linhas)} linhas encontradas na aba Aprovados.')
    return linhas


def cell(linha, col_name):
    """Retorna o valor de uma célula pelo nome do campo, ou string vazia."""
    idx = COL.get(col_name, -1)
    if idx < 0 or idx >= len(linha):
        return ''
    return str(linha[idx]).strip()


def converter_para_json(linha):
    """Converte uma linha (lista) em dict JSON do site."""
    artista = cell(linha, 'artista') or cell(linha, 'evento')
    data_raw = cell(linha, 'data')   # DD/MM/AAAA
    cidade = cell(linha, 'cidade')
    estado = cell(linha, 'estado')

    if not artista or not estado:
        log.warning(f'Linha ignorada — artista ou estado vazio: {linha[:5]}')
        return None

    # Converter data para ISO
    data_iso = ''
    try:
        if '/' in data_raw:
            dt = datetime.strptime(data_raw, '%d/%m/%Y')
        elif '-' in data_raw:
            dt = datetime.strptime(data_raw[:10], '%Y-%m-%d')
        else:
            raise ValueError(f'Formato de data não reconhecido: {data_raw}')
        data_iso = dt.strftime('%Y-%m-%d')
    except ValueError as e:
        log.warning(f'Data inválida para "{artista}": "{data_raw}" — {e}')
        return None

    gratuito_raw = cell(linha, 'gratuito').upper()
    gratuito = gratuito_raw in ('SIM', 'TRUE', '1', 'S', 'YES')

    show_id = cell(linha, 'id') or gerar_id(artista, data_iso, cidade)

    return {
        'id': show_id,
        'artista': artista,
        'genero': cell(linha, 'genero'),
        'data_iso': data_iso,
        'horario': cell(linha, 'horario'),
        'local': cell(linha, 'local'),
        'endereco': cell(linha, 'endereco'),
        'cidade': cidade,
        'estado': estado,
        'descricao': cell(linha, 'descricao'),
        'organizador': cell(linha, 'organizador'),
        'cnpj': cell(linha, 'cnpj'),
        'valores': cell(linha, 'valores'),
        'gratuito': gratuito,
        'link_compra': cell(linha, 'link_compra'),
        'cupom': cell(linha, 'cupom'),
        'classificacao': '',
        'status': 'Confirmado',
        'fonte': cell(linha, 'fonte'),
    }


def gerar_id(artista, data, cidade):
    chave = f'{artista.lower().strip()}-{data}-{cidade.lower().strip()}'
    return hashlib.md5(chave.encode()).hexdigest()[:12]


def carregar_json_estado(estado):
    caminho = DATA_DIR / f'{estado}.json'
    if caminho.exists():
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.error(f'Erro ao carregar {caminho}: {e}')
    return []


def salvar_json_estado(estado, shows):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    caminho = DATA_DIR / f'{estado}.json'
    shows_sorted = sorted(shows, key=lambda s: s.get('data_iso', ''))
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(shows_sorted, f, ensure_ascii=False, indent=2)
    log.info(f'{caminho}: {len(shows_sorted)} shows salvos.')


def main():
    log.info('=== ShowsBR Agente Publicador iniciado ===')

    planilha = conectar_sheets()
    aba_aprovados = planilha.worksheet('Aprovados')

    linhas = ler_aprovados(aba_aprovados)
    if not linhas:
        log.info('Nenhum show aprovado pendente. Encerrando.')
        return

    por_estado = {}
    validos = 0
    for linha in linhas:
        show = converter_para_json(linha)
        if not show:
            continue
        estado = show['estado']
        por_estado.setdefault(estado, []).append(show)
        validos += 1

    log.info(f'{validos} shows válidos em {len(por_estado)} estados.')

    for estado, novos_shows in por_estado.items():
        existentes = carregar_json_estado(estado)
        ids_existentes = {s['id'] for s in existentes}
        adicionados = 0
        for show in novos_shows:
            if show['id'] not in ids_existentes:
                existentes.append(show)
                ids_existentes.add(show['id'])
                adicionados += 1
            else:
                for i, ex in enumerate(existentes):
                    if ex['id'] == show['id']:
                        existentes[i] = show
                        break
        salvar_json_estado(estado, existentes)
        log.info(f'{estado}: {adicionados} shows novos adicionados.')

    log.info('=== Agente Publicador finalizado ===')


if __name__ == '__main__':
    main()
