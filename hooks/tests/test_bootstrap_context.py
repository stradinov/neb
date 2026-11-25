#!/usr/bin/env python3
"""test_bootstrap_context.py — el arranque en partes (bootstrap/neb-bootstrap-context.py, PD-742).

La plataforma topa cada salida de hook en 10,000 caracteres (supuesto R1); el arranque sale en partes de
LIMIT unidades UTF-16 o menos, una por entrada de hooks/hooks.json:
  • split_parts: sin pérdida, cada parte con su cabecera dentro de LIMIT, sin cortar un bloque de código,
    corte duro de una línea larga, caracteres fuera del BMP, desbordamiento con lugar para el aviso
  • el script como lo corre el hook: --part k reconstruye la salida completa con la misma huella y sin CR;
    parte fuera de rango, `neb: skip` y la subsesión interna no emiten nada; el aviso va en la última
  • --check-size (gate 6 del pre-push): pasa sobre el repo y falla con un núcleo inflado, en partes o en caracteres
  • main() dentro del proceso, con un stdout sin `.buffer`
  • la oferta de actualización automática (hooks/lib/autoupdate.py): desde un caché simulado, sin decidir
    avisa en la parte 1 y no escribe; decidido sale igual que fuera del caché; el tope del aviso; con los
    cuatro avisos el arranque cabe
  • la base sin migrar (solo neb-logbook.db, no vacío) sale en el aviso de migración guiada pendiente como
    el paso de 7.0.0, sin crear neb.db; ausente con neb.db o con la base vieja vacía; el arranque no abre
    la base vieja (sqlite3.connect)

Framework: unittest (stdlib). Árboles, workspaces y HOME/USERPROFILE temporales; nunca toca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_bootstrap_context.py
"""
import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sin_registro  # noqa: E402,F401 — sin el registro real de Windows
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
NEB = os.path.abspath(os.path.join(HERE, "..", ".."))
SCRIPT = os.path.join(NEB, "bootstrap", "neb-bootstrap-context.py")

_spec = importlib.util.spec_from_file_location("neb_bootstrap_context", SCRIPT)
nb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nb)

HEADER_RE = re.compile(r"^# Arranque de Neb — parte (\d+) de (\d+) · huella ([0-9a-f]{8})\n\n")
CLEAN = ("NEB_HOME", "CLAUDE_PLUGIN_ROOT", "NEB_WORKSPACE", "NEB_HOOKS", "NEB_PROJECT_HOOKS",
         "NEB_INTERNAL_SUBSESSION", "CLAUDE_PREPROCESS_RECURSION", "CLAUDE_PROJECT_DIR",
         "CLAUDE_CODE_PLUGIN_CACHE_DIR")


def _tmp_home(test):
    """HOME y USERPROFILE temporales (en Windows expanduser lee USERPROFILE): el aviso de base sin migrar
    no depende de la máquina."""
    home = tempfile.mkdtemp(prefix="neb-test-home-")
    test.addCleanup(shutil.rmtree, home, True)
    return {"HOME": home, "USERPROFILE": home}


def u16(s):
    return len(s.encode("utf-16-le")) // 2


def seccion(titulo, subsecciones, largo):
    parrafo = ("Relleno con acentos: canción, año, pingüino. " * (largo // 40 + 1))[:largo]
    return "# %s\n\n" % titulo + "".join("## Sub %d\n\n%s\n\n" % (i, parrafo) for i in range(subsecciones))


class TestSplit(unittest.TestCase):

    def assertPartes(self, text, parts, rest=""):
        self.assertEqual("".join(parts) + rest, text)
        header = u16(nb.HEADER % (99, 99, "f" * 8))
        for p in parts:
            self.assertLessEqual(header + u16(p), nb.LIMIT)

    def test_sin_perdida_y_dentro_del_limite(self):
        text = "".join(seccion("S%d" % i, 5, 1500) for i in range(6))
        parts, rest = nb.split_parts(text)
        self.assertEqual(rest, "")
        self.assertGreater(len(parts), 1)
        self.assertPartes(text, parts)

    def test_corta_en_secciones_cuando_caben(self):
        text = "".join(seccion("S%d" % i, 2, 1500) for i in range(8))
        parts, _ = nb.split_parts(text)
        for p in parts:
            self.assertTrue(p.startswith("# S"), p[:20])

    def test_no_corta_dentro_de_un_bloque_de_codigo(self):
        codigo = "```bash\n" + "".join("# comentario %d\necho %d\n" % (i, i) for i in range(120)) + "```\n"
        text = seccion("A", 3, 2000) + codigo + "\n" + seccion("B", 3, 2000)
        start = text.index("```bash")
        end = text.index("```\n", start + 3) + 4
        parts, _ = nb.split_parts(text)
        self.assertPartes(text, parts)
        pos = 0
        for p in parts[:-1]:
            pos += len(p)
            self.assertFalse(start < pos < end, "corte dentro del bloque de código en %d" % pos)

    def test_corte_duro_de_una_linea_larga(self):
        text = "# Larga\n\n" + "a" * 25000 + "\n"
        parts, _ = nb.split_parts(text)
        self.assertGreaterEqual(len(parts), 3)
        self.assertPartes(text, parts)

    def test_fuera_del_bmp_cuenta_doble(self):
        text = "# Emoji\n\n" + "\U0001F6A8" * 6000 + "\n"
        self.assertEqual(u16("\U0001F6A8"), 2)
        parts, _ = nb.split_parts(text)
        self.assertGreaterEqual(len(parts), 2)
        self.assertPartes(text, parts)

    def test_desbordamiento_deja_lugar_al_aviso(self):
        text = "".join("# S%d\n\n%s\n\n" % (i, "x" * 8000) for i in range(15))
        parts, rest = nb.split_parts(text)
        self.assertEqual(len(parts), nb.MAX_PARTS)
        self.assertTrue(rest)
        self.assertPartes(text, parts, rest)
        self.assertLessEqual(u16(parts[-1]), nb._body_budget() - nb.NOTICE_RESERVE)


class TestPartesDelArranque(unittest.TestCase):
    """El script como lo corre cada entrada de hooks/hooks.json."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="neb-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home_env = _tmp_home(self)

    def _run(self, *args, **env):
        e = {k: v for k, v in os.environ.items() if k not in CLEAN}
        e["NEB_HOME"] = NEB
        e.update(self.home_env)
        e.update(env)
        r = subprocess.run([sys.executable, SCRIPT] + [str(a) for a in args], env=e,
                           capture_output=True, timeout=60)
        return r.returncode, r.stdout.decode("utf-8"), r.stderr.decode("utf-8")

    def _out(self, *args, **env):
        rc, out, err = self._run(*args, **env)
        self.assertEqual(rc, 0, err)
        return out

    def _partes(self, **env):
        return [self._out("--part", k, **env) for k in range(1, nb.MAX_PARTS + 1)]

    def test_las_partes_reconstruyen_el_arranque(self):
        full = self._out()
        outs = self._partes()
        llenas = [o for o in outs if o]
        self.assertTrue(all(outs[:len(llenas)]), "las partes con contenido van primero")
        self.assertGreater(len(llenas), 1)
        cuerpos, n, huellas = [], set(), set()
        for k, o in enumerate(llenas, 1):
            m = HEADER_RE.match(o)
            self.assertIsNotNone(m, o[:80])
            self.assertEqual(int(m.group(1)), k)
            n.add(int(m.group(2)))
            huellas.add(m.group(3))
            self.assertNotIn("\r", o)
            self.assertLessEqual(u16(o), nb.LIMIT)
            cuerpos.append(o[m.end():])
        self.assertEqual(n, {len(llenas)})
        self.assertEqual(huellas, {nb.fingerprint(full)})
        self.assertEqual("".join(cuerpos), full)

    def test_parte_fuera_de_rango_no_emite(self):
        for arg in (nb.MAX_PARTS + 1, 0, "x"):
            self.assertEqual(self._out("--part", arg), "")

    def test_neb_skip_y_subsesion_no_emiten(self):
        with open(os.path.join(self.tmp, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("# Proyecto\n\n<!-- neb: skip -->\n")
        self.assertEqual(self._partes(CLAUDE_PROJECT_DIR=self.tmp), [""] * nb.MAX_PARTS)
        self.assertEqual(self._out("--part", 1, NEB_INTERNAL_SUBSESSION="1"), "")

    def test_desbordamiento_avisa_en_la_ultima(self):
        ov = os.path.join(self.tmp, "ws", "ov")
        os.makedirs(os.path.join(ov, "overlays"))
        open(os.path.join(ov, "overlays", "detect-profile.local.sh"), "w").close()
        with open(os.path.join(ov, "startup.md"), "w", encoding="utf-8") as f:
            f.write("".join("# Extensión %d\n\n%s\n\n" % (i, "y" * 8000) for i in range(15)))
        ws = os.path.join(self.tmp, "ws")
        ultima = self._out("--part", nb.MAX_PARTS, NEB_WORKSPACE=ws)
        self.assertIn("**Aviso de Neb (entorno):** el arranque no cupo en %d partes" % nb.MAX_PARTS, ultima)
        self.assertIn("overlay del adoptante", ultima)
        self.assertLessEqual(u16(ultima), nb.LIMIT)
        self.assertEqual(self._out("--part", nb.MAX_PARTS + 1, NEB_WORKSPACE=ws), "")

    def test_check_size_pasa_sobre_el_repo(self):
        rc, out, err = self._run("--check-size", "--root", NEB)
        self.assertEqual(rc, 0, err)
        self.assertIn("arranque del núcleo", out)

    def test_check_size_falla_con_un_nucleo_inflado(self):
        os.makedirs(os.path.join(self.tmp, "general"))
        with open(os.path.join(self.tmp, "general", "startup.md"), "w", encoding="utf-8") as f:
            f.write("# Arranque\n\n" + "".join(seccion("S%d" % i, 4, 2000) for i in range(10)))
        rc, _, err = self._run("--check-size", "--root", self.tmp)
        self.assertEqual(rc, 1)
        self.assertIn("tope %d de %d" % (nb.NUCLEUS_MAX_PARTS, nb.MAX_PARTS), err)

    def _nucleo(self, secciones):
        os.makedirs(os.path.join(self.tmp, "general"), exist_ok=True)
        with open(os.path.join(self.tmp, "general", "startup.md"), "w", encoding="utf-8") as f:
            f.write("# Arranque\n\n" + "".join(seccion("S%d" % i, 4, 2000) for i in range(secciones)))
        return self._run("--check-size", "--root", self.tmp)

    def test_check_size_falla_por_caracteres_aunque_quepa_en_partes(self):
        # Cada seccion mide ~8,100 caracteres y cabe en una parte.
        justo_arriba = nb.NUCLEUS_MAX_CHARS // 8100 + 1
        rc, _, err = self._nucleo(justo_arriba)
        self.assertEqual(rc, 1)
        self.assertIn("(tope %d)" % nb.NUCLEUS_MAX_CHARS, err)
        partes = int(re.search(r"; (\d+) partes", err).group(1))
        self.assertLessEqual(partes, nb.NUCLEUS_MAX_PARTS)
        rc, _, err = self._nucleo(justo_arriba - 2)
        self.assertEqual(rc, 0, err)

    def test_check_size_sin_raiz_falla(self):
        rc, _, err = self._run("--check-size")
        self.assertEqual(rc, 1)
        self.assertIn("uso:", err)


class TestMainEnProceso(unittest.TestCase):
    """test_subsession.py llama a main() con un io.StringIO, que no tiene `.buffer`."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, _tmp_home(self))
        patcher.start()
        self.addCleanup(patcher.stop)
        self._saved = {k: os.environ.get(k) for k in CLEAN}
        for k in CLEAN:
            os.environ.pop(k, None)
        os.environ["NEB_HOME"] = NEB

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _main(self, argv=None):
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            nb.main(argv)
        finally:
            sys.stdout = old
        return buf.getvalue()

    def test_sin_argumentos_y_con_parte(self):
        self.assertIn("Arranque de Neb (inyectado por el plugin)", self._main())
        self.assertIsNotNone(HEADER_RE.match(self._main(["--part", "1"])))


class TestAvisoActualizacion(unittest.TestCase):
    """La oferta de actualización automática: el script corre desde un caché de plugins simulado, que es
    de donde saca el marketplace y el dir de configuración (hooks/lib/autoupdate.py). Nunca toca ~/.claude."""

    AVISO = "la actualización automática del plugin de Neb no está decidida (marketplace `neb`)"

    def setUp(self):
        self.cfg = tempfile.mkdtemp(prefix="neb-test-cfg-")
        self.addCleanup(shutil.rmtree, self.cfg, True)
        self.root = os.path.join(self.cfg, "plugins", "cache", "neb", "neb", "9.9.9")
        skip = shutil.ignore_patterns("tests", "__pycache__")
        for d in ("bootstrap", "hooks"):
            shutil.copytree(os.path.join(NEB, d), os.path.join(self.root, d), ignore=skip)
        self.script = os.path.join(self.root, "bootstrap", "neb-bootstrap-context.py")
        self.helper = os.path.join(self.root, "hooks", "lib", "autoupdate.py")
        self.home_env = _tmp_home(self)

    def _config(self, settings=None, known=None):
        for path, value in ((os.path.join(self.cfg, "settings.json"), settings),
                            (os.path.join(self.cfg, "plugins", "known_marketplaces.json"), known)):
            entry = {"source": {"source": "github", "repo": "acme/neb"}}
            if value is not None:
                entry["autoUpdate"] = value
            data = {"neb": entry} if path.endswith("known_marketplaces.json") else {"extraKnownMarketplaces": {"neb": entry}}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)

    def _snapshot(self):
        out = {}
        for base, _, files in os.walk(self.cfg):
            for name in files:
                p = os.path.join(base, name)
                with open(p, "rb") as f:
                    out[os.path.relpath(p, self.cfg)] = f.read()
        return out

    def _out(self, *args, script=None, **env):
        e = {k: v for k, v in os.environ.items() if k not in CLEAN}
        e["NEB_HOME"] = NEB
        e["PYTHONDONTWRITEBYTECODE"] = "1"
        e["CLAUDE_CONFIG_DIR"] = self.cfg       # el dir de configuración en uso es el de la prueba
        e.update(self.home_env)
        e.update(env)
        r = subprocess.run([sys.executable, script or self.script] + [str(a) for a in args], env=e,
                           capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8"))
        return r.stdout.decode("utf-8")

    def _partes(self, **env):
        outs = [self._out("--part", k, **env) for k in range(1, nb.MAX_PARTS + 1)]
        llenas = [o for o in outs if o]
        heads = [HEADER_RE.match(o) for o in llenas]
        self.assertTrue(all(heads))
        self.assertEqual(len({m.group(3) for m in heads}), 1, "todas las partes llevan la misma huella")
        self.assertEqual({int(m.group(2)) for m in heads}, {len(llenas)})
        for o in llenas:
            self.assertLessEqual(u16(o), nb.LIMIT)
            self.assertNotIn("el arranque no cupo", o)
        return llenas

    def test_sin_decidir_avisa_en_la_parte_1_y_no_escribe(self):
        self._config()
        antes = self._snapshot()
        partes = self._partes()
        self.assertIn("**Aviso de Neb (entorno):** " + self.AVISO, partes[0])
        # La forma con la ruta del ayudante, si cabe en el tope; si no (dir temporal largo), la que no la trae.
        larga = "corre con Python `%s` con `enable`" % self.helper.replace("\\", "/")
        corta = "corre con Python `hooks/lib/autoupdate.py` del plugin con `enable`"
        cabe = u16(nb.ENV_NOTICE % (nb.AUTOUPDATE_NOTICE % ("neb", larga))) <= 800
        self.assertIn(larga if cabe else corta, partes[0])
        self.assertEqual(sum(self.AVISO in p for p in partes), 1)
        self.assertEqual(self._snapshot(), antes)

    def test_sin_la_entrada_en_el_settings_no_avisa(self):
        # Ahí `enable` y `disable` rechazan: una oferta que no se puede contestar volvería en cada sesión.
        self._config()
        settings = os.path.join(self.cfg, "settings.json")
        with open(settings, "w", encoding="utf-8") as f:
            json.dump({"env": {}, "extraKnownMarketplaces": {"otro": {}}}, f)
        self.assertNotIn(self.AVISO, self._out())
        os.remove(settings)
        self.assertNotIn(self.AVISO, self._out())

    def test_cache_fuera_del_dir_de_configuracion_no_avisa(self):
        # El settings solo se deduce de la ruta si el caché cuelga del dir de configuración en uso
        # (CLAUDE_CODE_PLUGIN_CACHE_DIR fija otra raíz, y puede no estar en el entorno del proceso).
        self._config()
        self.assertIn(self.AVISO, self._out())
        otro = tempfile.mkdtemp(prefix="neb-test-otro-")
        self.addCleanup(shutil.rmtree, otro, True)
        self.assertNotIn(self.AVISO, self._out(CLAUDE_CONFIG_DIR=otro))
        self.assertNotIn(self.AVISO, self._out(CLAUDE_CONFIG_DIR=otro,
                                               CLAUDE_CODE_PLUGIN_CACHE_DIR=os.path.join(self.cfg, "plugins")))

    def test_decidido_sale_igual_que_fuera_del_cache(self):
        fuera = self._out(script=SCRIPT)
        self.assertNotIn(self.AVISO, fuera)
        for settings, known in ((True, None), (False, None), (None, True), (None, False), (False, True)):
            self._config(settings, known)
            self.assertEqual(self._out(), fuera, (settings, known))

    def test_archivo_ilegible_o_marketplace_desconocido_no_avisa(self):
        self._config()
        with open(os.path.join(self.cfg, "settings.json"), "w", encoding="utf-8") as f:
            f.write("{ roto")
        self.assertNotIn(self.AVISO, self._out())
        os.remove(os.path.join(self.cfg, "settings.json"))
        os.remove(os.path.join(self.cfg, "plugins", "known_marketplaces.json"))
        self.assertNotIn(self.AVISO, self._out())

    def test_sin_el_modulo_no_avisa(self):
        self._config()
        os.remove(self.helper)
        out = self._out()
        self.assertNotIn(self.AVISO, out)
        self.assertIn("Arranque de Neb (inyectado por el plugin)", out)

    def test_con_los_cuatro_avisos_cabe(self):
        self._config()
        viejo = os.path.join(self.cfg, "plugins", "cache", "neb", "neb", "6.0.0")
        partes = self._partes(NEB_HOME=viejo, CLAUDE_PLUGIN_ROOT=NEB, NEB_HOOKS="usage-tracker,Notify")
        self.assertLessEqual(len(partes), nb.MAX_PARTS)
        todo = "".join(partes)
        for texto in ("`NEB_HOME` apunta al cache del plugin", "retirados que siguen activados",
                      "no reconoce", self.AVISO):
            self.assertIn(texto, todo)
        self.assertEqual(todo.count("**Aviso de Neb (entorno):**"), 4)

    def test_tope_del_aviso(self):
        self.assertEqual(nb.AUTOUPDATE_NOTICE_MAX, 800)
        for marketplace in ("neb", "m" * 40):
            for largo in (10, 60, 100, 140, 400):
                bootstrap_dir = os.path.join(os.sep + "x" * largo, "bootstrap")
                with mock.patch.object(nb, "pending_offer", return_value=marketplace):
                    aviso = nb._autoupdate_offer(bootstrap_dir)
                self.assertIsNotNone(aviso, (marketplace, largo))
                self.assertLessEqual(u16(nb.ENV_NOTICE % aviso), nb.AUTOUPDATE_NOTICE_MAX, (marketplace, largo))
                self.assertIn("`%s`" % marketplace, aviso)
                self.assertNotIn("\\", aviso)
                if largo >= 140:
                    self.assertIn("`hooks/lib/autoupdate.py` del plugin", aviso)
                elif largo <= 60 and marketplace == "neb":
                    self.assertIn("x/hooks/lib/autoupdate.py` con `enable`", aviso)

    def test_fuera_del_cache_no_hay_oferta(self):
        if "plugins" in NEB and "cache" in NEB:
            self.skipTest("el repo vive dentro de un caché de plugins")
        self.assertIsNone(nb._autoupdate_offer(os.path.join(NEB, "bootstrap")))


class TestAvisoBaseSinMigrar(unittest.TestCase):
    """La base con el nombre anterior a 7.0.0 se avisa como migración guiada pendiente (el paso
    7.0.0:renombrar-base); el arranque no crea neb.db ni abre la base vieja, ni en solo lectura."""

    AVISO = "Hay una migración guiada de Neb pendiente (`7.0.0`): 1 paso que pide configurar la máquina"

    def setUp(self):
        self.home_env = _tmp_home(self)
        self.base = os.path.join(self.home_env["HOME"], ".claude")
        os.makedirs(self.base)
        self.legacy = os.path.join(self.base, "neb-logbook.db")
        self.target = os.path.join(self.base, "neb.db")

    def _base(self, path):
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE work (id INTEGER PRIMARY KEY)")
        con.commit()
        con.close()

    def _out(self):
        e = {k: v for k, v in os.environ.items() if k not in CLEAN}
        e["NEB_HOME"] = NEB
        e.update(self.home_env)
        r = subprocess.run([sys.executable, SCRIPT], env=e, capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8"))
        return r.stdout.decode("utf-8")

    def _carpeta(self):
        return sorted(os.listdir(self.base))

    def test_critico_con_solo_la_base_vieja_avisa_la_migracion_guiada(self):
        self._base(self.legacy)
        st = os.stat(self.legacy)
        out = self._out()
        self.assertIn(self.AVISO, out)
        self.assertIn("/neb:migrate", out)
        self.assertNotIn("La bitácora sigue con el nombre anterior", out)
        self.assertEqual(self._carpeta(), ["neb-logbook.db"])
        st2 = os.stat(self.legacy)
        self.assertEqual((st.st_size, st.st_mtime_ns), (st2.st_size, st2.st_mtime_ns))

    def test_sin_la_base_vieja_no_avisa(self):
        self._base(self.target)
        self.assertNotIn("`7.0.0`", self._out())

    def test_critico_env_notices_no_abre_la_base_vieja(self):
        real = sqlite3.connect
        self._base(self.legacy)
        for neb_db in (False, True):
            with self.subTest(neb_db=neb_db):
                if neb_db:
                    self._base(self.target)
                abiertos = []

                def espia(path, *a, **k):
                    abiertos.append(str(path))
                    return real(path, *a, **k)
                with mock.patch.dict(os.environ, self.home_env), mock.patch("sqlite3.connect", espia):
                    notices = nb._env_notices(os.path.join(NEB, "bootstrap"))
                self.assertFalse([p for p in abiertos if "neb-logbook" in p], abiertos)
                self.assertEqual(any(self.AVISO in n for n in notices), not neb_db, notices)

    def test_base_vieja_vacia_no_avisa(self):
        open(self.legacy, "wb").close()
        with mock.patch.dict(os.environ, self.home_env):
            notices = nb._env_notices(os.path.join(NEB, "bootstrap"))
        self.assertFalse(any("`7.0.0`" in n for n in notices), notices)


class TestAvisoSonido(unittest.TestCase):
    """Los hooks notify-on-* activados que no suenan como se configuraron se avisan en el arranque (7.2.0).
    El aviso solo lee: no genera la caché de `chimes-loud`."""

    AVISO = "Hooks de sonido que no suenan como se configuraron"

    def setUp(self):
        self.home_env = _tmp_home(self)
        self.claude = os.path.join(self.home_env["HOME"], ".claude")
        os.makedirs(self.claude)
        self.falta = os.path.join(self.home_env["HOME"], "falta.wav")

    def _cfg(self, hook, data):
        with open(os.path.join(self.claude, "%s.json" % hook), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _notices(self, hooks="notify-on-stop,notify-on-permission", extra=None):
        env = dict(self.home_env, NEB_HOOKS=hooks)
        env.update(extra or {})
        with mock.patch.dict(os.environ, env):
            for k in ("NEB_PROJECT_HOOKS",):
                os.environ.pop(k, None)
            return [n for n in nb._env_notices(os.path.join(NEB, "bootstrap")) if self.AVISO in n]

    def _player_path(self):
        """PATH con un reproductor falso, para que en POSIX el aviso no salga por falta de reproductor."""
        if os.name == "nt":
            return {}
        bindir = tempfile.mkdtemp(prefix="neb-test-bin-")
        self.addCleanup(shutil.rmtree, bindir, True)
        exe = os.path.join(bindir, "aplay")
        with open(exe, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(exe, 0o755)
        return {"PATH": bindir}

    def test_critico_ruta_inexistente_avisa_y_config_valida_no(self):
        extra = self._player_path()
        self._cfg("notify-on-stop", {"wav": self.falta})
        notices = self._notices(extra=extra)
        self.assertEqual(len(notices), 1, notices)
        self.assertIn("`notify-on-stop` usa el sonido por defecto: no existe %s" % self.falta, notices[0])
        self.assertNotIn("`notify-on-permission`", notices[0])
        self._cfg("notify-on-stop", {"wav": None})
        self.assertEqual(self._notices(extra=extra), [])

    def test_critico_enabled_false_o_hook_no_activado_no_avisan(self):
        extra = self._player_path()
        self._cfg("notify-on-stop", {"enabled": False, "wav": self.falta})
        self.assertEqual(self._notices(extra=extra), [])
        self._cfg("notify-on-stop", {"wav": self.falta})
        self.assertEqual(self._notices(hooks="logbook-sync", extra=extra), [])
        self.assertEqual(self._notices(hooks="", extra=extra), [])

    def test_critico_chimes_loud_no_escribe_en_el_arranque(self):
        self._cfg("notify-on-stop", {"wav": "chimes-loud"})
        self._notices(extra=self._player_path())
        self.assertFalse(os.path.exists(os.path.join(self.claude, "neb-sounds")))

    @unittest.skipIf(os.name == "nt", "en Windows el reproductor lo da el sistema")
    def test_sin_reproductor_avisa(self):
        empty = tempfile.mkdtemp(prefix="neb-test-bin-")
        self.addCleanup(shutil.rmtree, empty, True)
        notices = self._notices(hooks="notify-on-permission", extra={"PATH": empty})
        self.assertEqual(len(notices), 1, notices)
        self.assertIn("`notify-on-permission` no suena: no hay reproductor", notices[0])


if __name__ == "__main__":
    unittest.main()
