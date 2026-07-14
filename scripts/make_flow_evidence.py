"""Valve opening vs actual pipe flow — evidence figure for the
verification report and docs/valve-modeling.md.

Reads results/coord_greedy.csv (Building80s, as-built rings, room-level
eTRVs; records both the commanded opening yVal[k] and the measured branch
flow mFlow[k]) and produces results/valve_flow_evidence.png:

  left   time series of opening and flow through one morning recovery —
         the flow at CONSTANT full opening falls as the neighbours close
         (riser interaction), then the staircase of the settling eTRV
  right  flow vs opening across five days: the installed quick-opening
         characteristic emerges as a BAND, not a curve — same opening,
         different flow depending on what the rest of the building does

  wsl -d Ubuntu-24.04 -u root -- bash -c \
      "cd /work && /opt/silenv/bin/python3 scripts/make_flow_evidence.py"
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DAY = 86400.0
K = 9                      # living room S, apartment 1, mid floor
Q_NOM = 1742.0             # W, its radiator rating (docs section 4)
M_DESIGN = Q_NOM / 4186.0 / 20.0 * 3600.0   # l/h at the 20 K spread

# TRV table from ApartmentBranch.mo
Y_CHA = [0, .03, .06, .10, .15, .22, .30, .45, .65, 1.0]
PHI_CHA = [1.5e-3, 2e-3, 3e-3, 0.12, 0.35, 0.60, 0.78, 0.88, 0.94, 1.0]

df = pd.read_csv(ROOT / "results" / "coord_greedy.csv")
y = df[f"yVal[{K}]"].to_numpy()
m = df[f"mFlow[{K}]"].to_numpy() * 3600.0
t = df["time"].to_numpy()

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))

# ---- left: one recovery morning, opening vs flow ----
w = (t >= 5 * DAY + 4.0 * 3600) & (t <= 5 * DAY + 12 * 3600)
h = (t[w] - 5 * DAY) / 3600.0
ax1.step(h, y[w], where="post", color="#2E5E8C", lw=1.4, label="opening y")
ax1.set_ylabel("valve opening / –", color="#2E5E8C")
ax1.set_ylim(0, 1.05)
ax1b = ax1.twinx()
ax1b.plot(h, m[w], color="#B8432F", lw=1.2, label="branch flow")
ax1b.set_ylabel("branch flow / l/h", color="#B8432F")
ax1.axvline(6, color="gray", ls=":", lw=0.8)
ax1.set_xlabel("hour of day 6")
ax1.set_title("Same opening, changing flow: the network works against you\n"
              "(06:00 boost: the neighbours open and this branch's flow collapses)")

# ---- right: installed characteristic as a band ----
w = (t >= 1 * DAY) & (t <= 6 * DAY)
sc = ax2.scatter(y[w], m[w], s=2, alpha=0.15, color="#2E5E8C",
                 label="operating points (days 1–6)")
yy = np.linspace(0, 1, 200)
phi = np.interp(yy, Y_CHA, PHI_CHA)
# reference: pure table shape scaled through the full-open median
full = np.median(m[w][y[w] > 0.95]) if np.any(y[w] > 0.95) else M_DESIGN
ax2.plot(yy, phi * full, color="#B8432F", lw=1.6,
         label="Kv table × full-open flow")
band_lo, band_hi = None, None
sel = w & (y >= 0.10) & (y <= 0.20)
if np.any(sel):
    band_lo, band_hi = np.percentile(m[sel], [5, 95])
    ax2.axvspan(0.10, 0.20, color="gray", alpha=0.10)
ax2.set_xlabel("valve opening / –")
ax2.set_ylabel("branch flow / l/h")
ax2.set_title("Installed characteristic is a band, not a curve\n"
              "(riser interaction spreads the flow at fixed opening)")
ax2.legend(fontsize=8, loc="upper left")

fig.tight_layout()
out = ROOT / "results" / "valve_flow_evidence.png"
fig.savefig(out, dpi=150)
print(f"wrote {out}")
if band_lo is not None:
    print(f"flow at working stroke y=0.13-0.17: {band_lo:.1f}-{band_hi:.1f} l/h "
          f"(P5-P95, spread ±{(band_hi-band_lo)/(band_hi+band_lo)*100:.0f} % "
          f"around the mid)")
print(f"full-open median flow: {full:.1f} l/h (design {M_DESIGN:.1f})")
