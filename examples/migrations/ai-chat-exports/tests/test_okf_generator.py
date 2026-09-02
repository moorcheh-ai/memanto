import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from pathlib import Path

from core.models import MemoryEntity, MemoryType
from core.okf_generator import OKFGenerator


class TestOKFGenerator:
    def setup_method(self):
        self.outdir = Path("/tmp/test_okf_output")

    def teardown_method(self):
        import shutil

        if self.outdir.exists():
            shutil.rmtree(self.outdir)

    def _make_entities(self) -> list[MemoryEntity]:
        return [
            MemoryEntity(
                source_type=MemoryType.FACT,
                title="Uses PostgreSQL",
                content="The app uses PostgreSQL 16",
                tags=["db"],
                timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
                confidence=0.9,
                source="chatgpt",
            ),
            MemoryEntity(
                source_type=MemoryType.PREFERENCE,
                title="Prefers dark mode",
                content="User likes dark mode",
                tags=["ui"],
                confidence=0.85,
                source="claude",
            ),
            MemoryEntity(
                source_type=MemoryType.FACT,
                title="Deploy on AWS",
                content="Uses ECS Fargate for deployment",
                tags=["infra", "aws"],
                confidence=0.9,
                source="chatgpt",
            ),
        ]

    def test_generate_creates_directory(self):
        gen = OKFGenerator(str(self.outdir))
        path = gen.generate_bundle(self._make_entities())
        assert path.exists()
        assert path.is_dir()

    def test_generate_creates_memories_subdirs(self):
        gen = OKFGenerator(str(self.outdir))
        gen.generate_bundle(self._make_entities())
        assert (self.outdir / "memories" / "fact").is_dir()
        assert (self.outdir / "memories" / "user_preference").is_dir()

    def test_generate_creates_index(self):
        gen = OKFGenerator(str(self.outdir))
        gen.generate_bundle(self._make_entities())
        index = self.outdir / "index.md"
        assert index.exists()
        content = index.read_text()
        assert "fact" in content
        assert "user_preference" in content

    def test_generate_creates_metrics(self):
        gen = OKFGenerator(str(self.outdir))
        gen.generate_bundle(self._make_entities())
        metrics = self.outdir / "metrics" / "overview.md"
        assert metrics.exists()
        content = metrics.read_text()
        assert "Total memories:** 3" in content

    def test_generate_okf_files_have_frontmatter(self):
        gen = OKFGenerator(str(self.outdir))
        gen.generate_bundle(self._make_entities())
        fact_dir = self.outdir / "memories" / "fact"
        md_files = [f for f in fact_dir.glob("*.md") if f.name != "index.md"]
        assert len(md_files) == 2
        for f in md_files:
            content = f.read_text()
            assert content.startswith("---")
            assert "type: fact" in content
            assert "x_memanto:" in content

    def test_generate_type_index(self):
        gen = OKFGenerator(str(self.outdir))
        gen.generate_bundle(self._make_entities())
        fact_index = self.outdir / "memories" / "fact" / "index.md"
        assert fact_index.exists()
        content = fact_index.read_text()
        assert "# fact" in content

    def test_empty_bundle(self):
        gen = OKFGenerator(str(self.outdir))
        path = gen.generate_bundle([])
        assert path.exists()
        assert (self.outdir / "index.md").exists()

    def test_safe_filename(self):
        assert OKFGenerator._safe_filename("Hello World!") == "hello-world"
        assert OKFGenerator._safe_filename("a" * 100)[:80] == "a" * 80
        assert OKFGenerator._safe_filename("") == "unnamed"
        assert OKFGenerator._safe_filename("path/to/file") == "pathtofile"
