# notify-on-stop.ps1 — Stop hook: reproduce un WAV al cerrar cada turno de Claude.
#
# Opt-in personal. Lineamiento: tooling/notify-on-stop.md.
# Defaults: 1 chime + 1 por cada minuto del turno (max 5), skip si < 10s.
# Configurable en ~/.claude/notify-on-stop.json (enabled, wav, min_seconds, max_chimes, scaling).
#
# Recursion guard: si CLAUDE_PREPROCESS_RECURSION=1 (subproceso `claude -p` del
# preprocess-prompt.py), abandona sin sonar — evita chime fantasma.

$ErrorActionPreference = 'SilentlyContinue'

if ($env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }

# --- Defaults ---------------------------------------------------------------

$cfg = @{
    enabled     = $true
    wav         = $null
    min_seconds = 10
    max_chimes  = 5
    scaling     = 'per-minute'
}

# --- Cargar config personal -------------------------------------------------

$cfgPath = Join-Path $env:USERPROFILE '.claude\notify-on-stop.json'
if (Test-Path -LiteralPath $cfgPath) {
    try {
        $user = Get-Content -LiteralPath $cfgPath -Raw -Encoding utf8 | ConvertFrom-Json
        foreach ($key in @('enabled','wav','min_seconds','max_chimes','scaling')) {
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

# personal/ vive en el workspace de gobernanza (NEB_WORKSPACE), no en el checkout de neb
$nebHome = if ($env:NEB_WORKSPACE) { $env:NEB_WORKSPACE } else { $env:NEB_HOME }
$wav = $cfg.wav
if (-not $wav) {
    $wav = Join-Path $nebHome 'personal\chimes-loud.wav'
}
if (-not (Test-Path -LiteralPath $wav)) {
    $fallback = Join-Path $nebHome 'personal\chimes-loud.wav'
    if ($cfg.wav -and (Test-Path -LiteralPath $fallback)) {
        [Console]::Error.WriteLine("[notify-on-stop] wav '$($cfg.wav)' no existe; usando default '$fallback'")
        $wav = $fallback
    } else {
        exit 0
    }
}

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
