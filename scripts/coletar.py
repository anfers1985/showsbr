"""
ShowsBR — Agente Coletor de Shows
Coleta shows via scraping do site Sympla e escreve na aba Pendentes do Google Sheets.
Roda via GitHub Actions seg–sex 8h, 12h, 17h BRT.

Nota: Sympla e Eventim bloqueiam IPs de datacenters (GitHub Actions).
A estratégia aqui é scraping do site público com headers realistas.
Se continuar com timeout, o fluxo manual (cadastro direto na aba Aprovados) supre.
"""

import os
import json
import hashlib
import logging
import time
import re
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
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

# Headers realistas para evitar bloqueio
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}

DATA_FIM = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')
DATA_INICIO = datetime.now().strftime('%Y-%m-%d')

# Estados ativos para coleta
ESTADOS_ATIVOS = [
    'SC', 'SP', 'RJ', 'MG', 'RS', 'PR',
    'BA', 'PE', 'GO', 'CE', 'AM', 'PA',
    'DF', 'ES', 'MT', 'MS', 'MA', 'PI',
    'PB', 'RN', 'AL', 'SE', 'TO', 'RO', 'AC', 'AP', 'RR'
]

# Mapa UF → nome de cidade principal para Sympla
SYMPLA_CIDADES = {
    'AC': 'Rio+Branco', 'AL': 'Maceio', 'AM': 'Manaus', 'AP': 'Macapa',
    'BA': 'Salvador', 'CE': 'Fortaleza', 'DF': 'Brasilia', 'ES': 'Vitoria',
    'GO': 'Goiania', 'MA': 'Sao+Luis', 'MG': 'Belo+Horizonte', 'MS': 'Campo+Grande',
    'MT': 'Cuiaba', 'PA': 'Belem', 'PB': 'Joao+Pessoa', 'PE': 'Recife',
    'PI': 'Teresina', 'PR': 'Curitiba', 'RJ': 'Rio+de+Janeiro', 'RN': 'Natal',
    'RO': 'Porto+Velho', 'RR': 'Boa+Vista', 'RS': 'Porto+Alegre', 'SC': 'Florianopolis',
    'SE': 'Aracaju', 'SP': 'Sao+Paulo', 'TO': 'Palmas',
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def conectar_sheets():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    sheets_id = os.environ.get('SHEETS_ID')
    if not creds_json or not sheets_id:
        raise ValueError('GOOGLE_CREDENTIALS e SHEETS_ID não configurados.')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(sheets_id)


def obter_ids_existentes(aba_pendentes, aba_aprovados):
    """Lê IDs existentes das abas para evitar duplicatas. Usa get_all_values()."""
    ids = set()
    for aba in [aba_pendentes, aba_aprovados]:
        try:
            vals = aba.get_all_values()
            for row in vals[1:]:   # pula cabeçalho
                if row and row[0]:
                    ids.add(row[0])
        except Exception as e:
            log.warning(f'Erro ao ler IDs da aba: {e}')
    return ids


def gerar_id(artista, data_iso, cidade):
    chave = f'{artista.lower().strip()}-{data_iso}-{cidade.lower().strip()}'
    return hashlib.md5(chave.encode()).hexdigest()[:12]


def escrever_pendentes(aba, shows):
    if not shows:
        log.info('Nenhum show novo para escrever.')
        return
    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    linhas = []
    for s in shows:
        linhas.append([
            s.get('id', ''),
            s.get('artista', ''),
            s.get('artista', ''),
            s.get('descricao', ''),
            s.get('genero', ''),
            s.get('data', ''),
            s.get('horario', ''),
            s.get('local', ''),
            s.get('endereco', ''),
            s.get('cidade', ''),
            s.get('estado', ''),
            s.get('organizador', ''),
            '',                          # CNPJ — preencher manualmente na revisão
            s.get('valores', ''),
            'NÃO',
            s.get('link_compra', ''),
            '',                          # cupom
            s.get('fonte', ''),
            agora,
        ])
    aba.append_rows(linhas, value_input_option='RAW')
    log.info(f'{len(linhas)} shows escritos na aba Pendentes.')


def coletar_sympla_busca(estado):
    """
    Scraping da página de busca pública do Sympla por estado.
    Endpoint: https://www.sympla.com.br/eventos?s=&state=SC
    """
    shows = []
    cidade = SYMPLA_CIDADES.get(estado, '')
    # Busca por estado na página pública
    url = f'https://www.sympla.com.br/eventos?s=&state={estado}'

    try:
        resp = SESSION.get(url, timeout=20)
        log.info(f'Sympla/{estado}: HTTP {resp.status_code} — {len(resp.text)} chars')

        if resp.status_code != 200:
            log.warning(f'Sympla/{estado}: resposta não-200, pulando.')
            return shows

        soup = BeautifulSoup(resp.text, 'html.parser')

        # Sympla renderiza os cards de evento com data-testid ou classes específicas
        # Tentamos múltiplos seletores para robustez
        cards = (
            soup.select('[data-testid="event-card"]') or
            soup.select('.EventCard') or
            soup.select('article.event') or
            soup.select('.sympla-event-card') or
            []
        )

        # Fallback: buscar links com /evento/ na URL
        if not cards:
            links = soup.find_all('a', href=re.compile(r'/evento/'))
            log.info(f'Sympla/{estado}: {len(links)} links /evento/ encontrados (fallback)')
            for link in links[:20]:
                href = link.get('href', '')
                nome = link.get_text(strip=True)
                if not nome or len(nome) < 3:
                    continue
                full_url = href if href.startswith('http') else f'https://www.sympla.com.br{href}'
                show_id = gerar_id(nome, DATA_INICIO, estado)
                shows.append({
                    'id': show_id,
                    'artista': nome,
                    'genero': '',
                    'data': '',
                    'horario': '',
                    'local': '',
                    'endereco': '',
                    'cidade': cidade.replace('+', ' '),
                    'estado': estado,
                    'organizador': '',
                    'valores': '',
                    'link_compra': full_url,
                    'fonte': f'sympla.com.br/eventos?state={estado}',
                })
            return shows

        log.info(f'Sympla/{estado}: {len(cards)} cards encontrados')
        for card in cards[:20]:
            nome_el = card.select_one('h2, h3, [class*="name"], [class*="title"]')
            data_el = card.select_one('time, [class*="date"]')
            local_el = card.select_one('[class*="location"], [class*="venue"]')
            link_el = card.select_one('a[href]')

            artista = nome_el.get_text(strip=True) if nome_el else ''
            data_str = data_el.get_text(strip=True) if data_el else ''
            local = local_el.get_text(strip=True) if local_el else ''
            link = link_el['href'] if link_el else ''
            if link and not link.startswith('http'):
                link = 'https://www.sympla.com.br' + link

            if not artista:
                continue

            show_id = gerar_id(artista, DATA_INICIO, estado)
            shows.append({
                'id': show_id,
                'artista': artista,
                'genero': '',
                'data': data_str,
                'horario': '',
                'local': local,
                'endereco': '',
                'cidade': cidade.replace('+', ' '),
                'estado': estado,
                'organizador': '',
                'valores': '',
                'link_compra': link,
                'fonte': f'sympla.com.br/eventos?state={estado}',
            })

    except requests.Timeout:
        log.warning(f'Sympla/{estado}: timeout — plataforma pode estar bloqueando IPs de datacenter.')
    except requests.RequestException as e:
        log.error(f'Sympla/{estado}: erro de rede — {e}')
    except Exception as e:
        log.error(f'Sympla/{estado}: erro inesperado — {e}')

    return shows


def main():
    log.info('=== ShowsBR Agente Coletor iniciado ===')
    log.info(f'Período: {DATA_INICIO} → {DATA_FIM}')
    log.info(f'Estados: {", ".join(ESTADOS_ATIVOS)}')

    planilha = conectar_sheets()
    aba_pendentes = planilha.worksheet('Pendentes')
    aba_aprovados = planilha.worksheet('Aprovados')

    ids_existentes = obter_ids_existentes(aba_pendentes, aba_aprovados)
    log.info(f'{len(ids_existentes)} IDs já existentes (deduplicação).')

    todos_novos = []

    for estado in ESTADOS_ATIVOS:
        log.info(f'--- Coletando: {estado} ---')
        shows = coletar_sympla_busca(estado)
        novos = [s for s in shows if s['id'] not in ids_existentes]
        log.info(f'  {len(shows)} coletados, {len(novos)} novos')
        for s in novos:
            ids_existentes.add(s['id'])
        todos_novos.extend(novos)
        time.sleep(3)  # delay entre estados

    log.info(f'Total de shows novos: {len(todos_novos)}')

    if todos_novos:
        escrever_pendentes(aba_pendentes, todos_novos)
    else:
        log.info(
            'Nenhum show coletado automaticamente desta vez. '
            'Isso é esperado se as plataformas estiverem bloqueando IPs de datacenter. '
            'Use o formulário de cadastro ou insira diretamente na aba Aprovados.'
        )

    log.info('=== Agente Coletor finalizado ===')


if __name__ == '__main__':
    main()
