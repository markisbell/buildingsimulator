"""Minimal failure probe for the dynamic-radiator NLS issue (generic FMU).

Mode A (default): all valves hard closed for 8 h, constant supply setpoint
and outdoor temperature. If it dies ~3 h in, the trigger is the trickle-flow
thermal state itself, not controller action.

Mode B (argv[1] = 'knee'): valves closed until hour 3, then a slow ramp
0 -> 0.12 over 30 min, crossing the quick-opening dead-zone knee. If A
survives and B dies at the ramp, the trigger is the valve characteristic.
"""
import sys
from pathlib import Path

from harness import BuildingFMU

ROOT = Path(__file__).resolve().parents[1]
FMU = str(ROOT / "build" / "MultiTenantBuilding.fmu")
MODE = sys.argv[1] if len(sys.argv) > 1 else "closed"

fmu = BuildingFMU(FMU)
n = 6
fmu.initialize({**{f"yVal[{i}]": 0.0 for i in range(1, n + 1)},
                **{f"QGain[{i}]": 0.0 for i in range(1, n + 1)},
                "TOut": 268.15, "TSupSet": 330.15})

dt = 30.0
t_end = 8 * 3600
try:
    while fmu.time < t_end:
        y = 0.0
        if MODE == "knee" and fmu.time >= 3 * 3600:
            y = min(0.12, 0.12 * (fmu.time - 3 * 3600) / 1800)
        fmu.set_inputs({f"yVal[{i}]": y for i in range(1, n + 1)})
        fmu.step(dt)
        if int(fmu.time) % 1800 == 0:
            out = fmu.get_outputs(["TSup", "TRet", "TRoom[1]", "mFlow[1]", "QRad[1]"])
            print(f"t={fmu.time/3600:5.2f} h  y={y:.3f}  "
                  f"TSup={out['TSup']-273.15:5.1f}  TRet={out['TRet']-273.15:5.1f}  "
                  f"TRoom1={out['TRoom[1]']-273.15:5.2f}  "
                  f"m1={out['mFlow[1]']*3600:7.3f} kg/h  QRad1={out['QRad[1]']:7.1f} W",
                  flush=True)
except Exception as exc:
    print(f"FAILED at t={fmu.time/3600:.3f} h ({fmu.time:.0f} s): {exc}")
    sys.exit(2)
print(f"survived to t={fmu.time/3600:.1f} h, mode={MODE}")
