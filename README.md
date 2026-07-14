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

## Alternative: Docker-free toolchain in WSL

If Docker Desktop is unavailable (e.g. its Windows service needs an admin start),
the same toolchain runs directly in a per-user WSL distro — no admin rights needed:

```powershell
wsl --install -d Ubuntu-24.04 --no-launch
wsl -d Ubuntu-24.04 -u root -- bash -c "tr -d '\r' < /mnt/c/<repo-path>/scripts/wsl_toolchain_setup.sh | bash"

# then build/run exactly like the docker variant, e.g.:
wsl -d Ubuntu-24.04 -u root -- bash -c "cd /work/build && omc /work/modelica/build_80s.mos"
wsl -d Ubuntu-24.04 -u root -- bash -c "cd /work/sil && /opt/silenv/bin/python3 run_design_day.py"
```

The setup script installs OpenModelica (apt stable), Modelica Buildings 13.0.0 and a
Python venv at `/opt/silenv`, and links the repo at `/work` so the `.mos` build
scripts work unchanged. If WSL has no network (campus NAT policies), put
`networkingMode=mirrored` under `[wsl2]` in `%UserProfile%\.wslconfig` and run
`wsl --shutdown` once. The Grafana/BOPTEST stack still requires Docker.

Division of labor: the **React dashboard** is the experiment workbench (building view,
run catalog, KPI board, device inspector); **Grafana** (http://localhost:3001,
provisioned "buildingsimulator runs" dashboard, Infinity datasource reading the same
API) covers free-form time-series exploration and live monitoring of long batches —
and later takes field-measurement data alongside simulations.

Simulation runs persist to `runs/<id>/` (manifest.json + series.csv); the dashboard
lists them, replays them with a time scrubber, and polls live while a run is in
progress. Falls back to bundled mock data when the API is unreachable.

Experiments are launched from the dashboard (new run: thermostat type, duration,
cloudiness, vacant apartments) via `POST /api/launch`, which spawns
`sil/run_experiment.py` inside the API container; running experiments can be stopped.
The leaderboard view ranks all runs by KPI (per-evaluated-day normalized, best values
highlighted).

## Layout

| Path | Content |
|------|---------|
| `docker/` | Toolchain image definition |
| `modelica/BuildingSimulator/` | Modelica package: `ApartmentBranch` (valve + radiator + 2R2C zone), `MultiTenantBuilding` (generic building), `Building80s` (verified 1979-83 German MFH, room-resolved, 90/70) |
| `modelica/PrototypeTwoRooms.mo` | Minimal two-room prototype |
| `sil/harness.py` | Generic FMU co-simulation loop (`BuildingFMU`, `run_simulation`) |
| `sil/controllers.py` | Controller interface + baseline PI thermostat — the SIL slot for control strategies under test |
| `sil/thermostat.py` | Realistic eTRV device model: sampled control, valve-mounted sensor bias/noise/quantization, actuation deadband, adaptation run, battery KPIs |
| `sil/actuator.py` | Valve actuator mechanics: pin force (spring/seal/friction/Δp), motor current with noise+ADC, backlash, unknown mechanical zero |
| `sil/kpi.py` | Discomfort (K·h), boiler/pump energy, valve travel KPIs |
| `sil/scenario_common.py` | Shared weather, heating curve, occupancy schedules, winter scenario factory |
| `sil/boiler.py` | Supervisory boiler logic: two-point burner relay (era on/off cycling) + Schnellaufheizung morning boost (+12 K on the curve until rooms recover) |
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

`BuildingSimulator.MultiTenantBuilding`: setpoint-tracking boiler (+80 l water mass)
and constant-speed pump feed a vertical two-pipe riser; on every floor `nApeFlo`
apartment branches tap off (EN 442-2 radiator with dynamic water/steel storage behind
a quick-opening TRV insert, 2R2C zone). Supply-side supervisory logic — outdoor-reset
curve, two-point burner cycling, Schnellaufheizung boost — lives in Python
(`sil/boiler.py`). Floor and apartment counts are compile-time parameters
(`.\scripts\build_multitenant_fmu.ps1 -Floors N -ApartmentsPerFloor M`).

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

- **In the FMU** (plant hydraulics): table-based quick-opening flow characteristic
  (`Buildings.Fluid.Actuators.Valves.TwoWayTable`, anchored to Danfoss RA-N data:
  ~80 % flow at 30 % stroke) with a sealing dead zone up to ~6 % stroke (elastomer
  seal) and a leakage floor of 0.15 % of Kvs (numerical robustness at trickle flows).
  Table is a model parameter (`yCha`/`phiCha` in `ApartmentBranch`). The 60 s
  full-stroke motor speed is enforced as a rate limit in the SIL harness — not as an
  in-FMU filter, whose states clash with the dynamic radiators via state selection
  (see docs/radiator-modeling.md §3).
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
4. ✅ Verified 1980s German MFH (`Building80s`): room-resolved (living/bedroom/kitchen/bath + hall),
   IWU-typology envelope, 90/70 system, per-stack risers — design-day verified at 65 W/m²,
   overnight cooldown calibrated to the field corridor (−0.2…−0.4 K/h)
   ([parameters + results](docs/building80s-parameters.md))
5. ✅ Manual valves (presetting rings + riser balancing as FMU inputs) with a damped
   proportional balancing routine — as-built / open / balanced baseline states
   ([details](docs/building80s-parameters.md))
6. ✅ Adaptive + distributed control strategies: cumulative firmware ladder (bias compensation,
   battery policies, optimal start) closing the device comfort penalty and cutting valve moves
   to a third, plus a documented negative result on distributed considerate recovery
   ([results](docs/phase3-adaptive-strategies.md))
7. ✅ Gymnasium interface (`sil/gym_env.py`): the verified plant as a standard RL environment —
   valve-vector actions through the real motor rate limit, leaderboard-consistent reward
   components, PI-policy equivalence validated (`sil/run_gym_smoke.py`)
8. ✅ Device-realistic observation mode (`observation_mode="device"`): agents observe through the
   eTRV valve-mounted sensor while the reward stays on true comfort — the
   learning-under-sensor-bias setting (validated: a sensed-obs PI reproduces the 1.4 K undershoot)
9. Benchmarking against [BOPTEST](https://ibpsa.github.io/project1-boptest/)
   `multizone_residential_hydronic` KPIs (requires Docker)
