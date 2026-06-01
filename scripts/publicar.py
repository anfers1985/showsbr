"""
ShowsBR — Agente Publicador de Shows
Lê a aba Aprovados do Google Sheets e atualiza os arquivos JSON no repositório.
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

DATA_DIR = Path('public/data/shows')


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
    """Lê todos os registros da aba Aprovados."""
    registros = aba.get_all_records()
    log.info(f'{len(registros)} registros encontrados na aba Aprovados.')
    return registros


def converter_para_json(registro):
    """Converte uma linha do Sheets no schema JSON do site."""
    artista = registro.get('Artista', '') or registro.get('Artista/Evento', '')
    data_raw = registro.get('Data', '')  # DD/MM/YYYY
    cidade = registro.get('Cidade', '')
    estado = registro.get('Estado', '')

    # Converter data para ISO
    data_iso = ''
    try:
        if '/' in data_raw:
            dt = datetime.strptime(data_raw, '%d/%m/%Y')
        else:
            dt = datetime.strptime(data_raw[:10], '%Y-%m-%d')
        data_iso = dt.strftime('%Y-%m-%d')
    except ValueError:
        log.warning(f'Data inválida para {artista}: "{data_raw}"')
        return None

    gratuito_raw = str(registro.get('Gratuito', 'NÃO')).upper()
    gratuito = gratuito_raw in ('SIM', 'TRUE', '1', 'S', 'YES')

    show_id = registro.get('ID', '') or gerar_id(artista, data_iso, cidade)

    return {
        'id': show_id,
        'artista': artista,
        'genero': registro.get('Gênero', '') or registro.get('Genero', ''),
        'data_iso': data_iso,
        'horario': registro.get('Horário', '') or registro.get('Horario', ''),
        'local': registro.get('Local', ''),
        'endereco': registro.get('Endereço', '') or registro.get('Endereco', ''),
        'cidade': cidade,
        'estado': estado,
        'descricao': registro.get('Descrição', '') or registro.get('Descricao', ''),
        'organizador': registro.get('Organizador', ''),
        'cnpj': registro.get('CNPJ', ''),
        'valores': registro.get('Valores', ''),
        'gratuito': gratuito,
        'link_compra': registro.get('Link Compra', '') or registro.get('Link_Compra', ''),
        'cupom': registro.get('Cupom', ''),
        'classificacao': registro.get('Classificação', '') or registro.get('Classificacao', ''),
        'status': registro.get('Status', 'Confirmado'),
        'fonte': registro.get('Fonte', ''),
    }


def gerar_id(artista, data, cidade):
    chave = f'{artista.lower().strip()}-{data}-{cidade.lower().strip()}'
    return hashlib.md5(chave.encode()).hexdigest()[:12]


def carregar_json_estado(estado):
    """Carrega o JSON atual de um estado (ou retorna lista vazia)."""
    caminho = DATA_DIR / f'{estado}.json'
    if caminho.exists():
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            log.error(f'Erro ao carregar {caminho}: {e}')
    return []


def salvar_json_estado(estado, shows):
    """Salva o JSON atualizado de um estado, ordenado por data."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    caminho = DATA_DIR / f'{estado}.json'

    # Ordenar por data
    shows_sorted = sorted(shows, key=lambda s: s.get('data_iso', ''))

    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(shows_sorted, f, ensure_ascii=False, indent=2)
    log.info(f'{caminho}: {len(shows_sorted)} shows salvos.')


def marcar_como_publicados(aba_aprovados, aba_publicados, rows_indices):
    """Move os registros publicados para a aba Publicados."""
    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    # Em produção: mover as linhas da aba Aprovados para Publicados
    # Por simplicidade, apenas loga — implementar movimentação conforme necessidade
    log.info(f'{len(rows_indices)} registros marcados para publicação em {agora}.')


def main():
    log.info('=== ShowsBR Agente Publicador iniciado ===')

    planilha = conectar_sheets()
    aba_aprovados = planilha.worksheet('Aprovados')
    aba_publicados = planilha.worksheet('Publicados')

    registros = ler_aprovados(aba_aprovados)
    if not registros:
        log.info('Nenhum show aprovado pendente. Encerrando.')
        return

    # Agrupar por estado
    por_estado = {}
    validos = []
    for reg in registros:
        show = converter_para_json(reg)
        if not show:
            continue
        estado = show['estado']
        if not estado:
            log.warning(f'Show sem estado: {show["artista"]} — ignorado.')
            continue
        por_estado.setdefault(estado, []).append(show)
        validos.append(show)

    log.info(f'{len(validos)} shows válidos em {len(por_estado)} estados.')

    # Atualizar JSONs por estado
    for estado, novos_shows in por_estado.items():
        existentes = carregar_json_estado(estado)
        ids_existentes = {s['id'] for s in existentes}

        # Adicionar somente shows novos (evitar duplicatas)
        adicionados = 0
        for show in novos_shows:
            if show['id'] not in ids_existentes:
                existentes.append(show)
                ids_existentes.add(show['id'])
                adicionados += 1
            else:
                # Atualizar show existente (pode ter sido editado)
                for i, ex in enumerate(existentes):
                    if ex['id'] == show['id']:
                        existentes[i] = show
                        break

        salvar_json_estado(estado, existentes)
        log.info(f'{estado}: {adicionados} novos shows adicionados.')

    marcar_como_publicados(aba_aprovados, aba_publicados, list(range(len(validos))))
    log.info('=== Agente Publicador finalizado ===')


if __name__ == '__main__':
    main()
