# notify-on-stop.ps1 — Stop hook: reproduce un WAV al cerrar cada turno de Claude.
#
# Opt-in personal. Lineamiento: tooling/notify-on-stop.md.
# Defaults: 1 chime + 1 por cada minuto del turno (max 5), skip si < 10s.
# Configurable en ~/.claude/notify-on-stop.json (enabled, wav, min_seconds, max_chimes, scaling).
#
# Guard de subsesión interna del corrector (preprocess-prompt.py): si
# NEB_INTERNAL_SUBSESSION=1 (o el alias legacy CLAUDE_PREPROCESS_RECURSION=1),
# abandona sin sonar — evita chime fantasma. Ver hooks/lib/subsession.py.

$ErrorActionPreference = 'SilentlyContinue'

if ($env:NEB_INTERNAL_SUBSESSION -eq '1' -or $env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }

# --- Defaults ---------------------------------------------------------------

$cfg = @{
    enabled     = $true
    min_seconds = 10
    max_chimes  = 5
    scaling     = 'per-minute'
}

# --- Cargar config personal -------------------------------------------------

$cfgPath = Join-Path $env:USERPROFILE '.claude\notify-on-stop.json'
if (Test-Path -LiteralPath $cfgPath) {
    try {
        $user = Get-Content -LiteralPath $cfgPath -Raw -Encoding utf8 | ConvertFrom-Json
        foreach ($key in @('enabled','min_seconds','max_chimes','scaling')) {
            if ($user.PSObject.Properties.Name -contains $key) {
                $cfg[$key] = $user.$key
            }
        }
    } catch {
        [Console]::Error.WriteLine("[notify-on-stop] config ilegible, usando defaults: $_")
    }
}

if (-not $cfg.enabled) { exit 0 }

# Normalización
if ($cfg.min_seconds -lt 0) { $cfg.min_seconds = 0 }
if ($cfg.max_chimes -lt 1)  { $cfg.max_chimes  = 1 }
if ($cfg.max_chimes -gt 20) { $cfg.max_chimes  = 20 }
if ($cfg.scaling -ne 'fixed' -and $cfg.scaling -ne 'per-minute') {
    $cfg.scaling = 'per-minute'
}

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
            $wav = & $py $resolver 'notify-on-stop' 2>$null | Select-Object -First 1
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

# --- Player -----------------------------------------------------------------

function Play-Chimes([int]$times, [int]$maxTimes) {
    if ($times -lt 1) { $times = 1 }
    if ($times -gt $maxTimes) { $times = $maxTimes }
    $cmd = @"
`$ErrorActionPreference = 'SilentlyContinue'
`$p = New-Object Media.SoundPlayer '$wav'
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
try { $hook = $raw | ConvertFrom-Json } catch { Play-Chimes 1 $cfg.max_chimes; exit 0 }

$transcript = $hook.transcript_path
if (-not $transcript -or -not (Test-Path -LiteralPath $transcript)) {
    Play-Chimes 1 $cfg.max_chimes; exit 0
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

if (-not $boundaryTime) { Play-Chimes 1 $cfg.max_chimes; exit 0 }

# --- Duración + scaling -----------------------------------------------------

$durationSec = [math]::Floor(((Get-Date).ToUniversalTime() - $boundaryTime.ToUniversalTime()).TotalSeconds)
if ($durationSec -lt $cfg.min_seconds) { exit 0 }

if ($cfg.scaling -eq 'fixed') {
    $n = 1
} else {
    $n = 1 + [math]::Floor($durationSec / 60)
}

Play-Chimes $n $cfg.max_chimes
exit 0
