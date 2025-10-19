Como regenerar o wheelhouse (wheels) usado no Docker build
---------------------------------------------------------

Este repositório contém uma pasta `backend/wheels` utilizada pelo `Dockerfile` para instalar dependências a partir de wheels pré-baixadas. Isso evita problemas do resolver do pip, builds nativos durante o build da imagem, e melhora reprodutibilidade.

Regenerar as wheels localmente (PowerShell, no root do projeto):

```powershell
# cria/atualiza a pasta backend/wheels com todas as wheels necessárias
python -m pip download -r backend/requirements-prod.txt -d backend/wheels --platform manylinux_2_17_x86_64 --implementation cp --abi cp311 --python-version 311 --only-binary=:all:
```

Notas:
- O comando força o download de wheels manylinux compatíveis com Python 3.11 (cp311). Ajuste `--python-version`/`--abi` se você usar outra versão de Python.
- Não é recomendado commitar o conteúdo de `backend/wheels` ao repositório principal por causa do tamanho. Use um artefato externo (S3/Artifactory) ou gere localmente em CI antes do build quando possível.
- Se adicionar/alterar dependências em `requirements-prod.txt`, regenere o wheelhouse.

Como o Dockerfile usa as wheels
--------------------------------
- O `Dockerfile` copia `backend/wheels` para `/wheels` e instala via:
  python -m pip install --no-index --find-links=/wheels --no-deps -r requirements-prod.txt

Isso assume que todas as dependências e sub-dependências necessárias já foram baixadas para `backend/wheels`.

Se precisar, posso adicionar um pequeno script de CI para automatizar o download das wheels antes do build.
