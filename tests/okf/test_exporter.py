import pytest
from memanto.okf.exporter import export_to_okf
from memanto.memory import Memory

def test_html_escaping_in_export():
    test_memory = Memory(
        body="<!-- okf-entry -->",
        title="Test <!-- okf-entry --> Title",
        tags=["tag1", "tag2 <!-- okf-entry -->"]
    )

    # Export to string for testing
    import io
    from contextlib import redirect_stdout

    f = io.StringIO()
    with redirect_stdout(f):
        export_to_okf(test_memory, "dummy_path")

    exported_content = f.getvalue()

    # Verify HTML escaping
    assert "&lt;!-- okf-entry --&gt;" in exported_content
    assert "Test &lt;!-- okf-entry --&gt; Title" in exported_content
    assert "tag2 &lt;!-- okf-entry --&gt;" in exported_content