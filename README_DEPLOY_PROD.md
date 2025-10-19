# README_DEPLOY_PROD.md

Guia de deploy (produção) — MongoDB Atlas + Frontend (Vercel/Netlify) + Backend (Render ou Fly)

Este documento descreve passo-a-passo como publicar a aplicação "Agendamento de Exames Demissionais" na internet usando MongoDB Atlas para o banco, Vercel/Netlify para frontend estático e Render ou Fly para o backend.

IMPORTANTE: nunca comite senhas e URIs com credenciais no repositório. Use secrets/variáveis de ambiente do provedor.

---

## Resumo rápido
- Banco: MongoDB Atlas (cluster gratuito possível)
- Frontend: Vercel (recomendado) ou Netlify
- Backend: Render (fácil) ou Fly (mais controle)
- Arquivos de ajuda já adicionados ao repositório:
  - `render.yaml` (raiz) — template para Render
  - `backend/fly.toml` — template para Fly

## Variáveis de ambiente necessárias (backend)
Coloque estas variáveis no painel do provedor (ou use `fly secrets set` no Fly):

- MONGO_URL: string de conexão do MongoDB Atlas (mongodb+srv://...)
- DB_NAME: `agendamento` (ou o nome que preferir)
- TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID (se usar Trello)
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM_EMAIL, SMTP_FROM_NAME (se enviar e-mails)
- ADMIN_EMAILS (CSV, ex: `admin@ex.com,other@ex.com`)
- COOKIE_SECURE (`true` em produção)
- ALLOWED_ORIGINS (domínios do frontend separados por vírgula, ex: `https://app.ex.com,https://staging.ex.com`)
- DEV_AUTH_ENABLED (`false` em produção)

Variáveis do frontend (definir no provedor do frontend):
- REACT_APP_BACKEND_URL (ex: `https://api.exemplo.com`)

---

## 1) Criar cluster MongoDB Atlas
1. Crie conta em https://www.mongodb.com/cloud/atlas
2. Crie um cluster (Shared Cluster) - pode usar o plano grátis para testes
3. Em "Database Access" -> add user -> crie um usuário com senha
4. Em "Network Access" -> Add IP Address -> para testes, adicione `0.0.0.0/0` temporariamente
   - Para produção: restrinja IPs ou use VPC peering
5. Em "Clusters" -> Connect -> "Connect your application" -> copie a connection string
   - Substitua `<password>` e `<dbname>` conforme necessário

Exemplo de MONGO_URL:
```
mongodb+srv://meuUser:MINHA_SENHA@cluster0.abcdef.mongodb.net/agendamento?retryWrites=true&w=majority
```

---

## 2) Deploy do Frontend (Vercel recomendado)
### Vercel
1. Crie conta em https://vercel.com e conecte o repositório GitHub/GitLab/Bitbucket
2. Ao criar o projeto, em **Environment Variables** adicione:
   - `REACT_APP_BACKEND_URL` = `https://<seu-backend-url>` (ex: `https://api.meusite.com` ou o host do Render/Fly)
3. Build & Output:
   - Build command: `npm run build`
   - Output directory: `build`
4. Deploy — Vercel fará build e disponibiliza o site em `https://<projeto>.vercel.app` com SSL automático
5. Para domínio próprio: Domains → Add domain → siga instruções de DNS (CNAME)

### Netlify (alternativa)
1. Conecte repositório em https://netlify.com
2. Em Site settings → Build & deploy → Environment → Add variable:
   - `REACT_APP_BACKEND_URL` = `https://<seu-backend-url>`
3. Build command: `npm run build`
   - Publish directory: `build`
4. Deploy — Netlify fornece SSL automático

> Observação: REACT_APP_BACKEND_URL é embutida no build. Se alterar o backend URL, re-deploy do frontend é necessário.

---

## 3) Deploy do Backend — Render (guia passo-a-passo)
Render é simples e usa o `backend/Dockerfile`.

### Usando o painel Render
1. Crie conta em https://render.com e conecte o repositório
2. Create → Web Service
   - Environment: `Docker`
   - Dockerfile Path: `backend/Dockerfile`
   - Instance Type: Starter (ou conforme necessidade)
   - Health Check Path: `/health`
3. Em Environment → configure as env vars (MONGO_URL, DB_NAME, COOKIE_SECURE, ALLOWED_ORIGINS, etc.)
   - Para variáveis sensíveis, prefira configurar no painel mesmo
4. Deploy automático: Render builda e starta o container
5. URL pública: `https://<servico>.onrender.com` (SSL automático)

### Exemplo rápido: `render.yaml`
Arquivo `render.yaml` já adicionado ao repo como template. Preencha `PLACEHOLDER_MONGO_URL` apenas se quiser, ou configure variáveis pelo painel.

### Teste
No PowerShell, rode:
```powershell
Invoke-RestMethod https://<seu-backend>.onrender.com/health
Invoke-RestMethod https://<seu-backend>.onrender.com/api/health/ready
```

---

## 4) Deploy do Backend — Fly.io (guia passo-a-passo)
Fly usa `flyctl` e `fly.toml`. O template `backend/fly.toml` foi adicionado.

### Instalar flyctl
Siga https://fly.io/docs/hands-on/install-flyctl/

### Criar e configurar app
No PowerShell:
```powershell
# ir para a pasta backend
Set-Location .\backend

# login
fly auth login

# criar app (escolha nome/região) - dará um fly.toml e você pode editar
fly launch --name agendamento-backend --region ord
```

Se preferir, não deixe que o CLI faça deploy inicial (responda `no` quando perguntado), e então ajuste `fly.toml` como quiser.

### Segredos (recomendado)
Use `fly secrets set` para variáveis sensíveis:
```powershell
fly secrets set MONGO_URL="mongodb+srv://user:pass@..." \
  TRELLO_API_KEY="..." TRELLO_TOKEN="..." ADMIN_EMAILS="admin@ex.com" COOKIE_SECURE="true" ALLOWED_ORIGINS="https://app.seudominio.com"
```

### Deploy
```powershell
fly deploy
```

### Teste
```powershell
Invoke-RestMethod https://agendamento-backend.fly.dev/health
```

---

## 5) Configurar Trello webhooks e URLs públicas
Se usar Trello webhooks, a URL do callback deve ser pública e aceitar requisições HEAD para verificação. Exemplo:
```
https://<seu-backend>/api/trello/webhook
```
Teste com `curl` ou `Invoke-RestMethod` — Trello fará HEAD e POST para essa URL.

---

## 6) Testes e verificação (end-to-end)
1. Backend healthy:
```powershell
Invoke-RestMethod https://<seu-backend>/health
Invoke-RestMethod https://<seu-backend>/api/health/ready
```
2. Frontend: acesse URL do Vercel/Netlify e verifique console do navegador (Network) — requisições devem apontar para `REACT_APP_BACKEND_URL/api/...`
3. Cookies: após login (ou `dev-login`), confira em Application → Cookies que `session_token` exista e esteja `Secure`/`HttpOnly` conforme `COOKIE_SECURE`
4. Logs:
   - Render: Dashboard → Logs
   - Fly: `fly logs --app agendamento-backend`

---

## 7) Comandos úteis (PowerShell)
```powershell
# Testar health
Invoke-RestMethod https://<seu-backend>/health

# Testar readiness
Invoke-RestMethod https://<seu-backend>/api/health/ready

# Fly: setar secrets e deploy
Set-Location .\backend
fly auth login
fly secrets set MONGO_URL="mongodb+srv://user:pass@..." ADMIN_EMAILS="admin@ex.com" COOKIE_SECURE="true" ALLOWED_ORIGINS="https://app.seudominio.com"
fly deploy

# Visualizar logs Fly
fly logs --app agendamento-backend

# Render: logs via painel (não necessita CLI)

# Vercel: re-deploy via painel ou vercel CLI (opcional)
```

---

## 8) Troubleshooting rápido
- Erro Mongo no readiness: verifique MONGO_URL e Network Access no Atlas (IP whitelist)
- CORS: verifique `ALLOWED_ORIGINS` no backend e que `REACT_APP_BACKEND_URL` foi configurado no frontend antes do build
- Cookies não salvos: use HTTPS e `COOKIE_SECURE=true`; se domínio diferente, cookie precisa `SameSite=None` (o backend ajusta isso automaticamente quando `COOKIE_SECURE=true`)
- Falha no build do frontend: verifique Node version definida pelo provedor (repo usa Node 18 no Dockerfile)

---

## 9) Próximos passos sugeridos (opcionais)
- Habilitar backups do MongoDB Atlas
- Mover DB para VPC ou restringir IPs ao provedor usado
- Adicionar CI/CD (GitHub Actions) que faz deploy automático para Render/Fly
- Habilitar monitoramento/alertas no Render/Fly e configurar rotação de logs

---

## Contato
Se quiser, eu posso:
- Preencher `render.yaml` com valores não sensíveis (já deixei template)
- Gerar um GitHub Actions para fazer deploy automático
- Ajudar a configurar DNS/SSL para domínio próprio

Fim.

---

## CI: GitHub Actions (deploy automático)

Incluí dois workflows de exemplo em `.github/workflows/`:

- `deploy-render.yml` — deploy para Render usando API Key e Service ID.
- `deploy-fly.yml` — deploy para Fly usando `flyctl`.

Secrets necessários no GitHub (Repository -> Settings -> Secrets & Variables -> Actions):

Para Render (`deploy-render.yml`):
- `RENDER_API_KEY` — API key gerada no painel Render
- `RENDER_SERVICE_ID` — ID do serviço (opcional dependendo da integração)

Para Fly (`deploy-fly.yml`):
- `FLY_API_TOKEN` — token criado no Fly (Settings -> Personal Tokens)

Observações:
- Ainda é recomendado usar o painel do provedor para variáveis sensíveis do runtime (MONGO_URL, SMTP, etc.).
- Os workflows disparam em push para branches `main`, `master` ou `release/**`.

Se quiser, posso adaptar os workflows para rodar apenas em tags ou em pull-requests aprovados.
