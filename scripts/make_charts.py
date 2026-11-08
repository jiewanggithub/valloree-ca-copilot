"""Charts for the evaluation report -> docs/img/*.png"""
import json
import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)
VERS = ["v1", "v2", "v3"]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = {"v1": "#2a78d6", "v2": "#eb6834", "v3": "#1baf7a"}
STATUS = {"OK": "#0ca30c", "EDIT": "#fab219", "UNACCEPTABLE": "#d03b3b"}
DIMS = ["personalization", "brand_voice", "naturalness", "appropriateness", "goal", "faithfulness"]

plt.rcParams.update({"font.family": ["Helvetica"], "font.size": 10, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2, "figure.facecolor": SURFACE,
                     "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE})


def human_counts(v):
    h = yaml.safe_load((ROOT / f"data/human_review_{v}.yaml").read_text(encoding="utf-8")) or {}
    un = sum(1 for x in h.values() if x["verdict"] == "UNACCEPTABLE")
    ed = sum(1 for x in h.values() if x["verdict"] == "EDIT")
    return {"OK": 150 - un - ed, "EDIT": ed, "UNACCEPTABLE": un}


# 1. human verdicts, 100% stacked bars ------------------------------------------------
fig, ax = plt.subplots(figsize=(7.2, 2.6), dpi=200)
for row, v in enumerate(reversed(VERS)):
    c = human_counts(v)
    left = 0
    for k in ["OK", "EDIT", "UNACCEPTABLE"]:
        w = c[k] / 150 * 100
        ax.barh(row, w, left=left, height=0.56, color=STATUS[k], edgecolor=SURFACE, linewidth=2,
                label={"OK": "OK", "EDIT": "Edit", "UNACCEPTABLE": "Unacceptable"}[k] if row == 0 else None)
        left += w
    ax.text(101.5, row, f"{c['OK']} · {c['EDIT']} · {c['UNACCEPTABLE']}", va="center", color=INK, fontsize=9)
ax.text(101.5, 2.62, "OK · Edit · Unacc.", va="center", color=INK2, fontsize=8)
ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.22), ncol=3, frameon=False, fontsize=9)
ax.set_yticks(range(3), [f"{v}" for v in reversed(VERS)], color=INK, fontsize=10)
ax.set_xlim(0, 100)
ax.set_ylim(-0.5, 2.8)
ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
for s in ["top", "right", "left"]:
    ax.spines[s].set_visible(False)
ax.tick_params(left=False)
ax.set_title("Manual review of 150 candidates per version", loc="left", color=INK, fontsize=11, fontweight="bold")
plt.tight_layout()
fig.savefig(OUT / "human_verdicts.png")

# 2. judge dimension means, dot plot -------------------------------------------------
means = {}
for v in VERS:
    acc = {d: [] for d in DIMS}
    for f in glob.glob(str(ROOT / f"results/{v}/*.json")):
        r = json.load(open(f))
        for c in r["judge"]["candidates"][:3]:
            for d in DIMS:
                if isinstance(c.get("scores", {}).get(d), int):
                    acc[d].append(c["scores"][d])
    means[v] = {d: sum(x) / len(x) for d, x in acc.items()}
fig, ax = plt.subplots(figsize=(7.2, 3.2), dpi=200)
for i, d in enumerate(reversed(DIMS)):
    xs = [means[v][d] for v in VERS]
    ax.plot([min(xs), max(xs)], [i, i], color=GRID, linewidth=2, zorder=1)
    for v in VERS:
        ax.scatter(means[v][d], i, s=70, color=SERIES[v], edgecolor=SURFACE, linewidth=2, zorder=3, label=v if i == 0 else None)
    ax.text(means["v3"][d] + 0.04, i, f"{means['v3'][d]:.2f}", va="center", color=INK, fontsize=8)
ax.set_yticks(range(len(DIMS)), list(reversed(DIMS)), color=INK)
ax.set_xlim(3.4, 5.0)
ax.grid(axis="x", color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
for s in ["top", "right", "left"]:
    ax.spines[s].set_visible(False)
ax.tick_params(left=False)
ax.set_xlabel("Mean LLM-judge score (1–5), same frozen judge for all versions")
ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.02), frameon=False, ncol=3, fontsize=9)
ax.set_title("Judge scores by dimension", loc="left", color=INK, fontsize=11, fontweight="bold", pad=24)
plt.tight_layout()
fig.savefig(OUT / "judge_dimensions.png")
print(json.dumps({v: {d: round(x, 2) for d, x in m.items()} for v, m in means.items()}, indent=1))
