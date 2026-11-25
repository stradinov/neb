# Instalar o actualizar Neb

> **Para Claude.** Llegaste aquí porque el usuario te pidió instalar o actualizar Neb siguiendo este archivo. Ejecuta las secciones en orden y repórtale en español qué encontraste y qué hiciste. Este archivo **no** es para que el usuario lo siga a mano. La vía manual está en la [Guía del usuario](docs/user-guide.md) § "Instalar".

Neb es un plugin de Claude Code (repo: <https://github.com/stradinov/neb>). Para usarlo no hace falta clonar el repo. El clon solo sirve para contribuir al núcleo (sección 5).

## Reglas al seguir este archivo

- **Instalar, actualizar, activar, desactivar, desinstalar, clonar y hacer `git pull` cambian la configuración del usuario.** Antes de cada una, ofrece la acción en un menú de selección (sin UI interactiva, una lista numerada). La opción recomendada va primero, marcada «(Recomendado)» y con una línea de razón. «No por ahora» también es una opción. Leer y comparar versiones no requiere permiso.
- **En el texto que el usuario lee, «yo» es el usuario.** Nómbrate «Claude» como sujeto de lo que haces tú («Claude actualiza el plugin»). En la etiqueta de una opción, la primera persona es el usuario («Lo actualizo yo»).
- **Claude no puede teclear comandos `/`** (`/plugin`, `/clear`, `/wakeup`). Cuando un paso los pida, dale al usuario el comando exacto en un bloque de código y espera a que te confirme que lo corrió.
- **CLI.** Los comandos `claude plugin …` equivalen a los `/plugin …` y sí los puedes correr tú. Si `claude` no está en el PATH (pasa en algunas instalaciones de la app de escritorio), usa la vía con `/`: el menú interactivo de `/plugin`, con la pestaña Installed para el plugin y la pestaña Marketplaces para el marketplace. Sin CLI, verifica releyendo `installed_plugins.json` (sección 2).
- **JSON en Windows.** Lee los JSON con un parser y desde Git Bash. Por ejemplo: `PYTHONIOENCODING=utf-8 python -c "import json,sys; d=json.load(open(sys.argv[1], encoding='utf-8-sig')); …" <archivo>`. Para la salida de `claude plugin list --json`, redirígela a un archivo y léelo igual. En PowerShell 5.1, la tubería antepone un BOM que rompe `json.load`, y `Get-Content` rompe los acentos.
- Un fallo se reporta tal cual, con el comando y la salida. No lo rodees con otra vía sin decirlo.

## 1. Requisitos

Revísalos y reporta los que falten. No los instales sin preguntar.

| Requisito | Cómo verificarlo | Si falta |
|---|---|---|
| **Windows: Git for Windows (Git Bash)** | Existe `CLAUDE_CODE_GIT_BASH_PATH` apuntando a un `bash.exe`, o `where git` da `<Git>\cmd\git.exe` y existe `<Git>\bin\bash.exe`. No uses `where bash`: suele resolver al `bash.exe` de WSL aunque Git Bash esté instalado | Claude Code corre los hooks del plugin en Git Bash. Sin él, caen a PowerShell y fallan en cada evento. Instalarlo desde <https://git-scm.com/download/win> |
| **Python 3 con SQLite ≥ 3.35.5, como `python` o `python3`** | Desde Git Bash (en macOS y Linux, desde `sh`): `python -c "import sys, sqlite3; print(sys.executable, sqlite3.sqlite_version)" \|\| python3 -c "…"`. Es el mismo intérprete que usan los hooks. El lanzador `py` no cuenta, y tampoco el alias de la Microsoft Store (`…\WindowsApps\python.exe`, que no da versión) | Lo pide el arranque de Neb (el hook `SessionStart` corre con `python … \|\| python3 …`), además de la bitácora y los pendientes. Sin él, Neb no se inyecta en ninguna sesión. En Windows, Python 3.12 o superior ya trae el SQLite necesario; al instalarlo, marcar «Add python.exe to PATH». Desde 7.6.0, si el Python que corre los hooks trae un SQLite anterior a 3.35.5 o es anterior a 3.8, el aviso de inicio de sesión lo dice y, en Windows con `winget`, Claude ofrece instalar Python 3.14 ([`tooling/migrations.md`](tooling/migrations.md) § "Requisitos del intérprete") |

Si falta alguno, Neb se puede instalar de todos modos, pero avisa qué no va a funcionar.

## 2. Detectar si Neb ya está instalado

```
claude plugin list --json
```

Busca las entradas cuyo `id` empiece con `neb@`. **El nombre del marketplace varía**: `neb@neb` si se instaló desde este repo, pero un equipo puede distribuir Neb por su propio marketplace (p. ej. `neb@<equipo>`). Anota de cada una el `id`, la `version`, `enabled` y `scope`.

Sin CLI, lee `<dir de configuración>/plugins/installed_plugins.json`, donde el dir de configuración es `$CLAUDE_CONFIG_DIR` o, si no está definido, `~/.claude`. Las llaves de `plugins` son los `id`, y cada una trae su lista de instalaciones con `scope` y `version`.

- **Ninguna entrada `neb@*`** → sección 3.
- **Una entrada** → sección 4. Si `enabled` es `false`, ofrece activarla (`claude plugin enable <id>`) antes de seguir.
- **Más de una entrada** (otro marketplace, u otro `scope` del mismo `id`) → dos copias activas inyectan el arranque dos veces. Repórtalas con su versión y su `scope`, y ofrece en un menú:
  - **Quedarme con `<id A>` (Recomendado si es el de su equipo)**: Claude desactiva la otra copia con `claude plugin disable <id B>`, o la desinstala con `claude plugin uninstall <id B>` si el usuario lo prefiere.
  - **Quedarme con `<id B>`**: lo mismo, al revés.
  - **No por ahora**: avisa que el arranque seguirá saliendo doble.

  Cuando la copia no es de `scope` `user`, pasa `-s <scope>` a `enable`, `disable`, `uninstall` y `update`. Después sigue con la sección 4, solo con el `id` que se quedó.

## 3. Instalar (no estaba instalado)

Con el OK del usuario:

```
claude plugin marketplace add stradinov/neb
claude plugin install neb@neb
```

Vía con `/` (la teclea el usuario):

```
/plugin marketplace add stradinov/neb
/plugin install neb@neb
```

**Marketplace del equipo.** Si el usuario dice que su equipo distribuye Neb por un marketplace propio, agrega ese marketplace en lugar de `stradinov/neb`. El `id` cambia a `neb@<name>`, donde `<name>` es el campo `name` de su `.claude-plugin/marketplace.json` (sale también en `claude plugin marketplace list` después del `add`). Instala ese `id`, no `neb@neb`.

Verifica con `claude plugin list --json`, o sin CLI con `installed_plugins.json`, que el `id` quedó instalado y activo, y anota su versión. Después sigue con la sección 5.

## 4. Verificar la versión (ya estaba instalado)

### 4.1 Versión de referencia

En `<dir de configuración>/plugins/marketplaces/<mkt>/.claude-plugin/marketplace.json`, donde `<mkt>` es lo que va después de `@` en el `id`, busca la `source` del plugin `neb`.

| Forma de `source` | Referencia |
|---|---|
| `{"source": "url", "url": "https://github.com/stradinov/neb.git"}` (la que usa el marketplace de este repo), `{"source": "github", "repo": "stradinov/neb"}` o `git` con esa misma URL; sin `ref` ni `sha`, o con `ref` `main` | `main` de `stradinov/neb`: `version` de <https://raw.githubusercontent.com/stradinov/neb/main/.claude-plugin/plugin.json> |
| Ese mismo repo con otra `ref` o un `sha` (el equipo fija una versión) | El `.claude-plugin/plugin.json` de esa `ref` o `sha`, en `https://raw.githubusercontent.com/stradinov/neb/<ref o sha>/.claude-plugin/plugin.json` |
| Otro repo, o una ruta relativa (el plugin vive dentro del repo del marketplace) | El `.claude-plugin/plugin.json` de esa fuente. Si no puedes leerlo, repórtalo y no compares |

Cuando la referencia no es `main`, díselo al usuario: la última versión publicada en `main` no es la que su equipo distribuye.

### 4.2 Actualización automática

Antes de comparar, revisa si la actualización automática está encendida para `<mkt>`. Manda la clave `autoUpdate` de `extraKnownMarketplaces.<mkt>` en el `settings.json` del usuario; si ahí falta, la de `<dir de configuración>/plugins/known_marketplaces.json`.

Si está en `true`, revisa también el entorno. Si existe `DISABLE_AUTOUPDATER` (la app de escritorio lo pone en sus sesiones) y no existe `FORCE_AUTOUPDATE_PLUGINS`, ni en el entorno ni en el bloque `env` de `settings.json`, repórtala como encendida pero sin efecto. Si no, dile al usuario que el plugin se pondrá al día solo en una sesión siguiente.

No la enciendas ni la apagues desde aquí. El detalle vive en la [Guía del usuario](docs/user-guide.md) § "Mantener Neb al día".

### 4.3 Comparar y decidir

Compara la versión instalada con la de referencia (SemVer). Se da uno de tres casos:

- **a. Al día** → díselo al usuario y sigue con la sección 5.
- **b. Atrasada** → antes de ofrecer la actualización, resume qué cambia. La fuente es el `CHANGELOG.md` de la misma fuente y `ref` de la sección 4.1; para `main`: <https://raw.githubusercontent.com/stradinov/neb/main/CHANGELOG.md>. Resume solo las entradas mayores a la instalada y hasta la de referencia, sin `[Unreleased]`. Destaca las de tipo **Major** y las líneas **Adoptantes** (lo que el usuario tiene que hacer). Después ofrece en un menú:
  - **Actualizar ahora (Recomendado)**: trae lo que acabas de resumir.

    ```
    claude plugin marketplace update <mkt>
    claude plugin update neb@<mkt>
    ```

    Vía con `/` (la teclea el usuario): `/plugin` → pestaña Marketplaces → actualizar `<mkt>`; después, pestaña Installed → actualizar `neb`.
  - **No por ahora**: la instalación se queda en su versión.

  Después de actualizar, confirma la versión nueva con `claude plugin list --json` o con `installed_plugins.json`. Si quedó por debajo de la referencia, repórtalo con la salida de los comandos y no lo fuerces. Sigue con la sección 5.
- **c. Más nueva que la referencia** (pasa con un clon de desarrollo) → repórtalo, no actualices y sigue con la sección 5.

## 5. Clon del repo (solo si hace falta)

El clon se necesita **solo** para contribuir al núcleo de Neb. Revisa si aplica:

- **`NEB_HOME` definido** (en el entorno o en el bloque `env` de `<dir de configuración>/settings.json`) → el usuario ya tiene un clon. Verifica que la ruta exista y sea un repo git. Corre `git -C <NEB_HOME> fetch`, que no imprime nada si no hay novedades; confirma que salió con código 0. Reporta la rama, si hay cambios sin confirmar y cuántos commits va adelante y atrás de `origin/main` (`git -C <NEB_HOME> rev-list --left-right --count HEAD...origin/main` da «adelante atrás»). Solo si va atrás, no va adelante y el árbol está limpio, ofrece `git -C <NEB_HOME> pull --ff-only`. Si va adelante (commits sin publicar), divergió o tiene cambios sin confirmar, solo repórtalo.
- **Sin `NEB_HOME`, y el usuario dijo que quiere contribuir** → ofrece clonar (`git clone https://github.com/stradinov/neb.git <ruta que elija el usuario>`) y remítelo a [Guía del usuario](docs/user-guide.md) § "Contribuir al núcleo", donde está el resto del montaje.
- **En cualquier otro caso** → no clones. Para usar Neb basta con el plugin.

## 6. Activar y montar el espacio de trabajo

1. Si se instaló, actualizó, activó o desactivó el plugin en esta sesión, pídele al usuario que **abra una sesión nueva** o corra `/clear`. El arranque de Neb lo inyecta el hook `SessionStart`, que solo corre al iniciar, al limpiar o al compactar una sesión. `/reload-plugins` no lo vuelve a inyectar.
2. Si el usuario todavía no tiene espacio de trabajo, pídele que corra `/wakeup` en esa sesión nueva: el recorrido lo conecta o lo monta (overlay y configuración personal) y lo guía para definir su primer profile. Para saber si ya lo tiene, revisa que `NEB_WORKSPACE` esté definido en el bloque `env` de `<dir de configuración>/settings.json` y que esa ruta exista.

## 7. Reporte final

Cierra con una tabla corta que cubra:

- **Requisitos:** ✔ o falta, por cada uno.
- **Plugin:** `id` y versión antes → después, y si la actualización automática está encendida y con efecto.
- **Clon:** no aplica / al día / atrasado / adelante / divergido, más «con cambios sin confirmar» si los hay.
- **Espacio de trabajo:** montado / pendiente de `/wakeup`.
- **Lo que queda del lado del usuario:** sesión nueva o `/clear`, y los comandos `/` que todavía tiene que correr.
