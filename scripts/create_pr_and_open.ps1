<#
Cria um Pull Request no GitHub para o branch atual e abre no navegador.

Uso: Execute na raiz do repositório. O script pedirá um GitHub PAT com scope `repo` caso não haja a variável de ambiente GITHUB_TOKEN.

Comportamento:
- tenta criar um PR (head = branch atual, base = main)
- se já existir um PR para esse head, buscará o PR aberto e abrirá a URL
#>

Set-StrictMode -Version Latest

$owner = 'heryssrique'
$repo  = 'Agendamento-de-exames-demissionais'

# Detecta branch atual
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
if (-not $branch) {
    Write-Error "Não foi possível detectar o branch atual. Rode a partir de um repositório git."; exit 1
}

Write-Host "Criando PR para branch: $branch"

# Token
if ($env:GITHUB_TOKEN) {
    $token = $env:GITHUB_TOKEN
} else {
    $secure = Read-Host -AsSecureString "Entre com seu GitHub PAT (scope: repo)"
    $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}

$headers = @{ Authorization = "token $token"; Accept = 'application/vnd.github+json'; 'User-Agent' = 'create-pr-script' }

# Body: usar o CHANGELOG.md como corpo se existir
if (Test-Path CHANGELOG.md) {
    $bodyText = Get-Content -Raw CHANGELOG.md
} else {
    $bodyText = "Automated PR created by script"
}

$payload = @{ title = "docs: add CHANGELOG + wheelhouse instructions (2025-10-18)"; head = $branch; base = 'main'; body = $bodyText } | ConvertTo-Json -Depth 10

$createUri = "https://api.github.com/repos/$owner/$repo/pulls"

# Tentativa de criação do PR
try {
    $resp = Invoke-RestMethod -Uri $createUri -Method Post -Headers $headers -Body $payload -ContentType 'application/json' -ErrorAction Stop
    Write-Host "PR criado: $($resp.html_url)"
    Start-Process $resp.html_url
    exit 0
} catch {
    Write-Warning "Não foi possível criar PR (talvez já exista). Tentando localizar PR existente...";
}

# Buscar PRs abertos para este head
$queryUri = "https://api.github.com/repos/$owner/$repo/pulls?head=$owner`:$branch&state=open"
try {
    $prs = Invoke-RestMethod -Uri $queryUri -Headers $headers -Method Get -ErrorAction Stop
    if ($prs -and $prs.Count -gt 0) {
        $pr = $prs[0]
        Write-Host "PR existente encontrado: $($pr.html_url)"
        Start-Process $pr.html_url
        exit 0
    } else {
        Write-Error "Nenhum PR encontrado para head $owner:$branch e criação falhou. Verifique permissões e tente manualmente."; exit 1
    }
} catch {
    Write-Error "Erro ao buscar PRs: $_"; exit 1
}
