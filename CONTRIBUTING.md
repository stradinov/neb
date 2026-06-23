# Cómo contribuir a Neb

> Stub inicial (MVP). Se ampliará a medida que el proyecto reciba contribuciones externas.

Gracias por tu interés en mejorar **Neb**. Neb se gobierna con sus propias reglas (profile `self-applied`): cada cambio a la metodología es un requerimiento que sigue sus propias fases y gates.

## Antes de empezar

- Lee el [README](README.md) para entender el modelo (fases, profiles, artefactos).
- Revisa [`CLAUDE.md`](CLAUDE.md) — las meta-instrucciones para editar Neb, incluidas las convenciones de versionado SemVer y el flujo de CHANGELOG.

## Flujo de una contribución

1. **Abre un issue** describiendo la fricción, el gap o la mejora antes de escribir código o documentación. Esto evita trabajo duplicado y permite acordar el alcance.
2. **Forkea y ramea** desde `main` con un nombre descriptivo (`fix/…`, `docs/…`, `feat/…`).
3. **Haz el cambio** siguiendo las convenciones del repo:
   - Archivos en `kebab-case.md`, sin prefijos numéricos.
   - Imports internos con paths relativos.
   - Cada carpeta mantiene su `index.md` con orden de lectura.
4. **Revisa tu diff** — no introduzcas PII, datos de clientes, marcas ni rutas absolutas de tu máquina. Neb es agnóstica de dominio: usa ejemplos genéricos.
5. **Registra el cambio en el CHANGELOG** — agrega un fragmento en `changelog.d/<X.Y.Z>.md` (formato [keep a changelog](https://keepachangelog.com/)) y corre `python bootstrap/assemble-changelog.py`.
6. **Bump SemVer** según el tipo de cambio (ver `CLAUDE.md`):
   - Patch: redacción, typos, aclaraciones.
   - Minor: nuevos lineamientos, profiles, skills, hooks.
   - Major: rupturas de imports o cambios incompatibles.
7. **Abre un Pull Request** referenciando el issue. Describe qué cambió y por qué.

## Estilo de commits

Mensajes en inglés, formato `tipo: descripción` (`docs:`, `feat:`, `fix:`, `profiles(<nombre>):`, …).

## Código de conducta

Sé respetuoso y constructivo. Un `CODE_OF_CONDUCT.md` formal se agregará en una iteración futura.
