# ShowsBR

**Do interior às capitais — shows por todo o Brasil.**

Portal informativo de shows musicais | showsbr.com.br

---

## Stack

- **Site:** HTML/CSS/JS estático (SPA) — sem framework, zero dependências de build
- **Hospedagem:** Cloudflare Pages (gratuito)
- **Repositório:** GitHub (público — Actions gratuito ilimitado)
- **Dados:** JSON por estado em `data/shows/` + `data/cupons.json`
- **Automação:** GitHub Actions (3 agentes: Coletor, Publicador, Monitor)
- **Formulário:** Tally.so → Google Sheets
- **Monetização:** Adsterra (banners 728×90 e 300×250)

---

## Estrutura do Repositório

```
showsbr/
├── .github/
│   └── workflows/
│       ├── coletar.yml       # Agente Coletor — seg–sex 8h, 12h, 17h BRT
│       ├── publicar.yml      # Agente Publicador — a cada 2h
│       └── monitorar.yml     # Agente Monitor — diariamente 6h BRT
├── data/
│   ├── shows/
│   │   ├── SC.json           # Shows de Santa Catarina
│   │   ├── SP.json           # Shows de São Paulo
│   │   └── ...               # Um arquivo por estado (UF.json)
│   └── cupons.json           # Cupons de desconto ativos
├── scripts/
│   ├── coletar.py            # Lógica do Agente Coletor
│   ├── publicar.py           # Lógica do Agente Publicador
│   └── monitorar.py          # Lógica do Agente Monitor
└── public/
    ├── index.html            # Site completo (SPA)
    ├── ads.txt               # Adsterra publisher file
    ├── robots.txt
    ├── sitemap.xml
    ├── _headers              # Headers de segurança (Cloudflare)
    └── _redirects            # Regras de roteamento (Cloudflare)
```

---

## Deploy no Cloudflare Pages

1. Faça fork ou clone este repositório para sua conta GitHub
2. Acesse [dash.cloudflare.com](https://dash.cloudflare.com) → **Pages** → **Create a project**
3. Conecte ao GitHub e selecione o repositório `showsbr`
4. Configure:
   - **Branch:** `main`
   - **Build command:** *(deixar vazio — site estático)*
   - **Build output directory:** `public`
5. Clique em **Save and Deploy**
6. Após deploy, vá em **Custom domains** e adicione `showsbr.com.br`
7. Configure os nameservers do domínio para apontar para o Cloudflare

**Resultado:** a cada push na branch `main`, o Cloudflare reconstrói o site automaticamente.

---

## Configuração do Google Sheets

### Estrutura da planilha

Crie uma planilha Google Sheets com **5 abas** com estes nomes exatos:

| Aba | Função |
|-----|--------|
| `Pendentes` | Shows coletados pelo agente. Você revisa aqui. |
| `Aprovados` | Shows validados. O Agente Publicador lê esta aba. |
| `Publicados` | Histórico de tudo que foi ao ar. |
| `Rejeitados` | Shows rejeitados com motivo. |
| `Configurações` | Parâmetros dos agentes. |

### Colunas (abas Pendentes e Aprovados)

| Col | Nome | Descrição |
|-----|------|-----------|
| A | ID | Hash único gerado pelo agente |
| B | Artista | Nome do artista ou banda |
| C | Artista/Evento | Nome unificado do evento |
| D | Descrição | Line-up, atrações, texto livre |
| E | Gênero | Estilo musical |
| F | Data | DD/MM/AAAA |
| G | Horário | HH:MM |
| H | Local | Nome do espaço |
| I | Endereço | Rua, número, bairro |
| J | Cidade | Município |
| K | Estado | Sigla UF |
| L | Organizador | Empresa ou entidade |
| M | CNPJ | CNPJ do organizador |
| N | Valores | Preços (um por linha) |
| O | Gratuito | SIM ou NÃO |
| P | Link Compra | URL oficial |
| Q | Cupom | Código e validade |
| R | Fonte | URL de origem |
| S | Data Coleta | DD/MM/AAAA HH:MM |

---

## Configuração dos GitHub Actions Secrets

Acesse: **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Como obter |
|--------|------------|
| `GOOGLE_CREDENTIALS` | JSON da Service Account (Google Cloud Console) |
| `SHEETS_ID` | ID da planilha — está na URL entre `/d/` e `/edit` |
| `EMAIL_ADMIN` | Seu e-mail para relatórios diários |
| `SMTP_USER` | E-mail Gmail para envio dos relatórios (opcional) |
| `SMTP_PASS` | Senha de app Gmail (opcional) |

### Como criar a Service Account Google

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Crie um projeto chamado `ShowsBR`
3. Ative a **Google Sheets API** e a **Google Drive API**
4. Vá em **IAM e administração → Contas de serviço → Criar conta de serviço**
5. Dê um nome (ex: `showsbr-bot`) e clique em Criar
6. Baixe a chave JSON da conta de serviço
7. **Copie o e-mail** da conta de serviço (ex: `showsbr-bot@showsbr.iam.gserviceaccount.com`)
8. **Compartilhe a planilha** com esse e-mail (como Editor)
9. Cole o JSON completo no secret `GOOGLE_CREDENTIALS`

---

## Configuração do Adsterra

1. Crie conta em [adsterra.com](https://adsterra.com) como Publisher
2. Adicione o site `showsbr.com.br`
3. Após aprovação (24–48h), gere dois tipos de banner:
   - `728×90` — para o topo das listagens
   - `300×250` — para a sidebar
4. **Atualize o `public/ads.txt`** com o conteúdo fornecido pelo Adsterra
5. Cole os códigos dos banners no `public/index.html` nos `<div class="ad-banner">` correspondentes
   - Procure por `<!-- ADSTERRA BANNER 728×90 -->` e `<!-- ADSTERRA BANNER 300×250 -->`

> **Regra editorial:** somente banners estáticos. Nunca ativar pop-up, interstitial ou push notification.

---

## Schema JSON dos Shows

Cada show no `data/shows/UF.json` segue este schema:

```json
{
  "id": "string — hash único (artista+data+cidade)",
  "artista": "string — nome do artista/banda/evento",
  "genero": "string — Sertanejo | Rock | Forró | etc.",
  "data_iso": "string — YYYY-MM-DD",
  "horario": "string — HH:MM (opcional)",
  "local": "string — nome do espaço",
  "endereco": "string — rua, número, bairro (opcional)",
  "cidade": "string",
  "estado": "string — sigla UF",
  "descricao": "string — line-up, atrações (opcional)",
  "organizador": "string — empresa ou entidade organizadora",
  "cnpj": "string — CNPJ do organizador",
  "valores": "string — preços em texto livre, um por linha (opcional)",
  "gratuito": "boolean",
  "link_compra": "string — URL oficial (opcional)",
  "cupom": "string — código de desconto (opcional)",
  "classificacao": "string — Livre | 14+ | 16+ | 18+ (opcional)",
  "status": "string — Confirmado | A confirmar | Cancelado | Esgotado",
  "fonte": "string — URL ou identificador da fonte"
}
```

---

## Fluxo Editorial

```
Internet (Sympla, Eventim, Ticket360, Formulário comunidade)
       ↓
GitHub Action — Agente Coletor (3× por dia, seg–sex)
       ↓
Google Sheets — Aba PENDENTES
       ↓  ← VOCÊ REVISA AQUI: verifica CNPJ, data, link ←
Google Sheets — Aba APROVADOS (move a linha após aprovação)
       ↓
GitHub Action — Agente Publicador (a cada 2h)
       ↓
data/shows/UF.json atualizado no repositório
       ↓
Cloudflare Pages — rebuild automático ao detectar push
       ↓
showsbr.com.br atualizado ✓
```

**Tempo médio do ciclo:** aprovação → publicação em até 2 horas.

---

## Processo de Revisão (Sheets)

Para cada linha na aba **Pendentes**:

1. Verificar se as informações fazem sentido: data futura, cidade e estado corretos, artista reconhecível
2. Verificar o CNPJ do organizador: `https://receitaws.com.br/v1/[CNPJ]` — confirmar empresa ativa
3. Confirmar se o link de compra abre corretamente
4. Corrigir erros de ortografia ou formatação
5. **Se aprovado:** mover a linha para a aba **Aprovados**
6. **Se rejeitado:** mover para **Rejeitados** e anotar o motivo

> Dica: use filtros no Google Sheets para revisar por estado ou por data de coleta.

---

## Monetização

| Fase | Ação |
|------|------|
| Lançamento | Adsterra — banners 728×90 e 300×250 |
| Mês 3–4 | Google AdSense (se tráfego > 5.000 visitas/mês) |
| Mês 4–6 | Afiliados: Booking.com + Decolar nas fichas de show |
| Mês 6+ | Destaques patrocinados para produtores |
| Mês 8+ | Afiliação de cupons (Sympla, Eventim, Ticket360) |

---

## Custos

| Item | Custo |
|------|-------|
| GitHub (público + Actions ilimitado) | Gratuito |
| Cloudflare Pages | Gratuito |
| Google Sheets + Drive API | Gratuito |
| Tally.so (até 100 submissões/mês) | Gratuito |
| Adsterra (publisher — você recebe) | Gratuito |
| Domínio showsbr.com.br | ≈ R$ 60–120/ano |
| **TOTAL** | **≈ R$ 5–10/mês** |

---

## Contato

**showsbr.com.br** — Do interior às capitais, shows por todo o Brasil.

contato@showsbr.com.br
