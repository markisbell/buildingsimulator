# BOPTEST benchmark: `multizone_residential_hydronic`

> [!NOTE]
> **AI-generated content.** This document, the benchmark adapter and the runner
> were produced with Claude (Anthropic) acting as a coding agent under human
> direction and review. See the repository README for the full disclaimer.

Cross-plant validation of the two central findings of this project, on a
building model we did not build, scored by KPIs we did not define:

1. **Device pathology** — a stock eTRV controlling on its warm-biased,
   valve-mounted sensor trades a large comfort loss for a small energy saving.
2. **Ladder recovery** — the Phase 3 firmware (night-anchor bias compensation
   + battery-aware actuation) recovers a substantial share of that loss
   without retuning.

Both effects were measured so far only on our own Modelica plants
(MultiTenantBuilding, Building80s). If they were artifacts of our building
model or our KPI definitions, they should disappear on an independent plant.
They do not.

## 1. Test case and interface mapping

[BOPTEST](https://ibpsa.github.io/project1-boptest/) test case
`multizone_residential_hydronic`: an IBPSA reference residential dwelling
(Brussels climate) with a gas boiler and hydronic radiators — five
valve-equipped zones plus a valveless hall, i.e. the same actuation topology
as our apartments. The eTRV firmware objects from `sil/thermostat.py` /
`sil/strategies.py` run **unmodified**; only the I/O wiring changes
(`sil/boptest_adapter.py`):

| Firmware side                    | BOPTEST point                                  |
|----------------------------------|------------------------------------------------|
| valve command u ∈ [0,1]          | `conHea<Z>_oveActHea_u` (+ `_activate`)        |
| true zone temperature            | `conHea<Z>_reaTZon_y`                          |
| delivered heat (drives the sensor-bias model) | `reaHea<Z>_y`                     |
| heating setpoint schedule        | forecast point `LowerSetp[<Z>]`                |

Zones `<Z>` ∈ {Liv, Ro1, Ro2, Ro3, Bth}. The boiler supply-temperature
control is left at the test case's baseline in **all** cases (no
`oveTSetSup` overwrite), so the cases differ only in TRV behavior.

The valve-sensor bias model needs each radiator's rating. A 2-day probe run
under the baseline controller measured the per-zone maximum delivered heat:
Liv 1481 W, Ro1 384 W, Ro2 400 W, Ro3 583 W, Bth 373 W.

## 2. Method

Scenario `peak_heat_day` (the two-week period around the annual peak heating
load, one-week warmup), `dynamic` electricity price, 300 s control step —
BOPTEST's standardized setup, re-initialized identically before every case.
Four cases, run sequentially on one test instance (2026-07-16):

| case       | controller                                                        |
|------------|-------------------------------------------------------------------|
| `baseline` | the test case's embedded reference controller (no overwrites)     |
| `pi`       | `PIThermostat` per zone on the **true** zone temperature          |
| `stock`    | `ElectronicThermostat`: sampled PI on the **biased valve sensor** (bias driven by `reaHea<Z>_y`), deadband, backlash, adaptation run |
| `ladder`   | `BatteryAwareThermostat`: stock + night-anchor bias compensation + battery-aware deadband/dwell (the Phase 3 firmware, factory settings, no retuning) |

Scored by BOPTEST's own KPIs. Note that `tdis_tot` is **two-sided** (K·h per
zone outside the lower *and* upper comfort bound) — stricter than the
one-sided discomfort KPI used in our simulator experiments, and immune to the
"run warm for free" caveat documented in
[phase3-adaptive-strategies.md](phase3-adaptive-strategies.md).

## 3. Results

Full KPI payloads in [results/boptest_benchmark.json](../results/boptest_benchmark.json).

| case       | tdis_tot [K·h/zone] | ener_tot [kWh/m²] | cost_tot [€/m²] | emis_tot [kgCO₂/m²] |
|------------|--------------------:|------------------:|----------------:|--------------------:|
| `baseline` |               21.41 |              8.24 |            0.81 |                1.43 |
| `pi`       |               25.48 |              8.23 |            0.81 |                1.43 |
| `stock`    |               69.66 |              8.06 |            0.80 |                1.40 |
| `ladder`   |               52.04 |              8.23 |            0.81 |                1.43 |

Derived, taking `pi` as the sensor-pathology-free reference:

- **The pathology reproduces.** Stock eTRV discomfort is **2.7×** the plain-PI
  level (+44.2 K·h/zone), bought with a 2.0 % energy saving — the rooms simply
  run cold. Same signature as on our plant (there: 2.1×).
- **The recovery reproduces.** The ladder firmware removes **17.6 K·h/zone
  (40 % of the pathology gap)** and returns energy, cost and emissions to
  PI-equal values — on a plant it has never seen, with factory priors.
- The embedded baseline beats our plain sampled PI slightly (21.4 vs
  25.5 K·h) — expected, it is the test case's tuned reference.

## 4. Comparison with the in-repo simulator

| quantity                                   | our simulator (generic, days 2–7) | BOPTEST (14 d incl. learning) |
|--------------------------------------------|----------------------------------:|------------------------------:|
| stock / PI discomfort ratio                |                              2.1× |                          2.7× |
| share of pathology gap recovered by ladder |                            ~100 % |                          40 % |
| ladder energy vs PI                        |                              ≈ +2 % |                         ≈ 0 % |

The partial (rather than full) recovery on BOPTEST is expected and honest:

1. **Learning transient counts.** Our simulator KPIs excluded day 1; BOPTEST
   accumulates from scenario start, so the night-anchor estimator's first
   learning nights are scored against it.
2. **Two-sided KPI.** Residual warm-side compensation error was free on our
   one-sided metric; BOPTEST charges it.
3. **Foreign plant, no retuning.** Zone time constants, radiator authority and
   hydraulics differ; the estimator's deliberate ~30 % under-correction
   (designed to prevent over-identification, see the phase 3 document)
   transfers as-is. That the *direction and rough magnitude* survive is the
   point of the exercise.

## 5. What this validates — and what it does not

**Validated:** the closed-loop *consequences* of the sensor pathology and of
the mitigation on an independently developed building/hydronics/weather model,
scored by standardized third-party KPIs; and the interface generality of the
firmware (identical objects drive FMU plants and the BOPTEST REST plant).

**Not validated:** the sensor-bias magnitude itself. The bias is part of our
device model (`ValveSensor`, driven here by BOPTEST's delivered-heat signal
`reaHea<Z>_y`) — BOPTEST does not model valve-mounted-sensor error. The bias
parameterization is field-motivated (see
[valve-modeling.md](valve-modeling.md)), but no plant model can confirm it;
only instrumented field devices can.

## 6. Reproduction

```bash
git clone https://github.com/ibpsa/project1-boptest boptest && cd boptest
# expose the web service on :8081 (docker-compose.override.yml, service `web`)
docker compose up -d web worker provision redis minio
docker stop boptest-test-1 && docker rm boptest-test-1   # see ops note 3
cd <this repo>
python sil/run_boptest_benchmark.py          # self-selects a test instance
```

Runtime ≈ 1.5 h (probe + 4 × 14-day cases; ~25 min of that is the five
scenario re-initializations). Operational notes, each learned the hard way:

1. Use `http://127.0.0.1:8081`, **never** `localhost`: Windows Python tries
   IPv6 `::1` first and pays a ~21 s connect timeout on *every* request.
2. `PUT /scenario` runs a 7-day warmup simulation (~5 min server-side). The
   adapter uses a 1800 s timeout there and fails fast on HTTP errors —
   naive timeout-retry queues duplicate jobs on the single worker.
3. The compose stack's CI self-test container (`boptest-test-1`) floods the
   worker with jobs (~1/s), starving the API into 500s. Stop **and remove**
   it after every `docker compose up`.
4. `POST`/`PUT` must always carry a JSON body (at least `{}`): the web
   service's body parser 500s on a JSON content-type with an empty body.
