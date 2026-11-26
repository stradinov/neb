"""Entorno aislado para las pruebas que tocan la carpeta de datos de Neb (8.0.0).

Importarlo quita NEB_DATA del entorno de este proceso (y, por herencia, de cada subproceso): si el dev la
declaró en el `env` de settings.json, el Bash de Claude la hereda y una prueba con HOME temporal escribiría
igual en su carpeta de datos real. Toda prueba que fije HOME/USERPROFILE debe importarlo.

    import _entorno
    home = _entorno.home_temporal(self)          # <home>/.claude y <home>/.neb no se crean
    env = _entorno.env_con_home(home)            # para subprocesos: HOME/USERPROFILE, sin NEB_DATA
    with _entorno.home_en_proceso(home): ...     # HOME/USERPROFILE del proceso, sin NEB_DATA
"""
import contextlib
import os
import shutil
import tempfile
from unittest import mock

DATA_ENV = "NEB_DATA"

os.environ.pop(DATA_ENV, None)


def home_temporal(test_case=None, claude=False, neb=False):
    """Home temporal; con `claude`/`neb` crea <home>/.claude y/o <home>/.neb. Con `test_case`, se borra al
    terminar la prueba."""
    home = tempfile.mkdtemp(prefix="neb-home-")
    if claude:
        os.makedirs(os.path.join(home, ".claude"))
    if neb:
        os.makedirs(os.path.join(home, ".neb"))
    if test_case is not None:
        test_case.addCleanup(shutil.rmtree, home, True)
    return home


def env_con_home(home, base=None, **extra):
    """Copia del entorno (o de `base`) con HOME y USERPROFILE en `home`, sin NEB_DATA ni CLAUDE_CONFIG_DIR,
    más `extra` (un valor None quita la variable)."""
    env = dict(os.environ if base is None else base)
    env.pop(DATA_ENV, None)
    env.pop("CLAUDE_CONFIG_DIR", None)
    env.update(HOME=home, USERPROFILE=home)
    for key, value in extra.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


@contextlib.contextmanager
def home_en_proceso(home, **extra):
    """HOME/USERPROFILE del proceso en `home` mientras dura el bloque, sin NEB_DATA salvo que `extra` la fije."""
    values = {"HOME": home, "USERPROFILE": home}
    values.update({k: v for k, v in extra.items() if v is not None})
    with mock.patch.dict(os.environ, values):
        if DATA_ENV not in values:                 # NEB_DATA=<ruta> en `extra` la fija; si no, se quita
            os.environ.pop(DATA_ENV, None)
        for key, value in extra.items():
            if value is None:
                os.environ.pop(key, None)
        yield
