# notify-on-permission.ps1 — Notification hook: reproduce un WAV cuando Claude
# pide permiso para una herramienta o el prompt input lleva idle > 60s.
#
# Opt-in personal. Lineamiento: tooling/notify-on-permission.md.
# Defaults: 1 chime fijo. Sin scaling, sin walk-back de transcript.
# Configurable en ~/.claude/notify-on-permission.json (enabled, wav).
#
# Guard de subsesión interna del corrector (preprocess-prompt.py): si
# NEB_INTERNAL_SUBSESSION=1 (o el alias legacy CLAUDE_PREPROCESS_RECURSION=1),
# abandona sin sonar — evita chime fantasma. Ver hooks/lib/subsession.py.

$ErrorActionPreference = 'SilentlyContinue'

if ($env:NEB_INTERNAL_SUBSESSION -eq '1' -or $env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }

# --- Defaults ---------------------------------------------------------------

$cfg = @{
    enabled = $true
}

# --- Cargar config personal -------------------------------------------------

$cfgPath = Join-Path $env:USERPROFILE '.claude\notify-on-permission.json'
if (Test-Path -LiteralPath $cfgPath) {
    try {
        $user = Get-Content -LiteralPath $cfgPath -Raw -Encoding utf8 | ConvertFrom-Json
        foreach ($key in @('enabled')) {
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

# Un solo resolvedor (lib\notify_sound.py): presets, ruta absoluta y respaldo. Bajo el
# despachador del plugin llega resuelto en NEB_NOTIFY_WAV; invocado directo (entradas de
# settings.json anteriores a 6.15.0) se le pregunta a su CLI. Sin Python, el sonido de neb.
$wav = $env:NEB_NOTIFY_WAV
if (-not $wav) {
    $resolver = Join-Path $PSScriptRoot 'lib\notify_sound.py'
    foreach ($py in @('py','python','python3')) {
        if (Get-Command $py -ErrorAction SilentlyContinue) {
            $prevEnc = [Console]::OutputEncoding
            [Console]::OutputEncoding = [Text.Encoding]::UTF8
            $env:PYTHONIOENCODING = 'utf-8'
            $wav = & $py $resolver 'notify-on-permission' 2>$null | Select-Object -First 1
            [Console]::OutputEncoding = $prevEnc
            # 3 = el dev apagó el hook en su JSON (criterio del resolvedor, también "enabled": "false").
            if ($LASTEXITCODE -eq 3) { exit 0 }
            # Un alias que no corre Python (el de la Microsoft Store) no imprime nada: se prueba el siguiente.
            if ($wav) { break }
        }
    }
}
if (-not $wav) { $wav = Join-Path $PSScriptRoot 'sounds\neb-chime.wav' }
if (-not (Test-Path -LiteralPath $wav)) { exit 0 }

# --- Player (1 chime async) -------------------------------------------------

$cmd = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$p = New-Object Media.SoundPlayer '$wav'
`$p.PlaySync()
"@
Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' `
    -ArgumentList @('-NoProfile','-NonInteractive','-Command',$cmd) | Out-Null

exit 0
