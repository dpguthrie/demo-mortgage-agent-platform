"""Release gate: exit 1 if the latest experiment with this name is below the threshold, has a
case at 0 (--no-zero), or left any case unscored. Writes the verdict to the experiment's
metadata.release_gate, so Braintrust (and Loop) read the gate's answer.

    python -m keystone_agents.evals.gate --experiment "ci · PR #12" --score "Condition decision" --min 0.95 --no-zero
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

API = os.environ.get("BRAINTRUST_API_URL") or "https://api.braintrust.dev"


def _req(method: str, path: str, **kw) -> requests.Response:
    h = {"Authorization": f"Bearer {os.environ['BRAINTRUST_API_KEY']}"}
    for i in range(6):
        r = requests.request(method, f"{API}{path}", headers=h, timeout=60, **kw)
        if r.status_code != 429 and r.status_code < 500:
            return r
        time.sleep(15)
    return r


def sql(q: str) -> list[dict]:
    r = _req("POST", "/btql", json={"query": q, "fmt": "json"})
    data = r.json().get("data")
    if data is None:
        raise SystemExit(f"query failed: {r.text[:300]}")
    return data


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
    covered = cases > 0 and scored == cases
    ok = covered and avg >= a.min and (not a.no_zero or under == 0)
    verdict = "PASS" if ok else "FAIL"
    print(f"{exp['name']}: {a.score} {avg * 100:.1f}% (gate {a.min * 100:.0f}%), cases at 0: {under}/{scored}, "
          f"scored {scored}/{cases} cases → {verdict}{'' if covered else ' (not every case was scored)'}")
    gate = {"verdict": verdict, "score": a.score, "value": round(avg, 4), "min": a.min, "rows_at_zero": under, "rows": scored,
            "cases": cases, "checked_at": datetime.now(timezone.utc).isoformat()}
    if os.environ.get("GITHUB_SHA"):
        gate["commit"] = os.environ["GITHUB_SHA"]
    if os.environ.get("PR_URL"):
        gate["pull_request"] = os.environ["PR_URL"]
    w = _req("PATCH", f"/v1/experiment/{exp['id']}", json={"metadata": {**(exp.get("metadata") or {}), "release_gate": gate}})
    if w.status_code >= 300:
        print(f"could not write the verdict to the experiment: {w.status_code}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
