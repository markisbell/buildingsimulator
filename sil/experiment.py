"""Config-driven experiment assembly: controllers, metadata, KPIs.

Config dict (all fields optional, defaults shown):
  name          "experiment"
  controller    "realistic" | "ideal"
  durationDays  7
  cloudiness    0.4
  vacant        [3]            apartment ids without a thermostat
"""

import re

import pandas as pd

from controllers import PIThermostat, ScriptedValve
from thermostat import ElectronicThermostat, SampledPI
from scenario_common import (DAY, SCHEDULES, day_night_setpoint,
                             default_orientations, make_winter_scenario)
import kpi

CONTROL_DT = 60.0


def effective_schedules(n_apt, vacant):
    sched = {}
    for i in range(1, n_apt + 1):
        base = SCHEDULES.get((i - 1) % 6 + 1)  # repeat pattern beyond 6 apts
        sched[i] = None if i in vacant else base
    return sched


def apartments_meta(n_apt, schedules, controller_label):
    ori = default_orientations(n_apt)
    apts = []
    for i in range(1, n_apt + 1):
        s = schedules[i]
        apts.append({
            "id": i,
            "floor": (i - 1) // 2 + 1,
            "facade": "south" if ori[i] == 180.0 else "north",
            "vacant": s is None,
            "controller": "—" if s is None else controller_label,
            "schedule": "vacant" if s is None else
                        f"{s[0]:g} °C {s[2]}–{s[3]} h / {s[1]:g} °C",
        })
    return apts


def build_controllers(kind, n_apt, schedules):
    controllers = {}
    for i in range(1, n_apt + 1):
        s = schedules[i]
        if s is None:
            controllers[f"yVal[{i}]"] = ScriptedValve([(0.0, 0.0)])
        elif kind == "ideal":
            controllers[f"yVal[{i}]"] = PIThermostat(
                f"TRoom[{i}]", day_night_setpoint(*s), dt=CONTROL_DT)
        else:
            controllers[f"yVal[{i}]"] = ElectronicThermostat(
                temp_output=f"TRoom[{i}]",
                q_rad_output=f"QRad[{i}]",
                dp_output=f"dpVal[{i}]",
                algorithm=SampledPI(day_night_setpoint(*s)),
                seed=i)
    return controllers


def compute_kpis(df, controllers, schedules, duration):
    discomfort = overheat = 0.0
    for i, s in schedules.items():
        if s is None:
            continue
        sp = day_night_setpoint(*s)
        discomfort += kpi.discomfort_kh(df, f"TRoom[{i}]", sp)
        overheat += kpi.overheat_kh(df, f"TRoom[{i}]", sp)
    kpis = {
        "discomfortKh": round(discomfort, 1),
        "overheatKh": round(overheat, 1),
        "boilerKwh": round(kpi.boiler_energy_kwh(df), 1),
        "pumpKwh": round(kpi.pump_energy_kwh(df), 2),
    }
    thermostats = {n: c for n, c in controllers.items()
                   if isinstance(c, ElectronicThermostat)}
    devices = None
    if thermostats:
        travel, moves = kpi.battery_kpis(thermostats.values())
        kpis["valveTravelStrokes"] = round(travel, 1)
        kpis["valveMoves"] = moves
        devices = {}
        for n, th in thermostats.items():
            i = int(re.search(r"\[(\d+)\]", n).group(1))
            a = th.adaptation or {}
            devices[str(i)] = {
                "zeroErrorUm": round(a.get("zero_error_mm", 0) * 1000),
                "sealEstUm": round((a.get("seal_est_mm") or 0) * 1000),
                "travelMm": round(th.travel_mm, 1),
                "moves": th.n_moves,
                "adaptationAgeDays": round((duration - a.get("t", 0)) / DAY, 1),
            }
    else:
        travel = moves = 0
        for name in controllers:
            if name.startswith("yVal") and name in df.columns:
                dy = df[name].diff().abs().dropna()
                travel += dy.sum()
                moves += int((dy > 1e-9).sum())
        kpis["valveTravelStrokes"] = round(travel, 1)
        kpis["valveMoves"] = moves
    return kpis, devices
