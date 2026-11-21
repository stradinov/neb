# logbook-sync.ps1 — Stop/SessionEnd/PreCompact hook (Windows): publica la entrada del work a la bitácora local.
# Declarar con "shell": "powershell" en settings.json — Claude Code envuelve en `powershell -NoProfile -Command`
# y propaga stdin (necesario porque el hook combina stdin + variables de entorno; ver hooks/README.md §Filosofía).
# Ver hooks/lib/logbook.py para la lógica. Defensivo: exit 0 siempre.
$ErrorActionPreference = "SilentlyContinue"

# Subsesión interna del corrector (preprocess-prompt.py): hook inerte — no escribir
# la subsesión Haiku a la bitácora. Ver hooks/lib/subsession.py.
if ($env:NEB_INTERNAL_SUBSESSION -eq '1' -or $env:CLAUDE_PREPROCESS_RECURSION -eq '1') { exit 0 }

$raw = [Console]::In.ReadToEnd()
try { $j = $raw | ConvertFrom-Json } catch { exit 0 }

$sid = $j.session_id
$cwd = $j.cwd
$tx  = $j.transcript_path
$ev  = $j.hook_event_name
# PowerShell 5.1 descarta un argumento vacío al invocar un nativo: logbook.py recibiría menos posicionales
# y los leería como un subcomando del CLI, con su respuesta en el stdout del hook.
if (-not $sid -or -not $cwd -or -not $tx -or -not $ev) { exit 0 }

$guide = if ($env:NEB_HOME) { $env:NEB_HOME } else { "$env:USERPROFILE\.claude\neb" }

$py = $null
foreach ($c in @("py", "python", "python3")) {
  if (Get-Command $c -ErrorAction SilentlyContinue) { $py = $c; break }
}
if (-not $py) { exit 0 }

try {
  & $py "$guide\hooks\lib\logbook.py" $sid $cwd $tx $ev $guide $env:USERPROFILE 2>$null | Out-Null
} catch {}

exit 0
