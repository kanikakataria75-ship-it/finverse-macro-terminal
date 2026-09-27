"""
Rebuilds the Truth Social topic -> market reaction study and ships it to the terminal.

The original research/analysis.py filtered on '^GSPC', but the event dataset uses 'SPY',
so key_findings.md came out empty (N=0, NaN). This script recomputes the study on the
cleaned, session-clustered data with bootstrap confidence intervals on *abnormal* returns
(topic mean minus the mean across all post sessions for that asset).

Usage:  python tools/build_rhetoric_study.py
Output: finverse/data/rhetoric_study.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = next(p for p in [ROOT / "analysis_output", ROOT / "research" / "analysis_output"] if p.exists())
OUT = ROOT / "finverse" / "data" / "rhetoric_study.json"

ASSETS = ["SPY", "QQQ", "^NSEI", "GC=F", "CL=F", "DX-Y.NYB", "TLT", "BTC-USD", "INR=X", "^VIX"]
HORIZONS = ["return_1d", "return_1w"]
RNG = np.random.default_rng(7)


def boot_ci(x: np.ndarray, n=2000):
    if len(x) < 5:
        return None, None
    idx = RNG.integers(0, len(x), size=(n, len(x)))
    means = x[idx].mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def main():
    clusters = pd.read_csv(SRC / "clean_event_clusters.csv", usecols=["cluster_id", "topic_string"])
    rets = pd.read_csv(SRC / "clean_event_returns.csv")
    rets = rets[(rets["is_partial_history"] == False) & (rets["status"] == "complete")]  # noqa: E712
    clusters["topic"] = clusters["topic_string"].str.split("|")
    exploded = clusters.explode("topic")[["cluster_id", "topic"]]
    df = rets.merge(exploded, on="cluster_id")

    n_tests = 0
    rows = []
    for asset in ASSETS:
        base_all = rets[rets["asset"] == asset]
        for h in HORIZONS:
            baseline = float(base_all[h].dropna().mean())
            for topic, g in df[df["asset"] == asset].groupby("topic"):
                x = g[h].dropna().to_numpy()
                if len(x) < 20:
                    continue
                n_tests += 1
                abn = x - baseline
                lo, hi = boot_ci(abn)
                rows.append({
                    "topic": topic, "asset": asset, "horizon": h.replace("return_", ""),
                    "n": int(len(x)), "mean": round(float(x.mean()), 4),
                    "baseline": round(baseline, 4), "abnormal": round(float(abn.mean()), 4),
                    "ci": [round(lo, 4), round(hi, 4)] if lo is not None else None,
                    "hit_rate": round(float((x > 0).mean()), 3),
                    "significant": bool(lo is not None and (lo > 0 or hi < 0)),
                })

    sig = [r for r in rows if r["significant"]]
    # Expected false positives at 95% with n_tests independent tests
    expected_fp = round(n_tests * 0.05, 1)
    summary = {
        "sessions": int(clusters["cluster_id"].nunique()),
        "tests": n_tests,
        "significant": len(sig),
        "expected_false_positives": expected_fp,
        "verdict": (
            "No robust edge: significant results are within the number expected by chance."
            if len(sig) <= expected_fp * 1.5 else
            "Some topic/asset pairs exceed chance - treat as hypotheses, not signals."
        ),
        "method": "Session-clustered posts (60-min windows), abnormal = topic mean - all-session mean, "
                  "95% bootstrap CI (2000 resamples). Source: 4y Truth Social archive.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(json.dumps(summary, indent=2))
    for r in sorted(sig, key=lambda r: -abs(r["abnormal"]))[:12]:
        print(f"  {r['topic'][:38]:38s} {r['asset']:9s} {r['horizon']:3s} abn={r['abnormal']:+.3f}% ci={r['ci']} n={r['n']}")


if __name__ == "__main__":
    main()
