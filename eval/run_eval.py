"""Run the 100-question validation set against a running backend and write a report.

    python eval/run_eval.py                              # API at http://localhost:8000
    python eval/run_eval.py --api https://your-host --label "after crawl, GPT-4o"

Writes eval/results/<timestamp>.csv (one row per question, with the answer) and
eval/results/<timestamp>.md (summary for the testing and validation report).

What each check means
  source_ok  the official page we expect is among the sources the assistant used
  behavior   answer   -> it answered (didn't say it couldn't find it)
             refuse   -> off-topic: it found no sources and said it couldn't find the answer
             dso      -> immigration status problem: the DSO safety banner was raised
             crisis   -> self-harm language: the crisis banner was raised
             pii      -> personal details were removed before processing
  flags      verification findings (unverified/misattributed figures, uncited statements, unsupported claims)

After running with a real AI key, a person should still read the answers in the CSV and mark each one
correct / partly correct / wrong in the "reviewer_grade" column. Automated checks can't replace that.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent


def ask(client: httpx.Client, api: str, question: str, role: str) -> dict:
    t0 = time.time()
    out = {"sources": [], "flags": {}, "text": "", "done": {}, "error": ""}
    with client.stream("POST", f"{api}/api/chat", json={"question": question, "role": role}) as r:
        if r.status_code != 200:
            out["error"] = f"HTTP {r.status_code}"
            return out
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                d = json.loads(line[6:])
                if event == "sources":
                    out["sources"], out["flags"] = d["sources"], d["flags"]
                elif event == "delta":
                    out["text"] += d["text"]
                elif event == "replace":
                    out["text"] = d["text"]
                elif event == "done":
                    out["done"] = d
                elif event == "error":
                    out["error"] = d.get("message", "error")
    out["seconds"] = round(time.time() - t0, 2)
    return out


def grade(row: dict, res: dict) -> dict:
    urls = [s["url"] for s in res["sources"]]
    expected = [e for e in row["expected_source"].split("|") if e]
    source_ok = (not expected) or any(e in u for e in expected for u in urls[:5])
    beh = row["expected_behavior"]
    answered = res["done"].get("answered", False)
    flags = res["flags"] or {}
    behavior_ok = {
        "answer": answered,
        "refuse": not res["sources"] and not answered,
        "dso": bool(flags.get("high_risk")),
        "crisis": bool(flags.get("crisis")),
        "pii": bool(flags.get("pii_removed")) and answered,
    }.get(beh, False)
    checks = {k: res["done"].get(k, []) for k in ("unverified", "misattributed", "uncited", "unsupported_claims", "ai_flags")}
    n_flags = sum(len(v) for v in checks.values())
    return {"source_ok": source_ok, "behavior_ok": behavior_ok, "flags": n_flags, "checks": checks,
            "passed": source_ok and behavior_ok and not res["error"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--questions", default=str(HERE / "questions.csv"))
    ap.add_argument("--label", default="")
    ap.add_argument("--delay", type=float, default=5.5, help="seconds between questions (stay under the rate limit)")
    a = ap.parse_args()

    meta = httpx.get(f"{a.api}/api/meta", timeout=10).json()
    rows = list(csv.DictReader(open(a.questions, encoding="utf-8")))
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    outdir = HERE / "results"
    outdir.mkdir(exist_ok=True)
    results = []
    with httpx.Client(timeout=120) as client:
        for i, row in enumerate(rows, 1):
            res = ask(client, a.api, row["question"], row["role"])
            g = grade(row, res)
            results.append((row, res, g))
            print(f"[{i:3}/{len(rows)}] {'PASS' if g['passed'] else 'FAIL'}  {row['question'][:70]}")
            time.sleep(a.delay)

    with open(outdir / f"{stamp}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "category", "role", "question", "expected_behavior", "passed", "source_ok", "behavior_ok",
                    "verification_flags", "flag_details", "seconds", "top_sources", "answer", "reviewer_grade", "reviewer_notes"])
        for row, res, g in results:
            w.writerow([row["id"], row["category"], row["role"], row["question"], row["expected_behavior"],
                        g["passed"], g["source_ok"], g["behavior_ok"], g["flags"],
                        json.dumps({k: v for k, v in g["checks"].items() if v}), res.get("seconds", ""),
                        " | ".join(s["url"] for s in res["sources"][:3]), res["text"].strip(), "", ""])

    by_cat = defaultdict(list)
    for row, _, g in results:
        by_cat[row["category"]].append(g["passed"])
    secs = [r.get("seconds", 0) for _, r, _ in results if r.get("seconds")]
    n = len(results)
    passed = sum(g["passed"] for _, _, g in results)
    flagged = sum(g["flags"] > 0 for _, _, g in results)
    lines = [
        f"# Validation run {stamp}" + (f" — {a.label}" if a.label else ""),
        "",
        f"- Mode: {'AI answers' if meta.get('ai') else 'official-text answers (no AI key)'}; search: {meta.get('retrieval')}",
        f"- Knowledge base: {meta.get('passages')} passages from {meta.get('sources')} pages",
        f"- **Passed: {passed}/{n} ({passed / n:.0%})**",
        f"- Correct source used: {sum(g['source_ok'] for _, _, g in results)}/{n}",
        f"- Correct behavior: {sum(g['behavior_ok'] for _, _, g in results)}/{n}",
        f"- Answers with verification flags: {flagged}/{n}",
        f"- Median response time: {statistics.median(secs):.1f}s" if secs else "",
        "",
        "| Category | Passed |",
        "|---|---|",
        *[f"| {c} | {sum(v)}/{len(v)} |" for c, v in sorted(by_cat.items())],
        "",
        "## Failures",
        "",
        *[f"- #{row['id']} ({row['category']}, expected {row['expected_behavior']}): {row['question']} — "
          f"{'wrong/missing source' if not g['source_ok'] else ''}{'; ' if not g['source_ok'] and not g['behavior_ok'] else ''}"
          f"{'wrong behavior' if not g['behavior_ok'] else ''}{'; ' + res['error'] if res['error'] else ''}"
          for row, res, g in results if not g["passed"]],
        "",
        "Next: open the CSV and have a reviewer grade each answer (correct / partly / wrong).",
    ]
    (outdir / f"{stamp}.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:10]))
    print(f"\nReport: {outdir / (stamp + '.md')}\nAnswers: {outdir / (stamp + '.csv')}")


if __name__ == "__main__":
    main()
