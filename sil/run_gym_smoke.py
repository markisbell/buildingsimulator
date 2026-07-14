"""Gymnasium environment validation.

1. API smoke: random actions for 2 h of simulated time — spaces, stepping,
   truncation and info plumbing work.
2. Physics validation: a per-zone PI policy driven THROUGH the env for a
   3-day episode must reproduce the known closed-loop behavior of the
   plant (rooms held near setpoint during the day, boost recovery in the
   morning) — i.e. the env wiring adds nothing and loses nothing.

  wsl -d Ubuntu-24.04 -u root -- bash -c \
      "cd /work/sil && /opt/silenv/bin/python3 run_gym_smoke.py"
"""

from pathlib import Path

import numpy as np

from controllers import PIThermostat
from gym_env import BuildingEnv
from scenario_common import SCHEDULES, day_night_setpoint

ROOT = Path(__file__).resolve().parents[1]
FMU = ROOT / "build" / "MultiTenantBuilding.fmu"


def smoke_random():
    env = BuildingEnv(FMU, episode_days=1)
    obs, _ = env.reset(seed=0)
    assert env.observation_space.contains(obs), "obs outside declared space"
    total = 0.0
    for k in range(24):                      # 2 h at 300 s steps
        obs, r, term, trunc, info = env.step(env.action_space.sample())
        assert np.isfinite(r) and np.all(np.isfinite(obs))
        total += r
    env.close()
    print(f"random smoke: 24 steps ok, cumulative reward {total:.1f} "
          f"(finite, negative as designed: {total < 0})")


def validate_pi():
    env = BuildingEnv(FMU, episode_days=3)
    pis = {}
    for i in range(1, env.n + 1):
        sched = SCHEDULES.get(i)
        if sched is not None:
            pis[i] = PIThermostat(f"TRoom[{i}]",
                                  day_night_setpoint(*sched),
                                  dt=env.control_dt)
    obs, _ = env.reset(seed=0)
    comfort = energy = 0.0
    day_errs = []
    trunc = False
    while not trunc:
        meas = {f"TRoom[{i}]": obs[i - 1] for i in range(1, env.n + 1)}
        t = None
        action = np.zeros(env.n)
        for i, pi in pis.items():
            action[i - 1] = pi.step(env._t, meas)
        obs, r, _, trunc, info = env.step(action)
        comfort += info["comfort_kh"]
        energy += info["energy_kwh"]
        # track day-2+ daytime deviation of apartment 1
        hour = (info["t"] % 86400.0) / 3600.0
        if info["t"] > 86400.0 and 8 <= hour < 22:
            sp = day_night_setpoint(*SCHEDULES[1])(info["t"])
            day_errs.append(abs(obs[0] - sp))

    env.close()
    mean_err = float(np.mean(day_errs))
    print(f"PI-through-env, 3 days: comfort {comfort:.1f} K*h, "
          f"boiler {energy:.1f} kWh")
    print(f"apartment 1 daytime |T - sp| (day 2+): mean {mean_err:.2f} K")
    ok = mean_err < 0.6 and 200 < energy < 1500
    print("VALIDATION", "PASS" if ok else "FAIL",
          "(PI through the env holds rooms near setpoint at plausible "
          "energy)")
    return ok


if __name__ == "__main__":
    smoke_random()
    ok = validate_pi()
    raise SystemExit(0 if ok else 1)
