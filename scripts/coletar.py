"""
ShowsBR — Agente Coletor de Shows
Coleta via API oficial da Sympla e API pública do Eventbrite.
Escreve shows novos na aba Pendentes do Google Sheets para revisão.

Chaves necessárias (GitHub Secrets):
  SYMPLA_API_KEY    → developers.sympla.com.br (gratuito, aprovação em até 5 dias)
  EVENTBRITE_TOKEN  → eventbrite.com/platform (gratuito, aprovação imediata)
  GOOGLE_CREDENTIALS → Service Account JSON
  SHEETS_ID          → ID da planilha Google Sheets
"""

import os
import json
import hashlib
import logging
import time
from datetime import datetime, timedelta

import requests
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

DATA_INICIO = datetime.now().strftime('%Y-%m-%d')
DATA_FIM = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')

ESTADOS_ATIVOS = [
    'SC','SP','RJ','MG','RS','PR','BA','PE','GO','CE',
    'AM','PA','DF','ES','MT','MS','MA','PI','PB','RN',
    'AL','SE','TO','RO','AC','AP','RR'
]

# Mapa UF → código de localização do Eventbrite (Brazil regions)
EVENTBRITE_REGIOES = {
    'SC': 'Florianópolis', 'SP': 'São Paulo', 'RJ': 'Rio de Janeiro',
    'MG': 'Belo Horizonte', 'RS': 'Porto Alegre', 'PR': 'Curitiba',
    'BA': 'Salvador', 'PE': 'Recife', 'GO': 'Goiânia', 'CE': 'Fortaleza',
    'AM': 'Manaus', 'PA': 'Belém', 'DF': 'Brasília', 'ES': 'Vitória',
    'MT': 'Cuiabá', 'MS': 'Campo Grande', 'MA': 'São Luís', 'PI': 'Teresina',
    'PB': 'João Pessoa', 'RN': 'Natal', 'AL': 'Maceió', 'SE': 'Aracaju',
    'TO': 'Palmas', 'RO': 'Porto Velho', 'AC': 'Rio Branco',
    'AP': 'Macapá', 'RR': 'Boa Vista',
}

HEADERS_BROWSER = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}


# ── GOOGLE SHEETS ──────────────────────────────────────────────────────────

def conectar_sheets():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    sheets_id  = os.environ.get('SHEETS_ID')
    if not creds_json or not sheets_id:
        raise ValueError('GOOGLE_CREDENTIALS e SHEETS_ID não configurados.')
    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=SCOPES)
    return gspread.authorize(creds).open_by_key(sheets_id)


def obter_ids_existentes(aba_pend, aba_aprov):
    ids = set()
    for aba in [aba_pend, aba_aprov]:
        try:
            for row in aba.get_all_values()[1:]:
                if row and row[0]:
                    ids.add(row[0])
        except Exception:
            pass
    return ids


def escrever_pendentes(aba, shows):
    if not shows:
        log.info('Nenhum show novo.')
        return
    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    linhas = [[
        s.get('id',''), s.get('artista',''), s.get('artista',''),
        s.get('descricao',''), s.get('genero',''), s.get('data',''),
        s.get('horario',''), s.get('local',''), s.get('endereco',''),
        s.get('cidade',''), s.get('estado',''), s.get('organizador',''),
        '', s.get('valores',''), 'NÃO', s.get('link_compra',''), '', s.get('fonte',''), agora,
    ] for s in shows]
    aba.append_rows(linhas, value_input_option='RAW')
    log.info(f'{len(linhas)} shows escritos na aba Pendentes.')


def gerar_id(artista, data_iso, estado):
    chave = f'{artista.lower().strip()}-{data_iso}-{estado.lower()}'
    return hashlib.md5(chave.encode()).hexdigest()[:12]


# ── SYMPLA API ─────────────────────────────────────────────────────────────
# Documentação: https://developers.sympla.com.br
# Chave gratuita — cadastro em developers.sympla.com.br
# Endpoint: GET https://api.sympla.com.br/public/v3/events
# Parâmetros: page, page_size, start_date, end_date, state

def coletar_sympla(estado, api_key):
    shows = []
    if not api_key:
        log.warning('SYMPLA_API_KEY não configurada — pulando Sympla.')
        return shows

    url = 'https://api.sympla.com.br/public/v3/events'
    headers = {**HEADERS_BROWSER, 'S_TOKEN': api_key}
    params = {
        'page': 1,
        'page_size': 50,
        'start_date': DATA_INICIO,
        'end_date': DATA_FIM,
        'state': estado,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        log.info(f'Sympla/{estado}: HTTP {resp.status_code}')

        if resp.status_code == 401:
            log.error('Sympla: chave inválida ou não autorizada. Verifique SYMPLA_API_KEY.')
            return shows
        if resp.status_code != 200:
            log.warning(f'Sympla/{estado}: resposta {resp.status_code}')
            return shows

        eventos = resp.json().get('data', [])
        log.info(f'Sympla/{estado}: {len(eventos)} eventos')

        for ev in eventos:
            artista = (ev.get('name') or '').strip()
            addr    = ev.get('address') or {}
            cidade  = (addr.get('city') or '').strip()
            data_raw = (ev.get('start_date') or '')[:10]
            if not artista or not cidade or not data_raw:
                continue
            try:
                dt = datetime.strptime(data_raw, '%Y-%m-%d')
                data_fmt = dt.strftime('%d/%m/%Y')
            except ValueError:
                continue

            shows.append({
                'id': gerar_id(artista, data_raw, estado),
                'artista': artista,
                'genero': (ev.get('category') or {}).get('name', '') if isinstance(ev.get('category'), dict) else '',
                'data': data_fmt,
                'horario': (ev.get('start_date') or '')[11:16],
                'local': addr.get('name', ''),
                'endereco': addr.get('formatted_address', ''),
                'cidade': cidade,
                'estado': estado,
                'organizador': ev.get('organizer_name', ''),
                'valores': '',
                'link_compra': f"https://www.sympla.com.br/evento/{ev.get('id','')}",
                'fonte': f'api.sympla.com.br/{estado}',
            })
    except requests.RequestException as e:
        log.error(f'Sympla/{estado}: erro de rede — {e}')
    except Exception as e:
        log.error(f'Sympla/{estado}: erro inesperado — {e}')

    return shows


# ── EVENTBRITE API ─────────────────────────────────────────────────────────
# Documentação: https://www.eventbrite.com/platform/api
# Token gratuito — criar conta em eventbrite.com/platform e gerar Private Token
# Endpoint: GET https://www.eventbriteapi.com/v3/events/search/
# Parâmetros: location.address, location.within, start_date.range_start, categories

EVENTBRITE_CATEGORIAS_MUSICA = '103'  # Music category ID no Eventbrite

def coletar_eventbrite(estado, token):
    shows = []
    if not token:
        log.warning('EVENTBRITE_TOKEN não configurada — pulando Eventbrite.')
        return shows

    cidade = EVENTBRITE_REGIOES.get(estado, '')
    if not cidade:
        return shows

    url = 'https://www.eventbriteapi.com/v3/events/search/'
    headers = {'Authorization': f'Bearer {token}', **HEADERS_BROWSER}
    params = {
        'location.address': f'{cidade}, Brasil',
        'location.within': '50km',
        'start_date.range_start': DATA_INICIO + 'T00:00:00',
        'start_date.range_end': DATA_FIM + 'T23:59:59',
        'categories': EVENTBRITE_CATEGORIAS_MUSICA,
        'expand': 'venue,organizer',
        'page_size': 50,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        log.info(f'Eventbrite/{estado}: HTTP {resp.status_code}')

        if resp.status_code == 401:
            log.error('Eventbrite: token inválido. Verifique EVENTBRITE_TOKEN.')
            return shows
        if resp.status_code != 200:
            log.warning(f'Eventbrite/{estado}: resposta {resp.status_code}')
            return shows

        eventos = resp.json().get('events', [])
        log.info(f'Eventbrite/{estado}: {len(eventos)} eventos')

        for ev in eventos:
            nome = (ev.get('name') or {}).get('text', '').strip()
            if not nome:
                continue

            inicio = ev.get('start') or {}
            data_raw = (inicio.get('local') or '')[:10]
            horario  = (inicio.get('local') or '')[11:16]

            venue = ev.get('venue') or {}
            addr  = venue.get('address') or {}
            local_nome = venue.get('name', '')
            end_str    = addr.get('localized_address_display', '')
            cidade_ev  = addr.get('city', cidade)

            org = ev.get('organizer') or {}

            try:
                dt = datetime.strptime(data_raw, '%Y-%m-%d')
                data_fmt = dt.strftime('%d/%m/%Y')
            except ValueError:
                continue

            shows.append({
                'id': gerar_id(nome, data_raw, estado),
                'artista': nome,
                'genero': '',
                'data': data_fmt,
                'horario': horario,
                'local': local_nome,
                'endereco': end_str,
                'cidade': cidade_ev,
                'estado': estado,
                'organizador': org.get('name', ''),
                'valores': 'Gratuito' if ev.get('is_free') else '',
                'link_compra': ev.get('url', ''),
                'fonte': f'eventbrite.com/{estado}',
            })
    except requests.RequestException as e:
        log.error(f'Eventbrite/{estado}: erro de rede — {e}')
    except Exception as e:
        log.error(f'Eventbrite/{estado}: erro inesperado — {e}')

    return shows


# ── MAIN ───────────────────────────────────────────────────────────────────

def main():
    log.info('=== ShowsBR Agente Coletor iniciado ===')
    log.info(f'Período: {DATA_INICIO} → {DATA_FIM}')

    sympla_key  = os.environ.get('SYMPLA_API_KEY', '')
    evbr_token  = os.environ.get('EVENTBRITE_TOKEN', '')

    if not sympla_key and not evbr_token:
        log.warning(
            'Nenhuma chave de API configurada.\n'
            '  → Sympla:     cadastre-se em developers.sympla.com.br e adicione o secret SYMPLA_API_KEY\n'
            '  → Eventbrite: cadastre-se em eventbrite.com/platform e adicione o secret EVENTBRITE_TOKEN\n'
            'Encerrando sem coletar.'
        )
        return

    planilha    = conectar_sheets()
    aba_pend    = planilha.worksheet('Pendentes')
    aba_aprov   = planilha.worksheet('Aprovados')
    ids_exist   = obter_ids_existentes(aba_pend, aba_aprov)
    log.info(f'{len(ids_exist)} IDs já existentes (deduplicação).')

    todos_novos = []

    for estado in ESTADOS_ATIVOS:
        log.info(f'--- {estado} ---')
        novos = []

        # Sympla
        for s in coletar_sympla(estado, sympla_key):
            if s['id'] not in ids_exist:
                ids_exist.add(s['id'])
                novos.append(s)

        # Eventbrite
        for s in coletar_eventbrite(estado, evbr_token):
            if s['id'] not in ids_exist:
                ids_exist.add(s['id'])
                novos.append(s)

        log.info(f'  {len(novos)} shows novos em {estado}')
        todos_novos.extend(novos)
        time.sleep(1)

    log.info(f'Total geral: {len(todos_novos)} shows novos')
    escrever_pendentes(aba_pend, todos_novos)
    log.info('=== Agente Coletor finalizado ===')


if __name__ == '__main__':
    main()
