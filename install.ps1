# Install or update the Higgsfield skill for Claude Code (default) or Codex (-Codex).
param([switch]$Codex)
$ErrorActionPreference = "Stop"
$repo = "https://github.com/Koushik890/higgsfield-skill.git"
if ($Codex) {
    $base = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME ".codex" }
    $dest = Join-Path $base "skills\higgsfield"
} else {
    $dest = Join-Path $HOME ".claude\skills\higgsfield"
}

if (Test-Path (Join-Path $dest ".git")) {
    git -C $dest pull --ff-only
} else {
    New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
    git clone $repo $dest
}

$conf = Join-Path $HOME ".config\higgsfield\.env"
if (-not (Test-Path $conf)) {
    New-Item -ItemType Directory -Force (Split-Path $conf) | Out-Null
    Copy-Item (Join-Path $dest ".env.example") $conf
    Write-Host "Created $conf - add your API key there."
}
Write-Host "Installed to $dest. Start a new agent session to use it."
