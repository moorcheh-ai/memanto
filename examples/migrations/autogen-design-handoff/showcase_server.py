"""Local display of the real pipeline for a screencast; no replayed results.

Set MOORCHEH_API_KEY privately, then run this file and open localhost:8769.
The one-shot button runs migrate_demo.py against a fresh synthetic demo agent.
Only the fixed synthetic run directory is readable through this server.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(tempfile.mkdtemp(prefix="autogen-screencast-"))
RUN = ROOT / "run"
STATE = {"started": False, "done": False, "exit_code": None, "log": "Ready to run the actual AutoGen → Memanto pipeline."}
LOCK = threading.Lock()


def pipeline():
    command = [sys.executable, "-u", str(HERE / "migrate_demo.py"), "--live", "--output", str(RUN)]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
        for line in process.stdout:
            key = os.environ.get("MOORCHEH_API_KEY", "")
            safe = line.replace(key, "[REDACTED]") if key else line
            with LOCK:
                STATE["log"] += safe.replace(str(Path.home()), "~")
        code = process.wait()
    with LOCK:
        STATE["exit_code"] = code
        STATE["done"] = True


HTML = r'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Own your agent memory · Live migration</title>
<style>*{box-sizing:border-box}body{margin:0;background:#0b1020;color:#e9edf8;font:16px system-ui;padding:30px}header{display:flex;justify-content:space-between;align-items:center}h1{font-size:35px;letter-spacing:-1px;margin:0 0 6px}p{color:#a6b0c7;margin:0}button{background:#b4eacb;color:#123124;border:0;border-radius:8px;padding:12px 25px;font-weight:700;cursor:pointer}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:24px}.card{background:#141d32;border:1px solid #263149;padding:20px;border-radius:12px}h2{font-size:15px;color:#a9b5d0;font-weight:600;letter-spacing:1px;margin:0 0 12px}.metric{font-size:34px;line-height:1.1;color:#b4eacb}pre{font:13px/1.45 ui-monospace,monospace;white-space:pre-wrap;overflow:auto;margin:8px 0 0;height:275px}.wide{grid-column:1/3;display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:16px 20px}.small{font-size:13px;color:#a6b0c7}#status{margin-top:9px;color:#c9d3eb}#qa{margin-top:10px;font-size:15px;line-height:1.7;white-space:pre-line}footer{margin-top:16px;font-size:12px;color:#8c9bb9}</style>
<header><div><h1>Keep the decision. Keep its history.</h1><p>AutoGen ListMemory → shipped Memanto CLI → portable OKF</p></div><button id="start">Run live migration</button></header>
<div id="status">Real source operations. Synthetic design decisions. No LLM.</div>
<div class="grid"><section class="card"><h2>LIVE COMMANDS</h2><pre id="log"></pre></section><section class="card"><h2>READABLE EXPORTED MARKDOWN</h2><pre id="okf">Waiting for the real cloud export…</pre></section>
<section class="card wide"><div><h2>RECORDS · SOURCE / MAPPED / EXPORTED</h2><div class="metric" id="count">— / — / —</div><div id="source" class="small">Simulated process reset: source clear and target checks pending</div><div class="small" id="cost">Savings: N/A · ListMemory has no measured embedding bill</div></div><div><h2>FULL-CONTEXT RECALL · SAME 8-RECORD SCOPE</h2><div id="qa">Waiting for actual cloud queries…</div></div></section></div>
<footer>Alex SOLONSKY · New adapter, real cloud run · Eight synthetic records; equal-volume recall; top-3 ranking reported separately.</footer>
<script>const button=document.querySelector('#start');button.onclick=async()=>{button.disabled=true;await fetch('/start',{method:'POST'});};setInterval(async()=>{const d=await(await fetch('/state')).json();document.querySelector('#log').textContent=d.log;document.querySelector('#log').scrollTop=999999;if(d.source){document.querySelector('#source').textContent='AutoGen add calls: '+d.source.add_calls+' · simulated reset → '+d.source.after_clear_count;}if(d.okf)document.querySelector('#okf').textContent=d.okf;if(d.summary){const s=d.summary;document.querySelector('#count').textContent=s.source_count+' / '+s.okf_count+' / '+s.exported_count;document.querySelector('#status').textContent=(d.exit_code===0?'PASS · ':'')+'Lossless payload roundtrip: '+s.lossless_payload_roundtrip+' · CLI import '+s.timings_seconds.cli_import+'s · export '+s.timings_seconds.cli_export+'s · ranked top-3: '+s.ranked_top3_passed+'/'+s.ranked_top3_total;}if(d.recall)document.querySelector('#qa').textContent=d.recall.map(q=>(q.passed?'✓ ':'✗ ')+q.answers.join(', ')).join('\n');if(d.done){button.textContent=d.exit_code===0?'Complete · verified':'Run failed';}else if(d.started){button.textContent='Running live…';}},200);</script></html>'''


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            payload, mime = HTML.encode(), "text/html; charset=utf-8"
        elif self.path == "/state":
            with LOCK:
                state = dict(STATE)
            for name, key in [("source-operations.json", "source"), ("migration-summary.json", "summary"), ("recall-after.json", "recall"), ("ranked-top3.json", "ranked")]:
                path = RUN / name
                if path.exists():
                    try:
                        state[key] = json.loads(path.read_text())
                    except json.JSONDecodeError:
                        pass
            candidates = list((RUN / "exported-okf" / "memories" / "decision").glob("*finish.md"))
            if candidates:
                state["okf"] = candidates[-1].read_text()
            payload, mime = json.dumps(state).encode(), "application/json"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if self.path != "/start" or self.headers.get("Origin") != "http://127.0.0.1:8769":
            self.send_error(403)
            return
        with LOCK:
            if STATE["started"]:
                self.send_error(409)
                return
            STATE["started"] = True
            STATE["log"] = ""
        threading.Thread(target=pipeline, daemon=True).start()
        self.send_response(202)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not os.environ.get("MOORCHEH_API_KEY"):
        raise SystemExit("Set MOORCHEH_API_KEY privately before starting.")
    print(f"Local screencast display: http://127.0.0.1:8769 · output {RUN}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", 8769), Handler).serve_forever()
