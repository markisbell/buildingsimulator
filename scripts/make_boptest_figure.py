"""Render results/boptest_benchmark.png from results/boptest_benchmark.json
(produced by sil/run_boptest_benchmark.py) for the verification report."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS = Path(__file__).resolve().parents[1] / "results"
k = json.loads((RESULTS / "boptest_benchmark.json").read_text())

CASES = [
    ("baseline", "BOPTEST baseline\n(embedded controller)", "#8a8577"),
    ("pi", "plain PI\n(true zone temp)", "#2E5E8C"),
    ("stock", "stock eTRV\n(biased valve sensor)", "#B8432F"),
    ("ladder", "ladder eTRV\n(Phase 3 firmware)", "#2F7D46"),
]

fig, (ax1, ax2) = plt.subplots(
    1, 2, figsize=(9.6, 3.6), gridspec_kw={"width_ratios": [1.15, 1]})

labels = [lab for _, lab, _ in CASES]
colors = [c for _, _, c in CASES]
y = range(len(CASES))

tdis = [k[key]["tdis_tot"] for key, _, _ in CASES]
ax1.barh(y, tdis, color=colors, height=0.62)
for i, v in enumerate(tdis):
    ax1.text(v + 0.8, i, f"{v:.1f}", va="center", fontsize=9)
ax1.set_yticks(y, labels, fontsize=8.5)
ax1.invert_yaxis()
ax1.set_xlabel("thermal discomfort  tdis_tot  [K·h/zone]  (two-sided)",
               fontsize=9)
ax1.set_xlim(0, max(tdis) * 1.14)

ener = [k[key]["ener_tot"] for key, _, _ in CASES]
ax2.barh(y, ener, color=colors, height=0.62)
for i, v in enumerate(ener):
    ax2.text(v + 0.05, i, f"{v:.2f}", va="center", fontsize=9)
ax2.set_yticks(y, ["" for _ in CASES])
ax2.invert_yaxis()
ax2.set_xlabel("HVAC energy  ener_tot  [kWh/m²]", fontsize=9)
ax2.set_xlim(0, max(ener) * 1.14)

for ax in (ax1, ax2):
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(labelsize=8.5)

fig.suptitle("BOPTEST multizone_residential_hydronic · peak_heat_day (14 d) · "
             "BOPTEST KPIs", fontsize=10)
fig.tight_layout(rect=(0, 0, 1, 0.94))
out = RESULTS / "boptest_benchmark.png"
fig.savefig(out, dpi=150)
print(f"wrote {out}")
