# Aporte al núcleo por pull request

Cómo un adoptante sin permiso de escritura en el repo del núcleo aporta una mejora que su Fase 9 identificó. Se lee cuando [`improvement.md`](improvement.md) § "Aplicar un ajuste" enruta aquí, y rige en todo clon del núcleo donde el dev no tiene permiso de escritura. El lado del mantenedor vive en [`../profiles/self-applied/deployment.md`](../profiles/self-applied/deployment.md) § "Incorporar un PR".

## Régimen del aporte

El aporte es parte de la Fase 9 del REQ que lo originó; no abre un REQ nuevo. En el clon de trabajo la detección da el profile `self-applied`, y de ese profile **no aplican**:

- El registro propio (Change MD) y el plan-review de roles: el mantenedor revisa el aporte con roles al incorporarlo.
- El CHANGELOG, el incremento de versión y la sección «Deploy» del profile: los asigna el mantenedor.
- La autonomía sobre `.md` para publicar: el push al fork, el PR, un issue y cada comentario piden OK del dev ([`../methodology/change-control-policy.md`](../methodology/change-control-policy.md) § "Ownership de archivos `.md`").
- El hook `pre-push` del mantenedor: no se instala en el clon de trabajo, porque su gate de fragmento rechaza un push sin CHANGELOG.

**Propuesta y cambio de profile.** La opción «Aportar por PR» del menú de [`improvement.md`](improvement.md) § "Aplicar un ajuste" muestra el delta (archivo del núcleo, sección y texto nuevo) y el nombre de la rama, y anuncia que el trabajo pasa al profile `self-applied`. Elegirla aprueba esa propuesta y confirma el cambio de profile ([`../general/profile-detection.md`](../general/profile-detection.md) § "Política de anuncio"). Si al editar el delta alcanza otro archivo u otra sección, Claude vuelve a pedir OK.

**Archivos reservados.** El aporte no toca `VERSION`, `CHANGELOG.md`, `changelog.d/`, `.gitattributes`, `.gitmodules` ni el campo `version` de `.claude-plugin/plugin.json`.

## Procedimiento

- `PY` es `python3` en macOS y Linux, y `py -3` o `python` en Windows (Python 3.8 o posterior, sin paquetes adicionales).
- «Con `gh`» significa que `gh auth status` termina en 0. Si no, Claude ofrece al dev iniciar sesión con `gh auth login` o sigue § "Sin `gh`".
- Abrir un PR o un issue requiere una cuenta de GitHub del dev.

1. **Repo del núcleo.** Claude toma la URL del campo `repository` del `.claude-plugin/plugin.json` del núcleo en uso (la raíz que nombra el arranque); `<owner>/<repo>` es la ruta de esa URL. No la toma del remoto del marketplace, que puede ser el repo del overlay del adoptante.
2. **Clon de trabajo.** `git clone <url>` en la ruta que el dev elija; Claude la anota en «Directorio de repos locales» de `personal/<usuario>.md`. Si el clon ya existe, `git fetch origin`. Nunca se edita el caché del plugin: no es un repositorio y cada actualización instala una copia nueva (supuesto R27 de [`../methodology/platform-assumptions.md`](../methodology/platform-assumptions.md)).
3. **Vigencia.** Si `origin/main` ya resuelve la mejora, no hay aporte: Claude lo informa y sugiere actualizar el plugin.
4. **Rama e identidad.** Rama `mejora/<slug>` desde `origin/main` recién traído; el slug no lleva nombres de cliente ni de proyecto. En el clon: `git config --local user.email "<id>+<login>@users.noreply.github.com"` (ambos de `gh api user --jq '.id, .login'`; sin `gh`, el dev lo copia de la configuración de correos de su cuenta de GitHub) y `git config --local user.name "<login>"`.
5. **Línea base.** Antes de la primera edición: `PY bootstrap/check-references.py --no-overlay --save-baseline <archivo fuera del clon>`.
6. **Edición.** Solo el delta aprobado. Los mensajes de commit describen el cambio en términos del núcleo, sin referencias al REQ de origen.
7. **Verificación**, desde la raíz del clon:
   - `git diff --name-only --no-renames origin/main...HEAD` no lista archivos reservados (con `--no-renames`, un archivo renombrado aparece también con su nombre anterior).
   - `git diff --summary origin/main...HEAD` no muestra `mode change` ni un archivo nuevo con modo distinto de `100644`, y `git diff --numstat origin/main...HEAD` da la misma salida con y sin `--ignore-cr-at-eol` (el cambio no reescribe fines de línea).
   - Los cuatro comandos terminan en 0:

     ```
     PY bootstrap/assemble-startup.py --check general/startup.md
     PY bootstrap/neb-bootstrap-context.py --check-size --root .
     PY bootstrap/check-style.py --root .
     PY bootstrap/check-references.py --no-overlay --baseline <archivo del paso 5>
     ```

   - Si el aporte toca algo que no es `.md`, también `PY -m unittest discover -s hooks/tests`.

   Un aporte que agrega texto al arranque puede exceder el tope del segundo comando; subir el tope lo decide el mantenedor, así que Claude reduce el texto o lo ubica en un archivo que el arranque no importa.
8. **Título y cuerpo.** Claude redacta el título y el cuerpo del PR según § "Cuerpo del PR" y guarda el cuerpo en un archivo fuera del clon.
9. **Saneamiento.** Se revisan cinco textos: `git diff origin/main...HEAD`, `git log --format=fuller origin/main..HEAD`, el nombre de la rama, y el título y el cuerpo del PR. Claude los escribe en un directorio temporal fuera del clon, de nombre neutro (`neb-aporte-<slug>`), y los revisa en dos capas:
   - **Determinista.** Si el overlay trae el guion `scan-forbidden-terms.sh` (`$NEB_WORKSPACE/*/scripts/`), Claude lo corre sobre ese directorio: `bash <guion> <directorio>` (en Windows, con Git Bash). La publicación sigue solo si termina en 0: con 1 se corrige lo que reporta; con otro valor la revisión no se hizo y la publicación queda bloqueada. Siempre busca además, en los cinco textos: el nombre de cada overlay del espacio de trabajo (las carpetas que contienen `overlays/detect-profile.local.sh`) y de cada proyecto del «Directorio de repos locales» —salvo el repo del núcleo—, el correo de `git config --global user.email`, y rutas absolutas (`C:\Users\`, `/home/`, `/Users/`). Una coincidencia bloquea la publicación hasta corregirla.
   - **Revisor.** Claude invoca al `context-completeness-reviewer` con un briefing que lleva solo esos cinco textos —no el REQ de origen— y, además de su mandato, la consigna de reportar todo dato que identifique a un cliente, una persona, un proyecto o una máquina. Con esta invocación se cumple la de Fase 7 de [`plan-review.md`](plan-review.md) § "Cuándo aplica el `context-completeness-reviewer`" para un repo público.
10. **Publicación (gate único).** Claude muestra al dev los cinco textos y el resultado de los pasos 7 y 9. Con su OK explícito, que cubre crear el fork, el push y el PR, desde la raíz del clon:

    ```
    gh repo fork --remote --remote-name fork --default-branch-only
    git push fork mejora/<slug>
    gh pr create --repo <owner>/<repo> --base main --head <login>:mejora/<slug> --title "<título>" --body-file <archivo del paso 8> --no-maintainer-edit
    ```

    El fork vive en la cuenta personal del dev. Si el remoto `fork` ya existe (`git remote get-url fork` termina en 0), se omite `gh repo fork`. Si `gh repo fork` termina con error, Claude lo reporta y no sigue con el push.
11. **Seguimiento.** Claude da de alta un pendiente con la URL del PR («revisar la respuesta del mantenedor») y, si el Change MD del REQ de origen sigue abierto, anota ahí la URL. No hace un commit adicional en el proyecto de origen solo para anotarla.

## Cuerpo del PR

- **Regla vigente**: archivo y sección del núcleo que se cambia.
- **Escenario**: la fricción o el defecto, reproducible, con nombres neutros.
- **Observación e hipótesis**, separadas.
- **Cambio propuesto** y **nivel SemVer sugerido** (según el `CLAUDE.md` del repo).
- **Entrada de CHANGELOG propuesta**: el mantenedor la usa como insumo.
- **Versión de Neb** instalada.
- **Origen**: qué lo detectó y en qué fase se originó (p. ej. «diagnóstico de un defecto, origen Fase 3» o «revisión agregada»), sin el nombre del REQ. Es la cita de origen que [`improvement.md`](improvement.md) pide para el CHANGELOG.

El cuerpo no cita el Change MD de origen ni pega salidas de comandos con rutas locales.

## Paliativo en el overlay

Mientras el PR espera, el adoptante puede aplicar la mejora en su overlay solo si estrecha o agrega ([`../methodology/personal-vs-team.md`](../methodology/personal-vs-team.md) § "Regla central", que aquí vale también para el overlay). El pendiente del paso 11 lo anota: al instalar la versión que incorpore el aporte, el paliativo se retira o se ajusta a lo incorporado.

## Responder a una revisión

Cuando el mantenedor pide cambios, el trabajo parte del pendiente del paso 11, sin REQ nuevo. Claude agrega commits a la misma rama (sin `push --force`), redacta el comentario de respuesta en un archivo fuera del clon y repite los pasos 7 y 9 sobre el delta nuevo; el comentario ocupa el lugar del título y el cuerpo. Con el OK del dev: `git push fork mejora/<slug>` y `gh pr comment <n> --repo <owner>/<repo> --body-file <archivo>`. No se crean de nuevo el fork ni el PR. Si el mantenedor pide actualizar la rama, `git merge origin/main` tras `git fetch origin`.

## Abrir un issue

Para la opción «Abrir un issue» del menú. Claude redacta el título y el cuerpo con los campos de la plantilla que aplica (defecto o propuesta de mejora, [`../CONTRIBUTING.md`](../CONTRIBUTING.md)) y guarda el cuerpo en un archivo fuera de cualquier clon. El saneamiento del paso 9 se aplica a esos dos textos. Con el OK explícito del dev: `gh issue create --repo <owner>/<repo> --title "<título>" --body-file <archivo>`; sin `gh`, el dev lo pega en la web con la plantilla. El seguimiento es el del paso 11.

## Sin `gh`

El dev crea el fork en la web de GitHub; Claude agrega el remoto (`git remote add fork <url del fork>`), hace el push con el mismo OK del paso 10 y entrega la URL `https://github.com/<owner>/<repo>/compare/main...<login>:mejora/<slug>?quick_pull=1` para que el dev abra el PR y pegue el cuerpo. Para responder a una revisión, Claude hace el push con el OK del dev y le entrega el comentario saneado para que lo pegue en la página del PR.
