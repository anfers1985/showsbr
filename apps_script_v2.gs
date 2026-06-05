/**
 * ShowsBR — Google Apps Script Web App v2
 * Recebe submissões via URLSearchParams (compatível com no-cors)
 * 
 * ATUALIZAR o script existente em script.google.com:
 * 1. Substitua TODO o código pelo código abaixo
 * 2. Clique em Implantar → Gerenciar implantações
 * 3. Clique no lápis (editar) na implantação atual
 * 4. Mude a versão para "Nova versão"
 * 5. Clique em Implantar
 * (A URL não muda — só atualiza o código)
 */

const SHEETS_ID = '1bPGULJMgUEbCXFGYnQwetTXjV5KrSeKC_wWoYPk0muQ';

function doPost(e) {
  try {
    // Aceita tanto URLSearchParams (e.parameter) quanto JSON (e.postData)
    let dados = {};

    if (e.parameter && Object.keys(e.parameter).length > 0) {
      dados = e.parameter;
    } else if (e.postData && e.postData.contents) {
      dados = JSON.parse(e.postData.contents);
    }

    const planilha = SpreadsheetApp.openById(SHEETS_ID);
    const aba = planilha.getSheetByName('Pendentes');
    const agora = new Date().toLocaleString('pt-BR', {timeZone: 'America/Sao_Paulo'});

    const id = Utilities.computeDigest(
      Utilities.DigestAlgorithm.MD5,
      `${dados.artista || ''}-${dados.data || ''}-${dados.estado || ''}`
    ).map(b => ('0' + (b & 0xFF).toString(16)).slice(-2)).join('').substring(0, 12);

    aba.appendRow([
      id,
      dados.artista     || '',
      dados.artista     || '',
      dados.descricao   || '',
      dados.genero      || '',
      dados.data        || '',
      dados.horario     || '',
      dados.local       || '',
      dados.endereco    || '',
      dados.cidade      || '',
      dados.estado      || '',
      dados.organizador || '',
      dados.cnpj        || '',
      dados.valores     || '',
      dados.gratuito    || 'NÃO',
      dados.link_compra || '',
      dados.cupom       || '',
      'formulario-showsbr.com.br',
      agora,
    ]);

    return ContentService
      .createTextOutput(JSON.stringify({ status: 'ok' }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: 'erro', msg: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService
    .createTextOutput(JSON.stringify({ status: 'ShowsBR Form API v2 ativa' }))
    .setMimeType(ContentService.MimeType.JSON);
}
