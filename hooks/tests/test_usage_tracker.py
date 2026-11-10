#!/usr/bin/env python3
"""test_usage_tracker.py — medidor de tokens por REQ y por ventana (6.29.0).

Cubre hooks/lib/usage-tracker.py:
  • lector: campos en `message.*`, una llamada por `message.id`, `<synthetic>` fuera, escritura 5 min / 1 h
  • subagentes y agentes de workflow con su `agentType`; dedupe global entre archivos (copias de --resume)
  • atribución: último change MD o active_*.md editado; previas al primer toque; «sin REQ»; subagente por hora
  • compactaciones y relecturas del transcript tras compactar, atribuidas al REQ vigente
  • precios: modelo sin precio ⇒ total parcial; tramo de contexto largo
  • --write: solo entre marcadores; sin marcadores no escribe

Framework: unittest (stdlib). Transcripts sintéticos en un directorio temporal; nunca toca ~/.claude.
  py -m unittest discover -s hooks/tests -p test_usage_tracker.py
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "lib")
_spec = importlib.util.spec_from_file_location("usage_tracker", os.path.join(LIB, "usage-tracker.py"))
ut = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ut)

PRICES = {
    "m-a": {"input_per_mtok": 1.0, "output_per_mtok": 10.0, "cache_write_per_mtok": 2.0,
            "cache_write_1h_per_mtok": 3.0, "cache_read_per_mtok": 0.5},
    "m-long": {"input_per_mtok": 1.0, "output_per_mtok": 0.0, "cache_read_per_mtok": 1.0,
               "long_context_above_tokens": 100, "long_context_multiplier": 5},
}


def _assistant(mid, ts, model="m-a", inp=1, out=10, cw=0, cw1=0, cr=0, tools=(), repeat=1):
    """Líneas de un mensaje del asistente: una por bloque, todas con el mismo id y usage (como el transcript)."""
    usage = {"input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": cw,
             "cache_read_input_tokens": cr,
             "cache_creation": {"ephemeral_1h_input_tokens": cw1, "ephemeral_5m_input_tokens": cw - cw1}}
    blocks = [{"type": "text", "text": "x"}] * repeat + [
        {"type": "tool_use", "name": n, "input": i} for n, i in tools]
    return [json.dumps({"type": "assistant", "timestamp": ts,
                        "message": {"id": mid, "model": model, "usage": usage, "content": [b]}})
            for b in blocks]


def _boundary(ts, trigger="auto", pre=500000):
    return [json.dumps({"type": "system", "subtype": "compact_boundary", "timestamp": ts,
                        "compactMetadata": {"trigger": trigger, "preTokens": pre}})]


def _t(minute):
    return "2026-11-09T10:%02d:00.000Z" % minute


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.projects = os.path.join(self.tmp, "projects")
        self.proj = os.path.join(self.projects, "C--repo")
        os.makedirs(self.proj)
        ut._active_cache.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, lines):
        path = os.path.join(self.proj, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def meta(self, rel, agent):
        with open(os.path.join(self.proj, rel), "w", encoding="utf-8") as f:
            json.dump({"agentType": agent}, f)

    def run_measure(self, **kw):
        files = ut.session_files(self.projects, **kw)
        return ut.measure(files)


class Lector(Base):
    def test_una_llamada_por_message_id_y_campos_anidados(self):
        p = self.write("s1.jsonl", _assistant("a", _t(0), inp=5, out=7, cw=100, cw1=60, cr=1000, repeat=4)
                       + _assistant("b", _t(1), model="<synthetic>"))
        events = [e for k, e in ut.read_transcript(p) if k == "call"]
        self.assertEqual(len(events), 1)
        c = events[0]
        self.assertEqual((c["model"], c["in"], c["out"], c["cw5"], c["cw1"], c["cr"]), ("m-a", 5, 7, 40, 60, 1000))

    def test_sin_desglose_por_ttl_cuenta_como_5_min(self):
        line = json.dumps({"type": "assistant", "timestamp": _t(0), "message": {
            "id": "a", "model": "m-a", "content": [],
            "usage": {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 50}}})
        p = self.write("s1.jsonl", [line])
        c = [e for k, e in ut.read_transcript(p) if k == "call"][0]
        self.assertEqual((c["cw5"], c["cw1"]), (50, 0))

    def test_subagentes_y_workflows_con_su_tipo(self):
        self.write("s1.jsonl", _assistant("a", _t(0)))
        self.write("s1/subagents/agent-x.jsonl", _assistant("b", _t(1)))
        self.meta("s1/subagents/agent-x.meta.json", "neb:qa-process-engineer")
        self.write("s1/subagents/workflows/wf_1/agent-y.jsonl", _assistant("c", _t(2)))
        self.meta("s1/subagents/workflows/wf_1/agent-y.meta.json", "workflow-subagent")
        self.write("s1/subagents/agent-z.jsonl", _assistant("d", _t(3)))      # sin meta
        calls, _ = self.run_measure()
        self.assertEqual(sorted(c["agent"] for c in calls),
                         sorted([ut.MAIN, "neb:qa-process-engineer", "workflow-subagent", "desconocido"]))

    def test_dedupe_global_entre_archivos(self):
        self.write("s1.jsonl", _assistant("a", _t(0)) + _assistant("b", _t(1)))
        self.write("s2.jsonl", _assistant("a", _t(0)) + _assistant("b", _t(1)) + _assistant("c", _t(2)))
        calls, _ = self.run_measure()
        self.assertEqual(sorted(c["id"] for c in calls), ["a", "b", "c"])


class Atribucion(Base):
    CH_X = "C:\\repo\\changes\\2026-11-09-req-x.md"
    CH_Y = "C:/repo/changes/2026-11-09-req-y.md"

    def test_ultimo_registro_editado_y_previas_al_primer_toque(self):
        self.write("s1.jsonl",
                   _assistant("a", _t(0))                                         # antes del primer toque → X
                   + _assistant("b", _t(1), tools=[("Write", {"file_path": self.CH_X})])
                   + _assistant("c", _t(2))                                       # X
                   + _assistant("d", _t(3), tools=[("Edit", {"file_path": self.CH_Y})])
                   + _assistant("e", _t(4)))                                      # Y
        calls, _ = self.run_measure()
        got = {c["id"]: c["req"] for c in calls}
        self.assertEqual(got, {"a": "req-x", "b": "req-x", "c": "req-x", "d": "req-y", "e": "req-y"})

    def test_sesion_sin_toques_queda_sin_req(self):
        self.write("s1.jsonl", _assistant("a", _t(0), tools=[("Read", {"file_path": self.CH_X})]))
        calls, _ = self.run_measure()
        self.assertEqual(calls[0]["req"], ut.NO_REQ)

    def test_active_md_resuelve_por_su_draft(self):
        mem = os.path.join(self.tmp, "memory")
        os.makedirs(mem)
        active = os.path.join(mem, "active_proj_nombre-largo.md")
        with open(active, "w", encoding="utf-8") as f:
            f.write("- **Nombre:** nombre-largo\n- **Draft changes MD:** changes/2026-11-01-req-z.md\n")
        self.write("s1.jsonl", _assistant("a", _t(0), tools=[("Edit", {"file_path": active})]))
        calls, _ = self.run_measure()
        self.assertEqual(calls[0]["req"], "req-z")

    def test_active_md_con_otro_campo_y_nombre_sucio(self):
        # Caso real: `Nombre` trae texto extra y el registro va en `Change MD:`, no en `Draft changes MD:`.
        mem = os.path.join(self.tmp, "memory")
        os.makedirs(mem)
        active = os.path.join(mem, "active_gonher_otro-nombre.md")
        with open(active, "w", encoding="utf-8") as f:
            f.write("- **Nombre:** req-z · **Rama:** feature/x\n- **Change MD:** `changes/2026-11-01-req-z.md`\n")
        self.write("s1.jsonl", _assistant("a", _t(0), tools=[("Edit", {"file_path": active})]))
        calls, _ = self.run_measure()
        self.assertEqual(calls[0]["req"], "req-z")

    def test_active_md_prefiere_su_campo_a_un_req_relacionado(self):
        mem = os.path.join(self.tmp, "memory")
        os.makedirs(mem)
        active = os.path.join(mem, "active_proj_req-z.md")
        with open(active, "w", encoding="utf-8") as f:
            f.write("- **Relacionado:** changes/2026-10-01-req-viejo.md\n"
                    "- **Draft changes MD:** changes/2026-11-01-req-z.md\n")
        self.write("s1.jsonl", _assistant("a", _t(0), tools=[("Edit", {"file_path": active})]))
        calls, _ = self.run_measure()
        self.assertEqual(calls[0]["req"], "req-z")

    def test_req_encuentra_la_sesion_que_solo_edito_el_active(self):
        mem = os.path.join(self.projects, "C--home", "memory")
        os.makedirs(mem)
        active = os.path.join(mem, "active_proj_nombre-distinto.md")
        with open(active, "w", encoding="utf-8") as f:
            f.write("- **Draft changes MD:** changes/2026-11-01-req-z.md\n")
        self.write("s1.jsonl", _assistant("a", _t(0), tools=[("Edit", {"file_path": active})]))
        self.write("s2.jsonl", _assistant("b", _t(0)))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ut.main(["report", "--req", "req-z", "--days", "3650", "--projects", self.projects])
        self.assertIn("llamadas únicas: 1 ", out.getvalue())

    def test_active_md_borrado_usa_su_nombre(self):
        gone = os.path.join(self.tmp, "memory", "active_proj_req-w.md")
        self.write("s1.jsonl", _assistant("a", _t(0), tools=[("Write", {"file_path": gone})]))
        calls, _ = self.run_measure()
        self.assertEqual(calls[0]["req"], "req-w")

    def test_subagente_hereda_el_req_vigente_a_su_hora(self):
        self.write("s1.jsonl",
                   _assistant("a", _t(0), tools=[("Write", {"file_path": self.CH_X})])
                   + _assistant("b", _t(10), tools=[("Write", {"file_path": self.CH_Y})])
                   + _assistant("c", _t(20)))
        self.write("s1/subagents/agent-1.jsonl", _assistant("s-early", _t(5)))
        self.write("s1/subagents/agent-2.jsonl", _assistant("s-late", _t(15)))
        calls, _ = self.run_measure()
        got = {c["id"]: c["req"] for c in calls}
        self.assertEqual((got["s-early"], got["s-late"]), ("req-x", "req-y"))

    def test_compactacion_y_relectura_tras_compactar(self):
        transcript = os.path.join(self.tmp, ".claude", "projects", "C--repo", "s1.jsonl")
        self.write("s1.jsonl",
                   _assistant("a", _t(0), tools=[("Write", {"file_path": self.CH_X})])
                   + _assistant("r0", _t(1), tools=[("Read", {"file_path": transcript})])   # antes: no cuenta
                   + _boundary(_t(2), trigger="manual")
                   + _assistant("r1", _t(3), tools=[("Read", {"file_path": transcript})]))
        _calls, stats = self.run_measure()
        self.assertEqual(stats["compactions"], [("req-x", "manual")])
        self.assertEqual(stats["rereads"], ["req-x"])

    def test_filtro_por_contenido(self):
        self.write("s1.jsonl", _assistant("a", _t(0), tools=[("Write", {"file_path": self.CH_X})]))
        self.write("s2.jsonl", _assistant("b", _t(0)))
        files = ut.session_files(self.projects, must_contain="req-x")
        self.assertEqual([os.path.basename(p) for _m, p, _s, _main in files], ["s1.jsonl"])


class Precios(unittest.TestCase):
    def call(self, **kw):
        c = {"model": "m-a", "in": 0, "out": 0, "cw5": 0, "cw1": 0, "cr": 0}
        c.update(kw)
        return c

    def test_componentes(self):
        usd = ut.cost(self.call(**{"in": 1_000_000, "out": 1_000_000, "cw5": 1_000_000, "cw1": 1_000_000,
                                   "cr": 1_000_000}), PRICES)
        self.assertAlmostEqual(usd, 1 + 10 + 2 + 3 + 0.5)

    def test_modelo_sin_precio_es_parcial(self):
        self.assertIsNone(ut.cost(self.call(model="nuevo"), PRICES))
        total, *_ = ut.summarize([dict(self.call(model="nuevo"), agent=ut.MAIN, req="r")], PRICES)
        self.assertTrue(total["partial"])

    def test_tramo_de_contexto_largo(self):
        corto = ut.cost(self.call(model="m-long", cr=100), PRICES)
        largo = ut.cost(self.call(model="m-long", cr=101), PRICES)
        self.assertAlmostEqual(corto, 100 / 1e6)
        self.assertAlmostEqual(largo, 101 * 5 / 1e6)

    def test_pricing_yml_del_repo_cubre_los_5x(self):
        prices = ut.load_pricing()
        for m in ("claude-opus-5-5", "claude-fable-5-1", "claude-sonnet-5-5", "claude-haiku-5-5"):
            self.assertIn("cache_write_1h_per_mtok", prices[m], m)


class Escritura(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _file(self, content):
        os.makedirs(os.path.join(self.tmp, "changes"), exist_ok=True)
        p = os.path.join(self.tmp, "changes", "2026-11-09-req-x.md")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return p

    def test_solo_entre_marcadores(self):
        before, after = "# Título\r\n\r\ntexto ñ → antes\r\n", "\r\ndespués\r\n"
        p = self._file(before + ut.START + "\r\nviejo\r\n" + ut.END + after)
        self.assertTrue(ut.write_block(p, "nuevo\nbloque"))
        with open(p, encoding="utf-8", newline="") as f:
            got = f.read()
        self.assertTrue(got.startswith(before + ut.START))
        self.assertTrue(got.endswith(ut.END + after))
        self.assertIn("\r\nnuevo\r\nbloque\r\n", got)
        self.assertNotIn("viejo", got)

    def test_sin_marcadores_no_escribe(self):
        p = self._file("sin marcadores\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertFalse(ut.write_block(p, "x"))
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), "sin marcadores\n")

    def test_cli_write_deriva_el_slug_del_change_md(self):
        projects = os.path.join(self.tmp, "projects", "C--repo")
        os.makedirs(projects)
        ch = self._file("a\n" + ut.START + "\n" + ut.END + "\n")
        with open(os.path.join(projects, "s1.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(_assistant("a", _t(0), model="claude-opus-5-5", out=1000,
                                         tools=[("Edit", {"file_path": ch})])) + "\n")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = ut.main(["report", "--write", ch, "--days", "3650", "--projects", os.path.dirname(projects)])
        self.assertEqual(rc, 0)
        with open(ch, encoding="utf-8") as f:
            got = f.read()
        self.assertIn("| hilo principal | 1 |", got)
        self.assertIn("$0.02", got)

    def test_argumentos_invalidos(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ut.main([]), 2)
            self.assertEqual(ut.main(["report", "--write", os.path.join(self.tmp, "otro.md")]), 2)


if __name__ == "__main__":
    unittest.main()
