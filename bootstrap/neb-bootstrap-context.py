#!/usr/bin/env python3
"""neb-bootstrap-context.py — Orquestador del hook SessionStart del plugin neb.

Emite a stdout el contexto de arranque que Claude Code inyecta al inicio de cada
sesion: (1) el arranque del framework (neb) ensamblado, (2) el arranque del overlay
del adoptante si existe, (3) su configuracion personal. El stdout se vuelve
additionalContext de la sesion.

La plataforma topa cada salida de hook en 10,000 caracteres: arriba de eso, Claude recibe
solo un adelanto y la ruta de un archivo (supuesto R1 de methodology/platform-assumptions.md).
Por eso hooks/hooks.json registra MAX_PARTS entradas por matcher (startup, clear, compact) y cada una emite una parte del arranque,
de LIMIT unidades UTF-16 o menos, con la cabecera «parte k de n · huella». Las partes no miran la base: en startup y
clear, una entrada más (`neb-migrate.py al-iniciar`, desde 7.5.0) corre la migración y emite su propio aviso.

Uso:
  neb-bootstrap-context.py                          el arranque completo, sin partes (pruebas, diagnostico)
  neb-bootstrap-context.py --part <k>               la parte k; nada si el arranque tiene menos partes
  neb-bootstrap-context.py --check-size --root <d>  gate 6 del pre-push: el arranque del nucleo de <d>
                                                    cabe en NUCLEUS_MAX_PARTS partes y en NUCLEUS_MAX_CHARS
                                                    caracteres (exit 1 si no)

Variables de entorno (provistas por Claude Code / el usuario):
  NEB_HOME                     working copy de neb (prioridad — permite editar y usar a la vez, D4).
                               Se ignora si apunta al cache del plugin (hooks/lib/neb_root.py).
  CLAUDE_PLUGIN_ROOT           raiz del plugin instalado (fallback si no hay NEB_HOME).
  NEB_WORKSPACE                workspace del adoptante (overlay/ + personal/ + changes/).
  CLAUDE_PLUGIN_OPTION_USERNAME nombre de usuario (de userConfig) para personal/<username>.md.

Defensivo: si algo falta, emite lo que pueda + una guia a /wakeup; nunca aborta.
"""
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
import sys
import importlib.util

# Helper de subsesión interna del corrector (hooks/lib/subsession.py). Fallback
# inline — el hook de arranque nunca debe romperse por esto.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "lib"))
try:
    from subsession import is_internal_subsession
except ImportError:
    def is_internal_subsession(env=None):
        env = os.environ if env is None else env
        return (env.get("NEB_INTERNAL_SUBSESSION") == "1"
                or env.get("CLAUDE_PREPROCESS_RECURSION") == "1")

# Raíz del núcleo (hooks/lib/neb_root.py): descarta un NEB_HOME fijado al caché del plugin.
try:
    from neb_root import resolve_neb_root, stale_neb_home
except ImportError:
    def resolve_neb_root(own_root, env=None):
        env = os.environ if env is None else env
        return env.get('NEB_HOME') or env.get('CLAUDE_PLUGIN_ROOT') or own_root

    def stale_neb_home(env=None):
        return ''

# Decisión sobre la actualización automática del plugin: clave `autoUpdate` del marketplace, supuesto R28 de
# methodology/platform-assumptions.md (hooks/lib/autoupdate.py). Sin el módulo, sin aviso.
try:
    from autoupdate import pending_offer
except ImportError:
    def pending_offer(script_path):
        return None


LIMIT = 9000            # unidades UTF-16 por parte, cabecera incluida (tope de la plataforma: 10,000)
MAX_PARTS = 12          # entradas por matcher SessionStart de hooks/hooks.json (las cuenta test_hooks_json.py)
OVERLAY_PARTS = 4       # partes que el gate 6 reserva al overlay y a la configuracion personal
NUCLEUS_MAX_PARTS = MAX_PARTS - OVERLAY_PARTS  # gate 6: partes que puede ocupar el arranque del nucleo
NUCLEUS_MAX_CHARS = 40000  # gate 6: caracteres del arranque del nucleo con la raiz LONG_ROOT; subirlo pide OK del dev
LONG_ROOT = 100         # raiz de instalacion que simula el gate 6 (la lleva la intro; los enlaces del nucleo son relativos)
NOTICE_RESERVE = 1000   # lugar que deja la ultima parte para el aviso de desbordamiento
HEADER = "# Arranque de Neb — parte %d de %d · huella %s\n\n"
ENV_NOTICE = "\n> **Aviso de Neb (entorno):** %s\n"
AUTOUPDATE_NOTICE_MAX = 800  # unidades UTF-16 del aviso de actualización automática, con su envoltura
AUTOUPDATE_NOTICE = (
    "la actualización automática del plugin de Neb no está decidida (marketplace `%s`): viene apagada. "
    "Si hay una persona presente, ofrécele encenderla al cierre de tu "
    "primera respuesta, como menú y una sola vez por conversación. El menú dice que cada versión publicada "
    "llegará en una sesión posterior, que vale para todos los plugins de ese marketplace y que en la app de "
    "escritorio se escribe además "
    "`FORCE_AUTOUPDATE_PLUGINS=1`, que aplica a todos sus marketplaces con actualización automática. "
    "Con su OK, %s; si la rechaza, con `disable`. Solo escribe su `settings.json`, con respaldo. "
    "Detalle: `docs/user-guide.md` § \"Mantener Neb al día\".")

# Puntos de corte, del mas grueso al mas fino: seccion, subseccion, parrafo, linea.
_LEVELS = (re.compile(r'^# ', re.M), re.compile(r'^## ', re.M), re.compile(r'\n\n'), re.compile(r'\n'))
_FENCE_RE = re.compile(r'^ {0,3}(```|~~~)')


def _utf8_stdout():
    # En Windows el stdout por defecto es cp1252; el arranque tiene Unicode.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass


def _emit(text):
    """UTF-8 con LF, para que la plataforma mida lo mismo que split_parts."""
    data = text.replace('\r\n', '\n')
    out = getattr(sys.stdout, 'buffer', None)
    if out is None:  # p. ej. io.StringIO, cuando una prueba llama a main() dentro del proceso
        sys.stdout.write(data)
        return
    out.write(data.encode('utf-8'))
    out.flush()


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_assembler(bootstrap_dir):
    return _load_module(os.path.join(bootstrap_dir, 'assemble-startup.py'), 'neb_assemble_startup')


DB_NOTICE_MAX = 900  # unidades UTF-16 del aviso de base incompatible, sin mudar o paso detenido, con su envoltura


def _db_path(home):
    """<datos>/neb.db (neb_paths.db_path: NEB_DATA absoluta o ~/.neb), la de _db_shared.resolve_db_path; None si
    el árbol no trae neb_paths (anterior a 8.0.0)."""
    try:
        import neb_paths
        return neb_paths.db_path(home)
    except Exception:  # noqa: BLE001 — el aviso es accesorio
        return None


def _readonly_db(mig, home):
    """Ruta de la base (<datos>/neb.db, la de resolve_db_path) si trae `work`, comprobado sin abrirla para
    escribir; None si no. La base que sigue en ~/.claude (sin mudar, hasta 7.x) no se abre aquí: la muda la
    migración guiada 8.0.0 y su aviso lo da _unmoved_notice."""
    p = _db_path(home)
    if p is None:
        return None
    con = mig.open_readonly(p)
    if con is None:
        return None
    try:
        return p if mig._table_exists(con, 'work') else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        con.close()


def _relax_axis_step(bootstrap_dir, home=None):
    """Baja a 2 la mínima compatible del paso 3 que dejó 7.3.0 (_migrations.relax_axis_step_min_code), para que
    una sesión abierta con 7.0.0–7.2.x, que lee la mínima tal cual está en la base, la opere desde la primera
    sesión tras actualizar y no hasta que algún CLI o hook de escritura de este código abra la base. Desde 7.5.0
    la llama `neb-migrate.py al-iniciar` con el candado entre corridas, no las partes del arranque: comprueba en solo lectura que la base existe, que no es más nueva que este código y
    que trae esa fila exacta; si no, no abre la base para escribir. Devuelve True si bajó la fila; un fallo no
    rompe el arranque (se reintenta en la siguiente conexión)."""
    own_root = os.path.dirname(bootstrap_dir)
    try:
        mig = _load_module(os.path.join(own_root, 'hooks', 'lib', '_migrations.py'), 'neb_migrations_own')
        relax = mig.relax_axis_step_min_code
        step, title, old_min = mig._AXIS_STEP_ROW_7_3_0
    except Exception:  # noqa: BLE001 — un árbol sin la reparación no hace nada
        return False
    db = _readonly_db(mig, home or os.path.expanduser('~'))
    if db is None:
        return False
    con = mig.open_readonly(db)
    if con is None:
        return False
    try:
        v, _f = mig.read_version(con)
        found = v <= mig.code_version() and con.execute(
            "SELECT 1 FROM schema_step WHERE step = ? AND min_code = ? AND title = ?",
            (step, old_min, title)).fetchone() is not None
    except Exception:  # noqa: BLE001
        found = False
    finally:
        con.close()
    if not found:
        return False
    try:
        # mode=rw: si la base desapareció entre la lectura y aquí (un restore), no la crea vacía.
        con = sqlite3.connect(Path(os.path.abspath(db)).as_uri() + '?mode=rw', uri=True, timeout=1.0)
    except sqlite3.Error:
        return False
    try:
        return bool(relax(con))
    except Exception:  # noqa: BLE001 — accesorio
        return False
    finally:
        con.close()


def _unmoved_notice(own_root, home):
    """Parte del aviso si la base sigue sin mudar en ~/.claude (_db_shared.unmoved_legacy: es una base de verdad y
    la carpeta de datos no tiene una usable): mientras tanto neb no captura. None si no; nunca levanta."""
    try:
        dbs = _load_module(os.path.join(own_root, 'hooks', 'lib', '_db_shared.py'), 'neb_db_shared_own')
        err = dbs.unmoved_legacy(home)
    except Exception:  # noqa: BLE001 — el aviso es accesorio
        return None
    if err is None:
        return None
    return "%s Avísale al dev: %s" % (err.detalle.rstrip('.') + '.', err.accion)


def _db_notice(bootstrap_dir, neb_home=None, home=None):
    """Aviso de base que un árbol de Neb ya no puede operar, de base sin mudar (sigue en ~/.claude, desde 8.0.0)
    o de un paso de base detenido; None si no hay nada que decir. Solo lee (mode=ro; nunca crea la base; la base
    sin mudar la prueba _db_shared._probe_db, que no la crea). Usa las migraciones del árbol propio; del clon
    (NEB_HOME) solo lee SCHEMA_VERSION como texto (un árbol sin _migrations.py cuenta como 1). Que la base
    esté atrás no es aviso por sí solo (lo normal en la primera sesión tras actualizar), ni que plugin y
    clon difieran de versión si los dos la entienden (M7 del REQ neb-migraciones-de-version)."""
    own_root = os.path.dirname(bootstrap_dir)
    try:
        mig = _load_module(os.path.join(own_root, 'hooks', 'lib', '_migrations.py'), 'neb_migrations_own')
    except Exception:  # noqa: BLE001 — un árbol anterior a 6.48.0 no lo trae
        return None
    home = home or os.path.expanduser('~')
    unmoved = _unmoved_notice(own_root, home)
    if unmoved is not None:
        return _fit_db_notice([unmoved])
    db = _readonly_db(mig, home)
    if db is None:
        return None
    con = mig.open_readonly(db)
    if con is None:
        return None
    try:
        v, f = mig.read_version(con)
        trees = [(own_root, mig.code_version(), True)]
        if neb_home and os.path.normcase(os.path.abspath(neb_home)) != os.path.normcase(os.path.abspath(own_root)):
            clone_mig = os.path.join(neb_home, 'hooks', 'lib', '_migrations.py')
            c_clone = mig.read_schema_version_text(clone_mig)
            if c_clone is not None:
                trees.append((neb_home, c_clone, os.path.isfile(clone_mig)))
        parts = []
        for root, c, knows_rule in trees:
            if v > c and c < f:
                effect = ("su captura no escribe y sus comandos responden `base-incompatible`" if knows_rule else
                          "es anterior a 6.48.0 y no conoce la regla: puede escribir en ella o responder vacío")
                parts.append(
                    "el árbol de Neb `%s` trae la versión de esquema %d y la base (`%s`) está en la %d, que pide "
                    "al menos la %d: ese código no la opera (%s). Ofrece al dev actualizar ese árbol"
                    % (root, c, db, v, f, effect))
        if v <= mig.code_version():
            for n, titulo, motivo in mig.blocked_report(con)[:2]:
                parts.append("el paso de base %d de Neb (%s) está detenido: %s. Avísale al dev; `%s status` da "
                             "el detalle" % (n, titulo, str(motivo)[:200],
                                             os.path.join(own_root, 'bootstrap', 'neb-migrate.py').replace('\\', '/')))
    except Exception:  # noqa: BLE001 — el aviso es accesorio
        return None
    finally:
        con.close()
    if not parts:
        return None
    return _fit_db_notice(parts)


def _fit_db_notice(parts):
    """Une las partes del aviso de base y lo recorta a DB_NOTICE_MAX (con su envoltura)."""
    text = '; '.join(parts)
    text = (text if text.endswith('.') else text + '.')
    text = text[0].upper() + text[1:]
    tail = '… (`neb-migrate.py status` da el detalle).'

    def u16(s):
        return len(s.encode('utf-16-le')) // 2
    if u16(ENV_NOTICE % text) > DB_NOTICE_MAX:
        room = DB_NOTICE_MAX - u16(ENV_NOTICE % tail)
        cut = text[:room]
        while cut and u16(cut) > room:
            cut = cut[:-1]
        text = cut.rstrip() + tail
    return text


def _env_notices(bootstrap_dir, neb_home=None):
    """Avisos sobre el entorno de Neb que Claude debe trasladar al dev. Vacio si todo esta en orden. No abre la
    base ni detecta pasos guiados (eso es de `neb-migrate.py al-iniciar`, desde 7.5.0)."""
    # La base no se mira aquí (desde 7.5.0): la entrada de migración de SessionStart (`neb-migrate.py
    # al-iniciar`) baja la mínima del paso 3 (_relax_axis_step), corre los pasos y emite el aviso de base
    # (_db_notice) y el de la migración guiada. Las partes dependen solo de archivos y entorno: una migración
    # en curso no puede cambiar su texto ni partir la huella.
    notices = []
    stale = stale_neb_home()
    if stale:
        notices.append(
            "`NEB_HOME` apunta al cache del plugin (`%s`) y se ignora: Neb corre la version instalada. "
            "Lo dejo un `/wakeup` anterior a 6.14.3. Ofrece al dev borrarlo del bloque `env` de "
            "`~/.claude/settings.json` (con su OK) y, si algun hook de su `settings.json` lo usa "
            "(`$NEB_HOME/hooks/...`), cambiarlo por la activacion con `NEB_HOOKS` (ver `hooks/README.md` "
            "§ \"Bajo el plugin de Neb\")." % stale)
    try:
        hook = _load_module(os.path.join(os.path.dirname(bootstrap_dir), 'hooks', 'neb-hook.py'),
                            'neb_hook')
        invalid = hook.invalid_tokens()
        names = ', '.join('`%s`' % n for n in hook.HOOKS)
        retired_map = getattr(hook, 'RETIRED', {})
    except Exception:  # noqa: BLE001 — el aviso es accesorio; el arranque no se rompe por el
        invalid, retired_map = [], {}
    retired = [(v, t) for v, t in invalid if t in retired_map]
    invalid = [(v, t) for v, t in invalid if t not in retired_map]
    if retired:
        notices.append(
            "Hooks opcionales retirados que siguen activados y ya no corren: %s. Ofrece al dev quitarlos de la "
            "variable (con su OK)." % ', '.join('`%s` en `%s` (retirado en %s)' % (t, v, retired_map[t])
                                                   for v, t in retired))
    if invalid:
        notices.append(
            "Valores que el gate de los hooks opcionales no reconoce, y que por eso no corren: %s. "
            "Van separados por comas y sin espacios; nombres validos: %s. Avisa al dev."
            % (', '.join('`%s` en `%s`' % (t, v) for v, t in invalid), names))
    sound = _sound_notice(bootstrap_dir)
    if sound:
        notices.append(sound)
    offer = _autoupdate_offer(bootstrap_dir)
    if offer:
        notices.append(offer)
    return [ENV_NOTICE % n for n in notices]


def _sound_notice(bootstrap_dir):
    """El aviso de los hooks de sonido activados que no suenan como se configuraron, o None.
    Solo lee: el diagnóstico de hooks/lib/notify_sound.py no genera la caché de `chimes-loud`."""
    try:
        hooks_dir = os.path.join(os.path.dirname(bootstrap_dir), 'hooks')
        hook = _load_module(os.path.join(hooks_dir, 'neb-hook.py'), 'neb_hook')
        sound = _load_module(os.path.join(hooks_dir, 'lib', 'notify_sound.py'), 'notify_sound')
        enabled = hook.enabled_hooks()
        found = [(name, sound.diagnose(name)) for name in sound.HOOKS if name in enabled]
    except Exception:  # noqa: BLE001 — el aviso es accesorio; el arranque no se rompe por el
        return None
    found = [(name, d) for name, d in found if d]
    if not found:
        return None
    return ("Hooks de sonido que no suenan como se configuraron: %s. Avisa al dev; los valores de `wav` "
            "están en `tooling/notify-on-stop.md` § \"Configuración personal default\"."
            % '; '.join('`%s` %s' % (name, d) for name, d in found))


def _autoupdate_offer(bootstrap_dir):
    """El aviso que ofrece encender la actualización automática del plugin, o None: el script no corre desde
    el caché de plugins, la decisión ya está tomada, el settings no trae la entrada donde escribirla o el texto
    no cabe en AUTOUPDATE_NOTICE_MAX. Solo lee. El texto nombra FORCE_AUTOUPDATE_PLUGINS (supuesto R29)."""
    marketplace = pending_offer(os.path.join(bootstrap_dir, 'neb-bootstrap-context.py'))
    if not marketplace:
        return None
    # Con `/`: la ruta sirve igual en Git Bash, en PowerShell y en sh.
    helper = os.path.join(os.path.dirname(bootstrap_dir), 'hooks', 'lib', 'autoupdate.py').replace('\\', '/')
    how = ("corre con Python `%s` con `enable`" % helper,
           "corre con Python `hooks/lib/autoupdate.py` del plugin con `enable`")
    for run in how:
        text = AUTOUPDATE_NOTICE % (marketplace, run)
        if _u16(ENV_NOTICE % text) <= AUTOUPDATE_NOTICE_MAX:
            return text
    return None


LANGUAGE_VALUE_MAX = 64   # tope por valor de `language` en el bloque: Neb no valida los valores (tooling/config.md)


def _language_block(bootstrap_dir):
    """El bloque de idioma del individuo: las perillas de la sección `language` de config.json que no son null
    (`base` solo si no es `es`, el valor por omisión), o None si no declara ninguna. Va después de la
    configuración personal: gana sobre la misma perilla escrita en prosa (methodology/personal-vs-team.md
    § "Idioma del individuo"). Solo lee; un árbol sin neb_paths (anterior a 8.0.0) o una config ilegible no lo
    emiten."""
    try:
        paths = _load_module(os.path.join(os.path.dirname(bootstrap_dir), 'hooks', 'lib', 'neb_paths.py'),
                             'neb_paths')
        lang = paths.section('language')
        where = paths.config_path()
    except Exception:  # noqa: BLE001 — el bloque es accesorio; el arranque no se rompe por el
        return None
    if not isinstance(lang, dict):
        return None
    declared = []
    for key, value in lang.items():
        if value is None or (key == 'base' and value == 'es'):
            continue
        text = json.dumps(value, ensure_ascii=False)
        if len(text) > LANGUAGE_VALUE_MAX:
            text = text[:LANGUAGE_VALUE_MAX] + '…'
        declared.append('- `%s`: `%s`' % (key, text.replace('`', "'")))
    if not declared:
        return None
    other = ''
    if lang.get('base') not in (None, 'es'):
        other = ("\nHoy solo `es` tiene lineamientos de redacción (`tooling/redaccion-es.md`); con otro `base`, "
                 "las demás perillas no tienen lista de valores que las respalde.\n")
    return ("\n\n---\n\n# Idioma del individuo (config.json, inyectado por el plugin)\n\n"
            "Perillas declaradas en la sección `language` de `%s`, para la conversación con el dev. Ganan sobre "
            "el núcleo, el overlay y la misma perilla en `personal/<usuario>.md` (si está ahí, recomienda al dev "
            "borrarla); un `<proyecto>/.claude/personal.md` la sigue sustituyendo en su proyecto "
            "(`methodology/personal-vs-team.md` § \"Idioma del individuo\").\n\n%s\n%s" % (where.replace('\\', '/'), '\n'.join(declared), other))


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


def _intro(neb_home):
    return (
        "# Arranque de Neb (inyectado por el plugin)\n\n"
        "Lo que sigue son las instrucciones operativas de la metodología Neb. Aplican "
        "desde el primer prompt de esta sesión y tienen prioridad, igual que un CLAUDE.md "
        "de proyecto. Llegan en varias partes, cada una de su propia entrada del hook, y pueden llegar en otro "
        "orden: cada parte abre con «parte k de n» y la misma huella; si falta una parte o las "
        "huellas no coinciden, avisa al dev. La metodología completa vive en NEB_HOME (`%s`). "
        "Los enlaces del arranque del núcleo son relativos a esa raíz: para abrir `[…](process/delivery.md)`, "
        "lee `%s` con Read cuando necesites una sección, sin buscarlo en el directorio de trabajo. "
        "Un enlace con ruta completa (overlay, configuración personal) se abre tal cual. Al citarle uno de estos "
        "enlaces al dev o pasárselo a un subagente, escribe la ruta completa: ellos no ven esta raíz.\n"
        % (neb_home, os.path.join(neb_home, 'process', 'delivery.md'))
    )


def _blocks(asm, neb_home, bootstrap_dir):
    """[(etiqueta, archivo fuente, texto)] del arranque, en el orden en que se inyecta."""
    blocks = [(None, None, _intro(neb_home))]
    blocks.extend((None, None, n) for n in _env_notices(bootstrap_dir, neb_home))
    startup = os.path.join(neb_home, 'general', 'startup.md')
    # Enlaces relativos a neb_home: la raiz la anuncia _intro() una sola vez (supuesto R34).
    blocks.append(('arranque del núcleo', startup, asm.assemble(startup, 0, frozenset(), neb_home)))

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
                blocks.append(('overlay del adoptante', ov,
                               "\n\n---\n\n# Overlay del adoptante (inyectado por el plugin)\n"
                               + asm.assemble(ov, 0, frozenset())))
                break

        user = (os.environ.get('CLAUDE_PLUGIN_OPTION_USERNAME')
                or os.environ.get('USER') or os.environ.get('USERNAME'))
        if user:
            personal = os.path.join(ws, 'personal', user + '.md')
            if os.path.isfile(personal):
                blocks.append(('configuración personal', personal,
                               "\n\n---\n\n# Configuracion personal (inyectada por el plugin)\n"
                               + asm.assemble(personal, 0, frozenset())))
    else:
        blocks.append((None, None,
                       "\n\n---\n\n> No hay `NEB_WORKSPACE` configurado todavia. Corre `/wakeup` para crear "
                       "tu workspace (overlay + personal + changes) y conectarlo.\n"))
    language = _language_block(bootstrap_dir)
    if language:
        blocks.append(('idioma del individuo', None, language))
    return blocks


def _u16(s):
    """Longitud en unidades UTF-16: un caracter fuera del BMP cuenta 2 (margen frente al conteo de la plataforma)."""
    return len(s.encode('utf-16-le')) // 2


def _fenced(text):
    """Intervalos [inicio, fin) de los bloques de codigo cercados: ahi no se corta."""
    spans, start, marker, pos = [], None, None, 0
    for line in text.splitlines(True):
        m = _FENCE_RE.match(line)
        if m and start is None:
            start, marker = pos, m.group(1)
        elif m and m.group(1) == marker:
            spans.append((start, pos + len(line)))
            start = marker = None
        pos += len(line)
    if start is not None:
        spans.append((start, len(text)))
    return spans


def _units(text, level):
    """El texto partido en los puntos de corte del nivel, fuera de los bloques de codigo."""
    at_line_start = level < 2
    spans = _fenced(text)
    cuts = []
    for m in _LEVELS[level].finditer(text):
        p = m.start() if at_line_start else m.end()
        if 0 < p < len(text) and not any(a < p < b for a, b in spans):
            cuts.append(p)
    out, prev = [], 0
    for p in cuts:
        out.append(text[prev:p])
        prev = p
    out.append(text[prev:])
    return [u for u in out if u]


def _hard_cut(text, budget):
    """Ultimo recurso, para una linea mas larga que budget: corta por caracteres."""
    out, cur, n = [], [], 0
    for ch in text:
        w = 2 if ord(ch) > 0xFFFF else 1
        if cur and n + w > budget:
            out.append(''.join(cur))
            cur, n = [], 0
        cur.append(ch)
        n += w
    if cur:
        out.append(''.join(cur))
    return out


def _atoms(text, budget, level=0):
    """Unidades de budget o menos, en orden: la seccion entera si cabe; si no, por el nivel siguiente."""
    if _u16(text) <= budget:
        return [text]
    if level >= len(_LEVELS):
        return _hard_cut(text, budget)
    out = []
    for u in _units(text, level):
        out.extend(_atoms(u, budget, level + 1) if _u16(u) > budget else [u])
    return out


def _pack(atoms, budget, small_at=None, small=None):
    """Empaca los atomos en orden en partes de budget o menos; la parte small_at, de small o menos."""
    parts, cur, n = [], '', 0
    for a in atoms:
        w = _u16(a)
        cap = small if len(parts) == small_at else budget
        if cur and n + w > cap:
            parts.append(cur)
            cur, n = '', 0
        cur += a
        n += w
    if cur:
        parts.append(cur)
    return parts


def _body_budget():
    return LIMIT - _u16(HEADER % (99, 99, 'f' * 8))


def split_parts(text, max_parts=MAX_PARTS):
    """(partes, resto): el texto en partes que, con su cabecera, miden LIMIT o menos. Sin perdida:
    ''.join(partes) + resto == texto. Si no cabe en max_parts, la ultima deja NOTICE_RESERVE para el
    aviso y resto es lo que quedo fuera."""
    budget = _body_budget()
    parts = _pack(_atoms(text, budget), budget)
    if len(parts) <= max_parts:
        return parts, ''
    small = budget - NOTICE_RESERVE
    parts = _pack(_atoms(text, small), budget, small_at=max_parts - 1, small=small)
    return parts[:max_parts], ''.join(parts[max_parts:])


def fingerprint(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:8]


def _overflow_notice(blocks, missing_from, rest):
    """Aviso al final de la ultima parte cuando el arranque no cupo: que bloques faltan y de donde leerlos."""
    sources, pos = [], 0
    for label, src, text in blocks:
        pos += len(text)
        if label and pos > missing_from:
            sources.append('%s (`%s`)' % (label, src))
    return ("\n\n> **Aviso de Neb (entorno):** el arranque no cupo en %d partes y quedaron fuera %d caracteres "
            "de: %s. Léelos con Read antes de responder y avisa al dev: hay que adelgazar el arranque.\n"
            % (MAX_PARTS, len(rest), ', '.join(sources) or 'el final del arranque'))


def _check_size(root):
    """Gate 6 del pre-push: el arranque del nucleo de root cabe en NUCLEUS_MAX_PARTS partes y en
    NUCLEUS_MAX_CHARS caracteres. Las partes aseguran que llega completo; los caracteres, que no crece sin decision.

    Mide el arbol en root, que el pre-push extrae del commit publicado (no NEB_HOME ni NEB_WORKSPACE, sin los guards del hook) y simula
    una raiz de instalacion de LONG_ROOT caracteres, que solo lleva la intro: los enlaces del nucleo son relativos."""
    _utf8_stdout()
    if not root or not os.path.isfile(os.path.join(root, 'general', 'startup.md')):
        sys.stderr.write("uso: neb-bootstrap-context.py --check-size --root <raiz de neb>\n")
        return 1
    root = os.path.abspath(root)
    asm = _load_assembler(os.path.dirname(os.path.abspath(__file__)))
    text = _intro(root) + asm.assemble(os.path.join(root, 'general', 'startup.md'), 0, frozenset(), root)
    long_root = '/' + 'x' * (LONG_ROOT - 1)
    for real in (root, root.replace('\\', '/')):
        text = text.replace(real, long_root)
    parts, _ = split_parts(text, max_parts=len(text))
    biggest = max(_u16(HEADER % (len(parts), len(parts), 'f' * 8)) + _u16(p) for p in parts)
    ok = len(parts) <= NUCLEUS_MAX_PARTS and biggest <= LIMIT and len(text) <= NUCLEUS_MAX_CHARS
    (sys.stdout if ok else sys.stderr).write(
        "arranque del núcleo: %d caracteres (tope %d) con una raíz de %d; %d partes (tope %d de %d); la mayor mide %d de %d\n"
        % (len(text), NUCLEUS_MAX_CHARS, LONG_ROOT, len(parts), NUCLEUS_MAX_PARTS, MAX_PARTS, biggest, LIMIT))
    return 0 if ok else 1


def _parse(argv):
    opts = {'part': None, 'check': False, 'root': None}
    args = iter(argv)
    for a in args:
        if a == '--part':
            try:
                opts['part'] = int(next(args, ''))
            except ValueError:
                opts['part'] = 0
        elif a == '--check-size':
            opts['check'] = True
        elif a == '--root':
            opts['root'] = next(args, None)
    return opts


def main(argv=None):
    opts = _parse(argv or [])
    if opts['check']:
        return _check_size(opts['root'])

    # Subsesión interna del corrector (preprocess-prompt.py): no inyectar el
    # arranque — evita que el Haiku corrector reciba instrucciones de asistente +
    # pendientes y responda la pregunta en vez de corregir ortografía.
    if is_internal_subsession():
        return 0

    _utf8_stdout()

    # neb: skip — si el proyecto activo lo declara en su CLAUDE.md, no inyectar nada (D2).
    if _project_opts_out():
        return 0

    bootstrap_dir = os.path.dirname(os.path.abspath(__file__))

    # NEB_HOME (working copy editable) tiene prioridad sobre el cache del plugin (D4), salvo que
    # apunte al propio cache: ese lo dejo fijado un /wakeup anterior a 6.14.3 (neb_root.py).
    neb_home = resolve_neb_root(os.path.dirname(bootstrap_dir))
    neb_home = os.path.abspath(neb_home)

    try:
        asm = _load_assembler(bootstrap_dir)
    except Exception as exc:  # noqa: BLE001 — el hook no debe romper la sesion
        if opts['part'] in (None, 1):
            _emit("<!-- neb-bootstrap-context: no se pudo cargar el ensamblador: %s -->\n" % exc)
        return 0

    blocks = _blocks(asm, neb_home, bootstrap_dir)
    text = ''.join(b[2] for b in blocks)
    if opts['part'] is None:
        _emit(text)
        return 0

    # Una entrada de hooks/hooks.json por parte: todas ensamblan lo mismo y cada una emite la suya.
    parts, rest = split_parts(text)
    k = opts['part']
    if not 1 <= k <= len(parts):
        return 0
    body = parts[k - 1]
    if rest and k == len(parts):
        body += _overflow_notice(blocks, len(''.join(parts)), rest)
    _emit(HEADER % (k, len(parts), fingerprint(text)) + body)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
