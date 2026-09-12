import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from grok_to_okf import main, redact, write_bundle  # noqa: E402


class GrokToOkfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.session = self.tmp / "session"
        self.session.mkdir()
        (self.session / "summary.json").write_text(
            json.dumps(
                {
                    "generated_title": "Ship the adapter",
                    "session_summary": "Lived-in Grok coding session",
                    "created_at": "2026-09-12T00:51:03Z",
                    "num_messages": 12,
                    "num_chat_messages": 4,
                    "current_model_id": "grok-4.6",
                    "agent_name": "grok-build-plan",
                    "info": {"cwd": "C:/Users/demo/projetos/demo"},
                }
            ),
            encoding="utf-8",
        )
        goal = self.session / "goal"
        goal.mkdir()
        (goal / "state.json").write_text(
            json.dumps({"objective": "Pay the operator at secret@example.com after work."}),
            encoding="utf-8",
        )
        (goal / "plan.md").write_text(
            "# Plan\n\n## Deviations\n- Skip BountyBook because the oracle crashes on code_test.\n",
            encoding="utf-8",
        )
        jsonl = [
            {
                "type": "user",
                "content": [{"type": "text", "text": "<user_query>\nDo not call take_snapshot without filePath.\n</user_query>"}],
            },
            {
                "type": "user",
                "synthetic_reason": "compaction_meta",
                "content": [{"type": "text", "text": "<user_query>\nignore this compacted dump\n</user_query>"}],
            },
            {
                "type": "assistant",
                "content": "I will use evaluate_script instead.",
            },
        ]
        (self.session / "chat_history.jsonl").write_text(
            "\n".join(json.dumps(r) for r in jsonl) + "\n",
            encoding="utf-8",
        )
        self.memory = self.tmp / "MEMORY.md"
        self.memory.write_text(
            "# Memory\n\n## Preferências\n- Relatar em PT-BR.\n\n## Mapa de trabalho\n| Onde | O que |\n|---|---|\n| projetos/grokgrana | Projeto Grok. Pode alterar. |\n\n## Padrões que voltam\n- ffmpeg ausente no PATH Windows.\n",
            encoding="utf-8",
        )
        self.out = self.tmp / "okf"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _bundle_text(self) -> str:
        return "\n".join(p.read_text(encoding="utf-8") for p in self.out.rglob("*.md"))

    def test_cli_writes_okf_and_redacts_email(self):
        rc = main(["--session", str(self.session), "--memory", str(self.memory), "--out", str(self.out)])
        self.assertEqual(rc, 0)
        index = (self.out / "index.md").read_text(encoding="utf-8")
        self.assertIn('okf_version: "0.2"', index)
        prefs = list((self.out / "memories" / "preference").glob("*.md"))
        self.assertTrue(any("PT-BR" in p.read_text(encoding="utf-8") for p in prefs if p.name != "index.md"))
        facts = list((self.out / "memories" / "fact").glob("*.md"))
        self.assertTrue(any("grokgrana" in p.read_text(encoding="utf-8") for p in facts if p.name != "index.md"))
        decisions = list((self.out / "memories" / "decision").glob("*.md"))
        self.assertTrue(any("BountyBook" in p.read_text(encoding="utf-8") for p in decisions if p.name != "index.md"))
        observations = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (self.out / "memories" / "observation").glob("*.md")
            if p.name != "index.md"
        )
        self.assertIn("take_snapshot", observations)
        self.assertNotIn("ignore this compacted dump", observations)
        bundle = self._bundle_text()
        self.assertNotIn("secret@example.com", bundle)
        self.assertIn("[REDACTED]", bundle)
        self.assertIn("type: episode", bundle)
        self.assertNotIn("C:/Users/demo", bundle)
        self.assertNotIn("C:\\Users", bundle)
        self.assertIn("Workspace leaf: `demo`", bundle)
        episode = (self.out / "memories" / "episode" / "grok-session-ship-the-adapter.md").read_text(encoding="utf-8")
        self.assertIn("resource: summary.json", episode)
        self.assertNotIn("session\\summary.json", episode.replace("/", "\\"))

    def test_redact_tokens(self):
        mj = "mj_live_ABCDEFG"
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaa.bbb"
        out = redact(f"key {mj} jwt {jwt}")
        self.assertNotIn(mj, out)
        self.assertNotIn(jwt, out)
        self.assertIn("[REDACTED]", out)

    def test_requires_input(self):
        self.assertEqual(main(["--out", str(self.out)]), 2)

    def test_empty_session_writes_indexes(self):
        empty = self.tmp / "empty-session"
        empty.mkdir()
        rc = main(["--session", str(empty), "--out", str(self.out)])
        self.assertEqual(rc, 0)
        self.assertTrue((self.out / "memories" / "index.md").is_file())
        self.assertTrue((self.out / "index.md").is_file())

    def test_write_bundle_empty_list(self):
        stats = write_bundle(self.out, [])
        self.assertEqual(stats["written"], 0)
        self.assertTrue((self.out / "memories" / "index.md").is_file())

    def test_skips_english_table_header(self):
        mem = self.tmp / "EN.md"
        mem.write_text(
            "# Memory\n\n## Work map\n| Where | What |\n|---|---|\n| grokgrana | project folder |\n",
            encoding="utf-8",
        )
        rc = main(["--memory", str(mem), "--out", str(self.out)])
        self.assertEqual(rc, 0)
        facts = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (self.out / "memories" / "fact").glob("*.md")
            if p.name != "index.md"
        )
        self.assertNotIn("Where → What", facts)
        self.assertIn("grokgrana", facts)

    def test_replaces_stale_output(self):
        stale = self.out / "memories" / "fact" / "stale.md"
        stale.parent.mkdir(parents=True)
        stale.write_text("obsolete document", encoding="utf-8")
        rc = main(["--session", str(self.session), "--memory", str(self.memory), "--out", str(self.out)])
        self.assertEqual(rc, 0)
        self.assertFalse(stale.exists())
        self.assertNotIn("obsolete document", self._bundle_text())

    def test_generated_at_is_stable(self):
        stamp = "2026-01-02T03:04:05Z"
        rc = main(
            [
                "--memory",
                str(self.memory),
                "--out",
                str(self.out),
                "--generated-at",
                stamp,
            ]
        )
        self.assertEqual(rc, 0)
        blob = self._bundle_text()
        self.assertIn(f"at: {stamp}", blob)
        self.assertNotIn("at: 2026-09-12T00:51:03Z", blob)


if __name__ == "__main__":
    unittest.main()
