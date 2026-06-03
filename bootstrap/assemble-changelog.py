#!/usr/bin/env python3
"""Ensambla CHANGELOG.md desde fragments en changelog.d/.

Cada fragment es `changelog.d/<X.Y.Z>.md` con contenido en formato
keep-a-changelog (`## [X.Y.Z] - YYYY-MM-DD` + secciones Added/Changed/etc.).

El ensamblador:
- Lee todos los fragments.
- Ordena por SemVer descendente.
- Antepone el header canónico (titulo, descripción, `## [Unreleased]`).
- Reescribe `CHANGELOG.md`.

Modo `--check`: salir con codigo 1 si `CHANGELOG.md` no coincide con el
output esperado. Util para hooks pre-commit / CI.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FRAGMENTS_DIR = REPO_ROOT / "changelog.d"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

HEADER = (
    "# Changelog\n"
    "\n"
    "Todos los cambios relevantes a esta metodología quedan registrados aquí. "
    "Formato: [keep a changelog](https://keepachangelog.com/en/1.1.0/). "
    "Versionado SemVer.\n"
    "\n"
    "## [Unreleased]\n"
    "\n"
)

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(stem: str) -> tuple[int, int, int]:
    m = VERSION_RE.match(stem)
    if not m:
        raise ValueError(f"Fragment con nombre no SemVer: {stem}.md")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def assemble() -> str:
    if not FRAGMENTS_DIR.is_dir():
        sys.stderr.write(f"ERROR: no existe {FRAGMENTS_DIR}\n")
        sys.exit(2)

    fragments: list[tuple[tuple[int, int, int], str, str]] = []
    for path in sorted(FRAGMENTS_DIR.glob("*.md")):
        version = parse_version(path.stem)
        content = path.read_text(encoding="utf-8").rstrip("\n")
        fragments.append((version, path.name, content))

    if not fragments:
        sys.stderr.write(f"ERROR: {FRAGMENTS_DIR} no contiene fragments .md\n")
        sys.exit(2)

    fragments.sort(key=lambda x: x[0], reverse=True)

    body = "\n\n".join(content for _, _, content in fragments)
    return HEADER + body + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="Salir 1 si CHANGELOG.md no coincide con el output ensamblado.",
    )
    args = ap.parse_args()

    new_content = assemble()

    if args.check:
        current = (
            CHANGELOG_PATH.read_text(encoding="utf-8")
            if CHANGELOG_PATH.exists()
            else ""
        )
        if current != new_content:
            sys.stderr.write(
                "CHANGELOG.md desactualizado respecto a changelog.d/.\n"
                "Correr: py bootstrap/assemble-changelog.py\n"
                "y stagear el resultado.\n"
            )
            return 1
        return 0

    CHANGELOG_PATH.write_text(new_content, encoding="utf-8")
    count = len(list(FRAGMENTS_DIR.glob("*.md")))
    print(f"Generado: {CHANGELOG_PATH} ({count} fragments)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
