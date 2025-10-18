Instruções de deploy local com Docker

Pré-requisitos:
- Docker & Docker Compose instalados

1) Copie o arquivo de exemplo de variáveis de ambiente e ajuste:

   cp .env.example .env
   # Edite .env com suas credenciais (Trello, SMTP, etc)

2) Construir e iniciar os containers:

   docker compose up --build -d

3) Acessar:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000

Notas e dicas:
- O `frontend` serve a build via nginx e faz proxy de /api para o container `backend`.
- Em produção considere:
  - Usar uma imagem do Mongo gerenciada (Atlas) ou volume persistente seguro.
  - Configurar variáveis de ambiente via Secrets/CI.
  - Usar um reverse-proxy (nginx/traefik) com TLS.

Se quiser, eu posso gerar um Dockerfile otimizado ou um deploy para um provedor (Heroku/Render/Cloud Run) — diga qual prefere.
