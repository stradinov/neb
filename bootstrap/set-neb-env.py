#!/usr/bin/env python3
"""set-neb-env.py — Setea variables de entorno de Neb en ~/.claude/settings.json (campo `env`).

Merge NO destructivo: preserva el resto del settings, hace backup `.bak`, escritura atomica.
Cross-platform (Python; evita el problema de archivos de texto en Windows). Usado por
setup-workspace.sh / wakeup para conectar el workspace (NEB_WORKSPACE) sin que el usuario
edite settings.json a mano.

Uso:
    python set-neb-env.py NEB_WORKSPACE=/ruta [NEB_HOME=/ruta ...] [--settings <path>]

Defensivo: settings.json ilegible -> aborta sin tocar (exit 1). Sin cambios -> no reescribe.
"""
import json
import os
import sys
import tempfile
import shutil


def main():
    args = sys.argv[1:]
    settings = os.path.join(os.path.expanduser('~'), '.claude', 'settings.json')
    pairs = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--settings':
            settings = args[i + 1]
            i += 2
            continue
        if '=' in a:
            k, _, v = a.partition('=')
            pairs[k] = v
        i += 1

    if not pairs:
        sys.stderr.write("Uso: set-neb-env.py KEY=VALUE ... [--settings <path>]\n")
        sys.exit(1)

    data = {}
    existed = os.path.isfile(settings)
    if existed:
        try:
            with open(settings, encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            sys.stderr.write("settings.json ilegible (%s); abortando sin tocar.\n" % exc)
            sys.exit(1)
        if not isinstance(data, dict):
            sys.stderr.write("settings.json no es un objeto JSON; abortando.\n")
            sys.exit(1)

    env = data.setdefault('env', {})
    if not isinstance(env, dict):
        sys.stderr.write("settings.json: 'env' no es un objeto; abortando.\n")
        sys.exit(1)

    changed = False
    for key, val in pairs.items():
        if env.get(key) != val:
            env[key] = val
            changed = True

    if not changed:
        sys.stdout.write("settings.json: valores ya correctos, sin cambios.\n")
        return

    os.makedirs(os.path.dirname(settings) or '.', exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(settings) or '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
        os.replace(tmp, settings)
    except OSError as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        sys.stderr.write("No se pudo escribir settings.json (%s).\n" % exc)
        sys.exit(1)
    sys.stdout.write("settings.json actualizado: %s\n" % ', '.join('%s=%s' % kv for kv in pairs.items()))


if __name__ == '__main__':
    main()
