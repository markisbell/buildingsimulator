"""VDI 6007-1 test cases 1-7 against the production 2R2C zone.

Drives build/VDI6007ZoneTest.fmu (the ApartmentBranch zone network,
extracted verbatim) with the excitations from data/vdi6007/cases.json and
compares hourly means on days 1/10/60 against the guideline reference
trajectories. Each case runs in two variants:

  production   C_air = 40 kJ/(m2 K) x 17.5 m2 = 0.70 MJ/K -- the furnished-
               room fast node exactly as parameterized in Building80s
  minimal-air  C_air = 63 kJ/K (bare room air) -- isolates the topology
               reduction from the deliberate fast-node convention, since
               the VDI reference network has NO air capacitance (VAir=0)

Diagnostic comparison, not a compliance claim: reported against the
guideline band (0.1 K / 1 W) and the AixLib implementation band
(0.15 K / 1.5 W). Results -> results/vdi6007_results.json + figure.
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from fmpy import simulate_fmu

ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "VDI6007ZoneTest.fmu")
CASES = json.loads((ROOT / "data" / "vdi6007" / "cases.json").read_text())["cases"]
RESULTS = ROOT / "results"

DAYS = 60
HOURS = DAYS * 24
STOP = DAYS * 86400.0
WINDOWS = [(3600.0, 86400.0), (781200.0, 864000.0), (5101200.0, 5184000.0)]
C_AIR = {"production": 0.70e6, "minimal-air": 0.063e6}


def hourly_from_table(table, col=1):
    """Day-periodic hourly value sequence from a step table (previous-value
    semantics; all VDI table breakpoints are hour-aligned)."""
    rows = np.array(table["rows"])
    t, v = rows[:, 0], rows[:, col] + table["offset"]
    out = np.empty(HOURS)
    for k in range(24):
        # value that holds during hour k of the day: sample just AFTER the
        # hour edge — the AixLib setpoint tables step via micro-ramps
        # (e.g. rows at 21600 and 21600.1), which exact-edge sampling misses
        i = np.searchsorted(t, k * 3600.0 + 1.0, side="right") - 1
        out[k::24] = v[i]
    return out


def build_input(case):
    """fmpy input array: piecewise-constant hour steps via duplicated
    breakpoints."""
    zeros = np.zeros(HOURS)
    qconv, qrad = zeros.copy(), zeros.copy()
    for target, col in case["gains_map"]:
        vals = hourly_from_table(case["intGai"], col)
        if target == "conv":
            qconv += vals
        else:
            qrad += vals
    if case.get("solarWindow"):
        ratio = case["vdi_params"]["ratioWinConRad"]
        raw = hourly_from_table(case["solarWindow"])
        if case.get("sunblind"):
            # sunblind closes above the irradiance threshold: g drops to 0.15
            b = case["sunblind"]
            raw = np.where(raw > b["threshold"], raw * b["g"], raw)
        sol = raw * case["A_transparent"] * case["vdi_params"]["gWin"]
        qconv += ratio * sol
        qrad += (1.0 - ratio) * sol
    tout = (hourly_from_table(case["outdoorTemp"])
            if case.get("outdoorTemp") else np.full(HOURS, 295.15))
    tset = (hourly_from_table(case["setTemp"]) + 273.15
            if case.get("setTemp") else np.full(HOURS, 295.15))

    # duplicated hour breakpoints -> exact steps
    t_edges = np.arange(HOURS + 1) * 3600.0
    times = np.repeat(t_edges, 2)[1:-1]

    def stepped(v):
        return np.repeat(v, 2)

    dtype = [("time", "f8"), ("TOut", "f8"), ("QConv", "f8"),
             ("QRadGain", "f8"), ("TSetHeat", "f8")]
    sig = np.zeros(len(times), dtype=dtype)
    sig["time"] = times
    sig["TOut"] = stepped(tout)
    sig["QConv"] = stepped(qconv)
    sig["QRadGain"] = stepped(qrad)
    sig["TSetHeat"] = stepped(tset)
    return sig


def run_case(n, case, c_air):
    m = case["mapped"]
    start_values = {
        "C_air": c_air, "C_mass": m["C_mass"], "G_int": m["G_int"],
        "G_wall": m["G_wall"], "G_win": m["G_win"],
        "T_start": m["T_start"], "heaterQ": case.get("heaterQ", 0.0)}
    res = simulate_fmu(FMU, start_values=start_values,
                       input=build_input(case),
                       output=["TAir", "QHeat"],
                       stop_time=STOP, output_interval=60.0)
    sig = res["QHeat"] if case["reference_is_power"] else res["TAir"]
    # hourly means over ((k-1) h, k h]; samples every 60 s, sample 0 at t=0
    hourly = sig[1:HOURS * 60 + 1].reshape(HOURS, 60).mean(axis=1)
    return hourly


def compare(case, hourly):
    rows = np.array(case["reference"]["rows"])
    t_ref = rows[:, 0]
    v_ref = rows[:, 1] + case["reference"]["offset"]
    mask = np.zeros(len(t_ref), dtype=bool)
    for lo, hi in WINDOWS:
        mask |= (t_ref >= max(lo, 3600.0)) & (t_ref <= hi)
    t_ref, v_ref = t_ref[mask], v_ref[mask]
    ours = hourly[(t_ref / 3600.0).astype(int) - 1]
    if case["reference_is_power"]:
        # the AixLib rigs differ in heat-flow sensor sign convention
        # (TC7 flips via gainMea k=-1); align by the better-matching sign
        if np.mean(np.abs(-ours - v_ref)) < np.mean(np.abs(ours - v_ref)):
            ours = -ours
    dev = ours - v_ref
    return t_ref, v_ref, ours, dev


def main():
    summary, trajectories = {}, {}
    for n in sorted(CASES, key=int):
        case = CASES[n]
        for variant, c_air in C_AIR.items():
            hourly = run_case(n, case, c_air)
            t_ref, v_ref, ours, dev = compare(case, hourly)
            key = f"TC{n}/{variant}"
            per_win = []
            for lo, hi in WINDOWS:
                m = (t_ref >= lo) & (t_ref <= hi)
                per_win.append(round(float(np.abs(dev[m]).max()), 3))
            summary[key] = {
                "max_abs_dev": round(float(np.abs(dev).max()), 3),
                "rms_dev": round(float(np.sqrt((dev ** 2).mean())), 3),
                "per_window_max": per_win,
                "threshold_aixlib": case["threshold"],
                "threshold_guideline": 1.0 if case["reference_is_power"] else 0.1,
                "unit": "W" if case["reference_is_power"] else "K",
            }
            trajectories[key] = (t_ref, v_ref, ours)
            print(f"{key:22s} max|dev| {summary[key]['max_abs_dev']:8.3f} "
                  f"{summary[key]['unit']}  (windows {per_win})")

    (RESULTS / "vdi6007_results.json").write_text(json.dumps({
        "windows_s": WINDOWS, "c_air_variants": C_AIR,
        "summary": summary}, indent=1))

    # figure: per-case day-1 + day-60 trajectories, reference vs variants
    fig, axes = plt.subplots(2, 4, figsize=(15, 6.5))
    for i, n in enumerate(sorted(CASES, key=int)):
        ax = axes.flat[i]
        power = CASES[n]["reference_is_power"]
        for variant, style in (("production", "-"), ("minimal-air", "--")):
            t, ref, ours = trajectories[f"TC{n}/{variant}"]
            x = np.arange(len(t))
            if variant == "production":
                ax.step(x, ref - (0 if power else 273.15), where="mid",
                        color="#1F2125", lw=1.6, label="VDI reference")
            ax.plot(x, ours - (0 if power else 273.15), style,
                    color="#B8432F", lw=1.1, label=f"2R2C {variant}")
        ax.set_title(f"TC{n}" + (" (heater W)" if power else " (°C)"),
                     fontsize=10)
        ax.axvline(23.5, color="gray", lw=0.5)
        ax.axvline(46.5, color="gray", lw=0.5)
        ax.text(0.02, 0.95, "d1 | d10 | d60", transform=ax.transAxes,
                fontsize=7, va="top", color="gray")
        if i == 0:
            ax.legend(fontsize=7)
    ax = axes.flat[7]
    keys = [f"TC{n}" for n in sorted(CASES, key=int)]
    for j, (variant, color) in enumerate(
            (("production", "#B8432F"), ("minimal-air", "#2E5E8C"))):
        devs = [summary[f"{k}/{variant}"]["max_abs_dev"] /
                (10.0 if summary[f"{k}/{variant}"]["unit"] == "W" else 1.0)
                for k in keys]
        ax.bar(np.arange(len(keys)) + 0.4 * j - 0.2, devs, 0.36,
               color=color, label=variant)
    ax.axhline(0.15, color="gray", ls="--", lw=0.8)
    ax.text(0.02, 0.152, "0.15 K / 1.5 W band", fontsize=7, color="gray")
    ax.set_xticks(range(len(keys)), keys, fontsize=8)
    ax.set_ylabel("max |dev| / K (heater: W/10)")
    ax.set_title("Deviation summary", fontsize=10)
    ax.legend(fontsize=7)
    for ax in axes.flat:
        ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(RESULTS / "vdi6007_check.png", dpi=150)
    print("wrote results/vdi6007_results.json + results/vdi6007_check.png")


if __name__ == "__main__":
    main()
