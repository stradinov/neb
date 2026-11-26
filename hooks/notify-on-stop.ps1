# notify-on-stop.ps1 — Stop hook: reproduce un WAV al cerrar cada turno de Claude.
#
# Opt-in personal. Lineamiento: tooling/notify-on-stop.md.
# Defaults: 1 chime + 1 por cada minuto del turno (max 5), skip si < 10s.
# Configurable en la sección notify.stop del config.json de la carpeta de datos de Neb
# (enabled, wav, min_seconds, max_chimes, scaling).
#
# Guard de subsesión interna del corrector (preprocess-prompt.py): si
# NEB_INTERNAL_SUBSESSION=1 (o el alias legacy CLAUDE_PREPROCESS_RECURSION=1),
# abandona sin sonar — evita chime fantasma. Ver hooks/lib/subsession.py.

$ErrorActionPreference = 'SilentlyContinue'

if ($env:NEB_INTERNAL_SUBSESSION -eq '1' -or $env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }

# --- Config efectiva --------------------------------------------------------

# Un solo resolvedor (lib\notify_sound.py) lee la sección notify.stop de config.json en la carpeta de
# datos de Neb, normaliza los valores y resuelve el WAV (presets, ruta absoluta, respaldo). Bajo el
# despachador del plugin llegan ya resueltos en variables NEB_NOTIFY_* (NEB_NOTIFY_WAV marca que vienen
# de él); invocado directo (entradas de settings.json anteriores a 6.15.0) se le piden a su CLI
# `config`, en líneas llave=valor. Sin Python: valores por defecto y el sonido de neb.
$cfg = @{
    enabled     = 'true'
    wav         = ''
    min_seconds = '10'
    max_chimes  = '5'
    scaling     = 'per-minute'
}

if ($env:NEB_NOTIFY_WAV) {
    $cfg.wav = $env:NEB_NOTIFY_WAV
    if ($env:NEB_NOTIFY_ENABLED)     { $cfg.enabled     = $env:NEB_NOTIFY_ENABLED }
    if ($env:NEB_NOTIFY_MIN_SECONDS) { $cfg.min_seconds = $env:NEB_NOTIFY_MIN_SECONDS }
    if ($env:NEB_NOTIFY_MAX_CHIMES)  { $cfg.max_chimes  = $env:NEB_NOTIFY_MAX_CHIMES }
    if ($env:NEB_NOTIFY_SCALING)     { $cfg.scaling     = $env:NEB_NOTIFY_SCALING }
} else {
    $resolver = Join-Path $PSScriptRoot 'lib\notify_sound.py'
    foreach ($py in @('py','python','python3')) {
        if (Get-Command $py -ErrorAction SilentlyContinue) {
            $prevEnc = [Console]::OutputEncoding
            [Console]::OutputEncoding = [Text.Encoding]::UTF8
            $env:PYTHONIOENCODING = 'utf-8'
            $out = @(& $py $resolver 'config' 'notify-on-stop' 2>$null)
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

# Normalización (red de seguridad: notify_sound.py ya entrega los valores normalizados)
$minSeconds = 10
$maxChimes = 5
try { $minSeconds = [int]$cfg.min_seconds } catch {}
try { $maxChimes = [int]$cfg.max_chimes } catch {}
if ($minSeconds -lt 0) { $minSeconds = 0 }
if ($maxChimes -lt 1)  { $maxChimes  = 1 }
if ($maxChimes -gt 20) { $maxChimes  = 20 }
$scaling = $cfg.scaling
if ($scaling -ne 'fixed' -and $scaling -ne 'per-minute') { $scaling = 'per-minute' }

$wav = $cfg.wav
if (-not $wav) { $wav = Join-Path $PSScriptRoot 'sounds\neb-chime.wav' }
if (-not (Test-Path -LiteralPath $wav)) { exit 0 }

# --- Player -----------------------------------------------------------------

function Play-Chimes([int]$times, [int]$maxTimes) {
    if ($times -lt 1) { $times = 1 }
    if ($times -gt $maxTimes) { $times = $maxTimes }
    # Literal de comillas simples: un apostrofo en la ruta (C:\Users\O'Neil, NEB_DATA) se duplica.
    $wavLit = $wav -replace "'", "''"
    $cmd = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$p = New-Object Media.SoundPlayer '$wavLit'
for (`$i = 0; `$i -lt $times; `$i++) {
    `$p.PlaySync()
    Start-Sleep -Milliseconds 200
}
"@
    Start-Process -WindowStyle Hidden -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile','-NonInteractive','-Command',$cmd) | Out-Null
}

# --- Leer hook event JSON ---------------------------------------------------

$raw = [Console]::In.ReadToEnd()
$hook = $null
try { $hook = $raw | ConvertFrom-Json } catch { Play-Chimes 1 $maxChimes; exit 0 }

$transcript = $hook.transcript_path
if (-not $transcript -or -not (Test-Path -LiteralPath $transcript)) {
    Play-Chimes 1 $maxChimes; exit 0
}

# --- Walk-back al último user message no-toolUseResult ----------------------

$lines = Get-Content -LiteralPath $transcript -Encoding utf8
$boundaryTime = $null
for ($i = $lines.Count - 1; $i -ge 0; $i--) {
    $rec = $null
    try { $rec = $lines[$i] | ConvertFrom-Json } catch { continue }
    if ($rec.type -eq 'user' -and $null -eq $rec.toolUseResult) {
        try { $boundaryTime = [datetime]$rec.timestamp } catch {}
        break
    }
}

if (-not $boundaryTime) { Play-Chimes 1 $maxChimes; exit 0 }

# --- Duración + scaling -----------------------------------------------------

$durationSec = [math]::Floor(((Get-Date).ToUniversalTime() - $boundaryTime.ToUniversalTime()).TotalSeconds)
if ($durationSec -lt $minSeconds) { exit 0 }

if ($scaling -eq 'fixed') {
    $n = 1
} else {
    $n = 1 + [math]::Floor($durationSec / 60)
}

Play-Chimes $n $maxChimes
exit 0
