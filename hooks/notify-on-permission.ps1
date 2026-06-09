# notify-on-permission.ps1 — Notification hook: reproduce un WAV cuando Claude
# pide permiso para una herramienta o el prompt input lleva idle > 60s.
#
# Opt-in personal. Lineamiento: tooling/notify-on-permission.md.
# Defaults: 1 chime fijo. Sin scaling, sin walk-back de transcript.
# Configurable en ~/.claude/notify-on-permission.json (enabled, wav).
#
# Recursion guard: si CLAUDE_PREPROCESS_RECURSION=1 (subproceso `claude -p` del
# preprocess-prompt.py), abandona sin sonar — evita chime fantasma.

$ErrorActionPreference = 'SilentlyContinue'

if ($env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }

# --- Defaults ---------------------------------------------------------------

$cfg = @{
    enabled = $true
    wav     = $null
}

# --- Cargar config personal -------------------------------------------------

$cfgPath = Join-Path $env:USERPROFILE '.claude\notify-on-permission.json'
if (Test-Path -LiteralPath $cfgPath) {
    try {
        $user = Get-Content -LiteralPath $cfgPath -Raw -Encoding utf8 | ConvertFrom-Json
        foreach ($key in @('enabled','wav')) {
            if ($user.PSObject.Properties.Name -contains $key) {
                $cfg[$key] = $user.$key
            }
        }
    } catch {
        [Console]::Error.WriteLine("[notify-on-permission] config ilegible, usando defaults: $_")
    }
}

if (-not $cfg.enabled) { exit 0 }

# --- Resolver WAV -----------------------------------------------------------

# personal/ vive en el workspace de gobernanza (NEB_WORKSPACE), no en el checkout de neb
$nebHome = if ($env:NEB_WORKSPACE) { $env:NEB_WORKSPACE } else { $env:NEB_HOME }
$wav = $cfg.wav
if (-not $wav) {
    $wav = Join-Path $nebHome 'personal\chimes-loud.wav'
}
if (-not (Test-Path -LiteralPath $wav)) {
    $fallback = Join-Path $nebHome 'personal\chimes-loud.wav'
    if ($cfg.wav -and (Test-Path -LiteralPath $fallback)) {
        [Console]::Error.WriteLine("[notify-on-permission] wav '$($cfg.wav)' no existe; usando default '$fallback'")
        $wav = $fallback
    } else {
        exit 0
    }
}

# --- Player (1 chime async) -------------------------------------------------

$cmd = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$p = New-Object Media.SoundPlayer '$wav'
`$p.PlaySync()
"@
Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' `
    -ArgumentList @('-NoProfile','-NonInteractive','-Command',$cmd) | Out-Null

exit 0
