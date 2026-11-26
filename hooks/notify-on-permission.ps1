# notify-on-permission.ps1 — Notification hook: reproduce un WAV cuando Claude
# pide permiso para una herramienta o el prompt input lleva idle > 60s.
#
# Opt-in personal. Lineamiento: tooling/notify-on-permission.md.
# Defaults: 1 chime fijo. Sin scaling, sin walk-back de transcript.
# Configurable en la sección notify.permission del config.json de la carpeta de datos de Neb
# (enabled, wav).
#
# Guard de subsesión interna del corrector (preprocess-prompt.py): si
# NEB_INTERNAL_SUBSESSION=1 (o el alias legacy CLAUDE_PREPROCESS_RECURSION=1),
# abandona sin sonar — evita chime fantasma. Ver hooks/lib/subsession.py.

$ErrorActionPreference = 'SilentlyContinue'

if ($env:NEB_INTERNAL_SUBSESSION -eq '1' -or $env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }

# --- Config efectiva --------------------------------------------------------

# Un solo resolvedor (lib\notify_sound.py) lee la sección notify.permission de config.json en la carpeta
# de datos de Neb y resuelve el WAV (presets, ruta absoluta, respaldo). Bajo el despachador del plugin
# llegan ya resueltos en NEB_NOTIFY_ENABLED y NEB_NOTIFY_WAV (esta marca que vienen de él); invocado
# directo (entradas de settings.json anteriores a 6.15.0) se le piden a su CLI `config`, en líneas
# llave=valor. Sin Python: encendido y el sonido de neb.
$cfg = @{
    enabled = 'true'
    wav     = ''
}

if ($env:NEB_NOTIFY_WAV) {
    $cfg.wav = $env:NEB_NOTIFY_WAV
    if ($env:NEB_NOTIFY_ENABLED) { $cfg.enabled = $env:NEB_NOTIFY_ENABLED }
} else {
    $resolver = Join-Path $PSScriptRoot 'lib\notify_sound.py'
    foreach ($py in @('py','python','python3')) {
        if (Get-Command $py -ErrorAction SilentlyContinue) {
            $prevEnc = [Console]::OutputEncoding
            [Console]::OutputEncoding = [Text.Encoding]::UTF8
            $env:PYTHONIOENCODING = 'utf-8'
            $out = @(& $py $resolver 'config' 'notify-on-permission' 2>$null)
            [Console]::OutputEncoding = $prevEnc
            # Un alias que no corre Python (el de la Microsoft Store) no imprime nada: se prueba el siguiente.
            if ($out.Count -eq 0) { continue }
            foreach ($line in $out) {
                $kv = "$line" -split '=', 2
                if ($kv.Count -eq 2 -and $cfg.ContainsKey($kv[0])) { $cfg[$kv[0]] = $kv[1].TrimEnd("`r") }
            }
            break
        }
    }
}

if ($cfg.enabled -ne 'true') { exit 0 }

$wav = $cfg.wav
if (-not $wav) { $wav = Join-Path $PSScriptRoot 'sounds\neb-chime.wav' }
if (-not (Test-Path -LiteralPath $wav)) { exit 0 }

# --- Player (1 chime async) -------------------------------------------------

# Literal de comillas simples: un apostrofo en la ruta (C:\Users\O'Neil, NEB_DATA) se duplica.
$wavLit = $wav -replace "'", "''"
$cmd = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$p = New-Object Media.SoundPlayer '$wavLit'
`$p.PlaySync()
"@
Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' `
    -ArgumentList @('-NoProfile','-NonInteractive','-Command',$cmd) | Out-Null

exit 0
