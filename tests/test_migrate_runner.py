import pytest

from memanto.cli.migrate.runner import load_export


class TestMigrateLoadExport:
    @pytest.mark.parametrize("payload", ["[]", '"not an export"', "null"])
    def test_load_export_rejects_non_object_json(self, tmp_path, payload):
        export_path = tmp_path / "mem0_export.json"
        export_path.write_text(payload, encoding="utf-8")

        with pytest.raises(ValueError, match="must be a JSON object"):
            load_export(export_path)
