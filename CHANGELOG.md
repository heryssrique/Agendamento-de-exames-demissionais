# CHANGELOG

Data: 2025-10-18

Resumo das alterações e correções importantes

## Correções e melhorias

- chore: travar `pymongo==4.8.0` em `backend/requirements-prod.txt`
  - Motivo: compatibilidade com `motor==3.3.1` (evitou ImportError relacionados a `_QUERY_OPTIONS`).

- Implementado wheelhouse local: `backend/wheels/`
  - Baixamos wheels manylinux compatíveis com CPython 3.11 para evitar falhas de build/segfaults durante `pip install` dentro do container.
  - Comando para regenerar (exemplo):

```powershell
python -m pip download -r backend/requirements-prod.txt -d backend/wheels \
  --platform manylinux2014_x86_64 --only-binary=:all: --implementation cp --abi cp311 -i https://pypi.org/simple
```

- Script de automação para Windows/WSL: `scripts/regenerate_wheels.ps1`
  - Tenta baixar com `--platform` e faz fallback para `--only-binary` caso necessário.

- Documentação: `backend/README_WHEELS.md` explicando o fluxo e recomendações (não commitar `backend/wheels/`).

- CI: atualização de `.github/workflows/ci-smoke.yml`
  - Garante que o serviço `mongo` seja iniciado no job.
  - Adiciona smoke tests HTTP (`/health`, `/api/health`, `/health/ready`, frontend root).
  - Adiciona teste DB end-to-end (one-off run dentro da imagem `backend`) que insere/consulta/exclui um documento em `ci_smoke_tests`.
  - Coleta logs e faz upload de artefatos em caso de falha.

## Como verificar localmente

1. Regenerar wheels (se necessário):

```powershell
./scripts/regenerate_wheels.ps1
```

ou (em Docker):

```powershell
docker run --rm -v ${PWD}:/src -w /src python:3.11-slim bash -lc "python -m pip install pip==23.1.2 setuptools wheel packaging resolvelib && python -m pip download -r backend/requirements-prod.txt -d backend/wheels --platform manylinux2014_x86_64 --only-binary=:all: --implementation cp --abi cp311 -i https://pypi.org/simple"
```

2. Build e subir:

```powershell
docker compose build backend frontend
docker compose up -d
```

3. Testes de smoke locais:

```powershell
curl -i http://localhost:8000/health
curl -i http://localhost:8000/health/ready
curl -i http://localhost:3000/
```

## Recomendações futuras

- Manter `pymongo` travado na versão testada (4.8.0) ou testar explicitamente ao atualizar `motor`.
- Considerar publicar o wheelhouse como artifact na pipeline CI para builds reproduzíveis.
- Expandir os testes de integração no CI para cobrir endpoints reais e operações de negócio.

---

Criado automaticamente pelo agente de manutenção em 2025-10-18.
