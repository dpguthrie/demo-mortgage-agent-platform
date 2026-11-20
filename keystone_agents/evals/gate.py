"""CI reporter and manual recheck for the same single-scorer release gate.

To recheck an experiment that already exists:
    python -m keystone_agents.evals.gate --experiment "ci · PR #12" --score "Condition decision" --min 0.95 --no-zero
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from math import isfinite
from statistics import mean

import requests
from braintrust import Reporter
from braintrust.framework import default_reporter


def _req(method: str, path: str, **kw) -> requests.Response:
    api = os.environ.get("BRAINTRUST_API_URL") or "https://api.braintrust.dev"
    h = {"Authorization": f"Bearer {os.environ['BRAINTRUST_API_KEY']}"}
    for i in range(6):
        r = requests.request(method, f"{api}{path}", headers=h, timeout=60, **kw)
        if r.status_code != 429 and r.status_code < 500:
            return r
        if i < 5:
            time.sleep(15)
    return r


def sql(q: str) -> list[dict]:
    r = _req("POST", "/btql", json={"query": q, "fmt": "json"})
    data = r.json().get("data")
    if data is None:
        raise SystemExit(f"query failed: {r.text[:300]}")
    return data


def _check_gate(score, minimum, *, avg, scored, cases, under, no_zero):
    covered = cases > 0 and scored == cases
    ok = covered and avg >= minimum and (not no_zero or under == 0)
    gate = {"verdict": "PASS" if ok else "FAIL", "score": score, "value": round(avg, 4),
            "min": minimum, "rows_at_zero": under, "rows": scored, "cases": cases,
            "checked_at": datetime.now(timezone.utc).isoformat()}
    if os.environ.get("GITHUB_SHA"):
        gate["commit"] = os.environ["GITHUB_SHA"]
    if os.environ.get("PR_URL"):
        gate["pull_request"] = os.environ["PR_URL"]
    message = (f"{score} {avg:.1%} (gate {minimum:.1%}), cases at 0: {under}/{scored}, "
               f"scored {scored}/{cases} cases → {gate['verdict']}")
    if not covered:
        message += " (requires a score on every case and at least one case)"
    return gate, message


def _write_gate(experiment_id, metadata, gate):
    try:
        response = _req("PATCH", f"/v1/experiment/{experiment_id}",
                        json={"metadata": {**(metadata or {}), "release_gate": gate}})
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"could not write the verdict to the experiment: {e}", file=sys.stderr)


def release_gate_reporter(agent: str, score: str, minimum: float):
    """Gate on one named score from the completed eval results."""
    if not 0 <= minimum <= 1:
        raise ValueError("GATE_MIN must be between 0 and 1")

    def report_eval(evaluator, result, verbose, jsonl):
        default_reporter.report_eval(evaluator, result, verbose, jsonl)
        values = [row.scores.get(score) for row in result.results if row.error is None]
        scores = [value for value in values if value is not None and isfinite(value)]
        gate, message = _check_gate(
            score, minimum, avg=mean(scores) if scores else 0.0, scored=len(scores),
            cases=len(result.results), under=scores.count(0), no_zero=True,
        )
        print(f"Release gate: {message}", file=sys.stderr)
        if result.summary.experiment_url:
            print(f"Experiment URL: {result.summary.experiment_url}", file=sys.stderr)
        if result.summary.experiment_id:
            _write_gate(result.summary.experiment_id, evaluator.metadata, gate)
        return gate["verdict"] == "PASS"

    def report_run(results):
        return bool(results) and all(results)

    return Reporter(f"{agent} release gate", report_eval=report_eval, report_run=report_run)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--score", required=True)
    ap.add_argument("--min", type=float, default=0.95)
    ap.add_argument("--no-zero", action="store_true")
    a = ap.parse_args()
    pid = os.environ["BRAINTRUST_PROJECT_ID"]
    exps = _req("GET", "/v1/experiment", params={"project_id": pid, "limit": 200}).json()["objects"]
    same = sorted([e for e in exps if e["name"] == a.experiment or e["name"].startswith(a.experiment + "-")], key=lambda e: e["created"], reverse=True)
    if not same:
        print(f"No experiment named {a.experiment}")
        return 1
    exp = same[0]
    s = a.score.replace('"', '')
    row = sql(f"SELECT avg(scores.\"{s}\") AS avg, sum(CASE WHEN scores.\"{s}\" = 0 THEN 1 ELSE 0 END) AS under, count(*) AS n "
              f"FROM experiment('{exp['id']}') WHERE span_attributes.type = 'score' AND scores.\"{s}\" IS NOT NULL")[0]
    cases = int(sql(f"SELECT count(*) AS cases FROM experiment('{exp['id']}') WHERE is_root = true")[0]["cases"] or 0)
    scored, under, avg = int(row["n"] or 0), int(row["under"] or 0), float(row["avg"] or 0)
    gate, message = _check_gate(a.score, a.min, avg=avg, scored=scored, cases=cases,
                                under=under, no_zero=a.no_zero)
    print(f"{exp['name']}: {message}")
    _write_gate(exp["id"], exp.get("metadata"), gate)
    return 0 if gate["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
