"""BOPTEST benchmark: our controller stack vs the reference test case.

Runs, sequentially on the selected `multizone_residential_hydronic`
instance, each over the standardized peak_heat_day scenario:

    probe    2 baseline days to estimate per-zone radiator ratings
             (needed by the sensor-bias model)
    pi       plain PI per zone on the TRUE zone temperature
    stock    the stock eTRV firmware (ElectronicThermostat: sampled,
             biased valve-mounted sensor fed by BOPTEST's delivered-heat
             signal, deadband, backlash) — the device-pathology run
    ladder   the Phase 3 firmware (bias compensation + battery policies)

Scored with BOPTEST's own KPIs (tdis_tot, ener_tot, cost_tot, emis_tot).
Results -> results/boptest_benchmark.json. The externally interesting
question: does the independent BOPTEST plant reproduce the pathology gap
and the ladder recovery seen in our simulator?

  python sil/run_boptest_benchmark.py <testid>
"""

import json
import sys
from pathlib import Path

from boptest_adapter import ZONES, BoptestClient
from controllers import PIThermostat
from strategies import BatteryAwareThermostat
from thermostat import ElectronicThermostat, SampledPI

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
STEP_S = 300


def setpoint_fn(client, horizon_s):
    """Zone -> callable t -> lower comfort bound (K), from the forecast
    fetched once at scenario start."""
    f = client.lower_setpoints(horizon_s)
    times = f["time"]
    fns = {}
    for z in ZONES:
        series = f[f"LowerSetp[{z}]"]

        def sp(t, times=times, series=series):
            # nearest-neighbour lookup; forecast interval == step
            i = min(range(len(times)), key=lambda j: abs(times[j] - t))
            return series[i]

        fns[z] = sp
    return fns


def run_case(client, name, make_controllers, days=15):
    print(f"running: {name} ...", flush=True)
    client.set_scenario("peak_heat_day")
    client.set_step(STEP_S)
    sps = setpoint_fn(client, days * 86400)
    controllers = make_controllers(sps)

    payload = client.advance({})          # first step, no overwrites yet
    n = 1
    while payload:
        t = payload["time"]
        meas = {}
        for z in ZONES:
            meas[f"T[{z}]"] = client.zone_temp(payload, z)
            meas[f"Q[{z}]"] = client.zone_heat(payload, z)
        commands = {z: controllers[z].step(t, meas) if controllers else 0.0
                    for z in ZONES} if controllers else {}
        payload = client.advance(
            client.valve_inputs(commands) if controllers else {})
        n += 1
        if n % 864 == 0:
            print(f"  day {n * STEP_S // 86400} ...", flush=True)
    k = client.kpis()
    print(f"  {name}: " + " ".join(
        f"{key}={k[key]:.2f}" for key in
        ("tdis_tot", "ener_tot", "cost_tot", "emis_tot") if key in k))
    return k


def probe_ratings(client, days=2):
    """Short baseline run: per-zone max delivered heat ~ radiator rating."""
    client.set_scenario("peak_heat_day")
    client.set_step(STEP_S)
    qmax = {z: 0.0 for z in ZONES}
    for _ in range(days * 86400 // STEP_S):
        payload = client.advance({})
        if not payload:
            break
        for z in ZONES:
            qmax[z] = max(qmax[z], client.zone_heat(payload, z))
    print("probed radiator ratings (W):",
          {z: round(q) for z, q in qmax.items()})
    return qmax


def main():
    client = BoptestClient(testid=sys.argv[1] if len(sys.argv) > 1 else None)
    if client.testid is None:
        client.select()
        print("selected testid:", client.testid)

    qnom = probe_ratings(client)

    def make_pi(sps):
        return {z: PIThermostat(f"T[{z}]", sps[z], dt=STEP_S)
                for z in ZONES}

    def make_stock(sps):
        return {z: ElectronicThermostat(
            temp_output=f"T[{z}]", q_rad_output=f"Q[{z}]",
            q_rad_nominal=max(qnom[z], 500.0),
            algorithm=SampledPI(sps[z]), auto_adapt=True,
            seed=10 + i) for i, z in enumerate(ZONES)}

    def make_ladder(sps):
        return {z: BatteryAwareThermostat(
            temp_output=f"T[{z}]", q_rad_output=f"Q[{z}]",
            q_rad_nominal=max(qnom[z], 500.0),
            algorithm=SampledPI(sps[z]), auto_adapt=True,
            seed=10 + i) for i, z in enumerate(ZONES)}

    results = {}
    results["baseline"] = run_case(client, "baseline (embedded)", lambda sps: None)
    results["pi"] = run_case(client, "pi", make_pi)
    results["stock"] = run_case(client, "stock eTRV", make_stock)
    results["ladder"] = run_case(client, "ladder eTRV", make_ladder)

    (RESULTS / "boptest_benchmark.json").write_text(
        json.dumps(results, indent=1))
    print("\nwrote results/boptest_benchmark.json")

    keys = ("tdis_tot", "ener_tot", "cost_tot", "emis_tot")
    print(f"\n{'case':22s}" + "".join(f"{k:>12s}" for k in keys))
    for name, k in results.items():
        print(f"{name:22s}" + "".join(
            f"{k.get(key, float('nan')):12.2f}" for key in keys))


if __name__ == "__main__":
    main()
