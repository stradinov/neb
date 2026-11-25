"""
Migración guiada de neb 7.3.0: compas.md al eje «proyecto» y sin roadmap, y compactación de neb.db como
mantenimiento recurrente: vacuum-neb-db se ofrece cada vez que la base acumula páginas libres (más de una cuarta
parte y más de 1 MB) y conserva solo la copia previa más reciente (neb.pre-vacuum.*.db).

Prompt: migrations/7.3.0.md. Formato: migrations/README.md.
"""

import os
import re
import shutil
import sqlite3
import sys
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_LIB = os.path.join(_ROOT, "hooks", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

import _machine  # noqa: E402
from _guided import GuidedStep, base_sin_otras_conexiones  # noqa: E402

COMPAS_NAME = "compas.md"
COMPAS_MAX_BYTES = 1024 * 1024        # compas.md es de unos cientos de bytes; más que esto se revisa a mano

VACUUM_MIN_FREE_BYTES = 1024 * 1024   # menos de 1 MB libre no vale la pena
VACUUM_MIN_FREE_RATIO = 0.25          # ni menos de una cuarta parte de las páginas

# Copias que deja vacuum-neb-db: neb.pre-vacuum.<_machine._stamp()>.db. Tras un VACUUM exitoso se borran las que
# casan con este patrón exacto, salvo la de esa corrida; ningún otro respaldo de neb-backups/ se toca.
_VACUUM_BACKUP_RE = re.compile(r"^neb\.pre-vacuum\.\d{8}T\d{6}\d*Z\.db$")


def _stamp():
    return _machine._stamp()


def _remove_quiet(path):
    try:
        os.remove(path)
    except OSError:
        pass


# --------------------------------------------------------------------------- compas-proyectos

# Misma forma de línea que lee parse_compas (`_field_value`): prefijo de guiones, asteriscos o espacios, la
# etiqueta y sus dos puntos. Solo esas líneas cuentan; un `Clientes:` dentro de un comentario o de prosa no.
_CLIENTES_RE = re.compile(r"^([ \t\-*]*)Clientes([ \t]*:)")
_ROADMAP_RE = re.compile(r"^[ \t\-*]*Roadmap[ \t]*:")
_FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", re.MULTILINE | re.DOTALL)
_VERSION_RE = re.compile(r"^version[ \t]*:[ \t]*(\d+)[ \t]*\r?$", re.MULTILINE)

# Frases fijas del comentario de cabecera que escribía write_compas de 7.2.x. Se cambian solo si están tal cual;
# un comentario editado a mano se deja como está.
_HEADER_PHRASES = (
    ("`Clientes:` = slug=+bonus del eje cliente (opcional).",
     "`Proyectos:` = slug=+bonus del eje proyecto (opcional)."),
    ("bonus por cliente)", "bonus por proyecto)"),
)


def _compas_path(ctx):
    return os.path.join(ctx.claude_dir, COMPAS_NAME)


def _frontmatter_version(text):
    """Versión del frontmatter (el primer bloque `---`), o None si no hay bloque o no trae `version:`."""
    fm = _FRONTMATTER_RE.search(text)
    if not fm:
        return None
    m = _VERSION_RE.search(fm.group(1))
    return int(m.group(1)) if m else None


def _compas_sin_migrar(text):
    """True si el texto trae una línea `Clientes:` o `Roadmap:`, o un frontmatter con versión menor a 3."""
    for line in text.splitlines():
        if _CLIENTES_RE.match(line) or _ROADMAP_RE.match(line):
            return True
    v = _frontmatter_version(text)
    return v is not None and v < 3


def _set_version(text):
    """El texto con `version: 3` en el frontmatter (reemplaza la línea o la agrega tras el `---` de apertura).
    Sin frontmatter, el texto queda igual: parse_compas no lo necesita."""
    fm = _FRONTMATTER_RE.search(text)
    if not fm:
        return text
    body = fm.group(1)
    m = _VERSION_RE.search(body)
    if m:
        new_body = body[:m.start(1)] + "3" + body[m.end(1):]
    else:
        nl = "\r\n" if body.endswith("\r\n") or "\r\n" in text else "\n"
        new_body = "version: 3" + nl + body
    return text[:fm.start(1)] + new_body + text[fm.end(1):]


def compas_rewrite(text):
    """compas.md v3: `Clientes:` -> `Proyectos:` (mismo contenido), sin líneas `Roadmap:`, `version: 3`.
    Conserva los fines de línea y todo lo demás."""
    out = []
    for line in text.splitlines(keepends=True):
        if _ROADMAP_RE.match(line):
            continue
        out.append(_CLIENTES_RE.sub(r"\1Proyectos\2", line, count=1))
    new = "".join(out)
    for old, repl in _HEADER_PHRASES:
        new = new.replace(old, repl)
    return _set_version(new)


def _read_compas(path):
    """Bytes de compas.md, o None si no existe o no es un archivo regular. Lee hasta el tope + 1 byte."""
    if _machine.is_link(path) or not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        return fh.read(COMPAS_MAX_BYTES + 1)


_BOM = b"\xef\xbb\xbf"


def _decode(raw):
    """(BOM, texto). UnicodeDecodeError si no es UTF-8."""
    bom = _BOM if raw.startswith(_BOM) else b""
    return bom, raw[len(bom):].decode("utf-8")


def _detectar_compas(ctx):
    """Solo lee: compas.md existe y está en la forma anterior a 7.3.0. Quita el BOM igual que aplicar, para que
    los dos vean el mismo texto (con BOM, un frontmatter en la primera línea no casaría con `^---`)."""
    try:
        raw = _read_compas(_compas_path(ctx))
    except OSError:
        return False
    if raw is None:
        return False
    data = raw[:COMPAS_MAX_BYTES]
    if data.startswith(_BOM):
        data = data[len(_BOM):]
    return _compas_sin_migrar(data.decode("utf-8", errors="replace"))


def _aplicar_compas(ctx):
    path = _compas_path(ctx)
    try:
        raw = _read_compas(path)
    except OSError as e:
        return {"estado": "fallo", "detalle": f"no se pudo leer compas.md ({type(e).__name__})"}
    if raw is None:
        return {"estado": "sin-cambio", "detalle": "no hay compas.md"}
    if len(raw) > COMPAS_MAX_BYTES:
        return {"estado": "manual",
                "detalle": "compas.md mide más de 1 MB: revísalo a mano (Clientes: -> Proyectos:, sin Roadmap:, "
                           "version: 3)"}
    try:
        bom, text = _decode(raw)
    except UnicodeDecodeError:
        return {"estado": "fallo", "detalle": "compas.md no es UTF-8: no se tocó"}
    if not _compas_sin_migrar(text):
        return {"estado": "sin-cambio", "detalle": "compas.md ya está en la forma de 7.3.0"}
    new = bom + compas_rewrite(text).encode("utf-8")
    if new == raw:
        return {"estado": "sin-cambio", "detalle": "compas.md ya está en la forma de 7.3.0"}
    if not os.access(path, os.W_OK):
        return {"estado": "fallo", "detalle": "compas.md es de solo lectura: no se tocó; quítale la protección "
                                              "y vuelve a correr apply --guiados"}

    backup = tmp = None
    try:
        _machine._private_dir(ctx.backups_dir)
        backup = os.path.join(ctx.backups_dir, f"compas.pre-7.3.0.{_stamp()}.md")
        with open(backup, "xb") as fh:          # archivo nuevo de esta corrida
            fh.write(raw)
        tmp = os.path.join(ctx.claude_dir, f".{COMPAS_NAME}.tmp-{_stamp()}")
        with open(tmp, "xb") as fh:
            fh.write(new)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            shutil.copymode(path, tmp)
        except OSError:
            pass
        # Si otra sesión lo reescribió mientras tanto (write-compas), no se pisa su versión.
        if _read_compas(path) != raw:
            _remove_quiet(tmp)
            _remove_quiet(backup)
            return {"estado": "pendiente", "detalle": "compas.md cambió mientras se migraba: vuelve a correr "
                                                      "apply --guiados"}
        os.replace(tmp, path)
        tmp = None
    except OSError as e:
        if tmp:
            _remove_quiet(tmp)
        if backup and os.path.exists(backup):
            _remove_quiet(backup)              # el original quedó intacto: el respaldo no hace falta
        return {"estado": "fallo", "detalle": f"no se pudo reescribir compas.md ({type(e).__name__}): "
                                              f"el original quedó intacto"}
    return {"respaldo": backup,
            "detalle": "compas.md pasó a la forma de 7.3.0: Clientes: -> Proyectos:, sin Roadmap:, version: 3"}


# --------------------------------------------------------------------------- vacuum-neb-db

def _is_sqlite(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _page_stats(con):
    page_size = con.execute("PRAGMA page_size").fetchone()[0]
    page_count = con.execute("PRAGMA page_count").fetchone()[0]
    free = con.execute("PRAGMA freelist_count").fetchone()[0]
    return page_size, page_count, free


def _fragmentada(page_size, page_count, free):
    return free * page_size > VACUUM_MIN_FREE_BYTES and free > VACUUM_MIN_FREE_RATIO * page_count


def _detectar_vacuum(ctx):
    """Solo lee (mode=ro): más de una cuarta parte de las páginas de neb.db están libres y suman más de 1 MB.
    Una base ocupada por otra sesión no se marca ahora; se vuelve a ver en la siguiente detección."""
    if not os.path.isfile(ctx.db_path) or not _is_sqlite(ctx.db_path):
        return False
    try:
        con = sqlite3.connect(Path(os.path.abspath(ctx.db_path)).as_uri() + "?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return False
    try:
        return _fragmentada(*_page_stats(con))
    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            return False
        raise
    finally:
        con.close()


def _condicion_vacuum(ctx):
    """Condición del exclusivo. Antes de aplicar: que ninguna otra conexión tenga la base abierta en este
    momento (la de omisión). Con el candado ya tomado por aplicar (ctx._vacuum_con): que siga retenido, es
    decir, que otra conexión no pueda leer la base."""
    if getattr(ctx, "_vacuum_con", None) is None:
        return base_sin_otras_conexiones(ctx)
    try:
        probe = sqlite3.connect(ctx.db_path, timeout=0)
    except sqlite3.Error as e:
        return f"la prueba del candado falló ({type(e).__name__})"
    try:
        probe.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return "el candado de la base no quedó retenido"
    except sqlite3.OperationalError as e:
        if "locked" in str(e) or "busy" in str(e):
            return None
        return f"la prueba del candado falló ({type(e).__name__})"
    finally:
        probe.close()


def _backup_db(con, dest):
    """Copia con la API de backup desde la conexión que retiene el candado, en journal_mode=DELETE e íntegra.
    Lanza sqlite3.Error/OSError sin dejar archivo a medias."""
    dst = None
    try:
        with open(dest, "xb"):                  # archivo nuevo de esta corrida
            pass
        dst = sqlite3.connect(dest)
        con.backup(dst)
        jm = str(dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower()
        if jm != "delete":
            raise sqlite3.DatabaseError("el respaldo no quedó en journal_mode=DELETE")
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise sqlite3.DatabaseError("el respaldo no pasa integrity_check")
        dst.close()
        dst = None
    except BaseException:
        if dst is not None:
            dst.close()
        for f in (dest, dest + "-journal", dest + "-wal", dest + "-shm"):
            _remove_quiet(f)
        raise


def _integra(con):
    """True si la base de la conexión pasa integrity_check; un error de SQLite al comprobarlo cuenta como no."""
    try:
        return con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.Error:
        return False


def _sin_integridad(backup):
    """Detalle de una base que no pasa integrity_check. neb-migrate restore solo toma respaldos de pasos de base:
    con este no hay restauración automática, así que se deja todo como está y se avisa al dev."""
    return (f"neb.db no pasa integrity_check: no corras nada más y avisa al dev; el respaldo íntegro del estado "
            f"previo es {backup} (restore no lo acepta: solo toma respaldos de pasos de base)")


def _existente(path):
    """La ruta misma o su ancestro más cercano que exista (neb-backups/ puede no existir todavía)."""
    p = os.path.abspath(path)
    while not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return p


def _volumen(path):
    """Identificador del volumen de una ruta (st_dev; en Windows, el número de serie del volumen)."""
    return os.stat(_existente(path)).st_dev


def _sqlite_temp_dir():
    """Directorio donde SQLite crea sus temporales (el VACUUM arma ahí la base nueva), con el mismo orden que
    SQLite: en Windows el de GetTempPath (TMP, TEMP, USERPROFILE); en los demás SQLITE_TMPDIR, TMPDIR, /var/tmp,
    /usr/tmp, /tmp. Si ninguno existe, el de tempfile."""
    if os.name == "nt":
        candidatos = [os.environ.get(k) for k in ("TMP", "TEMP", "USERPROFILE")]
    else:
        candidatos = [os.environ.get("SQLITE_TMPDIR"), os.environ.get("TMPDIR"), "/var/tmp", "/usr/tmp", "/tmp"]
    for c in candidatos:
        if c and os.path.isdir(c):
            return c
    import tempfile
    return tempfile.gettempdir()


def _falta_espacio(ctx, con, db_bytes):
    """Detalle si no alcanza el espacio libre para la copia y el VACUUM; None si alcanza. Por volumen se suma lo
    que pide cada uso: la copia en neb-backups/ (1 vez la base, y la copia sigue ahí durante el VACUUM), el
    journal del VACUUM en el volumen de la base (1 vez) y la base nueva en el volumen del temporal de SQLite
    (1 vez; nada si el temporal va en memoria). Si comparten volumen, se suman. Un volumen que no se puede medir no
    frena el paso: si el VACUUM se queda sin espacio, falla sin cambiar la base y sin dejar copia."""
    usos = [(ctx.backups_dir, db_bytes), (os.path.dirname(os.path.abspath(ctx.db_path)), db_bytes)]
    try:
        temp_en_memoria = con.execute("PRAGMA temp_store").fetchone()[0] == 2
    except sqlite3.Error:
        temp_en_memoria = False
    if not temp_en_memoria:
        usos.append((_sqlite_temp_dir(), db_bytes))
    porvol = {}
    for path, need in usos:
        try:
            key = _volumen(path)
        except OSError:
            key = ("?", path)
        if key in porvol:
            porvol[key][1] += need
        else:
            porvol[key] = [path, need]
    mb = 1024 * 1024
    for path, need in porvol.values():
        try:
            free = shutil.disk_usage(_existente(path)).free
        except OSError:
            continue
        if free < need:
            return (f"falta espacio en disco: la copia y el VACUUM piden {need / mb:.1f} MB libres en el volumen "
                    f"de {path} y hay {free / mb:.1f} MB; no se creó nada. Libera espacio y vuelve a correr "
                    f"apply --guiados")
    return None


def _borrar_copias_anteriores(ctx, keep):
    """Borra los neb.pre-vacuum.*.db de neb-backups/ salvo `keep` (la copia de esta corrida). Solo archivos
    regulares que casan con el patrón exacto; ningún otro respaldo se toca. Devuelve (borradas, no borradas)."""
    keep_n = os.path.normcase(os.path.realpath(keep))
    borradas = fallidas = 0
    try:
        entries = list(os.scandir(ctx.backups_dir))
    except OSError:
        return 0, 0
    for entry in entries:
        if not _VACUUM_BACKUP_RE.fullmatch(entry.name):  # fullmatch: `$` aceptaría un \n final
            continue
        if _machine.is_link(entry.path) or not entry.is_file(follow_symlinks=False):
            continue
        if os.path.normcase(os.path.realpath(entry.path)) == keep_n:
            continue
        try:
            os.remove(entry.path)
            borradas += 1
        except OSError:
            fallidas += 1
    return borradas, fallidas


def _aplicar_vacuum(ctx):
    """Toma el candado exclusivo de neb.db y lo retiene (journal_mode=DELETE + locking_mode=EXCLUSIVE) durante
    el respaldo, VACUUM y PRAGMA optimize; al final regresa la base a su modo de journal y suelta el candado.
    No cambia auto_vacuum. Antes de copiar comprueba el espacio libre (si no alcanza, pendiente sin crear nada);
    tras un VACUUM exitoso borra las copias neb.pre-vacuum.*.db anteriores y deja solo la de esta corrida."""
    if not os.path.isfile(ctx.db_path):
        return {"estado": "sin-cambio", "detalle": "no hay neb.db"}
    try:
        con = sqlite3.connect(ctx.db_path, timeout=0, isolation_level=None)
    except sqlite3.Error as e:
        return {"estado": "fallo", "detalle": f"no se pudo abrir neb.db ({type(e).__name__})"}
    orig_mode = None
    backup = None
    try:
        try:
            orig_mode = str(con.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            if orig_mode != "delete":
                got = str(con.execute("PRAGMA journal_mode=DELETE").fetchone()[0]).lower()
                if got != "delete":
                    orig_mode = None          # no cambió: no hay que regresarlo
                    return {"estado": "pendiente", "detalle": "otra sesión tiene la base abierta"}
            con.execute("PRAGMA locking_mode=EXCLUSIVE")
            con.execute("BEGIN EXCLUSIVE")
            con.execute("COMMIT")             # en locking_mode=EXCLUSIVE el candado queda tomado
        except sqlite3.OperationalError as e:
            if "locked" in str(e) or "busy" in str(e):
                return {"estado": "pendiente", "detalle": "otra sesión tiene la base abierta"}
            raise
        ctx._vacuum_con = con

        page_size, pages_before, free_before = _page_stats(con)
        if not _fragmentada(page_size, pages_before, free_before):
            return {"estado": "sin-cambio", "detalle": "neb.db ya está compacta"}

        falta = _falta_espacio(ctx, con, page_size * pages_before)
        if falta:
            return {"estado": "pendiente", "detalle": falta}

        _machine._private_dir(ctx.backups_dir)
        backup = os.path.join(ctx.backups_dir, f"neb.pre-vacuum.{_stamp()}.db")
        try:
            _backup_db(con, backup)
        except (sqlite3.Error, OSError) as e:
            backup = None
            return {"estado": "fallo", "detalle": f"el respaldo falló ({type(e).__name__}): no se compactó"}

        motivo = ctx.exclusivo_ok()
        if motivo:
            _remove_quiet(backup)             # no se compactó: la copia no hace falta
            return {"estado": "pendiente", "detalle": motivo}

        try:
            con.execute("VACUUM")
        except sqlite3.Error as e:
            # VACUUM es atómico: si falla, la base queda como estaba. Íntegra, la copia sobra (y con SQLITE_FULL
            # ocupa justo el espacio que faltó; cada reintento haría otra): se borra. Si no, se conserva y se
            # reporta.
            if _integra(con):
                _remove_quiet(backup)
                return {"estado": "fallo",
                        "detalle": f"el VACUUM falló ({type(e).__name__}): la base quedó como estaba y no quedó "
                                   f"copia; revisa el espacio libre del disco y vuelve a correr apply --guiados"}
            return {"estado": "fallo", "respaldo": backup,
                    "detalle": f"el VACUUM falló ({type(e).__name__}) y " + _sin_integridad(backup)}
        try:
            con.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass                              # solo afina las estadísticas del planificador; la compactación ya quedó
        if not _integra(con):
            return {"estado": "fallo", "respaldo": backup, "detalle": "tras el VACUUM " + _sin_integridad(backup)}
        mb = 1024 * 1024
        try:
            _ps, pages_after, free_after = _page_stats(con)
            sizes = (f"{pages_before * page_size / mb:.1f} MB -> {pages_after * page_size / mb:.1f} MB; "
                     f"páginas libres {free_before} -> {free_after}")
        except sqlite3.Error:
            sizes = f"antes {pages_before * page_size / mb:.1f} MB con {free_before} páginas libres"
        # Mantenimiento recurrente: solo se conserva la copia más reciente (la de esta corrida).
        borradas, fallidas = _borrar_copias_anteriores(ctx, backup)
        if borradas == 1:
            sizes += "; se borró la copia anterior (neb.pre-vacuum.*.db)"
        elif borradas:
            sizes += f"; se borraron {borradas} copias anteriores (neb.pre-vacuum.*.db)"
        if fallidas:
            sizes += f"; {fallidas} copia(s) anterior(es) no se pudieron borrar"
        return {"respaldo": backup, "detalle": "neb.db compactada: " + sizes}
    finally:
        ctx._vacuum_con = None
        if orig_mode and orig_mode != "delete":
            try:
                con.execute(f"PRAGMA journal_mode={orig_mode}")
            except sqlite3.Error:
                pass                          # la siguiente conexión de neb la deja en WAL
        try:
            con.execute("PRAGMA locking_mode=NORMAL")
            con.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()   # suelta el candado
        except sqlite3.Error:
            pass
        con.close()


STEPS = [
    GuidedStep("compas-proyectos", "Pasar compas.md al eje proyecto y sin roadmap (Clientes: -> Proyectos:)",
               detectar=_detectar_compas, aplicar=_aplicar_compas, respaldo=True),
    GuidedStep("vacuum-neb-db", "Compactar neb.db (VACUUM) para recuperar sus páginas libres",
               detectar=_detectar_vacuum, aplicar=_aplicar_vacuum, respaldo=True, exclusivo=True,
               condicion=_condicion_vacuum),
]
