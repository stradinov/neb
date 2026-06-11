#!/usr/bin/env python3
"""neb-bootstrap-context.py — Orquestador del hook SessionStart del plugin neb.

Emite a stdout el contexto de arranque que Claude Code inyecta al inicio de cada
sesion: (1) el arranque del framework (neb) ensamblado, (2) el arranque del overlay
del adoptante si existe, (3) su configuracion personal. El stdout se vuelve
additionalContext de la sesion.

Variables de entorno (provistas por Claude Code / el usuario):
  NEB_HOME                     working copy de neb (prioridad — permite editar y usar a la vez, D4).
  CLAUDE_PLUGIN_ROOT           raiz del plugin instalado (fallback si no hay NEB_HOME).
  NEB_WORKSPACE                workspace del adoptante (overlay/ + personal/ + changes/).
  CLAUDE_PLUGIN_OPTION_USERNAME nombre de usuario (de userConfig) para personal/<username>.md.

Defensivo: si algo falta, emite lo que pueda + una guia a /wakeup; nunca aborta.
"""
import os
import re
import sys
import importlib.util


def _utf8_stdout():
    # En Windows el stdout por defecto es cp1252; el arranque tiene Unicode.
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass


def _load_assembler(bootstrap_dir):
    path = os.path.join(bootstrap_dir, 'assemble-startup.py')
    spec = importlib.util.spec_from_file_location('neb_assemble_startup', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _project_opts_out():
    """True si el CLAUDE.md del proyecto activo declara el marcador <!-- neb: skip -->.

    El proyecto opta por NO recibir la inyeccion del arranque de Neb. Defensivo: si no hay
    CLAUDE_PROJECT_DIR o no hay CLAUDE.md legible, devuelve False (comportamiento normal).
    """
    proj = os.environ.get('CLAUDE_PROJECT_DIR')
    if not proj:
        return False
    try:
        with open(os.path.join(proj, 'CLAUDE.md'), encoding='utf-8') as f:
            content = f.read()
    except OSError:
        return False
    return re.search(r'<!--\s*neb:\s*skip\s*-->', content) is not None


def main():
    _utf8_stdout()

    # neb: skip — si el proyecto activo lo declara en su CLAUDE.md, no inyectar nada (D2).
    if _project_opts_out():
        return

    bootstrap_dir = os.path.dirname(os.path.abspath(__file__))

    # NEB_HOME (working copy editable) tiene prioridad sobre el cache del plugin (D4).
    neb_home = os.environ.get('NEB_HOME') or os.environ.get('CLAUDE_PLUGIN_ROOT') \
        or os.path.dirname(bootstrap_dir)
    neb_home = os.path.abspath(neb_home)

    try:
        asm = _load_assembler(bootstrap_dir)
    except Exception as exc:  # noqa: BLE001 — el hook no debe romper la sesion
        sys.stdout.write("<!-- neb-bootstrap-context: no se pudo cargar el ensamblador: %s -->\n" % exc)
        return

    out = []
    out.append(
        "# Arranque de Neb (inyectado por el plugin)\n\n"
        "Lo que sigue son las instrucciones operativas de la metodologia Neb. Aplican "
        "desde el primer prompt de esta sesion y tienen prioridad, igual que un CLAUDE.md "
        "de proyecto. La metodologia completa vive en NEB_HOME (`%s`); los links apuntan a "
        "rutas absolutas — leelos con Read on-demand cuando necesites una seccion.\n"
        % neb_home
    )
    out.append(asm.assemble(os.path.join(neb_home, 'general', 'startup.md'), 0, frozenset()))

    ws = os.environ.get('NEB_WORKSPACE')
    if ws and os.path.isdir(ws):
        # Overlay del adoptante (D1): <workspace>/overlay/startup.md, o el primer dir con
        # overlays/detect-profile.local.sh (mismo patron de descubrimiento que setup-workspace.sh).
        candidates = [os.path.join(ws, 'overlay', 'startup.md')]
        try:
            for entry in sorted(os.listdir(ws)):
                marker = os.path.join(ws, entry, 'overlays', 'detect-profile.local.sh')
                if os.path.isfile(marker):
                    candidates.append(os.path.join(ws, entry, 'startup.md'))
        except OSError:
            pass
        for ov in candidates:
            if os.path.isfile(ov):
                out.append("\n\n---\n\n# Overlay del adoptante (inyectado por el plugin)\n")
                out.append(asm.assemble(ov, 0, frozenset()))
                break

        user = (os.environ.get('CLAUDE_PLUGIN_OPTION_USERNAME')
                or os.environ.get('USER') or os.environ.get('USERNAME'))
        if user:
            personal = os.path.join(ws, 'personal', user + '.md')
            if os.path.isfile(personal):
                out.append("\n\n---\n\n# Configuracion personal (inyectada por el plugin)\n")
                out.append(asm.assemble(personal, 0, frozenset()))
    else:
        out.append(
            "\n\n---\n\n> No hay `NEB_WORKSPACE` configurado todavia. Corre `/wakeup` para crear "
            "tu workspace (overlay + personal + changes) y conectarlo.\n"
        )

    sys.stdout.write(''.join(out))


if __name__ == '__main__':
    main()
