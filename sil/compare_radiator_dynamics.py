"""A/B the radiator energy-dynamics change: quasi-static (before) vs
dynamic water/steel storage (after) on the same heat-up and cooldown
windows of the realistic-eTRV comparison run.

Usage:
  python3 compare_radiator_dynamics.py <dir-with-before-csvs>

The before-directory must hold cmp_ideal.csv / cmp_realistic.csv from the
quasi-static build (commit 1b6f60f); the after-CSVs are read from
results/. Writes results/radiator_dynamics_ab.png.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

C2K = 273.15
DAY = 86400.0
ROOT = Path(__file__).resolve().parents[1]
BEFORE = Path(sys.argv[1])

before_r = pd.read_csv(BEFORE / "cmp_realistic.csv")
after_r = pd.read_csv(ROOT / "results" / "cmp_realistic.csv")
before_i = pd.read_csv(BEFORE / "cmp_ideal.csv")
after_i = pd.read_csv(ROOT / "results" / "cmp_ideal.csv")


def window(df, h0, h1, d0=2):
    z = df[(df["time"] >= d0 * DAY + h0 * 3600)
           & (df["time"] <= d0 * DAY + h1 * 3600)].copy()
    z["h"] = (z["time"] - d0 * DAY) / 3600
    return z


fig, axes = plt.subplots(2, 2, figsize=(13, 8.5), sharey="row")

# --- heat-up window (06:00 boost, day 2) ---
for col in (0, 1):
    ideal, real = (before_i, before_r) if col == 0 else (after_i, after_r)
    zi, zr = window(ideal, 4.5, 14), window(real, 4.5, 14)
    ax = axes[0][col]
    ax.plot(zi["h"], zi["TRoom[1]"] - C2K, lw=1.4, label="ideal PI")
    ax.plot(zr["h"], zr["TRoom[1]"] - C2K, lw=1.4, label="realistic eTRV")
    ax.axhline(21, color="gray", ls="--", lw=0.8)
    ax.axvline(6, color="gray", ls=":", lw=0.8)
    ax.set_title(f"Heat-up — {'quasi-static (before)' if col == 0 else 'dynamic (after)'}")
    ax.set_xlabel("hour of day 2")
    if col == 0:
        ax.set_ylabel("room 1 / °C")
    ax.legend(fontsize=8)

# --- cooldown window (22:00 setback, day 2 -> 3) ---
for col in (0, 1):
    ideal, real = (before_i, before_r) if col == 0 else (after_i, after_r)
    zi, zr = window(ideal, 21.5, 30.2), window(real, 21.5, 30.2)
    ax = axes[1][col]
    ax.plot(zi["h"], zi["TRoom[1]"] - C2K, lw=1.4, label="ideal PI")
    ax.plot(zr["h"], zr["TRoom[1]"] - C2K, lw=1.4, label="realistic eTRV")
    ax.axhline(17, color="gray", ls="--", lw=0.8)
    ax.axvline(22, color="gray", ls=":", lw=0.8)
    ax.set_title(f"Cooldown — {'quasi-static (before)' if col == 0 else 'dynamic (after)'}")
    ax.set_xlabel("hour (day 2 continued)")
    if col == 0:
        ax.set_ylabel("room 1 / °C")
    ax.legend(fontsize=8)

fig.suptitle("Effect of radiator water/steel storage (8 l + 30 kg per kW)",
             fontsize=13)
fig.tight_layout()
out = ROOT / "results" / "radiator_dynamics_ab.png"
fig.savefig(out, dpi=150)
print(f"wrote {out}")

# numbers: overshoot and cooldown timing, realistic run
for name, df in [("before", before_r), ("after", after_r)]:
    z = window(df, 6, 16)
    t_max = z.loc[z["TRoom[1]"].idxmax()]
    z2 = window(df, 22, 30)
    below = z2[z2["TRoom[1]"] - C2K <= 17.0]
    t17 = below["h"].iloc[0] - 22 if len(below) else float("nan")
    print(f"{name}: day peak {t_max['TRoom[1]'] - C2K:.2f} degC at "
          f"{t_max['h']:.2f} h | setback-to-17degC {t17:.2f} h")
