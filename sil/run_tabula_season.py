"""TABULA season validation, part 1: simulate Building80s over a real
heating season (chunk-capable for parallel execution).

Scenario = era-authentic normal operation:
  - measured weather: DWD Rheinstetten 04177, hourly T + global/diffuse
    radiation (data/weather/, CC BY 4.0 "Quelle: Deutscher Wetterdienst"),
    season 2023-10-01 .. 2024-04-30, facade solar via pvlib transposition
  - realistic eTRVs everywhere, constant era setpoints (20/20/20/24 degC)
  - central two-point boiler on the 90/70 curve with Nachtabsenkung
    (-15 K on the curve 22:00-05:00) and Schnellaufheizung morning boost
  - stochastic internal gains + window events (fixed seed: chunks share
    one season profile)
  - manual valves fully open (authentic unbalanced as-built state)

Usage:  run_tabula_season.py <start_day> <days> <tag> [control_dt]
    start_day: offset from 2023-10-01 (chunks start 3 days early and the
               analyzer drops the warm-up)
Writes results/tabula_season_<tag>.csv.gz + .meta.json.
Aggregation and TABULA comparison: analyze_tabula_season.py.
"""

import gzip
import json
import sys
import time as clock
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib

from harness import run_simulation
from thermostat import ElectronicThermostat, SampledPI
from boiler import TwoPointBoiler, Schnellaufheizung
from gains import InternalGains
from scenario_common import C2K, DAY
from run_balancing import (FMU, N_ZON, N_FLO, T_SET, q_rad_nominal,
                           manual_inputs, zone_k)

ROOT = Path(__file__).resolve().parents[1]
WEATHER_CSV = ROOT / "data" / "weather" / "rheinstetten_2023-07_2024-06.csv"
RESULTS = ROOT / "results"

# station Rheinstetten (DWD 04177)
LAT, LON, ALT = 48.9726, 8.3301, 116.0
# season start 2023-10-01 00:00 local standard time (UTC+1)
T0_UTC = pd.Timestamp("2023-09-30 23:00:00", tz="UTC")

ORIENT = {1: 180.0, 2: 180.0, 3: 0.0, 4: 0.0, 5: 180.0, 6: 180.0, 7: 0.0, 8: 0.0}
WIN_AREA = {1: 4.6, 2: 2.8, 3: 1.8, 4: 0.8, 5: 4.6, 6: 2.8, 7: 1.8, 8: 0.8}
G_VALUE, FRAME_SHADING = 0.75, 0.7
SETBACK_K = 15.0          # Nachtabsenkung on the supply curve
NIGHT_FROM, NIGHT_TO = 22.0, 5.0   # h, local standard time
SEASON_DAYS_TOTAL = 213   # 2023-10-01 .. 2024-04-30


def heating_curve_9070(t_out_k):
    t_out = t_out_k - C2K
    t_sup = 30.0 + (90.0 - 30.0) * (20.0 - t_out) / 32.0
    return min(max(t_sup, 30.0), 90.0) + C2K


def load_weather():
    w = pd.read_csv(WEATHER_CSV, parse_dates=["time_utc"], index_col="time_utc")
    sec = (w.index - T0_UTC).total_seconds().to_numpy()
    tout = w["t_air_C"].to_numpy() + C2K

    # facade gains from measured radiation; solar position at mid-interval
    # (hourly values are interval means labelled at the left edge)
    loc = pvlib.location.Location(LAT, LON, tz="UTC", altitude=ALT)
    solpos = loc.get_solarposition(w.index + pd.Timedelta("30min"))
    zen = solpos["apparent_zenith"].to_numpy()
    cosz = np.clip(np.cos(np.radians(zen)), 0.065, None)
    ghi = w["ghi_Wm2"].to_numpy()
    dhi = np.minimum(w["dhi_Wm2"].to_numpy(), ghi)
    dni = np.clip((ghi - dhi) / cosz, 0.0, 1100.0)
    dni[zen > 87.0] = 0.0

    gains = {}
    for s, az in ORIENT.items():
        poa = pvlib.irradiance.get_total_irradiance(
            surface_tilt=90.0, surface_azimuth=az,
            solar_zenith=solpos["apparent_zenith"], solar_azimuth=solpos["azimuth"],
            dni=dni, ghi=ghi, dhi=dhi)
        gains[s] = (np.nan_to_num(np.asarray(poa["poa_global"], dtype=float))
                    .clip(min=0.0) * WIN_AREA[s] * G_VALUE * FRAME_SHADING)
    return sec, tout, gains


def main():
    start_day, days, tag = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    control_dt = float(sys.argv[4]) if len(sys.argv) > 4 else 60.0
    offset = start_day * DAY

    sec, tout, solar = load_weather()
    intern = InternalGains(N_ZON, days=SEASON_DAYS_TOTAL + 4, seed=7)
    manuals = manual_inputs(None)  # fully open, as-built

    def tout_at(t_abs):
        return float(np.interp(t_abs, sec, tout))

    def curve(t_abs):
        base = heating_curve_9070(tout_at(t_abs))
        hour = (t_abs / 3600.0) % 24.0
        if hour >= NIGHT_FROM or hour < NIGHT_TO:
            base = max(base - SETBACK_K, C2K + 25.0)
        return base

    def exogenous(t):
        t_abs = t + offset
        internal = intern.gains(t_abs)
        return {"TOut": tout_at(t_abs),
                **{f"QGain[{k}]":
                   float(np.interp(t_abs, sec, solar[(k - 1) % 8 + 1]))
                   + internal[k] for k in range(1, N_ZON + 1)},
                **manuals}

    setpoints = {f"TRoom[{k}]": (lambda t, sp=T_SET[(k - 1) % 8]: sp + C2K)
                 for k in range(1, N_ZON + 1)}
    booster = Schnellaufheizung(lambda t: curve(t + offset), setpoints,
                                day_start_h=NIGHT_TO)
    controllers = {"TSupSet": TwoPointBoiler(lambda t: curve(t + offset),
                                             booster=booster)}
    for f in range(1, N_FLO + 1):
        for s in range(8):
            k = zone_k(f, s)
            controllers[f"yVal[{k}]"] = ElectronicThermostat(
                temp_output=f"TRoom[{k}]", q_rad_output=f"QRad[{k}]",
                dp_output=f"dpVal[{k}]",
                algorithm=SampledPI(T_SET[s] + C2K),
                q_rad_nominal=q_rad_nominal(f, s), seed=k)

    outputs = ([f"TRoom[{k}]" for k in range(1, N_ZON + 1)]
               + [f"QRad[{k}]" for k in range(1, N_ZON + 1)]
               + [f"dpVal[{k}]" for k in range(1, N_ZON + 1)]
               + ["TSup", "TRet", "QBoi", "PPum"])

    print(f"chunk {tag}: day {start_day} +{days} d, dt={control_dt:g} s",
          flush=True)
    wall0 = clock.time()
    records = run_simulation(FMU, controllers, exogenous, duration=days * DAY,
                             control_dt=control_dt, output_names=outputs,
                             record_dt=300.0)
    wall = clock.time() - wall0

    df = pd.DataFrame(records)
    keep = (["time", "TOut", "TSup", "TRet", "QBoi", "PPum"]
            + [f"TRoom[{k}]" for k in range(1, N_ZON + 1)]
            + [f"QRad[{k}]" for k in range(1, N_ZON + 1)])
    out = RESULTS / f"tabula_season_{tag}.csv.gz"
    with gzip.open(out, "wt") as fh:
        df[keep].to_csv(fh, index=False)
    (RESULTS / f"tabula_season_{tag}.meta.json").write_text(json.dumps({
        "tag": tag, "start_day": start_day, "days": days,
        "control_dt": control_dt, "wall_s": round(wall, 1),
        "boost_hours": round(booster.boost_hours, 1),
        "burner_starts": controllers["TSupSet"].n_starts}))
    print(f"chunk {tag} done: {wall/60:.1f} min wall, "
          f"{controllers['TSupSet'].n_starts} burner starts -> {out.name}",
          flush=True)


if __name__ == "__main__":
    main()
