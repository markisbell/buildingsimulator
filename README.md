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

# dashboard stack: run-store API (8010) + Grafana (3001)
docker compose -p buildingsim up -d
cd ui; npm install; npm run dev        # React dashboard at http://localhost:5173
```

Division of labor: the **React dashboard** is the experiment workbench (building view,
run catalog, KPI board, device inspector); **Grafana** (http://localhost:3001,
provisioned "buildingsimulator runs" dashboard, Infinity datasource reading the same
API) covers free-form time-series exploration and live monitoring of long batches —
and later takes field-measurement data alongside simulations.

Simulation runs persist to `runs/<id>/` (manifest.json + series.csv); the dashboard
lists them, replays them with a time scrubber, and polls live while a run is in
progress. Falls back to bundled mock data when the API is unreachable.

## Layout

| Path | Content |
|------|---------|
| `docker/` | Toolchain image definition |
| `modelica/BuildingSimulator/` | Modelica package: `ApartmentBranch` (valve + radiator + zone), `MultiTenantBuilding` (riser network + plant) |
| `modelica/PrototypeTwoRooms.mo` | Minimal two-room prototype |
| `sil/harness.py` | Generic FMU co-simulation loop (`BuildingFMU`, `run_simulation`) |
| `sil/controllers.py` | Controller interface + baseline PI thermostat — the SIL slot for control strategies under test |
| `sil/thermostat.py` | Realistic eTRV device model: sampled control, valve-mounted sensor bias/noise/quantization, actuation deadband, adaptation run, battery KPIs |
| `sil/actuator.py` | Valve actuator mechanics: pin force (spring/seal/friction/Δp), motor current with noise+ADC, backlash, unknown mechanical zero |
| `sil/kpi.py` | Discomfort (K·h), boiler/pump energy, valve travel KPIs |
| `sil/scenario_common.py` | Shared weather, heating curve, occupancy schedules, winter scenario factory |
| `sil/solar.py` | Facade solar gains via pvlib (clear-sky + cloudiness, per-apartment orientation) |
| `sil/run_multitenant.py` | Multi-tenant scenarios: flow balancing; winter week with vacant apartment |
| `sil/run_thermostat_comparison.py` | Ideal PI vs realistic eTRV on identical scenario, KPI table |
| `sil/run_prototype.py` | Prototype scenarios: winter week closed-loop; hydraulic coupling demo |
| `ui/` | React dashboard (Vite + Recharts): run selector, building view, plant panel, KPI board, time scrubber, device inspector; live-polls running simulations |
| `sil/runstore.py` | Persists every run to `runs/<id>/` (manifest + series) |
| `server/main.py` | FastAPI run-store API (`/api/runs`, `/manifest`, `/series`) |
| `build/` | Compiled FMUs (generated) |
| `results/` | Plots + CSV time series (generated) |
| `docs/` | Research report, BOPTEST setup |

## Multi-tenant building model

`BuildingSimulator.MultiTenantBuilding`: ideal boiler + constant-speed pump feed a
vertical two-pipe riser; on every floor `nApeFlo` apartment branches tap off (EN 442-2
radiator behind an equal-percentage valve, single-capacity zone). Floor and apartment
counts are compile-time parameters (`.\scripts\build_multitenant_fmu.ps1 -Floors N
-ApartmentsPerFloor M`).

FMU inputs: `yVal[i]`, `QGain[i]` (solar + internal gains) per apartment, `TOut`, `TSupSet`.
FMU outputs: `TRoom[i]`, `mFlow[i]`, `QRad[i]`, `dpVal[i]`, `TSup`, `TRet`, `QBoi`, `PPum`.

Zones are 2R2C (fast air node + slow structural mass node): the air responds to solar
bursts and radiator action within minutes while the building mass stays slow. Weather
comes from Python: synthetic sinusoidal `TOut` plus **facade solar gains** via
[pvlib](https://pvlib-python.readthedocs.io/) (clear-sky Ineichen with cloudiness
factor, per-apartment facade orientation, window area × g-value × shading;
`sil/solar.py`). Measured weather (DWD TRY / EPW) can replace the synthetic model via
`pvlib.iotools` without touching the FMU.

Effects central to distributed thermostat control that are built in:
- **Riser hydraulics** — upper floors see less differential pressure, so open valves on
  the ground floor starve the top floor (unbalanced system, no static balancing valves).
- **Inter-apartment coupling** — stacked apartments exchange heat through floor/ceiling
  conductances; an unheated apartment "steals" heat from its neighbours.
- **Facade asymmetry** — south apartments get kW-scale midday solar gains in clear
  winter weather while north apartments see only diffuse light; thermostats must reject
  an apartment-specific disturbance (overheating KPI tracks failures).

### Valve realism (German M30 x 1.5 TRV inserts, 1.5 mm pin stroke)

- **In the FMU** (plant hydraulics): table-based flow characteristic
  (`Buildings.Fluid.Actuators.Valves.TwoWayTable`) with a sealing dead zone up to
  ~20 % stroke (elastomer seal), a steep quasi-linear rise, and saturation above
  ~60 % lift; seat leakage 0.04 % of Kvs. Table is a model parameter (`yCha`/`phiCha`
  in `ApartmentBranch`). 60 s full-stroke actuator filter models the eTRV motor.
- **In the device model** (`sil/thermostat.py`): 0.1 mm mechanical play between motor
  command and pin position — opening and closing paths differ (hysteresis) — plus an
  optional calibration-offset error. Verified by `sil/run_valve_sweep.py`.

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
3. ✅ Thermostat realism: sampled control, valve-mounted sensor bias, actuation deadband, battery KPIs
4. Gymnasium multi-agent interface; experiments: adaptive + distributed control; benchmarking against
   [BOPTEST](https://ibpsa.github.io/project1-boptest/) `multizone_residential_hydronic` KPIs
