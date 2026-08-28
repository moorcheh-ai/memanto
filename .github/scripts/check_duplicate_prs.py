"""Flag pull requests that appear to duplicate other open/merged PRs.

Runs in GitHub Actions. Reads only PR metadata (title, body, changed file
paths) via the REST API -- it never checks out PR code, so it is safe to run
under `pull_request_target`.

Pipeline:
  1. A cheap title+description token-overlap heuristic narrows the field to a
     few candidate PRs. Linked issues are deliberately ignored, so PRs sharing
     a generic "find bugs" issue are not treated as related.
  2. Mistral semantically compares the current PR against each candidate to
     catch "same bug, different approach" duplicates that heuristics miss.
  3. If anything scores above the confidence threshold, post/update a comment
     and apply the `possible-duplicate` label.

Stdlib only -- no third-party packages, so the workflow needs no `pip install`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

GITHUB_API = "https://api.github.com"
MISTRAL_API = "https://api.mistral.ai/v1/chat/completions"

# Tunables (override via workflow env if you want).
MAX_CANDIDATES = int(os.environ.get("MAX_CANDIDATES", "6"))
HEURISTIC_MIN = float(os.environ.get("HEURISTIC_MIN", "0.12"))
CONFIDENCE_MIN = float(os.environ.get("CONFIDENCE_MIN", "0.6"))
MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
LABEL = os.environ.get("DUPLICATE_LABEL", "possible-duplicate")
COMMENT_MARKER = "<!-- duplicate-pr-check -->"
# When set, print what would be posted instead of commenting/labelling.
DRY_RUN = os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"}

_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "for",
    "to",
    "of",
    "in",
    "on",
    "fix",
    "fixes",
    "bug",
    "add",
    "update",
    "remove",
    "support",
    "feat",
    "feature",
    "with",
    "when",
    "use",
    "make",
    "allow",
    "wip",
    "pr",
    "issue",
}


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _request(method: str, url: str, headers: dict, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode()
    return json.loads(body) if body else None


def gh(method: str, path: str, token: str, payload: dict | None = None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }
    url = path if path.startswith("http") else f"{GITHUB_API}{path}"
    return _request(method, url, headers, payload)


def gh_list(path: str, token: str, per_page: int = 100, max_pages: int = 10) -> list:
    """GET a paginated list endpoint, following pages until exhausted."""
    sep = "&" if "?" in path else "?"
    out: list = []
    for page in range(1, max_pages + 1):
        chunk = gh("GET", f"{path}{sep}per_page={per_page}&page={page}", token) or []
        out.extend(chunk)
        if len(chunk) < per_page:
            break
    return out


# --------------------------------------------------------------------------- #
# Heuristics
# --------------------------------------------------------------------------- #
def title_tokens(title: str) -> set[str]:
    raw = re.split(r"[^a-z0-9]+", title.lower())
    # Drop bare numbers (issue/PR/ticket refs) -- sharing #770 is not a signal.
    return {t for t in raw if len(t) > 2 and not t.isdigit() and t not in _STOPWORDS}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def changed_files(repo: str, number: int, token: str) -> set[str]:
    files = gh_list(f"/repos/{repo}/pulls/{number}/files", token)
    return {f["filename"] for f in files}


# --------------------------------------------------------------------------- #
# Mistral
# --------------------------------------------------------------------------- #
def _pr_text(body: str) -> str:
    # Strip ticket/PR refs so the model judges on content, not shared linkage.
    return re.sub(r"#\d+", "", body or "")[:1500]


def mistral_compare(api_key: str, current: dict, candidate: dict) -> dict:
    """Ask Mistral whether two PRs are redundant duplicates. Returns a verdict."""
    prompt = (
        "You compare two GitHub pull requests and decide whether they are "
        "DUPLICATES: two PRs that fix the SAME SPECIFIC bug or make the same "
        "specific change, so that merging one makes the other redundant.\n\n"
        "Judge by the actual change, not by shared themes or tickets:\n"
        "- duplicate = true: they fix the same specific defect or implement the "
        "same specific change -- this still counts even if they use a different "
        "approach or touch different files.\n"
        "- duplicate = false: they fix DIFFERENT specific defects, even if they "
        "share a category or umbrella effort (e.g. both add defensive parsing, "
        "both harden error handling).\n"
        "A shared linked issue or ticket number is not evidence either way; "
        "ignore ticket references.\n\n"
        f"PR A (#{current['number']}): {current['title']}\n"
        f"Description: {_pr_text(current['body'])}\n"
        f"Changed files: {', '.join(sorted(current['files'])[:40]) or 'unknown'}\n\n"
        f"PR B (#{candidate['number']}): {candidate['title']}\n"
        f"Description: {_pr_text(candidate['body'])}\n"
        f"Changed files: {', '.join(sorted(candidate['files'])[:40]) or 'unknown'}\n\n"
        "Respond with JSON only: "
        '{"duplicate": true|false, "confidence": 0.0-1.0, "reason": "one sentence"}.'
    )
    payload = {
        "model": MISTRAL_MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    raw: object = {}
    try:
        resp = _request("POST", MISTRAL_API, headers, payload)
        raw = json.loads(resp["choices"][0]["message"]["content"])
    except (urllib.error.HTTPError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"  ! Mistral comparison failed for #{candidate['number']}: {exc}")

    # JSON mode guarantees valid JSON, not these field types -- coerce/clamp.
    if not isinstance(raw, dict):
        raw = {}
    try:
        confidence = float(raw.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "duplicate": bool(raw.get("duplicate", False)),
        "confidence": max(0.0, min(1.0, confidence)),
        "reason": str(raw.get("reason") or ""),
    }


# --------------------------------------------------------------------------- #
# Comment / label output
# --------------------------------------------------------------------------- #
def build_comment(hits: list[dict]) -> str:
    lines = [
        COMMENT_MARKER,
        "### Possible duplicate PRs",
        "",
        "This PR may overlap with existing work. Please review before merging:",
        "",
    ]
    for h in sorted(hits, key=lambda x: x["confidence"], reverse=True):
        state = "merged" if h["merged"] else h["state"]
        pct = round(h["confidence"] * 100)
        lines.append(f"- #{h['number']} ({state}, ~{pct}% match) — {h['reason']}")
    lines += [
        "",
        "_Automated by the duplicate-PR check; close this comment if it's a false positive._",
    ]
    return "\n".join(lines)


def upsert_comment(repo: str, number: int, token: str, body: str) -> None:
    comments = gh_list(f"/repos/{repo}/issues/{number}/comments", token)
    for c in comments:
        if COMMENT_MARKER in (c.get("body") or ""):
            gh(
                "PATCH",
                f"/repos/{repo}/issues/comments/{c['id']}",
                token,
                {"body": body},
            )
            return
    gh("POST", f"/repos/{repo}/issues/{number}/comments", token, {"body": body})


def add_label(repo: str, number: int, token: str) -> None:
    gh("POST", f"/repos/{repo}/issues/{number}/labels", token, {"labels": [LABEL]})


def clear_flags(repo: str, number: int, token: str, pr: dict) -> None:
    """Remove a prior duplicate marker comment + label if the PR is no longer a dup."""
    if LABEL not in {lbl["name"] for lbl in pr.get("labels", [])}:
        return  # never flagged -> nothing to clean up
    if DRY_RUN:
        print(f"  [dry-run] would clear stale '{LABEL}' flag from #{number}")
        return
    for c in gh_list(f"/repos/{repo}/issues/{number}/comments", token):
        if COMMENT_MARKER in (c.get("body") or ""):
            gh("DELETE", f"/repos/{repo}/issues/comments/{c['id']}", token)
    gh(
        "DELETE",
        f"/repos/{repo}/issues/{number}/labels/{urllib.parse.quote(LABEL)}",
        token,
    )
    print(f"  Cleared stale duplicate flag from #{number}.")


def gather_pool(repo: str, token: str, exclude: int) -> list[dict]:
    """Open PRs + recently merged PRs, minus the PR itself."""
    others = gh_list(f"/repos/{repo}/pulls?state=open", token)
    # Closed list is intentionally a single recent window (not fully paginated);
    # keep only the ones that actually merged, so we don't flag abandoned work.
    closed = (
        gh(
            "GET",
            f"/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=50",
            token,
        )
        or []
    )
    merged = [p for p in closed if p.get("merged_at")]
    return [p for p in (others + merged) if p["number"] != exclude]


def process_pr(repo: str, token: str, mistral_key: str | None, pr: dict) -> None:
    number = pr["number"]
    current = {
        "number": number,
        "title": pr["title"] or "",
        "body": pr.get("body") or "",
        "files": changed_files(repo, number, token),
    }
    cur_tokens = title_tokens(current["title"] + " " + current["body"])

    pool = gather_pool(repo, token, number)

    # Heuristic shortlist based purely on title+description content overlap.
    # Linked issues are intentionally ignored: a generic "find bugs" issue
    # linked by many PRs says nothing about whether they fix the same bug.
    scored = []
    for p in pool:
        text = (p["title"] or "") + " " + (p.get("body") or "")
        score = jaccard(cur_tokens, title_tokens(text))
        if score >= HEURISTIC_MIN:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    shortlist = scored[:MAX_CANDIDATES]

    print(
        f"PR #{number}: {len(pool)} other PRs, {len(shortlist)} candidates after heuristics"
    )

    if not shortlist:
        print("  No candidates; nothing to flag.")
        clear_flags(repo, number, token, pr)
        return
    if not mistral_key:
        print("  MISTRAL_API_KEY not set; skipping semantic check.")
        return

    hits = []
    for score, p in shortlist:
        candidate = {
            "number": p["number"],
            "title": p["title"] or "",
            "body": p.get("body") or "",
            "files": changed_files(repo, p["number"], token),
        }
        verdict = mistral_compare(mistral_key, current, candidate)
        conf = float(verdict.get("confidence", 0))
        print(
            f"  #{p['number']}: heuristic={score:.2f} dup={verdict.get('duplicate')} conf={conf:.2f}"
        )
        if verdict.get("duplicate") and conf >= CONFIDENCE_MIN:
            hits.append(
                {
                    "number": p["number"],
                    "state": p["state"],
                    "merged": bool(p.get("merged_at")),
                    "confidence": conf,
                    "reason": verdict.get("reason", ""),
                }
            )

    if not hits:
        print("  No semantic duplicates above threshold.")
        clear_flags(repo, number, token, pr)
        return

    comment = build_comment(hits)
    if DRY_RUN:
        print(
            f"  [dry-run] would flag {len(hits)} duplicate(s) and add '{LABEL}':\n{comment}"
        )
        return

    upsert_comment(repo, number, token, comment)
    add_label(repo, number, token)
    print(f"  Flagged {len(hits)} possible duplicate(s).")


def resolve_prs(repo: str, token: str) -> list[dict]:
    """Decide which PR(s) to scan: explicit number, the triggering PR, or all open."""
    pr_number_env = os.environ.get("PR_NUMBER")
    if pr_number_env:
        return [gh("GET", f"/repos/{repo}/pulls/{pr_number_env}", token)]

    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        with open(event_path, encoding="utf-8") as fh:
            event = json.load(fh)
        if "pull_request" in event:
            return [event["pull_request"]]

    # No specific PR (e.g. a manual all-open backfill run): scan every open PR.
    print("No specific PR given; scanning all open PRs.")
    return gh_list(f"/repos/{repo}/pulls?state=open", token)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    mistral_key = os.environ.get("MISTRAL_API_KEY")

    prs = resolve_prs(repo, token)
    if not prs:
        print("No PRs to scan.")
        return 0

    for pr in prs:
        process_pr(repo, token, mistral_key, pr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
