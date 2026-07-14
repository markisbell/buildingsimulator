"""Unit probe: does the night-anchor bias learning fire on a synthetic room?

Pure-Python fake plant (no FMU): one RC room, radiator power proportional
to pin fraction, sensor pipeline exercised through the real device class.
Day setpoint 20, setback to 17 at 22:00 — the anchor must produce one
k_hat update per night.

  python sil/test_strategies.py
"""
import numpy as np

from scenario_common import day_night_setpoint
from strategies import BatteryAwareThermostat
from thermostat import SampledPI

Q_NOM = 1700.0
# single-node stand-in for the calibrated room: lump air+mass so the
# free-cool rate matches the building (~0.35 K/h), otherwise the night
# closure ends before the storage-aware anchor window completes
C_AIR, G = 7.2e6, 41.4
T_OUT = -5.0

dev = BatteryAwareThermostat(
    temp_output="TRoom[1]", q_rad_output="QRad[1]", dp_output=None,
    q_rad_nominal=Q_NOM,
    algorithm=SampledPI(day_night_setpoint(20.0, 17.0, 6, 22)),
    seed=1)

T = 293.15
DT = 30.0
q = 0.0
for i in range(int(3 * 86400 / DT)):
    t = i * DT
    meas = {"TRoom[1]": T, "QRad[1]": q}
    y = dev.step(t, meas)
    # crude plant: quick-opening flow -> saturating emission, tau-less
    phi = min(1.0, (max(0.0, y) / 0.3) ** 0.5)
    q = Q_NOM * 1.25 * phi ** 0.7 if phi > 0 else 0.0
    dT = (0.65 * q + G * ((T_OUT + 273.15) - T)) / C_AIR
    T += dT * DT

print("k_log:", [(round(t / 3600, 1), round(k, 2)) for t, k in dev.k_log])
print("k_hat:", round(dev.k_hat, 3))
print("closures seen:", "yes" if dev.k_log else "NO — anchor never fired")

# introspect the anchor state machine on the last night
print("closed_since:", dev._closed_since, "anchor:", dev._anchor)
print("position:", dev._position, "u_filt:", round(dev._u_filt, 3))
