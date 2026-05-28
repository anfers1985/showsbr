# ShowsBR — Guia de Implantação Passo a Passo

**Para:** Anderson (OAB/SC 44.858)
**Projeto:** showsbr.com.br
**Objetivo:** colocar o site no ar via GitHub + Cloudflare Pages, com automação via GitHub Actions e espaços preparados para Adsterra.

---

## VISÃO GERAL

O processo completo tem 4 fases:

| Fase | O que fazer | Tempo estimado |
|------|-------------|----------------|
| 0 — Contas e infraestrutura | GitHub, Cloudflare, Google Cloud | 1–2h |
| 1 — Repositório e deploy | Subir o código, ver o site no ar | 30min |
| 2 — Automação (Agentes) | Configurar os 3 agentes no GitHub | 1h |
| 3 — Adsterra | Cadastrar e inserir banners | Após aprovação (24–48h) |

---

## FASE 0 — CONTAS E INFRAESTRUTURA

### 0.1 — Conta no GitHub

1. Acesse **github.com** e crie uma conta gratuita (se ainda não tiver)
2. Confirme o e-mail
3. Crie um novo repositório:
   - Clique em **"New repository"** (botão verde no canto superior esquerdo)
   - Nome: `showsbr`
   - Visibilidade: **Public** (obrigatório para GitHub Actions gratuito ilimitado)
   - Marque **"Add a README file"**
   - Clique em **"Create repository"**

### 0.2 — Conta no Cloudflare

1. Acesse **cloudflare.com** e crie uma conta gratuita
2. Confirme o e-mail
3. Adicione seu domínio `showsbr.com.br`:
   - Clique em **"Add a Site"**
   - Digite `showsbr.com.br`
   - Selecione o plano **Free**
4. O Cloudflare vai mostrar os **nameservers** (dois endereços, ex: `ns1.cloudflare.com` e `ns2.cloudflare.com`)
5. **Copie esses dois nameservers** — você vai usá-los no registro do domínio

### 0.3 — Apontar o domínio para o Cloudflare

No painel do registro do seu domínio (onde comprou o `.com.br`):
1. Encontre a opção **"Alterar nameservers"** ou **"DNS"**
2. Substitua os nameservers atuais pelos dois fornecidos pelo Cloudflare
3. Aguarde até 24h para propagação (geralmente é mais rápido, 1–2h)

### 0.4 — Conta no Google Cloud (para os Agentes)

> Esta etapa é necessária apenas para os agentes automáticos. O site funciona sem ela.

1. Acesse **console.cloud.google.com** com sua conta Google
2. Clique em **"Novo projeto"** → nome: `ShowsBR` → **Criar**
3. No menu lateral: **APIs e serviços → Biblioteca**
4. Busque e ative estas duas APIs:
   - **Google Sheets API** → clicar em Ativar
   - **Google Drive API** → clicar em Ativar
5. No menu lateral: **IAM e administrador → Contas de serviço**
6. Clique em **"+ Criar conta de serviço"**:
   - Nome: `showsbr-bot`
   - Função: **Editor**
   - Clique em **Concluído**
7. Clique na conta de serviço criada → aba **Chaves** → **Adicionar chave → Criar nova chave → JSON**
8. Um arquivo `.json` será baixado. **Guarde-o com segurança — não compartilhe.**
9. **Copie o e-mail** da conta de serviço (termina em `@...iam.gserviceaccount.com`)

### 0.5 — Planilha Google Sheets

1. Crie uma nova planilha em **sheets.google.com**
2. Nomeie como `ShowsBR — Controle Editorial`
3. Renomeie as abas criando exatamente estas 5 (clique com botão direito na aba para renomear):
   - `Pendentes`
   - `Aprovados`
   - `Publicados`
   - `Rejeitados`
   - `Configurações`
4. Na aba **Pendentes**, crie os cabeçalhos na linha 1 (uma palavra por coluna A até S):
   `ID | Artista | Artista/Evento | Descrição | Gênero | Data | Horário | Local | Endereço | Cidade | Estado | Organizador | CNPJ | Valores | Gratuito | Link Compra | Cupom | Fonte | Data Coleta`
5. Repita os mesmos cabeçalhos na aba **Aprovados**
6. **Compartilhe a planilha** com o e-mail da conta de serviço (copiado no passo 0.4):
   - Clique em **"Compartilhar"** (botão azul no canto superior direito)
   - Cole o e-mail da conta de serviço
   - Permissão: **Editor**
   - Desmarque "Notificar pessoas" → Compartilhar
7. **Copie o ID da planilha**: está na URL entre `/d/` e `/edit`
   - Exemplo: `https://docs.google.com/spreadsheets/d/**1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms**/edit`
   - O ID é a parte destacada em negrito

---

## FASE 1 — REPOSITÓRIO E DEPLOY

### 1.1 — Subir o código no GitHub

Você tem duas opções: pelo site do GitHub (mais simples) ou pelo GitHub Desktop.

**Opção A — GitHub Desktop (recomendado, já que você usa no CalcuaPrazo):**

1. Abra o GitHub Desktop
2. Clone o repositório `showsbr` criado no passo 0.1
3. Descompacte o arquivo `showsbr.zip` entregue com este guia
4. Copie **todos os arquivos e pastas** para dentro da pasta do repositório local
5. No GitHub Desktop, você verá todos os arquivos listados como "changes"
6. Escreva uma mensagem de commit: `feat: deploy inicial ShowsBR`
7. Clique em **"Commit to main"**
8. Clique em **"Push origin"**

**Opção B — Upload direto no GitHub.com:**

1. Acesse seu repositório `showsbr` no github.com
2. Clique em **"uploading an existing file"**
3. Arraste os arquivos (pode fazer pasta por pasta se necessário)
4. Escreva uma mensagem de commit e clique em **"Commit changes"**

> **Estrutura que deve estar no repositório após o upload:**
> ```
> showsbr/
> ├── .github/workflows/coletar.yml
> ├── .github/workflows/publicar.yml
> ├── .github/workflows/monitorar.yml
> ├── data/shows/SC.json
> ├── data/shows/SP.json
> ├── data/cupons.json
> ├── scripts/coletar.py
> ├── scripts/publicar.py
> ├── scripts/monitorar.py
> ├── scripts/requirements.txt
> ├── public/index.html
> ├── public/ads.txt
> ├── public/robots.txt
> ├── public/sitemap.xml
> ├── public/_headers
> ├── public/_redirects
> ├── .gitignore
> └── README.md
> ```

### 1.2 — Conectar ao Cloudflare Pages

1. No painel do Cloudflare, clique em **Pages** no menu lateral esquerdo
2. Clique em **"Create a project"**
3. Selecione **"Connect to Git"**
4. Authorize o Cloudflare a acessar sua conta GitHub
5. Selecione o repositório `showsbr`
6. Configure o build:

| Campo | Valor |
|-------|-------|
| Project name | `showsbr` |
| Production branch | `main` |
| Build command | *(deixar vazio)* |
| Build output directory | `public` |

7. Clique em **"Save and Deploy"**
8. Aguarde o deploy (1–2 minutos). Você verá o site em `showsbr.pages.dev`

### 1.3 — Domínio personalizado

1. No painel do projeto no Cloudflare Pages, clique em **"Custom domains"**
2. Clique em **"Set up a custom domain"**
3. Digite `showsbr.com.br` → **Continue**
4. O Cloudflare vai criar automaticamente os registros DNS necessários
5. Clique em **"Activate domain"**
6. Aguarde a propagação SSL (5–30 minutos)

**Teste:** acesse `https://showsbr.com.br` — o site deve aparecer.

---

## FASE 2 — CONFIGURAÇÃO DOS AGENTES (GitHub Actions)

### 2.1 — Configurar os Secrets

1. No GitHub, acesse seu repositório `showsbr`
2. Clique em **Settings** (aba no topo)
3. No menu lateral: **Secrets and variables → Actions**
4. Clique em **"New repository secret"** e adicione um por um:

**Secret 1: GOOGLE_CREDENTIALS**
- Name: `GOOGLE_CREDENTIALS`
- Secret: abra o arquivo `.json` da conta de serviço (baixado no passo 0.4) em um editor de texto, selecione **todo o conteúdo** e cole aqui
- Clique em **"Add secret"**

**Secret 2: SHEETS_ID**
- Name: `SHEETS_ID`
- Secret: cole o ID da planilha (copiado no passo 0.5, item 7)
- Clique em **"Add secret"**

**Secret 3: EMAIL_ADMIN**
- Name: `EMAIL_ADMIN`
- Secret: seu endereço de e-mail pessoal (para receber relatórios)
- Clique em **"Add secret"**

### 2.2 — Ativar os workflows

Os 3 arquivos de workflow já estão no repositório em `.github/workflows/`. O GitHub Actions os detecta automaticamente.

Para verificar:
1. No repositório, clique na aba **Actions**
2. Você verá os 3 workflows listados: "Agente Coletor", "Agente Publicador", "Agente Monitor"
3. Se aparecer aviso de que os Actions estão desativados, clique em **"Enable GitHub Actions"**

### 2.3 — Testar os agentes manualmente

**Testar o Agente Coletor:**
1. Na aba Actions, clique em **"Agente Coletor de Shows"**
2. Clique em **"Run workflow"** → **"Run workflow"** (botão verde)
3. Aguarde 1–3 minutos
4. Se o ícone ficar verde (✓): funcionou. Abra sua planilha e veja a aba **Pendentes** — deve ter shows novos
5. Se ficar vermelho (✗): clique no workflow para ver o log de erro

**Testar o Agente Publicador:**
1. Primeiro, aprove manualmente alguns shows na planilha:
   - Abra a aba **Pendentes**
   - Verifique os dados (artista, data, cidade, CNPJ do organizador)
   - Se estiver correto: mova a linha para a aba **Aprovados** (recorte → cole)
2. Na aba Actions do GitHub, execute **"Agente Publicador"** manualmente
3. Aguarde 1–2 minutos
4. Verifique se os arquivos JSON foram atualizados (aba **Code** → `data/shows/`)
5. Acesse o site — os shows devem aparecer

---

## FASE 3 — ADSTERRA (banners)

> Faça o cadastro no Adsterra assim que o site estiver no ar e com os primeiros shows publicados.

### 3.1 — Cadastrar no Adsterra

1. Acesse **adsterra.com** e clique em **"Sign Up as Publisher"**
2. Preencha seus dados e crie a conta
3. Confirme o e-mail
4. Em **"My Sites"**, clique em **"Add Site"**:
   - URL: `showsbr.com.br`
   - Categoria: Entertainment / Music
   - Idioma: Portuguese
5. Escolha o método de verificação: **ads.txt** (mais simples)
6. O Adsterra vai fornecer uma linha de texto para colocar no `ads.txt`

### 3.2 — Atualizar o ads.txt

1. Abra o arquivo `public/ads.txt` do repositório
2. Substitua o conteúdo pelo fornecido pelo Adsterra
3. Faça commit e push — o Cloudflare vai atualizar o site automaticamente

### 3.3 — Gerar os banners

Após aprovação (24–48h):

1. No painel Adsterra, vá em **"My Sites" → seu site → "Get Ad Code"**
2. Gere o banner **728×90** (Leaderboard):
   - Formato: Banner
   - Tamanho: 728×90
   - Copie o código JavaScript gerado
3. Gere o banner **300×250** (Medium Rectangle):
   - Formato: Banner
   - Tamanho: 300×250
   - Copie o código JavaScript gerado

### 3.4 — Inserir os banners no site

Abra o arquivo `public/index.html` e localize os comentários (use Ctrl+F para encontrar):

```
<!-- ADSTERRA BANNER 728×90 — inserir código após aprovação -->
```

Substitua essa linha pelo código do banner 728×90. Faça o mesmo para o 300×250:

```
<!-- ADSTERRA BANNER 300×250 — inserir código após aprovação -->
```

> **Regra editorial:** somente banners estáticos (Banner display).
> **Nunca ativar:** Pop-under, Social Bar, Push Notifications — comprometem a experiência do usuário.

Faça commit e push das alterações.

---

## OPERAÇÃO DIÁRIA

### Revisar e aprovar shows (sua única tarefa recorrente)

1. Abra a planilha Google Sheets
2. Acesse a aba **Pendentes**
3. Para cada linha nova:
   - Verifique se os dados fazem sentido
   - Consulte o CNPJ do organizador: `https://receitaws.com.br/v1/CNPJ_AQUI` (sem pontuação)
   - Se aprovado: mova a linha para **Aprovados**
   - Se rejeitado: mova para **Rejeitados** e anote o motivo
4. O Agente Publicador pega os aprovados automaticamente em até 2h

### Cadastrar um show manualmente (sem o agente)

1. Abra a planilha e acesse a aba **Aprovados**
2. Adicione uma nova linha com os dados do show
3. Preencha todos os campos obrigatórios (ID, Artista, Gênero, Data, Local, Cidade, Estado)
4. Para o ID: use qualquer identificador único (ex: `sc-artista-cidade-data`)
5. O agente vai publicar em até 2h — ou execute-o manualmente pelo GitHub Actions

### Ver o relatório diário

O Agente Monitor envia um e-mail todo dia às 6h BRT com:
- Shows verificados nos próximos 14 dias
- Links com problemas detectados
- Possíveis cancelamentos

---

## RESOLUÇÃO DE PROBLEMAS

### O site não abre após o deploy

- Verifique se os nameservers do domínio foram alterados para o Cloudflare
- Aguarde até 24h para propagação do DNS
- No Cloudflare, veja se o deploy gerou erros (aba **Pages → seu projeto → Deployments**)

### O agente falha com erro de autenticação

- Verifique se o JSON no secret `GOOGLE_CREDENTIALS` está completo (começa com `{` e termina com `}`)
- Confirme que a planilha foi compartilhada com o e-mail da conta de serviço (com permissão de Editor)
- Confirme que as APIs do Google Sheets e Drive estão ativadas no projeto

### Os shows não aparecem no site após aprovação

- Aguarde o próximo ciclo do Agente Publicador (roda a cada 2h)
- Ou acione manualmente: GitHub → Actions → "Agente Publicador" → "Run workflow"
- Verifique se a linha aprovada na planilha tem Estado preenchido (obrigatório)

### O Agente Coletor não encontra shows

- É normal no início — os agentes dependem da disponibilidade das APIs das fontes
- Execute manualmente e veja o log de erros no GitHub Actions
- Adicione shows manualmente na aba **Aprovados** para validar o restante do fluxo

---

## CHECKLIST DE LANÇAMENTO

- [ ] Conta GitHub criada e repositório `showsbr` criado (público)
- [ ] Todos os arquivos do projeto enviados ao repositório
- [ ] Conta Cloudflare criada
- [ ] Domínio `showsbr.com.br` com nameservers apontando para Cloudflare
- [ ] Projeto no Cloudflare Pages conectado ao repositório GitHub
- [ ] Deploy realizado — site acessível em `showsbr.pages.dev`
- [ ] Domínio personalizado `showsbr.com.br` configurado e com SSL ativo
- [ ] Google Cloud: projeto criado, APIs ativadas, conta de serviço criada
- [ ] Planilha Google Sheets criada com as 5 abas e cabeçalhos corretos
- [ ] Planilha compartilhada com o e-mail da conta de serviço
- [ ] Secrets configurados no GitHub: `GOOGLE_CREDENTIALS`, `SHEETS_ID`, `EMAIL_ADMIN`
- [ ] GitHub Actions: 3 workflows visíveis e sem erros
- [ ] Agente Coletor testado manualmente: shows chegando na aba Pendentes
- [ ] Agente Publicador testado: shows publicados aparecendo no site
- [ ] Cadastro no Adsterra iniciado (pode ser feito antes da aprovação)
- [ ] `ads.txt` atualizado com os dados do Adsterra
- [ ] Banners Adsterra inseridos no `index.html` após aprovação
- [ ] Primeiros 20–30 shows cadastrados manualmente para o lançamento
- [ ] Site testado em celular (responsividade)
- [ ] Google Search Console: propriedade adicionada e sitemap enviado

---

*ShowsBR — Do interior às capitais, shows por todo o Brasil.*
*showsbr.com.br*
