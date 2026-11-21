"""Sin registro real de Windows en las pruebas: la migración guiada de 7.0.0 detecta variables de usuario
(`user_env_remove`), y el arranque y `neb-migrate.py` la recorren con el árbol real. Importarlo cambia
`winreg` por uno que no encuentra ninguna clave (WindowsUserEnv responde «no está» y no borra nada), en este
proceso y, por PYTHONPATH, en cada subproceso de Python que lancen las pruebas."""
import os
import sys
import types

_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "sin_registro")


def _sin_clave(*_a, **_k):
    raise FileNotFoundError("registro no disponible en las pruebas")


_fake = types.ModuleType("winreg")
_fake.__dict__.update(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2, KEY_QUERY_VALUE=1, KEY_SET_VALUE=2, KEY_READ=3,
                      OpenKey=_sin_clave, OpenKeyEx=_sin_clave, QueryValueEx=_sin_clave, DeleteValue=_sin_clave,
                      SetValueEx=_sin_clave, EnumKey=_sin_clave, EnumValue=_sin_clave, CloseKey=lambda *_a: None)
sys.modules["winreg"] = _fake

_paths = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
if _FIXTURE not in _paths:
    os.environ["PYTHONPATH"] = os.pathsep.join([_FIXTURE] + _paths)
