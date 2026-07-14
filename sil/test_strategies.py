"""Unit probe: night-anchor bias learning on synthetic rooms.

Two stand-in plants exercise the estimator's hard cases:

  slow  living-like room (tau ~ 48 h): long night closures, the easy case
  fast  bath-like room (strong relative losses incl. hall door): the
        valve reopens ~2-2.5 h after setback, so the anchor must work on
        a PARTIAL bias decay — the k_hat = 0 straggler case found in the
        coordinated-recovery experiment

Both include a radiator-storage tail (stored heat keeps emitting after
closure, tau_e ~ 40 min) — the effect that broke the original
settle-window estimator. Pass criterion: both devices learn k_hat > 0.5
within 3 nights.

  python sil/test_strategies.py
"""
import numpy as np

from scenario_common import day_night_setpoint
from strategies import BatteryAwareThermostat
from thermostat import SampledPI

T_OUT = -5.0
DT = 30.0

PLANTS = {
    #        C_air      G     Q_nom  day/night sp
    "slow": (7.2e6,   41.4,  1700.0, (20.0, 17.0)),
    "fast": (1.2e6,   25.0,  1200.0, (24.0, 21.0)),
}

for name, (C, G, qnom, (sp_d, sp_n)) in PLANTS.items():
    dev = BatteryAwareThermostat(
        temp_output="TRoom", q_rad_output="QRad", dp_output=None,
        q_rad_nominal=qnom,
        algorithm=SampledPI(day_night_setpoint(sp_d, sp_n, 6, 22)),
        seed=hash(name) % 1000)
    T = sp_d + 273.15
    q = q_store = 0.0
    closure_h = None
    t_close = None
    for i in range(int(3 * 86400 / DT)):
        t = i * DT
        y = dev.step(t, {"TRoom": T, "QRad": q})
        phi = min(1.0, (max(0.0, y) / 0.3) ** 0.5)
        q_hyd = qnom * 1.25 * phi ** 0.7 if phi > 0 else 0.0
        # radiator storage: emitted power lags hydraulic delivery (tau_e)
        q_store += (q_hyd - q_store) * min(1.0, DT / 2400.0)
        q = q_store
        T += (0.65 * q + G * ((T_OUT + 273.15) - T)) / C * DT
        # measure the first night's closure length
        if y <= 0.001 and t_close is None and t > 12 * 3600:
            t_close = t
        if y > 0.02 and t_close is not None and closure_h is None:
            closure_h = (t - t_close) / 3600
    print(f"{name}: first-night closure ~{closure_h if closure_h else float('nan'):.1f} h | "
          f"k_log {[(round(tt/3600,1), round(k,2)) for tt, k in dev.k_log]} | "
          f"k_hat {dev.k_hat:.2f} "
          f"{'PASS' if dev.k_hat > 0.5 else 'FAIL'}")
    for dbg in dev.anchor_debug:
        print(f"   anchor @{dbg['t_h']:.1f}h T={dbg['T_h']:.2f}h "
              f"d={dbg['d']} rho={dbg['rho'] if dbg['rho'] is None else round(dbg['rho'],2)} "
              f"b0={dbg['b0']} u0={dbg['u0']} k_obs={dbg['k_obs']}")
