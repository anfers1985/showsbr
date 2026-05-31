"""
ShowsBR — Agente Coletor de Shows
Sympla: API de organizador (retorna seus próprios eventos - aguardar chave developer)
Eventbrite: API pública com coordenadas geográficas (corrigido)
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
DATA_FIM    = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')

ESTADOS_ATIVOS = [
    'SC','SP','RJ','MG','RS','PR','BA','PE','GO','CE',
    'AM','PA','DF','ES','MT','MS','MA','PI','PB','RN',
    'AL','SE','TO','RO','AC','AP','RR'
]

# Coordenadas da cidade principal de cada estado
# Eventbrite usa lat/lng + raio em km — muito mais confiável que nome de cidade
COORDS = {
    'AC': (-9.9754,  -67.8249), 'AL': (-9.6658,  -35.7350),
    'AM': (-3.1190,  -60.0217), 'AP': (0.0356,   -51.0705),
    'BA': (-12.9714, -38.5014), 'CE': (-3.7172,  -38.5433),
    'DF': (-15.7975, -47.8919), 'ES': (-20.3155,  -40.3128),
    'GO': (-16.6869, -49.2648), 'MA': (-2.5297,  -44.3028),
    'MG': (-19.9167, -43.9345), 'MS': (-20.4697,  -54.6201),
    'MT': (-15.5961, -56.0968), 'PA': (-1.4558,  -48.4902),
    'PB': (-7.1195,  -34.8450), 'PE': (-8.0578,  -34.8829),
    'PI': (-5.0892,  -42.8019), 'PR': (-25.4284,  -49.2733),
    'RJ': (-22.9068, -43.1729), 'RN': (-5.7945,  -35.2110),
    'RO': (-8.7612,  -63.9004), 'RR': (2.8235,   -60.6758),
    'RS': (-30.0346, -51.2177), 'SC': (-27.5954,  -48.5480),
    'SE': (-10.9091, -37.0677), 'SP': (-23.5505,  -46.6333),
    'TO': (-10.2491, -48.3243),
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
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
        '', s.get('valores',''), 'NÃO' if not s.get('gratuito') else 'SIM',
        s.get('link_compra',''), '', s.get('fonte',''), agora,
    ] for s in shows]
    aba.append_rows(linhas, value_input_option='RAW')
    log.info(f'{len(linhas)} shows escritos na aba Pendentes.')


def gerar_id(artista, data_iso, estado):
    chave = f'{artista.lower().strip()}-{data_iso}-{estado.lower()}'
    return hashlib.md5(chave.encode()).hexdigest()[:12]


# ── SYMPLA (aguardando chave developer) ────────────────────────────────────

def coletar_sympla(estado, api_key):
    """
    Sympla/SC: HTTP 200 mas 0 eventos = chave de ORGANIZADOR (só seus eventos).
    A chave de DESENVOLVEDOR PARCEIRO (developers.sympla.com.br) retorna todos
    os eventos do Brasil. Aguardar aprovação.
    """
    shows = []
    if not api_key:
        return shows

    url = 'https://api.sympla.com.br/public/v3/events'
    headers = {**HEADERS, 'S_TOKEN': api_key}
    params  = {
        'page': 1, 'page_size': 50,
        'start_date': DATA_INICIO,
        'end_date': DATA_FIM,
        'state': estado,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        log.info(f'Sympla/{estado}: HTTP {resp.status_code}')
        if resp.status_code != 200:
            return shows

        eventos = resp.json().get('data', [])
        log.info(f'Sympla/{estado}: {len(eventos)} eventos')

        for ev in eventos:
            artista  = (ev.get('name') or '').strip()
            addr     = ev.get('address') or {}
            cidade   = (addr.get('city') or '').strip()
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
                'genero': '',
                'data': data_fmt,
                'horario': (ev.get('start_date') or '')[11:16],
                'local': addr.get('name', ''),
                'endereco': addr.get('formatted_address', ''),
                'cidade': cidade,
                'estado': estado,
                'organizador': ev.get('organizer_name', ''),
                'valores': '',
                'gratuito': False,
                'link_compra': f"https://www.sympla.com.br/evento/{ev.get('id','')}",
                'fonte': f'api.sympla.com.br/{estado}',
            })
    except Exception as e:
        log.error(f'Sympla/{estado}: {e}')

    return shows


# ── EVENTBRITE (corrigido com lat/lng) ─────────────────────────────────────

def coletar_eventbrite(estado, token):
    """
    Usa coordenadas geográficas em vez do nome da cidade.
    Endpoint correto: /v3/events/search/ com lat/lng + raio.
    """
    shows = []
    if not token:
        return shows

    coords = COORDS.get(estado)
    if not coords:
        return shows

    lat, lng = coords

    # Endpoint correto com autenticação Bearer
    url = 'https://www.eventbriteapi.com/v3/events/search/'
    headers = {**HEADERS, 'Authorization': f'Bearer {token}'}
    params  = {
        'location.latitude':  lat,
        'location.longitude': lng,
        'location.within':    '80km',
        'start_date.range_start': DATA_INICIO + 'T00:00:00Z',
        'start_date.range_end':   DATA_FIM    + 'T23:59:59Z',
        'categories':         '103',   # Music
        'expand':             'venue,organizer',
        'page_size':          50,
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        log.info(f'Eventbrite/{estado}: HTTP {resp.status_code}')

        if resp.status_code == 401:
            log.error('Eventbrite: token inválido. Verifique EVENTBRITE_TOKEN.')
            return shows
        if resp.status_code != 200:
            log.warning(f'Eventbrite/{estado}: {resp.status_code} — {resp.text[:200]}')
            return shows

        eventos = resp.json().get('events', [])
        log.info(f'Eventbrite/{estado}: {len(eventos)} eventos')

        for ev in eventos:
            nome = (ev.get('name') or {}).get('text', '').strip()
            if not nome:
                continue

            inicio   = ev.get('start') or {}
            data_raw = (inicio.get('local') or '')[:10]
            horario  = (inicio.get('local') or '')[11:16]

            venue    = ev.get('venue') or {}
            addr     = venue.get('address') or {}
            local_nm = venue.get('name', '')
            end_str  = addr.get('localized_address_display', '')
            cidade_ev = addr.get('city', '')

            # Só inclui se a cidade fica no estado correto (filtro por estado BR)
            estado_ev = addr.get('region', '')
            if estado_ev and estado_ev.upper() != estado:
                continue

            org = ev.get('organizer') or {}
            gratuito = bool(ev.get('is_free'))

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
                'local': local_nm,
                'endereco': end_str,
                'cidade': cidade_ev,
                'estado': estado,
                'organizador': org.get('name', ''),
                'valores': 'Gratuito' if gratuito else '',
                'gratuito': gratuito,
                'link_compra': ev.get('url', ''),
                'fonte': f'eventbrite.com/{estado}',
            })

    except Exception as e:
        log.error(f'Eventbrite/{estado}: {e}')

    return shows


# ── MAIN ───────────────────────────────────────────────────────────────────

def main():
    log.info('=== ShowsBR Agente Coletor iniciado ===')
    log.info(f'Período: {DATA_INICIO} → {DATA_FIM}')

    sympla_key = os.environ.get('SYMPLA_API_KEY', '')
    evbr_token = os.environ.get('EVENTBRITE_TOKEN', '')

    if not sympla_key and not evbr_token:
        log.warning('Nenhuma chave configurada. Encerrando.')
        return

    if sympla_key:
        log.info('Sympla: chave de organizador presente (HTTP 200 esperado, aguardando chave developer para todos os eventos)')
    if evbr_token:
        log.info('Eventbrite: token presente — usando coordenadas geográficas (corrigido)')

    planilha  = conectar_sheets()
    aba_pend  = planilha.worksheet('Pendentes')
    aba_aprov = planilha.worksheet('Aprovados')
    ids_exist = obter_ids_existentes(aba_pend, aba_aprov)
    log.info(f'{len(ids_exist)} IDs já existentes.')

    todos_novos = []

    for estado in ESTADOS_ATIVOS:
        log.info(f'--- {estado} ---')
        novos = []

        for s in coletar_sympla(estado, sympla_key):
            if s['id'] not in ids_exist:
                ids_exist.add(s['id'])
                novos.append(s)

        for s in coletar_eventbrite(estado, evbr_token):
            if s['id'] not in ids_exist:
                ids_exist.add(s['id'])
                novos.append(s)

        log.info(f'  {len(novos)} shows novos em {estado}')
        todos_novos.extend(novos)
        time.sleep(1)

    log.info(f'Total: {len(todos_novos)} shows novos')
    escrever_pendentes(aba_pend, todos_novos)
    log.info('=== Agente Coletor finalizado ===')


if __name__ == '__main__':
    main()
