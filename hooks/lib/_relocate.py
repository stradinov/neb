#!/usr/bin/env python3
"""
_relocate.py — mudanza de lo que Neb guardaba en ~/.claude a su carpeta de datos (Neb 8.0.0).

Lo usa la migración guiada de 8.0.0 (migrations/8.0.0.py). Tres piezas, ninguna imprime:

- move_db: mueve una base SQLite viva de una carpeta a otra. Es la lógica probada del migrador de nombre de
  7.0.0 (bootstrap/migrate-neb-db.py, retirado en 8.0.0) llevada a otra carpeta:
    1. solo acepta un destino ausente o de 0 bytes y sin -wal/-shm/-journal; un origen que es enlace no se mueve;
    2. integra el -wal (wal_checkpoint(TRUNCATE)) y saca la base de WAL (journal_mode=DELETE, que solo se logra
       sin otra conexión abierta);
    3. con una lectura retenida (nadie confirma escrituras mientras tanto) saca un respaldo NUEVO con la API de
       backup, en un solo archivo y verificado con integrity_check, y toma la huella del archivo (tamaño, mtime y
       los 100 bytes del encabezado: en journal_mode=DELETE el contador de cambios del encabezado sube con cada
       transacción); después, BEGIN EXCLUSIVE y ROLLBACK;
    4. cierra y, justo antes de mover, comprueba otra vez que no aparecieron -wal/-shm/-journal de ninguna de las
       dos y que la huella no cambió: si cambió, alguien escribió después del respaldo y no se mueve nada;
    5. en el mismo volumen, os.replace (instantáneo) y, de inmediato, la base testigo ocupa el lugar del origen;
       entre volúmenes (EXDEV), copia con la API de backup a un temporal junto al destino, la verifica (tabla
       `work` y el mismo número de filas), la pone en su lugar y retira el origen reemplazándolo por la testigo
       (o borrándolo), solo si su huella sigue igual; si el retiro falla, borra la copia;
    6. verifica el destino con _db_shared._probe_db (en el mismo volumen, si no resultó usable lo devuelve a su
       lugar) y lo regresa a WAL.
- plan_moves / apply_moves: mueve archivos sin pisar nada. Un homónimo idéntico en el destino quita el origen;
  uno distinto es un conflicto que queda en su lugar (salvo `newer_wins`, para estado efímero y caché, donde queda
  el más nuevo). Antes de mover escribe un MANIFIESTO JSON nuevo (origen, destino y tamaño de cada archivo), que es
  con qué deshacer el movimiento, y al terminar lo reescribe con lo que pasó.
- write_witness / is_witness: la base testigo, una base SQLite con solo la tabla schema_step y la fila
  (step=1000, min_code=1000), sin tabla `work`. El código 6.48–7.6 de una sesión abierta antes de actualizar la
  lee como una base más nueva e incompatible (IncompatibleDb) y no escribe; sin ella, crearía en ~/.claude una base
  vacía y capturaría ahí, lejos de la mudada.

No sigue ni escribe a través de enlaces (symlink o junction). Residuo de transición: sale en 9.0.0 junto con la
migración 8.0.0. Documento: migrations/8.0.0.md y tooling/migrations.md § "Mudanza a la carpeta de datos (8.0.0)".
"""

import errno
import json
import os
import shutil
import sqlite3
import stat
from datetime import datetime, timezone

import _db_shared
import _migrations
import neb_paths

SIDECARS = ("-wal", "-shm", "-journal")

WITNESS_STEP = 1000
WITNESS_TITLE = "mudada a la carpeta de datos (8.0.0)"

_COPY_CHUNK = 1024 * 1024


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_link(path):
    """Symlink o junction (la regla de neb_paths: no se escribe ni se sigue a través de uno)."""
    try:
        if os.path.islink(path):
            return True
        st = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def same_path(a, b):
    """Misma ruta por grafía o mismo archivo en disco (neb_paths.same_path)."""
    return neb_paths.same_path(a, b)


def _size(path):
    try:
        return os.path.getsize(path) if os.path.isfile(path) else None
    except OSError:
        return None


def _remove_quiet(path):
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def sidecars(*paths):
    """Los -wal/-shm/-journal que existen junto a cada ruta."""
    return [p + s for p in paths for s in SIDECARS if os.path.lexists(p + s)]


def ensure_tree(root, rel=""):
    """Crea `root` y cada carpeta de `rel` debajo (0700), comprobando en cada nivel que no sea un enlace
    (neb_paths.ensure_dir solo revisa la carpeta que recibe). Devuelve la carpeta final; ValueError si un nivel es
    un enlace o no es carpeta."""
    path = neb_paths.ensure_dir(root)
    for part in [p for p in rel.replace("\\", "/").split("/") if p]:
        path = neb_paths.ensure_dir(os.path.join(path, part))
    return path


# =========================================================================== base testigo

def write_witness(path, neb_version):
    """Crea en `path`, que no debe existir, la base testigo (journal_mode=DELETE, un solo archivo). Lanza
    OSError/sqlite3.Error sin dejar archivo a medias."""
    with open(path, "xb"):
        pass
    con = None
    try:
        con = sqlite3.connect(path)
        con.execute(_migrations._BOOKKEEPING_DDL[0])            # schema_step, la misma forma que el mecanismo
        con.execute("INSERT INTO schema_step (step, min_code, title, neb_version, applied_at, backup) "
                    "VALUES (?, ?, ?, ?, ?, NULL)", (WITNESS_STEP, WITNESS_STEP, WITNESS_TITLE, neb_version, _now()))
        con.commit()
        con.close()
        con = None
    except BaseException:
        if con is not None:
            con.close()
        for f in (path,) + tuple(path + s for s in SIDECARS):
            _remove_quiet(f)
        raise
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def is_witness(path):
    """True si `path` es la base testigo: schema_step con la fila de la mudanza y sin tabla `work`. Solo lee, pero
    con una conexión normal y no mode=ro: el código 6.48–7.6 pasa la testigo a WAL al abrirla, y una conexión de
    solo lectura sobre una base en WAL deja -wal/-shm al lado; la normal los quita al cerrar. No abre un enlace
    ni un archivo que falta o pesa 0 (no lo crea). False ante cualquier error."""
    try:
        if is_link(path) or not os.path.isfile(path) or os.path.getsize(path) == 0:
            return False
    except OSError:
        return False
    con = None
    try:
        con = sqlite3.connect(path, timeout=0.5)
        if _migrations._table_exists(con, "work"):
            return False
        return con.execute("SELECT 1 FROM schema_step WHERE step = ? AND min_code = ? AND title = ?",
                           (WITNESS_STEP, WITNESS_STEP, WITNESS_TITLE)).fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        if con is not None:
            con.close()


# =========================================================================== mover la base

def _result(codigo, mensaje, respaldo=None, aviso=None, modo=None):
    """codigo: ok (se movió) · nada (no había qué mover) · ocupada (otra conexión: se reintenta) · aborto (el dev
    debe hacer algo antes) · error (falló algo de la mudanza). modo: replace | copia."""
    return {"codigo": codigo, "mensaje": mensaje, "respaldo": respaldo, "aviso": aviso, "modo": modo}


def _busy(e):
    msg = str(e).lower()
    return "locked" in msg or "busy" in msg


def _fingerprint(path):
    """(tamaño, mtime en ns, encabezado de 100 bytes) del archivo: cambia con cualquier escritura en
    journal_mode=DELETE (el contador de cambios del encabezado sube con cada transacción) y con el paso a WAL."""
    st = os.stat(path)
    with open(path, "rb") as fh:
        return st.st_size, st.st_mtime_ns, fh.read(100)


def backup_sqlite(con, dst_path):
    """Copia con la API de backup desde `con` a un archivo nuevo, en journal_mode=DELETE (un solo archivo: lo exige
    la comprobación del respaldo declarado de un paso guiado) y verificada con integrity_check. Lanza
    sqlite3.Error/OSError sin dejar archivo a medias."""
    with open(dst_path, "xb"):                  # archivo nuevo de esta corrida
        pass
    dst = None
    try:
        dst = sqlite3.connect(dst_path)
        con.backup(dst)
        mode = dst.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if str(mode).lower() != "delete":
            raise sqlite3.DatabaseError(f"la copia quedó en journal_mode={mode}")
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if ok != "ok":
            raise sqlite3.DatabaseError(f"integrity_check de la copia: {ok}")
        dst.close()
        dst = None
    except BaseException:
        if dst is not None:
            dst.close()
        for f in (dst_path,) + tuple(dst_path + s for s in SIDECARS):
            _remove_quiet(f)
        raise
    try:
        os.chmod(dst_path, 0o600)
    except OSError:
        pass
    return dst_path


def _back_to_wal(path):
    """Deja la base otra vez en WAL tras un aborto posterior al cambio a DELETE (sin espera; si otra conexión lo
    impide, la siguiente conexión de neb la regresa a WAL)."""
    try:
        c = sqlite3.connect(path, timeout=0)
        try:
            c.execute("PRAGMA journal_mode=WAL")
        finally:
            c.close()
    except sqlite3.Error:
        pass


def _precheck(src, dst):
    """Revisión solo con os.path: ('ok', None) si se puede mudar; ('nada'|'aborto', mensaje) si no."""
    src_size = _size(src)
    if src_size is None and not os.path.lexists(src):
        return "nada", f"no hay {src} que mudar. Nada que hacer."
    if is_link(src) or src_size is None:
        return "aborto", (f"{src} no es un archivo regular (es un enlace o una carpeta): la mudanza no lo sigue. "
                          "Muévelo a mano. No se tocó nada.")
    if src_size == 0:
        return "nada", f"{src} está vacío (0 bytes): no hay datos que mudar. No se tocó nada."
    if os.path.lexists(dst) and (is_link(dst) or not os.path.isfile(dst)):
        return "aborto", f"{dst} existe y no es un archivo regular: la mudanza no lo pisa. No se tocó nada."
    dst_size = _size(dst)
    if dst_size:
        return "aborto", f"ya existe {dst} ({dst_size} bytes) y la mudanza no lo pisa. No se tocó nada."
    found = sidecars(dst)
    if found:
        return "aborto", (f"existen archivos auxiliares de {dst} ({', '.join(found)}): muévelos fuera de "
                          f"{os.path.dirname(dst)} y vuelve a correr. No se tocó nada.")
    return "ok", None


def _work_count(path):
    con = sqlite3.connect(path, timeout=0)
    try:
        return con.execute("SELECT count(*) FROM work").fetchone()[0]
    finally:
        con.close()


def _copy_across(src, dst, fp, witness, busy_msg):
    """Mudanza entre volúmenes (EXDEV). None si quedó hecha; (codigo, mensaje) si no, con el origen intacto y sin
    copia en el destino."""
    tmp = os.path.join(os.path.dirname(os.path.abspath(dst)), f".{os.path.basename(dst)}.tmp-{_stamp()}")
    try:
        c = sqlite3.connect(src, timeout=0, isolation_level=None)
        try:
            c.execute("BEGIN")
            n = c.execute("SELECT count(*) FROM work").fetchone()[0]        # lectura retenida durante la copia
            if _fingerprint(src) != fp:
                c.execute("ROLLBACK")
                return "ocupada", f"{src} cambió después del respaldo: otra conexión escribió en ella. {busy_msg}"
            backup_sqlite(c, tmp)
            c.execute("COMMIT")
        finally:
            c.close()
        if _db_shared._probe_db(tmp) != "usable" or _work_count(tmp) != n:
            raise sqlite3.DatabaseError("la copia no quedó igual a la base")
        os.replace(tmp, dst)                     # mismo volumen que el destino
    except (OSError, sqlite3.Error) as e:
        for f in (tmp,) + tuple(tmp + s for s in SIDECARS):
            _remove_quiet(f)
        if isinstance(e, sqlite3.Error) and _busy(e):
            return "ocupada", f"no se pudo copiar {src} ({e}): {busy_msg}"
        return "error", f"la copia a otro volumen falló ({e}). {src} sigue en su lugar."
    # Retiro del origen: solo si nadie lo tocó desde el respaldo.
    try:
        unchanged = not sidecars(src) and _fingerprint(src) == fp
    except OSError:
        unchanged = False
    if not unchanged:
        _remove_quiet(dst)
        return "ocupada", f"{src} cambió mientras se copiaba: otra conexión la abrió. {busy_msg}"
    try:
        if witness:
            os.replace(witness, src)             # la testigo reemplaza al origen en un solo paso
        else:
            os.remove(src)
    except OSError as e:
        _remove_quiet(dst)
        return "ocupada", f"no se pudo retirar {src} tras copiarla ({e}): {busy_msg}"
    return None


def move_db(src, dst, backup_path, witness=None):
    """Mueve la base `src` a `dst` (ver el encabezado del módulo). `backup_path`: el respaldo nuevo que se saca antes
    de mover. `witness`: una base testigo ya creada en la carpeta de `src` (write_witness), que ocupa el lugar de
    `src` en cuanto la base sale de ahí. Devuelve _result; nunca levanta por un error de archivo o de SQLite."""
    code, msg = _precheck(src, dst)
    if code != "ok":
        return _result(code, msg)
    busy_msg = ("otra sesión o proceso la usa: no se movió; se reintenta cuando nadie más la tenga abierta "
                "(siguiente inicio de sesión o /neb:migrate).")
    try:
        con = sqlite3.connect(src, timeout=0, isolation_level=None)
    except sqlite3.Error as e:
        return _result("error", f"no se pudo abrir {src} ({e}). No se tocó nada.")
    switched = False
    bak = fp = None
    try:
        try:
            con.execute("SELECT count(*) FROM work").fetchone()
            mode = str(con.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        except sqlite3.Error as e:
            if _busy(e):
                return _result("ocupada", f"no se pudo tomar {src} ({e}): {busy_msg}")
            return _result("aborto", f"{src} no es una base usable de la bitácora ({e}) y no se muda. Muévelo fuera "
                                     f"de {os.path.dirname(src)} (no lo borres sin revisarlo): neb crea una base "
                                     "nueva en la carpeta de datos. No se tocó nada.")
        if mode == "wal":
            row = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if row is None or row[0] == 1 or row[1] != row[2]:
                return _result("ocupada", f"wal_checkpoint(TRUNCATE) devolvió {row}: {busy_msg}")
            got = con.execute("PRAGMA journal_mode=DELETE").fetchone()
            if got is None or str(got[0]).lower() != "delete":
                return _result("ocupada", f"journal_mode quedó en {got}: otra conexión tiene abierta la base. "
                                          f"{busy_msg}")
            switched = True
        con.execute("BEGIN")
        con.execute("SELECT count(*) FROM work").fetchone()     # lectura retenida: nadie confirma escrituras
        try:
            backup_sqlite(con, backup_path)
        except (OSError, sqlite3.Error) as e:
            return _result("error", f"falló el respaldo ({e}). {src} sigue intacta en su lugar.")
        bak = backup_path
        fp = _fingerprint(src)
        con.execute("COMMIT")
        con.execute("BEGIN EXCLUSIVE")
        con.execute("ROLLBACK")
    except (sqlite3.Error, OSError) as e:
        _remove_quiet(bak)
        bak = None
        if isinstance(e, sqlite3.Error) and _busy(e):
            return _result("ocupada", f"no se pudo tomar {src} ({e}): {busy_msg}")
        return _result("error", f"en el checkpoint o el respaldo ({e}). {src} sigue en su lugar.")
    finally:
        con.close()
        if switched and bak is None:
            _back_to_wal(src)

    def undo(codigo, mensaje):
        _remove_quiet(bak)
        _back_to_wal(src)
        return _result(codigo, mensaje)

    found = sidecars(src, dst)
    if found:
        return undo("ocupada", f"aparecieron archivos auxiliares ({', '.join(found)}): otra conexión abrió la base. "
                               f"{busy_msg}")
    if _size(dst):
        return undo("aborto", f"apareció {dst} ({_size(dst)} bytes) durante la mudanza. No se movió nada.")
    try:
        unchanged = _fingerprint(src) == fp
    except OSError:
        unchanged = False
    if not unchanged:
        return undo("ocupada", f"{src} cambió después del respaldo: otra conexión escribió en ella. {busy_msg}")

    modo, aviso = "replace", None
    try:
        os.replace(src, dst)
    except OSError as e:
        if e.errno != errno.EXDEV:
            return undo("ocupada", f"no se pudo mover {src} -> {dst} ({e}). {busy_msg}")
        modo = "copia"
        failed = _copy_across(src, dst, fp, witness, busy_msg)
        if failed:
            return undo(*failed)
    if modo == "replace" and witness:
        try:
            os.replace(witness, src)             # de inmediato: una sesión vieja ya no encuentra el lugar vacío
        except OSError as e:
            aviso = (f"no se pudo dejar la base testigo en {src} ({e}): una sesión abierta con una versión anterior "
                     "de neb puede crear ahí una base vacía y capturar en ella; el siguiente inicio de sesión lo "
                     "detecta.")

    state = _db_shared._probe_db(dst)
    if state in ("sin-work", "no-base", "vacia", "ausente"):
        if modo == "replace":
            try:
                os.replace(dst, src)             # devuelve la base a su lugar (pisa la testigo)
                return _result("error", f"{dst} no resultó usable tras moverla ({state}); se devolvió a {src}. "
                                        f"Respaldo en {bak}.", bak)
            except OSError as e:
                return _result("error", f"{dst} no resultó usable ({state}) y no se pudo devolver a {src} ({e}). "
                                        f"Respaldo en {bak}.", bak)
        return _result("error", f"{dst} no resultó usable tras copiarla ({state}). Respaldo en {bak}.", bak)
    notes = [aviso] if aviso else []
    if state != "usable":
        notes.append(f"{dst} quedó en su lugar pero la verificación dio '{state}' (otra conexión la abrió); no la "
                     "muevas.")
    else:
        try:
            c = sqlite3.connect(dst, timeout=0)
            try:
                wal = c.execute("PRAGMA journal_mode=WAL").fetchone()
            finally:
                c.close()
            if wal is None or str(wal[0]).lower() != "wal":
                notes.append(f"{dst} quedó en journal_mode={wal}; la primera conexión de neb la pasa a WAL.")
        except sqlite3.Error as e:
            notes.append(f"{dst} quedó en journal_mode=DELETE ({e}); la primera conexión de neb la pasa a WAL.")
    how = " (entre volúmenes: copia verificada y retiro del origen)" if modo == "copia" else ""
    return _result("ok", f"OK: {src} -> {dst}{how}.", bak, " ".join(notes) or None, modo)


# =========================================================================== mover archivos

def walk_files(root):
    """Rutas relativas de los archivos regulares bajo `root`, sin seguir enlaces (un enlace, a archivo o carpeta,
    se omite). Sin `root`, o si `root` es un enlace, vacío."""
    if is_link(root) or not os.path.isdir(root):
        return []
    out = []

    def walk(rel):
        try:
            entries = list(os.scandir(os.path.join(root, rel) if rel else root))
        except OSError:
            return
        for e in sorted(entries, key=lambda x: x.name):
            r = os.path.join(rel, e.name) if rel else e.name
            if is_link(e.path):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    walk(r)
                elif e.is_file(follow_symlinks=False):
                    out.append(r)
            except OSError:
                continue
    walk("")
    return out


def tree_pairs(src_root, dst_root):
    """[(origen, destino)] de cada archivo regular bajo src_root, al mismo lugar relativo bajo dst_root."""
    if same_path(src_root, dst_root):
        return []
    return [(os.path.join(src_root, r), os.path.join(dst_root, r)) for r in walk_files(src_root)]


def same_content(a, b):
    """True si los dos archivos tienen los mismos bytes."""
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                ca, cb = fa.read(_COPY_CHUNK), fb.read(_COPY_CHUNK)
                if ca != cb:
                    return False
                if not ca:
                    return True
    except OSError:
        return False


def plan_moves(pairs, newer_wins=False):
    """Clasifica cada (origen, destino) de archivos regulares: dict de listas
       mover        el destino no existe
       iguales      el destino tiene los mismos bytes: se quita el origen
       conflictos   el destino es distinto (o no es un archivo regular): nada se toca
       reemplazar   con newer_wins, el origen es más nuevo: reemplaza al destino
       descartar    con newer_wins, el destino es más nuevo: se quita el origen
    Cada elemento: {"origen", "destino", "bytes"}. Solo lee."""
    out = {"mover": [], "iguales": [], "conflictos": [], "reemplazar": [], "descartar": []}
    for src, dst in pairs:
        if same_path(src, dst) or is_link(src) or not os.path.isfile(src):
            continue
        row = {"origen": src, "destino": dst, "bytes": _size(src)}
        if not os.path.lexists(dst):
            out["mover"].append(row)
        elif is_link(dst) or not os.path.isfile(dst):
            out["conflictos"].append(row)
        elif same_content(src, dst):
            out["iguales"].append(row)
        elif newer_wins:
            try:
                newer = os.path.getmtime(src) > os.path.getmtime(dst)
            except OSError:
                newer = False
            out["reemplazar" if newer else "descartar"].append(row)
        else:
            out["conflictos"].append(row)
    return out


def _write_new_json(path, payload):
    """Archivo nuevo (falla si existe) con permiso solo para el usuario donde el sistema lo respeta."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())


def write_json_atomic(path, payload):
    """Reemplaza `path` de un solo paso (temporal en la misma carpeta + os.replace). No escribe a través de un
    enlace."""
    if is_link(path):
        raise ValueError(f"{path} es un enlace: Neb no escribe a través de enlaces")
    folder = os.path.dirname(os.path.abspath(path))
    tmp = os.path.join(folder, f".{os.path.basename(path)}.tmp-{_stamp()}")
    try:
        _write_new_json(tmp, payload)
        os.replace(tmp, path)
    except BaseException:
        _remove_quiet(tmp)
        raise


def _move_no_clobber(src, dst):
    """Mueve sin pisar: FileExistsError si el destino existe; OSError con errno EXDEV entre volúmenes. En Windows
    os.rename no reemplaza; fuera, un enlace duro + borrado (falla si el destino existe) y, sin enlaces duros en ese
    sistema de archivos, os.rename tras comprobar que el destino no existe."""
    if os.name == "nt":
        os.rename(src, dst)
        return
    try:
        os.link(src, dst)
    except OSError as e:
        if e.errno in (errno.EEXIST, errno.EXDEV):
            raise
        if os.path.lexists(dst):
            raise FileExistsError(errno.EEXIST, "el destino existe", dst)
        os.rename(src, dst)
        return
    os.unlink(src)


def _copy_then_remove(src, dst, overwrite=False):
    """Entre volúmenes: copia a un temporal junto al destino, verifica el tamaño, lo pone en su lugar (sin pisar,
    salvo `overwrite`) y borra el origen."""
    tmp = os.path.join(os.path.dirname(os.path.abspath(dst)), f".{os.path.basename(dst)}.tmp-{_stamp()}")
    try:
        shutil.copy2(src, tmp)
        if os.path.getsize(tmp) != os.path.getsize(src):
            raise OSError(errno.EIO, "la copia no tiene el tamaño del original", tmp)
        if overwrite:
            os.replace(tmp, dst)
        else:
            _move_no_clobber(tmp, dst)
    except BaseException:
        _remove_quiet(tmp)
        raise
    os.remove(src)


def _move_one(src, dst, overwrite=False):
    try:
        if overwrite:
            os.replace(src, dst)
        else:
            _move_no_clobber(src, dst)
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
        _copy_then_remove(src, dst, overwrite=overwrite)


def _prune_empty_dirs(roots, keep):
    """Borra, de abajo hacia arriba, las carpetas vacías bajo cada raíz (y la raíz) que la mudanza dejó; nunca una
    de `keep` ni un enlace."""
    keep_n = {os.path.normcase(os.path.abspath(k)) for k in keep}
    for root in roots:
        if is_link(root) or not os.path.isdir(root):
            continue
        dirs = []
        for cur, subdirs, _files in os.walk(root, topdown=True, followlinks=False):
            subdirs[:] = [d for d in subdirs if not is_link(os.path.join(cur, d))]
            dirs.append(cur)
        for d in sorted(dirs, key=len, reverse=True):
            if os.path.normcase(os.path.abspath(d)) in keep_n:
                continue
            try:
                os.rmdir(d)                      # solo si está vacía
            except OSError:
                pass


def apply_moves(pairs, manifest_path, step, dst_root, newer_wins=False, prune=(), keep=()):
    """Mueve lo que plan_moves deja mover, con su manifiesto. `dst_root`: la carpeta bajo la que caen los destinos
    (se crea, sin enlaces, nivel por nivel). `prune`: carpetas de origen que se borran si quedan vacías (nunca las
    de `keep`). Devuelve {"manifiesto", "movidos", "iguales", "reemplazados", "descartados", "conflictos",
    "fallos"} (listas de filas {"origen", "destino", "bytes"[, "motivo"]}); "manifiesto" es None si no hubo nada
    que hacer. Lanza OSError/ValueError solo si no se pudo escribir el manifiesto (entonces no se movió nada)."""
    p = plan_moves(pairs, newer_wins)
    res = {"manifiesto": None, "movidos": [], "iguales": [], "reemplazados": [], "descartados": [],
           "conflictos": list(p["conflictos"]), "fallos": []}
    if not (p["mover"] or p["iguales"] or p["reemplazar"] or p["descartar"]):
        return res
    entries = ([dict(r, accion="mover") for r in p["mover"]]
               + [dict(r, accion="quitar-origen-igual") for r in p["iguales"]]
               + [dict(r, accion="reemplazar-por-el-mas-nuevo") for r in p["reemplazar"]]
               + [dict(r, accion="quitar-origen-mas-viejo") for r in p["descartar"]])
    manifest = {"paso": step, "creado": _now(), "estado": "en-curso",
                "deshacer": "mover cada «destino» de vuelta a su «origen»; las entradas quitar-origen-* no se "
                            "deshacen (el destino tenía los mismos bytes, o era más nuevo)",
                "entradas": entries, "conflictos": p["conflictos"]}
    _write_new_json(manifest_path, manifest)
    res["manifiesto"] = manifest_path

    def prepare(dst):
        folder = os.path.dirname(os.path.abspath(dst))
        try:
            rel = os.path.relpath(folder, os.path.abspath(dst_root))
        except ValueError:                       # otra unidad (Windows)
            rel = os.pardir
        if rel == os.pardir or rel.startswith(os.pardir + os.sep):
            neb_paths.ensure_dir(folder)         # fuera de dst_root: solo se revisa la carpeta final
        else:
            ensure_tree(dst_root, "" if rel == os.curdir else rel)

    for row in p["mover"]:
        try:
            prepare(row["destino"])
            _move_one(row["origen"], row["destino"])
            res["movidos"].append(row)
        except FileExistsError:
            res["conflictos"].append(row)        # apareció en el destino entre el plan y el movimiento
        except (OSError, ValueError) as e:
            res["fallos"].append(dict(row, motivo=f"{type(e).__name__}: {getattr(e, 'strerror', '') or e}"))
    for row in p["iguales"]:
        try:
            if same_path(row["origen"], row["destino"]):
                continue                         # el mismo archivo por otra ruta: borrarlo sería borrar el único
            if same_content(row["origen"], row["destino"]):
                os.remove(row["origen"])
                res["iguales"].append(row)
            else:
                res["conflictos"].append(row)
        except OSError as e:
            res["fallos"].append(dict(row, motivo=f"{type(e).__name__}: {getattr(e, 'strerror', '') or e}"))
    for row in p["reemplazar"]:
        try:
            prepare(row["destino"])
            _move_one(row["origen"], row["destino"], overwrite=True)
            res["reemplazados"].append(row)
        except (OSError, ValueError) as e:
            res["fallos"].append(dict(row, motivo=f"{type(e).__name__}: {getattr(e, 'strerror', '') or e}"))
    for row in p["descartar"]:
        try:
            if row.get("destino") and same_path(row["origen"], row["destino"]):
                continue                         # el mismo archivo por otra ruta: no se descarta el único
            os.remove(row["origen"])
            res["descartados"].append(row)
        except OSError as e:
            res["fallos"].append(dict(row, motivo=f"{type(e).__name__}: {getattr(e, 'strerror', '') or e}"))
    _prune_empty_dirs(prune, keep)
    manifest.update(estado="hecho", terminado=_now(),
                    **{k: res[k] for k in ("movidos", "iguales", "reemplazados", "descartados", "conflictos",
                                           "fallos")})
    try:
        write_json_atomic(manifest_path, manifest)
    except (OSError, ValueError):
        pass                                     # queda el manifiesto «en-curso», con todo lo planeado
    return res
