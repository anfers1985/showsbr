"""
ShowsBR — Agente Coletor de Shows
Coleta shows de Sympla, Eventim e Ticket360 e escreve na aba Pendentes do Google Sheets.
Roda via GitHub Actions: seg–sex às 8h, 12h e 17h (BRT).
"""

import os
import json
import hashlib
import logging
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials

# ── LOGGING ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

# ── CONSTANTES ────────────────────────────────────────────────────────────────
SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; ShowsBR-Bot/1.0; +https://showsbr.com.br/sobre)',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}

# Estados para coletar (expandir gradualmente)
ESTADOS_ATIVOS = ['SC', 'SP', 'RJ', 'MG', 'RS', 'PR', 'BA', 'PE', 'GO', 'CE']

# Período de coleta: próximos 90 dias
DATA_INICIO = datetime.now().strftime('%Y-%m-%d')
DATA_FIM = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')


# ── GOOGLE SHEETS ─────────────────────────────────────────────────────────────
def conectar_sheets():
    """Conecta ao Google Sheets usando a Service Account."""
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    sheets_id = os.environ.get('SHEETS_ID')

    if not creds_json or not sheets_id:
        raise ValueError('GOOGLE_CREDENTIALS e SHEETS_ID devem estar configurados como Secrets.')

    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    planilha = client.open_by_key(sheets_id)
    return planilha


def obter_ids_existentes(aba_pendentes, aba_aprovados, aba_publicados):
    """Retorna set com todos os IDs já na planilha (para evitar duplicatas)."""
    ids = set()
    for aba in [aba_pendentes, aba_aprovados, aba_publicados]:
        try:
            todos = aba.col_values(1)  # Coluna A = ID
            ids.update(todos[1:])      # Pula o cabeçalho
        except Exception:
            pass
    return ids


def escrever_pendentes(aba, shows):
    """Escreve os shows novos na aba Pendentes."""
    if not shows:
        log.info('Nenhum show novo para escrever.')
        return

    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    linhas = []
    for s in shows:
        linhas.append([
            s.get('id', ''),
            s.get('artista', ''),
            s.get('artista', ''),              # Coluna C = artista/evento
            s.get('descricao', ''),
            s.get('genero', ''),
            s.get('data', ''),
            s.get('horario', ''),
            s.get('local', ''),
            s.get('endereco', ''),
            s.get('cidade', ''),
            s.get('estado', ''),
            s.get('organizador', ''),
            s.get('cnpj', ''),
            s.get('valores', ''),
            s.get('gratuito', 'NÃO'),
            s.get('link_compra', ''),
            s.get('cupom', ''),
            s.get('fonte', ''),
            agora,
        ])

    aba.append_rows(linhas, value_input_option='RAW')
    log.info(f'{len(linhas)} shows escritos na aba Pendentes.')


# ── GERAÇÃO DE ID ─────────────────────────────────────────────────────────────
def gerar_id(artista, data, cidade):
    """Gera ID único determinístico: hash de artista+data+cidade."""
    chave = f'{artista.lower().strip()}-{data}-{cidade.lower().strip()}'
    return hashlib.md5(chave.encode()).hexdigest()[:12]


# ── COLETA: SYMPLA ────────────────────────────────────────────────────────────
def coletar_sympla(estado):
    """
    Coleta eventos do Sympla por estado.
    Usa a API pública de listagem (endpoint JSON).
    """
    shows = []
    url = (
        f'https://www.sympla.com.br/api/v3/events'
        f'?states={estado}'
        f'&page=1&page_size=50'
        f'&start_date={DATA_INICIO}&end_date={DATA_FIM}'
    )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning(f'Sympla/{estado}: HTTP {resp.status_code}')
            return shows

        data = resp.json()
        eventos = data.get('data', [])
        log.info(f'Sympla/{estado}: {len(eventos)} eventos encontrados')

        for ev in eventos:
            artista = ev.get('name', '').strip()
            cidade = (ev.get('address', {}) or {}).get('city', '').strip()
            data_str = ev.get('start_date', '')[:10]  # YYYY-MM-DD

            if not artista or not cidade or not data_str:
                continue

            shows.append({
                'id': gerar_id(artista, data_str, cidade),
                'artista': artista,
                'genero': ev.get('category', {}).get('name', '') if isinstance(ev.get('category'), dict) else '',
                'data': datetime.strptime(data_str, '%Y-%m-%d').strftime('%d/%m/%Y'),
                'horario': ev.get('start_date', '')[11:16] if len(ev.get('start_date', '')) > 10 else '',
                'local': (ev.get('address', {}) or {}).get('name', ''),
                'endereco': (ev.get('address', {}) or {}).get('formatted_address', ''),
                'cidade': cidade,
                'estado': estado,
                'organizador': ev.get('organizer_name', ''),
                'cnpj': '',
                'valores': '',
                'gratuito': 'SIM' if ev.get('free', False) else 'NÃO',
                'link_compra': f"https://www.sympla.com.br/evento/{ev.get('id', '')}",
                'cupom': '',
                'fonte': f"sympla.com.br/{estado}",
            })

    except requests.RequestException as e:
        log.error(f'Sympla/{estado}: erro de rede — {e}')
    except Exception as e:
        log.error(f'Sympla/{estado}: erro inesperado — {e}')

    return shows


# ── COLETA: EVENTIM ───────────────────────────────────────────────────────────
def coletar_eventim(estado):
    """
    Coleta eventos do Eventim por estado via scraping da listagem.
    Eventim não tem API pública; usamos BeautifulSoup.
    """
    shows = []
    # Mapa UF → slug de cidade principal (ponto de entrada)
    cidades_map = {
        'SP': 'sao-paulo', 'RJ': 'rio-de-janeiro', 'MG': 'belo-horizonte',
        'SC': 'florianopolis', 'RS': 'porto-alegre', 'PR': 'curitiba',
        'BA': 'salvador', 'PE': 'recife', 'GO': 'goiania', 'CE': 'fortaleza',
    }
    cidade_slug = cidades_map.get(estado)
    if not cidade_slug:
        return shows

    url = f'https://www.eventim.com.br/city/{cidade_slug}/?affiliate=EVD'

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            log.warning(f'Eventim/{estado}: HTTP {resp.status_code}')
            return shows

        soup = BeautifulSoup(resp.text, 'html.parser')
        # Eventim usa data-testid="event-item" nos cards
        cards = soup.select('[data-testid="event-item"]')
        log.info(f'Eventim/{estado}: {len(cards)} cards encontrados')

        for card in cards[:20]:
            nome_el = card.select_one('h2, h3, .event-name, [data-testid="event-name"]')
            data_el = card.select_one('time, .event-date, [data-testid="event-date"]')
            local_el = card.select_one('.event-location, [data-testid="event-location"]')
            link_el = card.select_one('a[href]')

            artista = nome_el.get_text(strip=True) if nome_el else ''
            data_raw = data_el.get('datetime', data_el.get_text(strip=True)) if data_el else ''
            local = local_el.get_text(strip=True) if local_el else ''
            link = 'https://www.eventim.com.br' + link_el['href'] if link_el else ''

            # Normalizar data para DD/MM/YYYY
            data_str = ''
            data_iso = ''
            if data_raw:
                for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%d/%m/%Y'):
                    try:
                        dt = datetime.strptime(data_raw[:10], fmt[:len(data_raw[:10])])
                        data_str = dt.strftime('%d/%m/%Y')
                        data_iso = dt.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue

            if not artista or not data_iso:
                continue

            shows.append({
                'id': gerar_id(artista, data_iso, estado),
                'artista': artista,
                'genero': '',
                'data': data_str,
                'horario': '',
                'local': local,
                'endereco': '',
                'cidade': cidade_slug.replace('-', ' ').title(),
                'estado': estado,
                'organizador': '',
                'cnpj': '',
                'valores': '',
                'gratuito': 'NÃO',
                'link_compra': link,
                'cupom': '',
                'fonte': f'eventim.com.br/{cidade_slug}',
            })

        time.sleep(1)  # Delay entre requisições

    except requests.RequestException as e:
        log.error(f'Eventim/{estado}: erro de rede — {e}')
    except Exception as e:
        log.error(f'Eventim/{estado}: erro inesperado — {e}')

    return shows


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    log.info('=== ShowsBR Agente Coletor iniciado ===')
    log.info(f'Período: {DATA_INICIO} → {DATA_FIM}')
    log.info(f'Estados ativos: {", ".join(ESTADOS_ATIVOS)}')

    # Conectar ao Sheets
    planilha = conectar_sheets()
    aba_pendentes = planilha.worksheet('Pendentes')
    aba_aprovados = planilha.worksheet('Aprovados')
    aba_publicados = planilha.worksheet('Publicados')

    ids_existentes = obter_ids_existentes(aba_pendentes, aba_aprovados, aba_publicados)
    log.info(f'{len(ids_existentes)} IDs já existentes na planilha (deduplicação).')

    todos_novos = []

    for estado in ESTADOS_ATIVOS:
        log.info(f'--- Coletando: {estado} ---')

        # Sympla
        shows_sympla = coletar_sympla(estado)
        novos_sympla = [s for s in shows_sympla if s['id'] not in ids_existentes]
        log.info(f'  Sympla: {len(shows_sympla)} coletados, {len(novos_sympla)} novos')

        # Eventim
        shows_eventim = coletar_eventim(estado)
        novos_eventim = [s for s in shows_eventim if s['id'] not in ids_existentes]
        log.info(f'  Eventim: {len(shows_eventim)} coletados, {len(novos_eventim)} novos')

        novos = novos_sympla + novos_eventim
        # Adicionar novos IDs ao set para evitar duplicatas entre estados
        for s in novos:
            ids_existentes.add(s['id'])

        todos_novos.extend(novos)
        time.sleep(2)  # Respeitar limite de rate

    log.info(f'Total de shows novos: {len(todos_novos)}')
    escrever_pendentes(aba_pendentes, todos_novos)
    log.info('=== Agente Coletor finalizado ===')


if __name__ == '__main__':
    main()
