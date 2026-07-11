# buildingsimulator

Simulation environment for a multi-tenant building with hydronic radiator heating,
covering the full path **central heat generation → distribution → individual radiators
with valves**. Used as software-in-the-loop (SIL) feedback for investigating control
strategies of electronic radiator thermostats: adaptive control of individual
thermostats and distributed control of all thermostats in the building.

## Stack

Modelica ([Buildings library](https://simulationresearch.lbl.gov/modelica/)) building +
plant model → FMU export via OpenModelica (in Docker, no local install needed) →
Python SIL harness via [FMPy](https://github.com/CATIA-Systems/FMPy). Rationale and
package survey: [docs/simulation-package-research.md](docs/simulation-package-research.md).

## Quickstart (Windows, Docker Desktop required)

```powershell
.\scripts\build_image.ps1     # once: toolchain image (OpenModelica 1.27 + Buildings 13 + FMPy)
.\scripts\build_fmu.ps1       # compile modelica/PrototypeTwoRooms.mo -> build/PrototypeTwoRooms.fmu
.\scripts\run_prototype.ps1   # run both SIL scenarios -> results/*.png, results/*.csv
```

## Layout

| Path | Content |
|------|---------|
| `docker/` | Toolchain image definition |
| `modelica/` | Plant/building models (`PrototypeTwoRooms.mo`) + FMU build script |
| `sil/harness.py` | Generic FMU co-simulation loop (`BuildingFMU`, `run_simulation`) |
| `sil/controllers.py` | Controller interface + baseline PI thermostat — the SIL slot for control strategies under test |
| `sil/run_prototype.py` | Scenario A: winter week closed-loop; Scenario B: hydraulic coupling demo |
| `build/` | Compiled FMUs (generated) |
| `results/` | Plots + CSV time series (generated) |
| `docs/` | Research report, architecture |

## Prototype model

`PrototypeTwoRooms.mo`: ideal boiler with supply-temperature setpoint → constant-speed
pump (realistic pump curve) → common supply/return riser resistances → two parallel
radiator branches (EN 442-2 radiators, equal-percentage valves) → two RC room zones.
FMU inputs: `yVal1`, `yVal2` (valve positions 0…1), `TOut`, `TSupSet`.
FMU outputs: `TRoom1/2`, `TSup`, `TRet`, `mFlow1/2`, `QBoi`.

Because the pump runs at constant speed behind shared riser resistances, closing one
valve shifts differential pressure and flow to the other branch — the hydraulic coupling
that distributed thermostat control has to deal with (demonstrated in Scenario B).

## Roadmap

1. ✅ Toolchain + prototype SIL loop (this state)
2. Parameterizable multi-tenant model: N floors × M apartments, riser network, boiler/heat-pump plant
3. Thermostat realism (sampling, valve travel limits, battery duty cycle) + Gymnasium multi-agent interface
4. Experiments: adaptive + distributed control; benchmarking against
   [BOPTEST](https://ibpsa.github.io/project1-boptest/) `multizone_residential_hydronic` KPIs
