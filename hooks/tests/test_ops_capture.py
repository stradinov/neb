#!/usr/bin/env python3
"""test_ops_capture.py — helper determinístico del hook ops-capture (pieza 2a).

Cubre el código testeable de hooks/lib/ops_inbox.py:
  • resolve_inbox_dir: default vs override por env
  • inbox_filename: formato + sanitización cross-OS
  • extract_operational_excerpts: GATE (detecta señales / vacío en conversación /
    respeta max / amplía con NEB_OPS_SIGNALS_EXTRA)
  • transcript_text_lines: parsea JSONL / tolera no-JSON / [] si el archivo no existe

NO testea el juicio del subagente LLM (no es determinístico). Framework: unittest
(stdlib), NO pytest. No toca ~/.claude.
"""
import json
import os
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(HOOKS_DIR, "lib")
sys.path.insert(0, LIB_DIR)
import ops_inbox as OI  # noqa: E402


class TestResolveInboxDir(unittest.TestCase):
    def test_default(self):
        got = OI.resolve_inbox_dir(env={}, home="/home/x")
        self.assertEqual(got, os.path.join("/home/x", ".claude", "ops-inbox"))

    def test_env_override(self):
        got = OI.resolve_inbox_dir(env={"NEB_OPS_INBOX_DIR": "/tmp/custom-inbox"}, home="/home/x")
        self.assertEqual(got, "/tmp/custom-inbox")

    def test_env_override_expands_user(self):
        got = OI.resolve_inbox_dir(env={"NEB_OPS_INBOX_DIR": "~/ops"}, home="/home/x")
        self.assertEqual(got, os.path.expanduser("~/ops"))


class TestInboxFilename(unittest.TestCase):
    def test_format(self):
        got = OI.inbox_filename("gonher", "abc123", "20260619-101500")
        self.assertEqual(got, "20260619-101500-gonher-abc123.inbox.md")

    def test_sanitizes_unsafe_chars(self):
        got = OI.inbox_filename("my/proj name", "a:b*c", "20260619-101500")
        self.assertNotIn("/", got)
        self.assertNotIn(":", got)
        self.assertNotIn("*", got)
        self.assertTrue(got.endswith(".inbox.md"))

    def test_empty_tokens_fallback(self):
        got = OI.inbox_filename("", "", "20260619-101500")
        self.assertEqual(got, "20260619-101500-unknown-unknown.inbox.md")


class TestExtractOperationalExcerpts(unittest.TestCase):
    def test_detects_signals(self):
        lines = [
            "Hola, como estas",
            "corri ssh -i key.pem ec2-user@10.0.0.1",
            "todo bien",
        ]
        hits = OI.extract_operational_excerpts(lines, env={})
        self.assertEqual(len(hits), 1)
        self.assertIn("ssh", hits[0])

    def test_empty_on_plain_conversation(self):
        lines = ["hola", "gracias", "perfecto, seguimos manana", "que opinas del diseno"]
        self.assertEqual(OI.extract_operational_excerpts(lines, env={}), [])

    def test_detects_ip_and_sql(self):
        lines = ["el server es 18.118.238.102", "ALTER TABLE ps_orders ADD COLUMN x INT"]
        hits = OI.extract_operational_excerpts(lines, env={})
        self.assertEqual(len(hits), 2)

    def test_respects_max(self):
        lines = ["sudo systemctl restart httpd"] * 100
        hits = OI.extract_operational_excerpts(lines, env={}, max_excerpts=5)
        self.assertEqual(len(hits), 5)

    def test_extra_signals_from_env(self):
        lines = ["el flujo IDoc DEBMAS llego al hub"]
        # sin extra: no matchea
        self.assertEqual(OI.extract_operational_excerpts(lines, env={}), [])
        # con extra: matchea
        hits = OI.extract_operational_excerpts(lines, env={"NEB_OPS_SIGNALS_EXTRA": r"\bIDoc\b"})
        self.assertEqual(len(hits), 1)


class TestTranscriptTextLines(unittest.TestCase):
    def test_parses_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write(json.dumps({"role": "user", "content": "ssh al server"}) + "\n")
                f.write(json.dumps({"role": "assistant", "content": ["ok", {"text": "listo"}]}) + "\n")
            lines = OI.transcript_text_lines(p)
            self.assertEqual(len(lines), 2)
            self.assertIn("ssh al server", lines[0])
            self.assertIn("listo", lines[1])

    def test_tolerates_non_json_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.jsonl")
            with open(p, "w", encoding="utf-8") as f:
                f.write("no soy json pero menciono mysqldump\n")
                f.write("\n")  # línea vacía ignorada
            lines = OI.transcript_text_lines(p)
            self.assertEqual(len(lines), 1)
            self.assertIn("mysqldump", lines[0])

    def test_missing_file_returns_empty(self):
        self.assertEqual(OI.transcript_text_lines("/no/such/file.jsonl"), [])


class TestExtractFromFile(unittest.TestCase):
    """Gate en streaming con ventana (extract_operational_excerpts_from_file)."""

    def _write(self, d, contents):
        p = os.path.join(d, "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            for c in contents:
                f.write(json.dumps({"role": "x", "content": c}) + "\n")
        return p

    def test_all_fit_no_mark(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write(d, ["hola que tal", "corri ssh al server", "ALTER TABLE x ADD c INT"])
            out = OI.extract_operational_excerpts_from_file(p, env={})
            self.assertEqual(len(out), 2)  # ssh + ALTER TABLE; "hola..." no es hit
            self.assertFalse(any("omitidos" in x for x in out))

    def test_window_keeps_head_and_tail(self):
        with tempfile.TemporaryDirectory() as d:
            # 10 hits; max_excerpts=4 -> 2 head + marca + 2 tail
            p = self._write(d, [f"ssh hit numero {i}" for i in range(1, 11)])
            out = OI.extract_operational_excerpts_from_file(p, env={}, max_excerpts=4)
            self.assertEqual(len(out), 5)
            self.assertIn("numero 1", out[0])       # primero conservado
            self.assertIn("numero 10", out[-1])     # ÚLTIMO conservado (no se pierde el final)
            self.assertTrue(any("6 fragmentos" in x for x in out))  # 10-2-2 = 6 omitidos

    def test_missing_file_empty(self):
        self.assertEqual(OI.extract_operational_excerpts_from_file("/no/such.jsonl", env={}), [])


if __name__ == "__main__":
    unittest.main()
