# Open-Source Simulation Packages for a Multi-Tenant Radiator Heating Building Simulator

**Research report — 2026-07-11**

## 1. Project requirements

The simulator must serve as software-in-the-loop (SIL) feedback for electronic radiator
thermostat control strategies (adaptive single-thermostat control and distributed
building-wide coordination). This imposes requirements that discriminate sharply between
the available packages:

| # | Requirement | Why |
|---|-------------|-----|
| R1 | Per-radiator resolution incl. valve behavior | The electronic thermostat's actuator *is* the radiator valve; controller output = valve position |
| R2 | **Hydraulic coupling** between radiators | Closing one valve raises differential pressure and shifts flow to other radiators — the central physical interaction that distributed control must handle. Zone-load-based tools cannot represent this |
| R3 | Full plant path | Heat generator (boiler/heat pump), circulation pump, supply-temperature control, distribution pipes/risers, radiators |
| R4 | External control interface for Python | SIL loop: controller code (later firmware logic) runs outside the simulator; standard interfaces are FMI/FMU co-simulation or a REST API |
| R5 | Multi-tenant scalability | Parameterizable N floors × M apartments × zones |
| R6 | Open source, runs on Windows (via Docker acceptable) | Project constraint |

## 2. Package survey

### 2.1 Modelica ecosystem (recommended)

Modelica is an equation-based modeling language; models are compiled by a Modelica tool
(open-source: **OpenModelica**) and can be exported as **FMUs** (Functional Mock-up Units)
for co-simulation from Python. It is the only open-source ecosystem that models the
complete hydraulically coupled path from heat generator to individual radiator valve
(R1–R3).

| Library | Maintainer | Notes |
|---------|-----------|-------|
| [Modelica Buildings](https://simulationresearch.lbl.gov/modelica/) | LBNL (US) | Largest, best-tested. [`Buildings.Examples.HydronicHeating.TwoRoomsWithStorage`](https://simulationresearch.lbl.gov/modelica/releases/latest/help/Buildings_Examples_HydronicHeating.html) is almost exactly our system in miniature: boiler + storage tank + variable-speed pumps + two EN 442 radiators with thermostatic valves + two rooms, incl. outdoor-reset supply temperature control |
| [AixLib](https://www.tandfonline.com/doi/full/10.1080/19401493.2023.2250521) | RWTH Aachen EBC | Same physics core, German/EU residential building focus, boiler + radiator + TRV components, district-level extensions |
| [BESMod](https://github.com/RWTH-EBC/BESMod) | RWTH Aachen EBC | Modular building-energy-system templates on top of AixLib/IBPSA — useful later for assembling the multi-tenant system quickly |
| [IBPSA library](https://build.openmodelica.org/Documentation/IBPSA.html) | IBPSA Project | Common core shared by Buildings, AixLib, IDEAS, BuildingSystems |

Radiators follow EN 442-2 (nonlinear exponent model), valves have realistic Kv
characteristics, and the pressure/flow network is solved simultaneously — R2 comes for
free.

**Toolchain status (verified):** OpenModelica now simulates ~97 % of the Buildings library
and ~99 % of IBPSA and has robust FMU export
([OpenModelica status 2026](https://openmodelica.org/images/M_images/OpenModelicaWorkshop_2026/OpenModelica2026-talk01-FrancescoCasella-OpenModelica-Workshop-StatusDirections-v1.pdf)),
so no commercial Dymola license is needed. The Buildings library is
[tested against OpenModelica releases](https://simulationresearch.lbl.gov/modelica/releases/latest/help/Buildings_UsersGuide_ReleaseNotes.html).

### 2.2 BOPTEST — control benchmarking framework (recommended as complement)

[BOPTEST](https://ibpsa.github.io/project1-boptest/) (IBPSA Project 2,
[journal paper](https://www.tandfonline.com/doi/full/10.1080/19401493.2021.1986574))
packages validated Modelica building emulators into Docker containers with a REST API,
baseline controllers, standardized KPIs (thermal discomfort, energy, cost, emissions), and
forecast endpoints. Directly relevant test cases:

- **`multizone_residential_hydronic`** — residential building, gas boiler, radiator with
  thermostatic valve per conditioned zone
  ([test case overview](https://www.osti.gov/servlets/purl/3009414))
- **`twozone_apartment_hydronic`** — apartment with two zones, hydronic system
- **`singlezone_commercial_hydronic`** — district-heating-fed radiator zone

Strengths: reproducible benchmarking of control strategies (the exact purpose of the
framework), zero model-building effort. Limitation: fixed test cases — a custom
parameterizable multi-tenant building requires building our own emulator anyway (using the
same Modelica libraries). **Role in this project: reference benchmark to sanity-check our
own emulator and to compare controllers against published results.**
[BOPTEST-Gym](https://github.com/ibpsa/project1-boptest-gym) adds a Gymnasium RL interface.

### 2.3 Gym-style RL testbeds (partial fit)

- [Sinergym](https://github.com/ugr-sail/sinergym) — well-maintained Gymnasium wrapper
  around **EnergyPlus**. Good RL infrastructure, but EnergyPlus (see 2.4) can't model the
  hydronic path. Useful as an architecture reference for our own Gym interface.
- [Energym](https://github.com/bsl546/energym) — FMU-based environments (Modelica +
  EnergyPlus) incl. apartment models with thermostat control; conceptually close to what we
  need but effectively unmaintained (last release 2021). Useful as a code reference for the
  FMPy-based co-simulation pattern.

### 2.4 EnergyPlus (not suitable as core engine)

[EnergyPlus](https://energyplus.net/) excels at envelope/zone thermal simulation, but
hydronic systems are load-driven and idealized: no valve-level hydraulic network, no
pressure coupling between radiators (fails R1/R2). TRV studies with EnergyPlus operate at
zone-setpoint level only. FMU export exists
([EnergyPlusToFMU](https://simulationresearch.lbl.gov/projects/energyplustofmu)), and
[Spawn of EnergyPlus](https://lbl-srg.github.io/soep/) couples the EnergyPlus envelope with
Modelica HVAC — an option if envelope detail ever becomes the bottleneck.

### 2.5 Pure-Python simulators (not suitable as core engine)

[HydronicPy](https://link.springer.com/chapter/10.1007/978-3-031-55684-5_22),
[hydronic-simulation](https://github.com/hsnyder/hydronic-simulation),
[python-hvac](https://github.com/TomLXXVI/python-hvac) — lightweight and hackable, but
small communities, little validation, and rebuilding a validated radiator/valve/network
model in Python duplicates what Modelica libraries already provide.

## 3. Recommended architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ Python SIL harness (FMPy)                                           │
│                                                                     │
│  Thermostat controller instances (device under test)                │
│  ┌──────────┐ ┌──────────┐     ┌──────────┐   ┌──────────────────┐  │
│  │ Ctrl R1  │ │ Ctrl R2  │ ... │ Ctrl Rn  │◄──┤ coordination     │  │
│  └────┬─────┘ └────┬─────┘     └────┬─────┘   │ layer (distributed│ │
│       │ valve pos. │                │         │ control)          │ │
│       ▼            ▼                ▼         └──────────────────┘  │
│  ═══════════════ FMU co-simulation interface ═══════════════════   │
│       ▲            ▲                ▲                               │
│       │ room T, supply/return T, flows, energy                     │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │ Building FMU (Modelica → OpenModelica export)           │       │
│  │ boiler → pump → distribution → radiators+valves → zones │       │
│  └─────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```

- **Building + plant model:** Modelica (Buildings library; AixLib/BESMod components where
  they fit better), parameterizable multi-tenant typology (N floors × M apartments).
- **Compilation:** OpenModelica in Docker (`openmodelica/openmodelica:v1.27.0-ompython`) —
  no admin rights needed on Windows, reproducible builds.
- **SIL interface:** FMU (FMI 2.0 co-simulation), driven from Python with
  [FMPy](https://github.com/CATIA-Systems/FMPy). FMU inputs = valve positions (0…1) per
  radiator; outputs = room temperatures, supply/return temperatures, mass flows, boiler
  power.
- **Controllers:** plain Python classes with a fixed interface (`observe → act` per time
  step) so the same code slot later takes adaptive controllers, RL agents, or a port of
  real thermostat firmware logic. A Gymnasium wrapper can be added on top for RL work.
- **Benchmarking:** BOPTEST `multizone_residential_hydronic` via Docker as an independent
  reference environment and KPI framework.

### Why not the alternatives

- *EnergyPlus/Sinergym:* no hydraulic network → cannot study valve interaction (R2).
- *BOPTEST alone:* fixed test cases → no parameterizable multi-tenant typology (R5).
- *Pure Python:* unvalidated physics, duplicated effort.

## 4. Roadmap

| Phase | Content | Status |
|-------|---------|--------|
| 0 | Toolchain + prototype SIL loop: Dockerized OpenModelica, FMU of a 2-room hydronic example with valve inputs exposed, Python harness with baseline PI thermostats, hydraulic-coupling demonstration | this session |
| 1 | Parameterizable multi-tenant Modelica model: apartments × zones, riser/distribution network, boiler or heat-pump plant, configurable envelope quality | next |
| 2 | Controller framework: thermostat model incl. realistic constraints (sampling interval, battery-driven duty cycling, valve travel limits), Gymnasium multi-agent interface | |
| 3 | Experiments: adaptive single-thermostat control; distributed/coordinated control (e.g., demand balancing, return-temperature optimization, pump-pressure coordination); benchmarking against BOPTEST baselines and KPIs | |

## 5. Sources

- [Modelica Buildings library](https://simulationresearch.lbl.gov/modelica/) · [HydronicHeating example](https://simulationresearch.lbl.gov/modelica/releases/latest/help/Buildings_Examples_HydronicHeating.html) · [library paper](https://simulationresearch.lbl.gov/wetter/download/2009-modelicaBuildings.pdf)
- [AixLib paper (2023)](https://www.tandfonline.com/doi/full/10.1080/19401493.2023.2250521) · [BESMod GitHub](https://github.com/RWTH-EBC/BESMod) · [BESMod paper](https://2022.american.conference.modelica.org/documents/01_papers/02_full/1_Wullhorst.pdf)
- [BOPTEST site](https://ibpsa.github.io/project1-boptest/) · [BOPTEST journal paper](https://www.tandfonline.com/doi/full/10.1080/19401493.2021.1986574) · [test case update (2025)](https://www.osti.gov/servlets/purl/3009414)
- [Sinergym GitHub](https://github.com/ugr-sail/sinergym) · [Sinergym paper](https://arxiv.org/html/2412.08293v1) · [Energym GitHub](https://github.com/bsl546/energym)
- [OpenModelica status & Buildings/IBPSA coverage (2026 workshop)](https://openmodelica.org/images/M_images/OpenModelicaWorkshop_2026/OpenModelica2026-talk01-FrancescoCasella-OpenModelica-Workshop-StatusDirections-v1.pdf)
- [EnergyPlusToFMU](https://simulationresearch.lbl.gov/projects/energyplustofmu) · [IEA EBC Annex 60 / FMI activity](https://www.iea-annex60.org/finalReport/activity_1_2.html)
- [HydronicPy paper](https://link.springer.com/chapter/10.1007/978-3-031-55684-5_22) · [hydronic-simulation](https://github.com/hsnyder/hydronic-simulation) · [python-hvac](https://github.com/TomLXXVI/python-hvac)
