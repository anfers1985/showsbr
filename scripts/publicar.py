"""
ShowsBR — Agente Publicador de Shows
Lê a aba Aprovados do Google Sheets e atualiza os arquivos JSON no repositório.
Roda via GitHub Actions a cada 2 horas.
"""

import os
import json
import hashlib
import logging
import re
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
SHOWS_DIR = Path('public/shows')
SITE_URL = 'https://showsbr.com.br'


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
        json.dump(shows_sorted, f, ensure_ascii=False, indent=2, allow_nan=False)
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
        log.info('Nenhum show aprovado pendente — regenerando páginas e sitemap com shows existentes.')
        gerar_all_json()
        log.info('=== Agente Publicador finalizado ===')
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
    # Gerar all.json combinando todos os estados
    gerar_all_json()
    log.info('=== Agente Publicador finalizado ===')


def gerar_slug(artista, cidade, data_iso):
    """
    Gera um slug amigável para URL a partir do artista, cidade e data.
    Ex: 'Coldplay' + 'São Paulo' + '2026-07-01' -> 'coldplay-sao-paulo-2026-07-01'
    """
    texto = f'{artista}-{cidade}-{data_iso}'
    texto = texto.lower()
    # Remove acentos comuns em português
    substituicoes = {
        'á':'a','à':'a','ã':'a','â':'a','ä':'a',
        'é':'e','è':'e','ê':'e','ë':'e',
        'í':'i','ì':'i','î':'i','ï':'i',
        'ó':'o','ò':'o','õ':'o','ô':'o','ö':'o',
        'ú':'u','ù':'u','û':'u','ü':'u',
        'ç':'c','ñ':'n',
    }
    for orig, sub in substituicoes.items():
        texto = texto.replace(orig, sub)
    texto = re.sub(r'[^a-z0-9]+', '-', texto)
    texto = re.sub(r'-+', '-', texto).strip('-')
    return texto[:120]  # limite razoável de tamanho de URL


def escapar_html(texto):
    """Escapa caracteres especiais para uso seguro em HTML."""
    if not texto:
        return ''
    return (str(texto)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


def gerar_pagina_show(show):
    """
    Gera uma página HTML estática e independente para um show, com
    marcação schema.org/Event embutida em JSON-LD. Isso dá ao show uma
    URL própria e indexável (coisa que o site SPA principal não oferece,
    já que toda a navegação ali acontece via JavaScript sem mudar a URL),
    e ajuda o Google a exibir informações estruturadas (datas, local,
    preço) diretamente no resultado de busca.
    """
    artista = show.get('artista', 'Show')
    cidade = show.get('cidade', '')
    estado = show.get('estado', '')
    data_iso = show.get('data_iso', '')
    horario = show.get('horario', '') or '20:00'
    local = show.get('local', '')
    endereco = show.get('endereco', '')
    descricao = show.get('descricao', '') or f'{artista} em {cidade}, {estado}.'
    link_compra = show.get('link_compra', '')
    genero = show.get('genero', '')
    gratuito = show.get('gratuito', False)
    valores = show.get('valores', '')

    titulo_pagina = f'{artista} em {cidade}, {estado} — {data_iso} | ShowsBR'
    slug = gerar_slug(artista, cidade, data_iso)
    url_canonica = f'{SITE_URL}/shows/{slug}.html'

    data_hora_iso = f'{data_iso}T{horario}:00-03:00' if data_iso else ''

    # Preço estruturado: 0 se gratuito, senão omite valor exato (texto livre)
    oferta_json = ''
    if link_compra:
        preco = '0' if gratuito else None
        oferta_dict = {
            '@type': 'Offer',
            'url': link_compra,
            'availability': 'https://schema.org/InStock',
        }
        if preco is not None:
            oferta_dict['price'] = preco
            oferta_dict['priceCurrency'] = 'BRL'
        oferta_json = ',\n      "offers": ' + json.dumps(oferta_dict, ensure_ascii=False)

    schema = {
        '@context': 'https://schema.org',
        '@type': 'Event',
        'name': artista,
        'startDate': data_hora_iso,
        'eventAttendanceMode': 'https://schema.org/OfflineEventAttendanceMode',
        'eventStatus': 'https://schema.org/EventScheduled',
        'description': descricao,
        'location': {
            '@type': 'Place',
            'name': local or cidade,
            'address': {
                '@type': 'PostalAddress',
                'streetAddress': endereco,
                'addressLocality': cidade,
                'addressRegion': estado,
                'addressCountry': 'BR',
            }
        }
    }
    schema_json = json.dumps(schema, ensure_ascii=False, indent=2)
    if oferta_json:
        # injeta offers dentro do mesmo objeto JSON-LD
        schema['offers'] = json.loads(oferta_json.split(': ', 1)[1])
        schema_json = json.dumps(schema, ensure_ascii=False, indent=2)

    html = f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escapar_html(titulo_pagina)}</title>
<meta name="description" content="{escapar_html(descricao)[:160]}">
<link rel="canonical" href="{url_canonica}">
<meta property="og:title" content="{escapar_html(artista)} em {escapar_html(cidade)}, {escapar_html(estado)}">
<meta property="og:description" content="{escapar_html(descricao)[:200]}">
<meta property="og:type" content="event">
<meta property="og:url" content="{url_canonica}">
<script type="application/ld+json">
{schema_json}
</script>
<style>
  body{{font-family:system-ui,-apple-system,sans-serif;max-width:640px;margin:40px auto;padding:0 20px;color:#1a1a2e;line-height:1.6}}
  a{{color:#0a7;text-decoration:none}}
  .voltar{{font-size:14px;margin-bottom:24px;display:inline-block}}
  h1{{font-size:28px;margin-bottom:4px}}
  .meta{{color:#666;font-size:15px;margin-bottom:20px}}
  .cta{{display:inline-block;background:#0a7;color:#fff;padding:12px 24px;border-radius:6px;margin-top:16px;font-weight:600}}
  .tag{{display:inline-block;background:#eee;padding:4px 10px;border-radius:4px;font-size:13px;margin-right:6px}}
</style>
</head>
<body>
<a class="voltar" href="/">&larr; Voltar para ShowsBR</a>
<h1>{escapar_html(artista)}</h1>
<p class="meta">{escapar_html(data_iso)} {escapar_html(horario)} &middot; {escapar_html(local)} &middot; {escapar_html(cidade)}/{escapar_html(estado)}</p>
<p>{escapar_html(descricao)}</p>
<p>
  {f'<span class="tag">{escapar_html(genero)}</span>' if genero else ''}
  <span class="tag">{'Gratuito' if gratuito else escapar_html(valores) or 'Confira valores'}</span>
</p>
{f'<a class="cta" href="{escapar_html(link_compra)}" target="_blank" rel="noopener">Ver ingressos / informações</a>' if link_compra else ''}
</body>
</html>'''

    return slug, html


def gerar_paginas_estaticas(shows):
    """
    Gera (ou atualiza) uma página HTML estática por show em public/shows/.
    Remove páginas de shows que já não estão na lista atual (encerrados
    ou cancelados), para não deixar lixo acumulando no repositório.
    """
    SHOWS_DIR.mkdir(parents=True, exist_ok=True)

    slugs_atuais = set()
    for show in shows:
        if not show.get('data_iso'):
            continue
        slug, html = gerar_pagina_show(show)
        slugs_atuais.add(slug)
        caminho = SHOWS_DIR / f'{slug}.html'
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write(html)

    # Limpeza: remove páginas de shows que não existem mais na lista atual
    removidos = 0
    for arquivo in SHOWS_DIR.glob('*.html'):
        if arquivo.stem not in slugs_atuais:
            arquivo.unlink()
            removidos += 1

    log.info(f'{len(slugs_atuais)} páginas de show geradas em {SHOWS_DIR}/ ({removidos} antigas removidas).')
    return slugs_atuais


def gerar_sitemap(shows):
    """
    Gera o sitemap.xml dinamicamente a partir da lista atual de shows,
    incluindo uma URL por show (que agora tem página própria graças a
    gerar_paginas_estaticas) além das páginas fixas do site. Roda a cada
    execução do Publicador, então o sitemap nunca fica desatualizado —
    shows novos entram automaticamente, encerrados saem.
    """
    agora = datetime.now().strftime('%Y-%m-%d')

    paginas_fixas = [
        (f'{SITE_URL}/', 'hourly', '1.0', agora),
        (f'{SITE_URL}/#estados', 'daily', '0.8', agora),
        (f'{SITE_URL}/#gratuitos', 'daily', '0.7', agora),
        (f'{SITE_URL}/#cupons', 'weekly', '0.6', agora),
        (f'{SITE_URL}/#cadastrar', 'monthly', '0.5', agora),
        (f'{SITE_URL}/#sobre', 'monthly', '0.4', agora),
    ]

    linhas = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    for loc, freq, prio, lastmod in paginas_fixas:
        linhas.append('  <url>')
        linhas.append(f'    <loc>{loc}</loc>')
        linhas.append(f'    <lastmod>{lastmod}</lastmod>')
        linhas.append(f'    <changefreq>{freq}</changefreq>')
        linhas.append(f'    <priority>{prio}</priority>')
        linhas.append('  </url>')

    vistos = set()
    for show in shows:
        if not show.get('data_iso'):
            continue
        slug = gerar_slug(show.get('artista', ''), show.get('cidade', ''), show['data_iso'])
        if slug in vistos:
            continue
        vistos.add(slug)
        linhas.append('  <url>')
        linhas.append(f'    <loc>{SITE_URL}/shows/{slug}.html</loc>')
        linhas.append(f'    <lastmod>{agora}</lastmod>')
        linhas.append('    <changefreq>weekly</changefreq>')
        linhas.append('    <priority>0.9</priority>')
        linhas.append('  </url>')

    linhas.append('</urlset>')

    with open('public/sitemap.xml', 'w', encoding='utf-8') as f:
        f.write('\n'.join(linhas))

    log.info(f'sitemap.xml gerado: {len(paginas_fixas)} páginas fixas + {len(vistos)} shows.')


def gerar_all_json():
    """Combina todos os JSONs de estado em um único public/data/shows/all.json."""
    import glob
    todos = []
    pasta = Path('public/data/shows')
    for caminho in sorted(pasta.glob('??.json')):  # só arquivos de 2 letras (UF)
        try:
            with open(caminho, 'r', encoding='utf-8') as f:
                shows = json.load(f)
                todos.extend(shows)
        except Exception as e:
            log.error(f'Erro ao ler {caminho}: {e}')

    todos.sort(key=lambda s: s.get('data_iso', ''))

    all_path = pasta / 'all.json'
    with open(all_path, 'w', encoding='utf-8') as f:
        json.dump(todos, f, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

    log.info(f'all.json gerado: {len(todos)} shows — {all_path.stat().st_size} bytes')

    # Apenas shows futuros entram nas páginas estáticas e no sitemap —
    # não há valor em indexar ou gerar página para shows já realizados.
    hoje = datetime.now().strftime('%Y-%m-%d')
    futuros = [s for s in todos if s.get('data_iso', '') >= hoje]

    gerar_paginas_estaticas(futuros)
    gerar_sitemap(futuros)


if __name__ == '__main__':
    main()
