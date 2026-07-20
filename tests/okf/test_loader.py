import pytest
from memanto.okf.loader import load_from_okf

def test_html_unescaping_in_loader():
    # Create test file with HTML-escaped content
    test_content = """---
title: Test <!-- okf-entry --> Title
tags: [tag1, tag2 <!-- okf-entry -->]
resource: test_resource
x_memanto:
  encoding: html
---
Document the literal internal marker & keep &amp; and <tags> unchanged:
&lt;!-- okf-entry --&gt;
It is part of the memory, not a record boundary.
"""

    with open("test_escaped.okf", "w") as f:
        f.write(test_content)

    # Load and verify
    imported_memories = load_from_okf("test_escaped.okf")
    assert len(imported_memories) == 1
    imported_memory = imported_memories[0]

    assert "<!-- okf-entry -->" in imported_memory.body
    assert "<!-- okf-entry -->" in imported_memory.title
    assert any("<!-- okf-entry -->" in tag for tag in imported_memory.tags)