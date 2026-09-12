import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from grok_to_okf import main, redact  # noqa: E402


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
        bundle = "\n".join(p.read_text(encoding="utf-8") for p in self.out.rglob("*.md"))
        self.assertNotIn("secret@example.com", bundle)
        self.assertIn("[REDACTED]", bundle)
        self.assertIn("type: episode", bundle)

    def test_redact_tokens(self):
        sample = "key mj_live_ABCDEFG jwt eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaa.bbb"
        out = redact(sample)
        self.assertNotIn("mj_live_ABCDEFG", out)
        self.assertIn("[REDACTED]", out)

    def test_requires_input(self):
        self.assertEqual(main(["--out", str(self.out)]), 2)


if __name__ == "__main__":
    unittest.main()
