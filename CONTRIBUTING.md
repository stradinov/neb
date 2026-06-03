# Cómo contribuir a neb

> Stub inicial (MVP). Se ampliará a medida que el proyecto reciba contribuciones externas.

Gracias por tu interés en mejorar **neb**. El framework se gobierna con sus propias reglas (stack `self-applied`): cada cambio a la metodología es un requerimiento que sigue sus propias fases y gates.

## Antes de empezar

- Leé el [README](README.md) para entender el modelo (fases, stacks, artefactos).
- Revisá [`CLAUDE.md`](CLAUDE.md) — las meta-instrucciones para editar el framework, incluidas las convenciones de versionado SemVer y el flujo de CHANGELOG.

## Flujo de una contribución

1. **Abrí un issue** describiendo la fricción, el gap o la mejora antes de escribir código o documentación. Esto evita trabajo duplicado y permite acordar el alcance.
2. **Forkeá y rameá** desde `main` con un nombre descriptivo (`fix/…`, `docs/…`, `feat/…`).
3. **Hacé el cambio** siguiendo las convenciones del repo:
   - Archivos en `kebab-case.md`, sin prefijos numéricos.
   - Imports internos con paths relativos.
   - Cada carpeta mantiene su `index.md` con orden de lectura.
4. **Revisá tu diff** — no introduzcas PII, datos de clientes, marcas ni rutas absolutas de tu máquina. El framework es agnóstico de dominio: usá ejemplos genéricos.
5. **Registrá el cambio en el CHANGELOG** — agregá un fragment en `changelog.d/<X.Y.Z>.md` (formato [keep a changelog](https://keepachangelog.com/)) y corré `python bootstrap/assemble-changelog.py`.
6. **Bump SemVer** según el tipo de cambio (ver `CLAUDE.md`):
   - Patch: redacción, typos, aclaraciones.
   - Minor: nuevos lineamientos, stacks, skills, hooks.
   - Major: rupturas de imports o cambios incompatibles.
7. **Abrí un Pull Request** referenciando el issue. Describí qué cambió y por qué.

## Estilo de commits

Mensajes en inglés, formato `tipo: descripción` (`docs:`, `feat:`, `fix:`, `stacks(<nombre>):`, …).

## Código de conducta

Sé respetuoso y constructivo. Un `CODE_OF_CONDUCT.md` formal se agregará en una iteración futura.
