"""Focused UI output regression; run with Python and Node, without packages.

    python tests/ui_date_rendering.py

An optional first argument selects another index.html for a before/after run.
The actual source functions run in Node. Their text-only DOM operation uses
ElementTree serialization; HTMLParser checks the returned markup and text.
This is a component regression, not browser or event-handler execution.
"""

import json
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

NODE_RUNNER = r"""
const fs = require('node:fs');
const vm = require('node:vm');
function receive() {
  const bytes = [];
  const byte = Buffer.alloc(1);
  while (fs.readSync(0, byte, 0, 1, null)) {
    if (byte[0] === 10) return JSON.parse(Buffer.from(bytes).toString());
    bytes.push(byte[0]);
  }
  throw new Error('input closed');
}
function send(value) { fs.writeSync(1, JSON.stringify(value) + '\n'); }
const input = receive();
const source = fs.readFileSync(input.source, 'utf8');
function extract(name) {
  const start = source.indexOf('function ' + name + '(');
  if (start < 0) throw new Error('missing function ' + name);
  let end = source.indexOf('\n', start);
  for (let count = 0; count < 250 && end >= 0; count++) {
    const text = source.slice(start, end);
    try { new vm.Script('(' + text + ')'); return text; }
    catch (error) { if (!(error instanceof SyntaxError)) throw error; }
    end = source.indexOf('\n', end + 1);
  }
  throw new Error('could not extract ' + name);
}
const document = {
  createElement(tag) {
    if (tag !== 'div') throw new Error('unexpected DOM element ' + tag);
    return {
      textContent: '',
      get innerHTML() {
        send({kind: 'serialize-text', text: String(this.textContent ?? '')});
        return receive().html;
      },
    };
  },
};
const context = vm.createContext({document});
const names = ['confClass', 'confBadge', 'fmtDate', 'trunc', 'escHtml',
  'attrEsc', 'buildMemoryTable', 'migWarnings', 'renderMigratePreview'];
for (const name of names) vm.runInContext(extract(name), context);
const outputs = [];
for (const created_at of input.dates) {
  const memory = {id: 'local-render-probe', title: 'Normal title',
    content: 'Normal memory body', type: 'fact', confidence: 0.8,
    provenance: 'imported', created_at, updated_at: created_at};
  const preview = {provider: 'okf', source_label: 'Local controlled fixture',
    source_count: 1, mapped_count: 1, skipped: 0, batch_count: 1,
    type_counts: {fact: 1}, sample: [memory], warnings: []};
  outputs.push({created_at, display: context.fmtDate(created_at),
    table: context.buildMemoryTable([memory], true),
    preview: context.renderMigratePreview(preview)});
}
send({kind: 'result', outputs});
"""


class ParsedMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []
        self.cells = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "td":
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append("".join(self.cell))
            self.cell = None

    def handle_data(self, data):
        self.text.append(data)
        if self.cell is not None:
            self.cell.append(data)


def render(source, dates):
    process = subprocess.Popen(
        ["node", "--max-old-space-size=24", "-e", NODE_RUNNER],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None and process.stdout is not None
    process.stdin.write(json.dumps({"source": str(source), "dates": dates}) + "\n")
    process.stdin.flush()
    outputs = None
    for line in process.stdout:
        message = json.loads(line)
        if message["kind"] == "serialize-text":
            element = ElementTree.Element("div")
            element.text = message["text"]
            markup = ElementTree.tostring(element, method="html", encoding="unicode")
            process.stdin.write(json.dumps({"html": markup[5:-6]}) + "\n")
            process.stdin.flush()
        elif message["kind"] == "result":
            outputs = message["outputs"]
    process.stdin.close()
    stderr = process.stderr.read() if process.stderr is not None else ""
    if process.wait() or outputs is None:
        raise RuntimeError(stderr or "renderer returned no output")
    return outputs


def main():
    source = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else Path(__file__).resolve().parents[1]
        / "memanto/app/ui/static/index.html"
    )
    payload = '<img src=x data-memanto-probe="date">'
    dates = [payload, "2026-10-04T07:00:00Z", None, "not a date & <literal>"]
    outputs = render(source, dates)
    for row in outputs:
        table_text = ""
        for name in ("table", "preview"):
            parsed = ParsedMarkup()
            parsed.feed(row[name])
            assert "img" not in parsed.tags, f"injected image in {name}"
            assert "literal" not in parsed.tags, f"unescaped date text in {name}"
            if name == "table":
                assert parsed.cells[6] == row["display"], "date display changed"
                table_text = "".join(parsed.text)
            elif row["created_at"] is None:
                assert '<div class="meta">fact</div>' in row[name]
            else:
                assert row["display"] in "".join(parsed.text)
        if row["created_at"] in (payload, dates[-1]):
            assert row["display"] == row["created_at"], (
                "fmtDate must stay plain text"
            )
            assert f"Updated: {row['display']}" in table_text, (
                "existing escaped date changed"
            )
    print("PASS: 8 rendered cases (4 date values in memory and migration output)")


if __name__ == "__main__":
    main()
