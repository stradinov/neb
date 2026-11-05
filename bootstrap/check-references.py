#!/usr/bin/env python3
"""Verifica enlaces relativos, anclas y citas de sección en los .md de neb y del overlay.

Uso: py bootstrap/check-references.py [--overlay <dir>]... [--no-overlay]
                                      [--save-baseline <f>] [--baseline <f>]

Recorre los .md versionados (git ls-files) de neb y de cada overlay del adoptante. Sin
--overlay, el overlay se descubre como en el hook SessionStart: cada <dir> de NEB_WORKSPACE
con overlays/detect-profile.local.sh. Fuentes excluidas: CHANGELOG.md, changelog.d/ y
*.template (sus enlaces son relativos al lugar donde se instancian); las plantillas sí
cuentan como destino. Se ignoran los bloques cercados y el código en línea.

Qué se verifica:
- [t](ruta) relativo: la ruta existe; con #ancla, el ancla es el slug de un encabezado.
- Cita de sección: § "T", §"T", § «T», sección "T" y [t](ruta) "T". El título casa con un
  encabezado o con una etiqueta en negrita al inicio de línea (igual, prefijo seguido de
  separador, citado dentro del encabezado o tras «: »), sin distinguir mayúsculas,
  backticks ni numeración.
- Archivo de la cita: el enlace o la ruta .md (en código o suelta) adyacente, con «del repo»,
  «en el repo `x`» o «(repo x)» de por medio; el que sigue (§ "T" de/en <ruta>); el de
  «su § "T"»; el de la cita previa encadenada (§ "A" y § "B"); el del final de la línea
  anterior si la línea abre con la cita; los .md de profiles/x/ con «profile `x`». Una «§»
  sin archivo nombrado se verifica contra el propio archivo («§ sin archivo»); «sección "T"»
  sin archivo no se verifica (suele nombrar una sección genérica del change MD).
- Una ruta se resuelve contra el directorio del archivo y sus ancestros hasta la raíz del
  repo, la raíz de neb y, si no, por sufijo único entre los archivos recorridos. Si no se
  localiza (otro repo, memoria, ruta ambigua), sale como «aviso» y no cuenta.

- @import en línea propia (@ruta.md): la ruta existe (relativa al archivo; @~/ no se verifica).

No verifica citas sin comillas (§ Contexto) ni la línea de una cita con número
(`archivo.md:46` solo verifica el archivo).

Salida: una línea por roto, <repo>:<archivo>:<línea> TAB <tipo> TAB <destino> TAB <título>.
--save-baseline guarda las claves (sin número de línea) de los rotos actuales; --baseline
reporta solo los que exceden el conteo de su clave en la base. Exit 0 sin rotos (nuevos),
1 con rotos, 2 error de uso.
"""
import argparse
import collections
import os
import re
import subprocess
import sys

LINK = re.compile(r"\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
IMPORT = re.compile(r"^\s*@([^\s`]+\.md)\s*$")
SECTION = re.compile(r'(?:§|\bsecci[oó]n)\s*(?:"([^"]+)"|«([^»]+)»|“([^”]+)”)'
                     r'|(?<=\)) (?:"([^"]+)"|«([^»]+)»)')
CODE = re.compile(r"(`+)(.+?)\1")
MDPATH = re.compile(r"^[\w./~<>-]*\.md(?:\.template)?(?::\d+(?:-\d+)?)?$")
BARE_MD = re.compile(r"(?<![\w`/.\-\[(])((?:[\w.-]+/)*[\w-]+\.md)\b(?!`)")
BOLD = re.compile(r"^\s*(?:[-*]|\d+\.)?\s*\*\*([^*]+?)\*\*")
FENCE = re.compile(r"^\s*(```|~~~)")
ADJACENT = re.compile(r"[\s()\]*_,]*"
                      r"|[\s(]*(?:del repo|en el repo `?\w+`?|\(repo `?\w+`?\))[\s,(]*")
FOLLOWING = re.compile(r"[\s,]*(?:de|del|en)\s+(?:el\s+|la\s+)?")
CHAINED = re.compile(r"[\s,]*(?:y|o|e|›|>)?[\s,]*")
PROFILE = re.compile(r"profile `([\w-]+)`")

SKIP = "skip"
_headings = {}
SUFFIXES = collections.defaultdict(list)
ROOTS = []  # (raíz del repo, subdirectorio recorrido o None)


def git_files(root, *patterns):
    out = subprocess.run(["git", "-C", root, "ls-files", *patterns], capture_output=True,
                         text=True, encoding="utf-8")
    return [f for f in out.stdout.split("\n") if f]


def headings(path):
    if path not in _headings:
        out = []
        try:
            with open(path, encoding="utf-8") as fh:
                in_fence = False
                for line in fh:
                    if FENCE.match(line):
                        in_fence = not in_fence
                    elif not in_fence:
                        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
                        if m:
                            out.append(m.group(1))
                        elif BOLD.match(line):
                            out.append(BOLD.match(line).group(1).rstrip(":. "))
        except (OSError, UnicodeDecodeError):
            pass
        _headings[path] = out
    return _headings[path]


def norm(s):
    return re.sub(r"\s+", " ", s.replace("`", "").replace("*", "").strip().lower())


def title_matches(title, heads):
    t = norm(title)
    for h in heads:
        for cand in (norm(h), re.sub(r"^[\d.]+\s+", "", norm(h))):
            if cand == t or f'"{t}"' in cand or f"«{t}»" in cand or cand.endswith(": " + t):
                return True
            if cand.startswith(t) and cand[len(t):len(t) + 1] in (":", " ", ".", ",", "(", "—", "-"):
                return True
    return False


def slug(h):
    return re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-")


def resolve_path(text, base, repo_root, neb_root):
    p = re.sub(r":\d+(?:-\d+)?$", "", text)
    if "<" in p or "*" in p or p.startswith("~"):
        return SKIP
    dirs, d = [], base
    while True:
        dirs.append(d)
        if os.path.normcase(d) == os.path.normcase(repo_root) or os.path.dirname(d) == d:
            break
        d = os.path.dirname(d)
    for r in dirs + [neb_root]:
        cand = os.path.normpath(os.path.join(r, p))
        if os.path.isfile(cand):
            return cand
    hits = SUFFIXES.get(p.replace("\\", "/"), [])
    return hits[0] if len(hits) == 1 else None


def files_with_title(title):
    found = {f for fs in SUFFIXES.values() for f in fs
             if not re.search(r"(^|[\\/])(CHANGELOG\.md|changelog\.d)", f) and title_matches(title, headings(f))}
    return sorted(found)


def display(f):
    for root, sub in ROOTS:
        if os.path.normcase(f).startswith(os.path.normcase(root) + os.sep):
            tag = "neb" if root == ROOTS[0][0] else os.path.basename(root)
            return f"{tag}:" + os.path.relpath(f, root).replace("\\", "/")
    return f


def check_file(path, rel, repo_root, neb_root):
    base = os.path.dirname(path)
    found = []
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except UnicodeDecodeError:
        return [(rel, 0, "no-utf8", "", "")]
    in_fence = False
    carry = None
    for n, line in enumerate(lines, 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        im = IMPORT.match(line)
        if im and not im.group(1).startswith("~"):
            if not os.path.isfile(os.path.normpath(os.path.join(base, im.group(1)))):
                found.append((rel, n, "import", im.group(1), ""))
            continue
        owners = []  # (inicio, fin, archivo | lista | None | SKIP, texto)
        code_spans = []
        masked = list(line)
        for m in CODE.finditer(line):
            code_spans.append((m.start(), m.end()))
            inner = m.group(2).strip()
            if MDPATH.match(inner):
                owners.append((m.start(), m.end(), resolve_path(inner, base, repo_root, neb_root), inner))
            masked[m.start():m.end()] = " " * (m.end() - m.start())
        masked = "".join(masked)
        link_spans = []
        for m in LINK.finditer(line):
            if any(a <= m.start() < b for a, b in code_spans):
                continue
            link_spans.append((m.start(), m.end()))
            target = m.group(2)
            if "<" in target:
                continue
            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                owners.append((m.start(), m.end(), SKIP, target))
                continue
            file_part, _, anchor = target.partition("#")
            resolved = os.path.normpath(os.path.join(base, file_part)) if file_part else path
            if not os.path.exists(resolved):
                found.append((rel, n, "enlace", target, ""))
                owners.append((m.start(), m.end(), SKIP, target))
                continue
            if anchor and os.path.isfile(resolved) and anchor not in {slug(h) for h in headings(resolved)}:
                found.append((rel, n, "ancla", target, ""))
            owners.append((m.start(), m.end(), resolved if os.path.isfile(resolved) else SKIP, target))
        for m in BARE_MD.finditer(masked):
            if not any(a <= m.start() < b for a, b in link_spans):
                owners.append((m.start(), m.end(), resolve_path(m.group(1), base, repo_root, neb_root), m.group(1)))
        for m in PROFILE.finditer(line):
            dirs = [os.path.join(r, sub or "", "profiles", m.group(1)) for r, sub in ROOTS]
            mds = [os.path.join(d, f) for d in dirs if os.path.isdir(d) for f in os.listdir(d) if f.endswith(".md")]
            owners.append((m.start(), m.end(), mds or None, f"profile {m.group(1)}"))
        if carry and re.match(r"^\s*\(?\s*§", masked):
            owners.append((-1, 0, carry[0], carry[1]))
        owners.sort(key=lambda o: (o[0], o[1]))
        last = max((o for o in owners if o[0] >= 0), key=lambda o: o[1], default=None)
        carry = (last[2], last[3]) if last and re.fullmatch(r"[\s(]*", line[last[1]:]) else None

        prev = None
        for s in SECTION.finditer(masked):
            s = SECTION.match(line, s.start()) or s
            title = next(g for g in s.groups() if g)
            bound = not s.group(0).startswith("§")  # «sección "T"» y «[t](ruta) "T"»
            if "<" in title or "..." in title or "…" in title:
                continue
            owner = None
            for st, en, res, txt in owners:
                gap = line[en:s.start()] if en <= s.start() else None
                if gap is not None and (ADJACENT.fullmatch(gap) or re.search(r"(?<!\w)su\s*\(?\s*$", gap)):
                    owner = (res, txt)
            if owner is None:
                for st, en, res, txt in owners:
                    if st >= s.end() and FOLLOWING.fullmatch(line[s.end():st]):
                        owner = (res, txt)
                        break
            if owner is None and prev and CHAINED.fullmatch(line[prev[0]:s.start()]):
                owner = prev[1]
            prev = (s.end(), owner)
            if owner is None and bound:
                continue  # sin archivo, solo la «§» se verifica contra el propio archivo
            if owner is None:
                targets, label = [path], "(mismo archivo)"
            else:
                res, txt = owner
                if res == SKIP:
                    continue
                if res is None:
                    found.append((rel, n, "aviso", txt, title))
                    continue
                targets, label = (res if isinstance(res, list) else [res]), txt
            if not any(title_matches(title, headings(t)) for t in targets):
                if owner is None:
                    elsewhere = [f for f in files_with_title(title) if f != path]
                    if elsewhere:
                        label += " — título en " + ", ".join(display(f) for f in elsewhere[:3])
                found.append((rel, n, "seccion", label, title))
    return found


def display_root(root, sub):
    return os.path.join(root, sub).replace("\\", "/") if sub and sub != "." else root.replace("\\", "/")


def discover_overlays():
    ws = os.environ.get("NEB_WORKSPACE")
    if not ws or not os.path.isdir(ws):
        return []
    return [os.path.join(ws, e) for e in sorted(os.listdir(ws))
            if os.path.isfile(os.path.join(ws, e, "overlays", "detect-profile.local.sh"))]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--overlay", action="append", default=[], help="dir del overlay (repetible)")
    ap.add_argument("--no-overlay", action="store_true")
    ap.add_argument("--save-baseline", metavar="F")
    ap.add_argument("--baseline", metavar="F")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    neb = os.path.normpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ROOTS.append((neb, None))
    overlays = [] if a.no_overlay else (a.overlay or discover_overlays())
    for ov in overlays:
        ov = os.path.abspath(ov)
        top = subprocess.run(["git", "-C", ov, "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True).stdout.strip()
        if not top:
            print(f"error: {ov} no está en un repo git", file=sys.stderr)
            return 2
        top = os.path.normpath(top)
        ROOTS.append((top, os.path.relpath(ov, top).replace("\\", "/")))
    sources = []
    for root, sub in ROOTS:
        for f in git_files(root, "*.md", "*.md.template"):
            if sub and sub != "." and not f.startswith(sub + "/"):
                continue
            full = os.path.normpath(os.path.join(root, f))
            parts = f.split("/")
            for i in range(len(parts)):
                SUFFIXES["/".join(parts[i:])].append(full)
            if f == "CHANGELOG.md" or f.startswith("changelog.d/") or f.endswith(".template"):
                continue
            sources.append((root, f, full))
    rows = []
    for root, f, full in sources:
        tag = "neb" if root == neb else os.path.basename(root)
        rows += [(tag,) + r for r in check_file(full, f, root, neb)]
    broken = [r for r in rows if r[3] != "aviso"]
    key = lambda r: f"{r[0]}:{r[1]}\t{r[3]}\t{r[4]}\t{r[5]}"
    if a.save_baseline:
        with open(a.save_baseline, "w", encoding="utf-8") as fh:
            fh.writelines(key(r) + "\n" for r in broken)
    allowed = collections.Counter()
    if a.baseline:
        with open(a.baseline, encoding="utf-8") as fh:
            allowed.update(l.rstrip("\n") for l in fh if l.strip())
    shown = 0
    for r in rows:
        if r[3] != "aviso":
            if allowed[key(r)] > 0:
                allowed[key(r)] -= 1
                continue
            shown += 1
        print(f"{r[0]}:{r[1]}:{r[2]}\t{r[3]}\t{r[4]}\t{r[5]}")
    avisos = sum(1 for r in rows if r[3] == "aviso")
    print("raíces: " + ", ".join(display_root(r, sub) for r, sub in ROOTS), file=sys.stderr)
    if len(ROOTS) == 1 and not a.no_overlay:
        print("aviso: sin overlay (NEB_WORKSPACE sin overlays/detect-profile.local.sh); usa --overlay o --no-overlay",
              file=sys.stderr)
    print(f"rotos{' nuevos' if a.baseline else ''}: {shown} · avisos: {avisos} · archivos: {len(sources)}",
          file=sys.stderr)
    return 1 if shown else 0


if __name__ == "__main__":
    sys.exit(main())
