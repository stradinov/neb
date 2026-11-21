"""
Migración guiada de neb 7.0.0: cambio de nombre de la base y retiro de la configuración del backend central.

Prompt: migrations/7.0.0.md. Formato: migrations/README.md. Residuo de transición: sale en 8.0.0.
"""

import glob
import importlib.util
import os
import sys
import types

from _guided import GuidedStep, base_sin_otras_conexiones

_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_LIB = os.path.join(_ROOT, "hooks", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, _LIB)

LEGACY_NAME = "neb-logbook.db"
TOKEN = "NEB_LOGBOOK_TOKEN"
BAK_GLOB = "settings.json.bak-neb-*"
BAK_MAX_FILES = 200                 # tope de archivos que se revisan
BAK_MAX_BYTES = 1024 * 1024         # tope de bytes que se leen de cada uno


# --------------------------------------------------------------------------- renombrar-base

def _legacy_ctx(ctx):
    return types.SimpleNamespace(db_path=os.path.join(ctx.claude_dir, LEGACY_NAME))


def _sin_migrar(ctx):
    import _db_shared
    return _db_shared.unmigrated_legacy(ctx.home) is not None


def _base_vieja_libre(ctx):
    """Condición de exclusivo sobre neb-logbook.db (la de omisión mira neb.db, que todavía no existe): que
    ninguna otra conexión la tenga abierta en este momento. El migrador la vuelve a comprobar con su propio
    candado (journal_mode=DELETE, lectura retenida durante el respaldo y BEGIN EXCLUSIVE justo antes del
    cambio de nombre).

    Si neb-logbook.db no es una base SQLite, la prueba de exclusividad fallaría siempre y el paso pediría
    cerrar sesiones para siempre: la condición se da por cumplida y el migrador la rechaza con su motivo."""
    legacy = _legacy_ctx(ctx)
    try:
        with open(legacy.db_path, "rb") as fh:
            if fh.read(16) != b"SQLite format 3\x00":
                return None
    except OSError:
        return None
    return base_sin_otras_conexiones(legacy)


def _migrator():
    spec = importlib.util.spec_from_file_location("neb_migrate_neb_db_700",
                                                  os.path.join(_ROOT, "bootstrap", "migrate-neb-db.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _renombrar(ctx):
    motivo = ctx.exclusivo_ok()
    if motivo:
        return {"estado": "pendiente", "detalle": motivo}
    r = _migrator().rename(ctx.home)
    detalle = " ".join(x for x in (r["mensaje"], r["aviso"]) if x)
    if r["codigo"] == "ok":
        if r["escribio"]:
            return {"estado": "manual", "respaldo": r["respaldo"], "detalle": detalle}
        return {"respaldo": r["respaldo"], "detalle": detalle}
    if r["codigo"] == "nada":
        return {"estado": "sin-cambio", "detalle": detalle}
    if r["codigo"] == "ocupada":
        return {"estado": "pendiente", "detalle": detalle}
    if r["codigo"] == "aborto":
        return {"estado": "manual", "detalle": detalle}
    return {"estado": "fallo", "respaldo": r["respaldo"], "detalle": detalle}


# --------------------------------------------------------------------------- respaldos de settings.json

def _bak_todos(ctx):
    """Los settings.json.bak-neb-* del dir de configuración; el dir va escapado para que un `[` en la ruta no sea patrón."""
    return sorted(glob.glob(os.path.join(glob.escape(ctx.config_dir), BAK_GLOB)))


def _bak_con_token(ctx):
    """Respaldos settings.json.bak-neb-* del dir de configuración que traen el texto NEB_LOGBOOK_TOKEN. Busca el
    nombre como texto, sin parsear el archivo ni leer el valor, con tope de archivos y de bytes por archivo."""
    out = []
    for path in _bak_todos(ctx)[:BAK_MAX_FILES]:
        try:
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            with open(path, "rb") as fh:
                if TOKEN.encode("ascii") in fh.read(BAK_MAX_BYTES):
                    out.append(path)
        except OSError:
            continue
    return out


def _hay_bak_con_token(ctx):
    """Pendiente si alguno trae el token o si hay más respaldos que el tope (los de más no se revisaron)."""
    return bool(_bak_con_token(ctx)) or len(_bak_todos(ctx)) > BAK_MAX_FILES


def _borrar_bak(ctx):
    found = _bak_con_token(ctx)
    failed = 0
    for path in found:
        try:
            os.remove(path)
        except OSError:
            failed += 1
    if failed:
        return {"estado": "fallo", "detalle": f"no se pudieron borrar {failed} de {len(found)} respaldos"}
    if len(_bak_todos(ctx)) > BAK_MAX_FILES:
        return {"estado": "manual", "detalle": f"borrados {len(found)} respaldos que traían {TOKEN}; hay más de "
                                                f"{BAK_MAX_FILES} respaldos settings.json.bak-neb-*: se revisaron los "
                                                f"primeros {BAK_MAX_FILES}; revisa a mano los demás"}
    return {"detalle": f"borrados {len(found)} respaldos settings.json.bak-neb-* que traían {TOKEN}"}


STEPS = [
    GuidedStep("renombrar-base", "Cambiar el nombre de la base de neb-logbook.db a neb.db",
               detectar=_sin_migrar, aplicar=_renombrar, respaldo=True, exclusivo=True,
               condicion=_base_vieja_libre),
    GuidedStep("quitar-logbook-settings", "Quitar NEB_LOGBOOK_ENDPOINT y NEB_LOGBOOK_TOKEN de settings.json",
               op="settings_env_remove",
               args={"claves": ["NEB_LOGBOOK_ENDPOINT", TOKEN], "secretas": [TOKEN]}),
    GuidedStep("quitar-endpoint-entorno", "Quitar la variable de usuario NEB_LOGBOOK_ENDPOINT",
               op="user_env_remove", args={"nombre": "NEB_LOGBOOK_ENDPOINT"}),
    GuidedStep("quitar-token-entorno", "Quitar la variable de usuario NEB_LOGBOOK_TOKEN",
               op="user_env_remove", args={"nombre": TOKEN}),
    GuidedStep("borrar-respaldos-settings",
               "Borrar los respaldos settings.json.bak-neb-* que traen NEB_LOGBOOK_TOKEN",
               detectar=_hay_bak_con_token, aplicar=_borrar_bak),
]
