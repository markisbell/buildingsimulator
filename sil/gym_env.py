"""Gymnasium environment around the SIL building simulator.

Exposes the verified FMU plant (generic MultiTenantBuilding by default,
Building80s via fmu_path/n-zone autodetection) as a standard `gym.Env`:

  action       Box [0,1]^n — commanded valve openings, one per zone.
               Applied through the same 60 s full-stroke rate limit as the
               SIL harness, so an agent faces the real motor constraint.
  observation  [T_1..n (K), TSup, TRet, TOut, sp_1..n (K),
                sin(2*pi*h/24), cos(2*pi*h/24)]  (float32, raw units —
               normalization is the agent's business). Two modes:
               observation_mode="plant"  T_i = true room temperature
               observation_mode="device" T_i through the eTRV valve-mounted
                 sensor (thermostat.ValveSensor: radiator-proportional
                 lagged bias, 0.1 K quantization, noise) — the
                 learning-under-sensor-bias setting. Ground truth stays
                 available in info["TRoom_true"]; the REWARD always uses
                 the true temperatures (the physical objective), so agents
                 in device mode face a partially observed problem.
  reward       -( sum_occupied |T - sp| * dt/3600            [K*h]
                 + w_energy * Q_boiler * dt/3.6e6            [kWh]
                 + w_travel * sum |delta y| )                [strokes]
               components reported in `info` each step.
  episode      `episode_days` of the shared winter scenario (weather +
               facade solar + occupancy schedules from scenario_common);
               truncated at the horizon, never terminated early.

The supply side runs the standard supervisory logic internally
(outdoor-reset curve + Schnellaufheizung boost watching the true room
temperatures) — the agent controls valves only, like a swarm of eTRVs.
A device-realistic observation mode (through the eTRV sensor model) is a
planned extension; v1 observes plant-level room temperatures.

Smoke-test / validation: sil/run_gym_smoke.py.
"""

import re

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as exc:                       # pragma: no cover
    raise ImportError("pip install gymnasium") from exc

from fmpy import read_model_description

from boiler import Schnellaufheizung
from harness import STROKE_TIME, BuildingFMU
from scenario_common import (SCHEDULES, day_night_setpoint, heating_curve,
                             make_winter_scenario, winter_weather)
from thermostat import ValveSensor

DAY = 86400.0


class BuildingEnv(gym.Env):
    """One agent, all valves — the centralized-control view of the swarm."""

    metadata = {"render_modes": []}

    def __init__(self, fmu_path, episode_days=3, control_dt=300.0,
                 fmu_dt=60.0, w_energy=0.1, w_travel=0.01,
                 schedules=None, boost_dK=12.0, t_sup_max=348.15,
                 observation_mode="plant", q_rad_nominal=5100.0,
                 sensor_seed=0):
        super().__init__()
        if observation_mode not in ("plant", "device"):
            raise ValueError("observation_mode must be 'plant' or 'device'")
        self.observation_mode = observation_mode
        self.q_rad_nominal = q_rad_nominal   # scalar or per-zone sequence
        self.sensor_seed = sensor_seed
        self.fmu_path = str(fmu_path)
        md = read_model_description(self.fmu_path)
        names = {v.name for v in md.modelVariables}
        self.n = len([n for n in names if re.fullmatch(r"TRoom\[\d+\]", n)])
        self.has_manuals = "yPreset[1]" in names

        self.episode_days = episode_days
        self.control_dt = control_dt
        self.fmu_dt = fmu_dt
        self.w_energy = w_energy
        self.w_travel = w_travel
        self.schedules = schedules or SCHEDULES
        self._setpoints = {
            i: (day_night_setpoint(*s) if s is not None else None)
            for i, s in ((i, self.schedules.get(i))
                         for i in range(1, self.n + 1))}

        self._exogenous, _ = make_winter_scenario(self.n,
                                                  days=episode_days + 1)
        rooms = {f"TRoom[{i}]": sp for i, sp in self._setpoints.items()
                 if sp is not None}
        day_start = min(s[2] for s in self.schedules.values()
                        if s is not None)
        self._make_supply = lambda: Schnellaufheizung(
            lambda t: heating_curve(winter_weather(t)), rooms,
            day_start_h=day_start, boost_dK=boost_dK, t_sup_max=t_sup_max)

        self._outputs = ([f"TRoom[{i}]" for i in range(1, self.n + 1)]
                         + [f"QRad[{i}]" for i in range(1, self.n + 1)]
                         + ["TSup", "TRet", "QBoi"])

        self.action_space = spaces.Box(0.0, 1.0, (self.n,), np.float32)
        obs_dim = 2 * self.n + 5
        self.observation_space = spaces.Box(-np.inf, np.inf, (obs_dim,),
                                            np.float32)
        self._fmu = None

    # ------------------------------------------------------------------
    def _temps(self, meas, t):
        if self.observation_mode == "plant":
            return [meas[f"TRoom[{i}]"] for i in range(1, self.n + 1)]
        return [self._sensors[i - 1].read(t, meas[f"TRoom[{i}]"],
                                          meas[f"QRad[{i}]"])
                for i in range(1, self.n + 1)]

    def _obs(self, meas, t):
        sps = [self._setpoints[i](t) if self._setpoints[i] else 273.15
               for i in range(1, self.n + 1)]
        h = (t % DAY) / 3600.0
        vec = (self._temps(meas, t)
               + [meas["TSup"], meas["TRet"], meas.get("TOut", 0.0)]
               + sps
               + [np.sin(2 * np.pi * h / 24), np.cos(2 * np.pi * h / 24)])
        return np.asarray(vec, dtype=np.float32)

    def _exo(self, t):
        exo = dict(self._exogenous(t))
        if self.has_manuals:   # Building80s: rings/riser valves open
            exo.update({f"yPreset[{k}]": 1.0 for k in range(1, self.n + 1)})
            exo.update({f"yBalance[{s}]": 1.0 for s in range(1, 9)})
        return exo

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if self._fmu is not None:
            self._fmu.close()
        self._fmu = BuildingFMU(self.fmu_path)
        self._supply = self._make_supply()
        qn = (list(self.q_rad_nominal)
              if np.ndim(self.q_rad_nominal) else
              [self.q_rad_nominal] * self.n)
        self._sensors = [ValveSensor(q_rad_nominal=qn[i],
                                     seed=self.sensor_seed + i)
                         for i in range(self.n)]
        self._y = np.zeros(self.n)
        self._t = 0.0
        exo = self._exo(0.0)
        self._fmu.initialize({**exo,
                              **{f"yVal[{i}]": 0.0
                                 for i in range(1, self.n + 1)},
                              "TSupSet": self._supply.initial_output})
        meas = self._fmu.get_outputs(self._outputs)
        meas["TOut"] = exo["TOut"]
        return self._obs(meas, 0.0), {}

    def step(self, action):
        action = np.clip(np.asarray(action, dtype=float), 0.0, 1.0)
        travel = 0.0
        comfort_kh = 0.0
        energy_kwh = 0.0
        # sub-step the plant at fmu_dt with the motor rate limit active
        n_sub = max(1, int(round(self.control_dt / self.fmu_dt)))
        for _ in range(n_sub):
            meas = self._fmu.get_outputs(self._outputs)
            t_sup_set = self._supply.step(self._t, meas)
            max_dy = self.fmu_dt / STROKE_TIME
            y_new = np.clip(action, self._y - max_dy, self._y + max_dy)
            travel += float(np.abs(y_new - self._y).sum())
            self._y = y_new
            exo = self._exo(self._t)
            self._fmu.set_inputs({**exo, "TSupSet": t_sup_set,
                                  **{f"yVal[{i}]": self._y[i - 1]
                                     for i in range(1, self.n + 1)}})
            self._fmu.step(self.fmu_dt)
            self._t = self._fmu.time
            meas = self._fmu.get_outputs(self._outputs)
            for i in range(1, self.n + 1):
                sp = self._setpoints[i]
                if sp is not None:
                    comfort_kh += (abs(meas[f"TRoom[{i}]"] - sp(self._t))
                                   * self.fmu_dt / 3600.0)
            energy_kwh += max(meas["QBoi"], 0.0) * self.fmu_dt / 3.6e6

        meas["TOut"] = exo["TOut"]
        reward = -(comfort_kh + self.w_energy * energy_kwh
                   + self.w_travel * travel)
        truncated = self._t >= self.episode_days * DAY
        info = {"comfort_kh": comfort_kh, "energy_kwh": energy_kwh,
                "travel": travel, "t": self._t,
                "TRoom_true": np.array([meas[f"TRoom[{i}]"]
                                        for i in range(1, self.n + 1)])}
        return self._obs(meas, self._t), reward, False, truncated, info

    def close(self):
        if self._fmu is not None:
            self._fmu.close()
            self._fmu = None
