"""Config-driven experiment runner (launched by the API server or CLI).

Usage:
  python3 run_experiment.py '{"name": "my-run", "controller": "realistic",
                              "durationDays": 7, "cloudiness": 0.4, "vacant": [3]}'
"""

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd
from fmpy import read_model_description

from harness import run_simulation
from runstore import create_run
from scenario_common import DAY, make_winter_scenario
import experiment

ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "MultiTenantBuilding.fmu")


def main(config: dict):
    name = re.sub(r"[^a-zA-Z0-9_-]+", "-", config.get("name", "experiment"))[:48]
    kind = config.get("controller", "realistic")
    duration = float(config.get("durationDays", 7)) * DAY
    cloudiness = float(config.get("cloudiness", 0.4))
    vacant = set(config.get("vacant", [3]))

    md = read_model_description(FMU)
    n_apt = len([v for v in md.modelVariables
                 if re.fullmatch(r"TRoom\[\d+\]", v.name)])
    schedules = experiment.effective_schedules(n_apt, vacant)
    label = "ideal PI" if kind == "ideal" else "eTRV / SampledPI"

    writer = create_run(name, {
        "durationDays": duration / DAY,
        "building": {"floors": n_apt // 2, "apartmentsPerFloor": 2},
        "scenario": {"weather": "synthetic winter + clear-sky solar",
                     "cloudiness": cloudiness, "startDate": "2026-01-12"},
        "apartments": experiment.apartments_meta(n_apt, schedules, label),
        "config": config,
        "pid": os.getpid(),
    })
    try:
        exogenous, _ = make_winter_scenario(
            n_apt, cloudiness=cloudiness, days=int(duration / DAY) + 1)
        controllers = experiment.build_controllers(kind, n_apt, schedules)
        outputs = ([f"TRoom[{i}]" for i in range(1, n_apt + 1)]
                   + [f"mFlow[{i}]" for i in range(1, n_apt + 1)]
                   + [f"QRad[{i}]" for i in range(1, n_apt + 1)]
                   + [f"dpVal[{i}]" for i in range(1, n_apt + 1)]
                   + ["TSup", "TRet", "QBoi", "PPum"])
        records = run_simulation(FMU, controllers, exogenous,
                                 duration=duration,
                                 control_dt=experiment.CONTROL_DT,
                                 output_names=outputs,
                                 record_dt=experiment.CONTROL_DT,
                                 on_record=writer.append)
        df = pd.DataFrame(records)
        kpis, devices = experiment.compute_kpis(df, controllers, schedules,
                                                duration)
        writer.finish(kpis=kpis, devices=devices)
        print(f"finished: {writer.manifest['id']}")
    except Exception as e:
        writer.finish(status="failed")
        raise


if __name__ == "__main__":
    main(json.loads(sys.argv[1]) if len(sys.argv) > 1 else {})
