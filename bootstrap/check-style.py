#!/usr/bin/env python3
"""Verifica la forma única de términos y de citas de sección en los .md de neb.

Uso: py bootstrap/check-style.py [--root <dir>]

Recorre los .md y .md.template bajo --root (por defecto, el repo del script) sin depender de
git: el pre-push lo corre sobre el árbol extraído del commit. Excluye CHANGELOG.md,
changelog.d/, los research fechados (research/<AAAA-MM-DD>-*.md), personal/ (configuración de
cada dev, fuera de git) y los directorios ocultos. Ignora los bloques cercados y el código en
línea: una forma vetada se documenta en código. Los bloques con sangría sí cuentan, y una cerca
de cuatro comillas que contenga una de tres invierte el estado, igual que en check-references.py.

Reglas:
- V1  «change MD» en minúscula          → Change MD
- V2  F<n> suelto como abreviatura      → Fase <n>
- V3  «single source of truth»          → fuente única
- C1  § sin espacio y comillas dobles   → § "Título" (la mención «§» no cuenta)
- C2  enlace seguido de "Título" sin §  → [t](ruta) § "Título"

Salida: una línea por hallazgo, <archivo>:<línea> TAB <regla> TAB <texto> TAB <forma canónica>.
Exit 0 sin hallazgos, 1 con hallazgos, 2 error de uso.
"""
import argparse
import os
import re
import sys

FENCE = re.compile(r"^\s*(```|~~~)")
CODE = re.compile(r"(`+)(.+?)\1")
DATED_RESEARCH = re.compile(r"^research/\d{4}-\d{2}-\d{2}-")
SKIP_DIRS = {"changelog.d", "node_modules", "__pycache__", "personal"}

RULES = (
    ("V1", re.compile(r"\bchange MDs?\b"), "Change MD"),
    ("V2", re.compile(r"(?<![\w.])F[1-9](?![\w.])"), "Fase <n>"),
    ("V3", re.compile(r"single source of truth", re.I), "fuente única"),
    ("C1", re.compile(r"§(?! \")(?!»)"), '§ "Título"'),
    ("C2", re.compile(r"\]\([^)\s]+\) [\"«]"), '[t](ruta) § "Título"'),
)


def sources(root):
    out = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(files):
            if not (name.endswith(".md") or name.endswith(".md.template")):
                continue
            rel = os.path.relpath(os.path.join(base, name), root).replace("\\", "/")
            if rel == "CHANGELOG.md" or DATED_RESEARCH.match(rel):
                continue
            out.append(rel)
    return out


def check_file(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except UnicodeDecodeError:
        return [(rel, 0, "utf8", "", "UTF-8")]
    found = []
    in_fence = False
    for n, line in enumerate(lines, 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        masked = CODE.sub(lambda m: " " * len(m.group(0)), line)
        for rule, pat, canon in RULES:
            for m in pat.finditer(masked):
                a, b = max(0, m.start() - 20), min(len(line), m.end() + 30)
                found.append((rel, n, rule, line[a:b].strip(), canon))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", help="raíz a recorrer (por defecto, el repo del script)")
    a = ap.parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    root = os.path.abspath(a.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not os.path.isdir(root):
        print(f"error: {root} no es un directorio", file=sys.stderr)
        return 2
    files = sources(root)
    found = [f for rel in files for f in check_file(root, rel)]
    for rel, n, rule, text, canon in found:
        print(f"{rel}:{n}\t{rule}\t{text}\t{canon}")
    print(f"hallazgos: {len(found)} · archivos: {len(files)}", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
