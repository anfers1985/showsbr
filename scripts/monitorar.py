"""
ShowsBR — Agente Monitor de Shows
Verifica links de compra, detecta cancelamentos e envia relatório diário.
Roda via GitHub Actions todo dia às 6h BRT.
"""

import os
import json
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

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

DATA_DIR = Path('data/shows')
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; ShowsBR-Monitor/1.0; +https://showsbr.com.br)'}
JANELA_DIAS = 14  # Verificar shows nos próximos 14 dias


def conectar_sheets():
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    sheets_id = os.environ.get('SHEETS_ID')
    if not creds_json or not sheets_id:
        raise ValueError('GOOGLE_CREDENTIALS e SHEETS_ID não configurados.')
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(sheets_id)


def carregar_todos_shows():
    """Carrega todos os shows de todos os JSONs."""
    shows = []
    for arquivo in DATA_DIR.glob('*.json'):
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                shows.extend(json.load(f))
        except Exception as e:
            log.error(f'Erro ao carregar {arquivo}: {e}')
    return shows


def filtrar_proximos(shows, dias=JANELA_DIAS):
    """Filtra shows nos próximos N dias."""
    hoje = datetime.now().date()
    limite = hoje + timedelta(days=dias)
    proximos = []
    for show in shows:
        data_iso = show.get('data_iso', '')
        if not data_iso:
            continue
        try:
            data_show = datetime.strptime(data_iso, '%Y-%m-%d').date()
            if hoje <= data_show <= limite:
                proximos.append(show)
        except ValueError:
            continue
    return proximos


def verificar_link(url, timeout=10):
    """Verifica se um link está acessível. Retorna (ok, status_code)."""
    if not url or not url.startswith('http'):
        return None, None
    try:
        resp = requests.head(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        ok = resp.status_code < 400
        return ok, resp.status_code
    except requests.RequestException as e:
        log.warning(f'Erro ao verificar {url}: {e}')
        return False, None


def verificar_cancelamento_sympla(show):
    """
    Heurística simples: verifica se a página do show no Sympla contém
    palavras-chave de cancelamento.
    """
    url = show.get('link_compra', '')
    if 'sympla.com.br' not in url:
        return False

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            texto = resp.text.lower()
            palavras_cancelamento = ['cancelado', 'evento cancelado', 'adiado', 'event canceled']
            return any(p in texto for p in palavras_cancelamento)
    except Exception:
        pass
    return False


def atualizar_status_json(estado, show_id, novo_status):
    """Atualiza o status de um show no JSON do estado."""
    caminho = DATA_DIR / f'{estado}.json'
    if not caminho.exists():
        return

    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            shows = json.load(f)

        for show in shows:
            if show.get('id') == show_id:
                show['status'] = novo_status
                break

        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump(shows, f, ensure_ascii=False, indent=2)

        log.info(f'Status de {show_id} atualizado para "{novo_status}" em {estado}.json')
    except Exception as e:
        log.error(f'Erro ao atualizar status: {e}')


def montar_relatorio(resultados):
    """Monta o texto do relatório de monitoramento."""
    hoje = datetime.now().strftime('%d/%m/%Y %H:%M')
    total = len(resultados)
    ok = sum(1 for r in resultados if r['link_ok'] is not False)
    problemas = [r for r in resultados if r['link_ok'] is False or r['cancelado']]

    linhas = [
        f'ShowsBR — Relatório de Monitoramento',
        f'Gerado em: {hoje}',
        f'',
        f'RESUMO',
        f'Shows verificados (próximos {JANELA_DIAS} dias): {total}',
        f'Links OK: {ok}',
        f'Problemas detectados: {len(problemas)}',
        f'',
    ]

    if problemas:
        linhas.append('PROBLEMAS DETECTADOS')
        linhas.append('=' * 40)
        for r in problemas:
            linhas.append(f'')
            linhas.append(f'Show: {r["artista"]} — {r["cidade"]}/{r["estado"]}')
            linhas.append(f'Data: {r["data"]}')
            linhas.append(f'Link: {r["link"]}')
            linhas.append(f'Status HTTP: {r["status_code"] or "Sem resposta"}')
            if r['cancelado']:
                linhas.append(f'⚠️ POSSÍVEL CANCELAMENTO DETECTADO')
            linhas.append(f'Ação: revisar no Sheets e atualizar status')
    else:
        linhas.append('Todos os shows verificados estão com links ativos.')

    linhas.append('')
    linhas.append('showsbr.com.br — Do interior às capitais.')
    return '\n'.join(linhas)


def enviar_email(relatorio):
    """Envia o relatório por e-mail (via Gmail SMTP simples)."""
    email_admin = os.environ.get('EMAIL_ADMIN', '')
    if not email_admin:
        log.info('EMAIL_ADMIN não configurado — relatório não enviado por e-mail.')
        return

    # Para envio real, configure SMTP_USER e SMTP_PASS nos Secrets do GitHub
    smtp_user = os.environ.get('SMTP_USER', '')
    smtp_pass = os.environ.get('SMTP_PASS', '')

    if not smtp_user or not smtp_pass:
        log.info('SMTP não configurado. Imprimindo relatório no log:')
        log.info(relatorio)
        return

    msg = MIMEText(relatorio, 'plain', 'utf-8')
    msg['Subject'] = f'ShowsBR Monitor — {datetime.now().strftime("%d/%m/%Y")}'
    msg['From'] = smtp_user
    msg['To'] = email_admin

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        log.info(f'Relatório enviado para {email_admin}')
    except Exception as e:
        log.error(f'Erro ao enviar e-mail: {e}')
        log.info('Relatório completo:')
        log.info(relatorio)


def main():
    log.info('=== ShowsBR Agente Monitor iniciado ===')

    todos_shows = carregar_todos_shows()
    log.info(f'Total de shows carregados: {len(todos_shows)}')

    proximos = filtrar_proximos(todos_shows)
    log.info(f'Shows nos próximos {JANELA_DIAS} dias: {len(proximos)}')

    resultados = []
    atualizados = []

    for show in proximos:
        artista = show.get('artista', '')
        link = show.get('link_compra', '')
        estado = show.get('estado', '')
        show_id = show.get('id', '')

        log.info(f'Verificando: {artista} ({show.get("data_iso", "")}) — {link or "sem link"}')

        link_ok, status_code = verificar_link(link)
        cancelado = verificar_cancelamento_sympla(show) if link else False

        resultado = {
            'artista': artista,
            'cidade': show.get('cidade', ''),
            'estado': estado,
            'data': show.get('data_iso', ''),
            'link': link,
            'link_ok': link_ok,
            'status_code': status_code,
            'cancelado': cancelado,
        }
        resultados.append(resultado)

        # Atualizar status se cancelamento detectado
        if cancelado and show.get('status') != 'Cancelado':
            log.warning(f'Possível cancelamento: {artista} — atualizando status.')
            atualizar_status_json(estado, show_id, 'Cancelado')
            atualizados.append(show_id)

    log.info(f'Verificação concluída. {len(atualizados)} status atualizados.')

    relatorio = montar_relatorio(resultados)
    enviar_email(relatorio)

    # Sempre imprimir no log para visibilidade no GitHub Actions
    log.info('\n' + relatorio)
    log.info('=== Agente Monitor finalizado ===')


if __name__ == '__main__':
    main()
