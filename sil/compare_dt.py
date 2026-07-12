"""Compare oscillation signatures between the 30 s and 10 s runs on the
overlapping day-2 window [24 h, 41 h]."""
import glob

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

C2K = 273.15
T0, T1 = 24 * 3600, 41 * 3600


def load(pattern):
    path = sorted(glob.glob(f"/work/runs/*{pattern}/series.csv"))[-1]
    df = pd.read_csv(path)
    return df[(df["time"] >= T0) & (df["time"] <= T1)].reset_index(drop=True)


def signatures(d):
    firing = (d["QBoi"] > 500).astype(int)
    starts = int((firing.diff() == 1).sum())
    hours = (d["time"].iloc[-1] - d["time"].iloc[0]) / 3600
    pkpk = d["TSup"].quantile(0.98) - d["TSup"].quantile(0.02)
    troom = d["TRoom[9]"] - C2K
    ripple = (troom - troom.rolling(60, center=True, min_periods=1).mean()).std()
    flow = d["mFlow[9]"] * 3600
    cv = flow.std() / max(flow.mean(), 1e-9)
    return {"starts_per_day": starts / hours * 24, "pkpk_K": pkpk,
            "ripple_K": ripple, "flow_cv": cv,
            "mean_QBoi_kW": d["QBoi"].mean() / 1000,
            "mean_TRoom9_C": troom.mean()}


d30 = load("typical-day-80s-realistic")
d10 = load("typical-day-80s-realistic-dt10")
s30, s10 = signatures(d30), signatures(d10)

print(f"{'signature':28s} {'dt=30 s':>10s} {'dt=10 s':>10s} {'diff %':>8s}")
for k in s30:
    a, b = s30[k], s10[k]
    print(f"{k:28s} {a:10.3f} {b:10.3f} {(b/a-1)*100:8.1f}")

fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
for d, label, lw in ((d30, "dt = 30 s", 1.3), (d10, "dt = 10 s", 0.9)):
    z = d[(d["time"] >= 24 * 3600 + 7 * 3600) & (d["time"] <= 24 * 3600 + 10 * 3600)]
    h = (z["time"] - 24 * 3600) / 3600
    axes[0].plot(h, z["TSup"] - C2K, lw=lw, label=label)
    axes[1].plot(h, z["mFlow[9]"] * 3600, lw=lw, label=label)
axes[0].set_ylabel("supply / °C")
axes[0].legend(fontsize=9)
axes[0].set_title("Communication-step comparison — day 2, 07–10 h")
axes[1].set_ylabel("flow living A1 F2 / l/h")
axes[1].set_xlabel("time / h")
axes[1].legend(fontsize=9)
fig.tight_layout()
fig.savefig("/work/results/dt_comparison_80s.png", dpi=150)
print("plot: results/dt_comparison_80s.png")
