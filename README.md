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
.\scripts\build_image.ps1              # once: toolchain image (OpenModelica 1.27 + Buildings 13 + FMPy)

# multi-tenant building (default 3 floors x 2 apartments)
.\scripts\build_multitenant_fmu.ps1 -Floors 3 -ApartmentsPerFloor 2
docker run --rm -v "${PWD}:/work" -w /work/sil buildingsimulator:dev python3 run_multitenant.py

# two-room prototype
.\scripts\build_fmu.ps1                # compile modelica/PrototypeTwoRooms.mo
.\scripts\run_prototype.ps1            # run both prototype scenarios
```

## Layout

| Path | Content |
|------|---------|
| `docker/` | Toolchain image definition |
| `modelica/BuildingSimulator/` | Modelica package: `ApartmentBranch` (valve + radiator + zone), `MultiTenantBuilding` (riser network + plant) |
| `modelica/PrototypeTwoRooms.mo` | Minimal two-room prototype |
| `sil/harness.py` | Generic FMU co-simulation loop (`BuildingFMU`, `run_simulation`) |
| `sil/controllers.py` | Controller interface + baseline PI thermostat — the SIL slot for control strategies under test |
| `sil/run_multitenant.py` | Multi-tenant scenarios: flow balancing; winter week with vacant apartment |
| `sil/run_prototype.py` | Prototype scenarios: winter week closed-loop; hydraulic coupling demo |
| `build/` | Compiled FMUs (generated) |
| `results/` | Plots + CSV time series (generated) |
| `docs/` | Research report, BOPTEST setup |

## Multi-tenant building model

`BuildingSimulator.MultiTenantBuilding`: ideal boiler + constant-speed pump feed a
vertical two-pipe riser; on every floor `nApeFlo` apartment branches tap off (EN 442-2
radiator behind an equal-percentage valve, single-capacity zone). Floor and apartment
counts are compile-time parameters (`.\scripts\build_multitenant_fmu.ps1 -Floors N
-ApartmentsPerFloor M`).

FMU inputs: `yVal[i]` per apartment, `TOut`, `TSupSet`.
FMU outputs: `TRoom[i]`, `mFlow[i]`, `TSup`, `TRet`, `QBoi`, `PPum`.

Two effects central to distributed thermostat control are built in:
- **Riser hydraulics** — upper floors see less differential pressure, so open valves on
  the ground floor starve the top floor (unbalanced system, no static balancing valves).
- **Inter-apartment coupling** — stacked apartments exchange heat through floor/ceiling
  conductances; an unheated apartment "steals" heat from its neighbours.

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

1. ✅ Toolchain + prototype SIL loop
2. ✅ Parameterizable multi-tenant model: N floors × M apartments, riser network, central plant
3. Thermostat realism (sampling, valve travel limits, battery duty cycle) + Gymnasium multi-agent interface
4. Experiments: adaptive + distributed control; benchmarking against
   [BOPTEST](https://ibpsa.github.io/project1-boptest/) `multizone_residential_hydronic` KPIs
