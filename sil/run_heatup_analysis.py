"""Decompose one morning heat-up (generic building, realistic eTRV run):
room temperature, radiator power, water temperatures, solar gain.
Evidence figure for docs/heatup-dynamics.md.

Run inside the container after run_thermostat_comparison.py:
  docker run --rm -v ${PWD}:/work -w /work/sil buildingsimulator:dev \
      python3 run_heatup_analysis.py
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

C2K = 273.15
DAY = 86400.0
ROOT = Path(__file__).resolve().parents[1]

df = pd.read_csv(ROOT / "results" / "cmp_realistic.csv")
z = df[(df["time"] >= 2 * DAY + 4.5 * 3600) & (df["time"] <= 2 * DAY + 13 * 3600)]
h = (z["time"] - 2 * DAY) / 3600

fig, axes = plt.subplots(4, 1, figsize=(11, 10), sharex=True)
axes[0].plot(h, z["TRoom[1]"] - C2K, lw=1.6)
axes[0].axvline(6, color="gray", ls=":", lw=0.8)
axes[0].set_ylabel("room 1 / °C")
axes[0].set_title("Morning heat-up decomposition — apartment 1 (south), day 2")

axes[1].plot(h, z["QRad[1]"], label="radiator power", lw=1.2)
axes[1].plot(h, z["QGain[1]"], label="solar gain", lw=1.2)
axes[1].set_ylabel("W")
axes[1].legend(fontsize=8)

axes[2].plot(h, z["TSup"] - C2K, label="supply", lw=1.2)
axes[2].plot(h, z["TRet"] - C2K, label="return", lw=1.2)
axes[2].set_ylabel("water / °C")
axes[2].legend(fontsize=8)

axes[3].plot(h, z["mFlow[1]"] * 3600, lw=1.2)
axes[3].set_ylabel("flow / l/h")
axes[3].set_xlabel("hour of day 2")

fig.tight_layout()
fig.savefig(ROOT / "results" / "heatup_decomposition.png", dpi=150)
print("wrote results/heatup_decomposition.png")
