#!/usr/bin/env python3
"""assemble-startup.py — Ensambla el arranque de Neb resolviendo @import inline.

Toma un archivo markdown raiz (tipicamente general/startup.md) y produce UN solo
texto con todos sus @import resueltos en linea. Reescribe los links markdown
relativos (`[txt](algo.md)`) a paths ABSOLUTOS basados en la ubicacion real del
archivo, para que el contexto inyectado por el hook SessionStart conserve enlaces
navegables on-demand (el resto de la metodologia se lee con Read bajo demanda).
Con --relative-to <raiz> (o rel_root en assemble) los escribe RELATIVOS a esa raiz
(`process/delivery.md`): quien inyecta el texto anuncia la raiz una sola vez. Un
destino fuera de la raiz conserva su path absoluto.

Uso:
    python3 assemble-startup.py <archivo-raiz>
    py assemble-startup.py <archivo-raiz>          (Windows)
    python3 assemble-startup.py --check <archivo-raiz>
    python3 assemble-startup.py --relative-to <raiz> <archivo-raiz>

Salida: el arranque ensamblado a stdout. Pure Python (stdlib).
Guards: profundidad maxima de imports (4 hops, como Claude Code) y deteccion de ciclos.
Defensivo (modo normal): un archivo ilegible o un import faltante se reemplaza por un
comentario, nunca aborta (el arranque debe emitirse siempre que sea posible).
Estricto (--check): recorre la cadena de imports y sale con exit 1 listando los
imports faltantes/ilegibles — para el gate pre-push del maintainer, que NO debe
publicar un kernel degradado aunque el runtime lo tolere.
"""
import os
import re
import sys

MAX_DEPTH = 4
# Una directiva @import es una linea cuyo unico contenido es @<path> (sin backticks ni texto).
IMPORT_RE = re.compile(r'^@(\S+)$')
# Link markdown: captura el destino entre ']( ' y ')'.
LINK_RE = re.compile(r'(\]\()([^)\s]+)(\))')


def _is_relative_md(dest):
    """True si el destino es un link relativo a un .md (candidato a reescribir)."""
    if dest.startswith(('http://', 'https://', '#', '/', '~', '<', 'mailto:')):
        return False
    return '.md' in dest


def _under_root(abspath, rel_root):
    """Path de abspath relativo a rel_root (POSIX-style), o None si queda fuera de la raiz."""
    try:
        rel = os.path.relpath(abspath, rel_root)
    except ValueError:  # otra unidad en Windows
        return None
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        return None
    return rel.replace(os.sep, '/')


def _rewrite_links(line, file_dir, rel_root=None):
    """Reescribe links relativos a .md como paths absolutos (POSIX-style) o, con rel_root, relativos a esa raiz."""
    def repl(m):
        dest = m.group(2)
        if not _is_relative_md(dest):
            return m.group(0)
        path_part, sep, anchor = dest.partition('#')
        abspath = os.path.normpath(os.path.join(file_dir, path_part))
        rel = _under_root(abspath, rel_root) if rel_root else None
        abspath = rel if rel is not None else abspath.replace('\\', '/')
        return m.group(1) + abspath + (sep + anchor if sep else '') + m.group(3)
    return LINK_RE.sub(repl, line)


def assemble(path, depth, seen, rel_root=None):
    path = os.path.normpath(os.path.abspath(path))
    if rel_root:
        rel_root = os.path.normpath(os.path.abspath(rel_root))
    if depth > MAX_DEPTH:
        return "<!-- assemble-startup: profundidad maxima ({}) excedida -->\n".format(MAX_DEPTH)
    if path in seen:
        return "<!-- assemble-startup: ciclo evitado ({}) -->\n".format(os.path.basename(path))
    seen = seen | {path}
    try:
        with open(path, encoding='utf-8') as fh:
            lines = fh.readlines()
    except OSError as exc:
        return "<!-- assemble-startup: no se pudo leer {}: {} -->\n".format(path, exc)
    file_dir = os.path.dirname(path)
    out = []
    for line in lines:
        m = IMPORT_RE.match(line.strip())
        if m:
            imp_path = os.path.join(file_dir, m.group(1))
            out.append(assemble(imp_path, depth + 1, seen, rel_root))
        else:
            out.append(_rewrite_links(line, file_dir, rel_root))
    return ''.join(out)


def collect_errors(path, depth, seen, errors):
    """Modo --check: recorre la cadena de imports acumulando faltantes/ilegibles."""
    path = os.path.normpath(os.path.abspath(path))
    if depth > MAX_DEPTH:
        errors.append("profundidad maxima ({}) excedida en {}".format(MAX_DEPTH, path))
        return
    if path in seen:
        return
    seen.add(path)
    try:
        with open(path, encoding='utf-8') as fh:
            lines = fh.readlines()
    except OSError as exc:
        errors.append("import faltante o ilegible: {} ({})".format(path, exc))
        return
    file_dir = os.path.dirname(path)
    for line in lines:
        m = IMPORT_RE.match(line.strip())
        if m:
            collect_errors(os.path.join(file_dir, m.group(1)), depth + 1, seen, errors)


def main():
    # En Windows el stdout por defecto es cp1252 y el arranque tiene Unicode (≥, ─, etc.).
    # Forzar UTF-8 evita UnicodeEncodeError (relevante tambien cuando lo invoca el hook).
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
    argv = sys.argv[1:]
    rel_root = None
    if '--relative-to' in argv:
        i = argv.index('--relative-to')
        rel_root = argv[i + 1] if i + 1 < len(argv) else ''
        argv = argv[:i] + argv[i + 2:] if rel_root and not rel_root.startswith('--') else []
    args = [a for a in argv if a != '--check']
    check_mode = '--check' in argv
    if not args:
        sys.stderr.write("Uso: assemble-startup.py [--check] [--relative-to <raiz>] <archivo-raiz>\n")
        sys.exit(1)
    if check_mode:
        errors = []
        collect_errors(args[0], 0, set(), errors)
        if errors:
            for e in errors:
                sys.stderr.write("[assemble-startup --check] {}\n".format(e))
            sys.exit(1)
        sys.stdout.write("assemble-startup --check: cadena de imports integra\n")
        return
    sys.stdout.write(assemble(args[0], 0, frozenset(), rel_root))


if __name__ == '__main__':
    main()
