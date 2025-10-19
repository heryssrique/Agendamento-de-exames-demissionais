Netlify deployment notes
=======================

Este repositório contém o backend FastAPI em `backend/server.py`. Para rodar o backend como uma função do Netlify utilizaramos o wrapper ASGI `Mangum`.

O setup mínimo realizado aqui:

- `netlify.toml` redireciona `/api/*` para a função `/.netlify/functions/app`.
- `netlify/functions/app.py` importa `backend/server.py` e expõe um handler Mangum.
- `netlify/functions/requirements.txt` contém dependências mínimas para instalar na função.

Recomendações e caveats:

- Netlify Functions tem limite de tempo de execução (10s para Free, 26s para Business/Enterprise) — operações longas (p.ex. contactar Trello, Mongo queries pesadas, envio de emails síncrono) podem estourar o timeout. Recomenda-se mover tarefas longas para jobs assíncronos ou usar serviços externos (filas, workers, ou hospedagem dedicada).
- O projeto usa `motor` (MongoDB async). Netlify Functions reconstroem o ambiente a cada invocação — conexões persistentes podem não ser eficientes. Use pool reduzido e teste a latência.
- Alternativa recomendada: hospedar o backend num serviço que suporte aplicações ASGI persistentes (Vercel Serverless Functions com adaptações, Fly.io, Render, Railway, DigitalOcean App Platform, Heroku/Cloud Run) ou usar Docker.
- Variáveis de ambiente: configure `MONGO_URL`, `DB_NAME`, `TRELLO_*`, `SMTP_*`, `ADMIN_EMAILS`, etc. no painel do Netlify (Site settings -> Build & deploy -> Environment -> Environment variables).

Como testar localmente com Netlify CLI:

1. Instale Netlify CLI: `npm i -g netlify-cli`
2. No diretório do repo, rode:

```powershell
netlify dev
```

Ele instalará um ambiente local de funções. Ao usar o `netlify dev` certifique-se de criar um `.env` em `backend/.env` com as variáveis necessárias.

Observação final:
Este wrapper é uma solução rápida para experimentação. Para produção, prefira um host que suporte apps ASGI persistentes ou converta apenas endpoints leves em funções serverless e mantenha o núcleo do backend em um serviço persistente.
