# Modeling assumptions driving the system dynamics

What creates — and what deliberately limits — the transient behavior of the simulator.
Companion to [radiator-modeling.md](radiator-modeling.md),
[valve-modeling.md](valve-modeling.md) and [heatup-dynamics.md](heatup-dynamics.md);
parameter provenance in [building80s-parameters.md](building80s-parameters.md).

## 1. Where the states live

The deliberate design decision of this simulator is that **dynamics live where their
time constants matter for thermostat control**, and everything faster is treated
quasi-statically:

| Subsystem | Dynamic states | Quasi-static (no states) |
|---|---|---|
| Zone | air/fast node, structural mass node (per room) | — |
| Radiator | water + steel temperature per element (5 per radiator) | emission characteristic (algebraic EN 442 law) |
| Valve/actuator | — (60 s stroke rate-limited harness-side) | flow–pressure relation |
| Hydraulic network | — | algebraic pressure/flow solution |
| Distribution | riser water column (1 per stack), boiler water mass | pipes, return side, pump volume |
| Devices (Python) | sensor-bias lag, integrators, relay + boost states (incl. Schnellaufheizung supply boost) | — |

## 2. The room: 2R2C with a deliberately "thick" fast node

$$C_{air}\dot T_{air} = \dot Q_{conv} + G_{int}(T_{mass}-T_{air}) + G_{win}(T_{out}-T_{air}) + f_{air}\dot Q_{gain} + G_{door}(T_{hall}-T_{air})$$
$$C_{mass}\dot T_{mass} = \dot Q_{rad} + G_{int}(T_{air}-T_{mass}) + G_{wall}(T_{out}-T_{mass}) + (1-f_{air})\dot Q_{gain} + G_{vert}\Delta T_{stack}$$

| Parameter | Value | Assumption it encodes |
|---|---|---|
| $C_{air}$ | 40 kJ/(m²K)·A | the fast node is **not bare air** (×13 multiplier): furniture, contents and interior surface layers move with the air (EnergyPlus multiplier practice 1–20; ISO 52016 surface-layer capacitance; [Johra & Heiselberg 2017](https://doi.org/10.1016/j.rser.2016.11.145)) |
| $C_{mass}$ | 450 kJ/(m²K)·A | night-accessible capacity of masonry + concrete-slab construction (bottom-up inventory; DIN V 18599-2 heavy class 468, DIN V 4108-6 ≈ 560). The ISO 13790 class value (heavy, 260) is a monthly-method convention that made free cooling 2× faster than field records — calibration: sil/calibrate_deep_mass.py, heatup-dynamics.md §6 |
| $G_{int}$ | 15.5 W/(m²K)·A | ISO 13790 convention $h_{is}\!\cdot\!A_t = 3.45 \times 4.5\,A_{floor}$ — combined convective+radiative surface film, constant (no $h(\Delta T)$ or airflow dependence) |
| $G_{win}, G_{wall}$ | per IWU U-values | infiltration constant at n = 0.7 h⁻¹ (no wind/stack effects, no window-opening geometry — openings appear as negative gain pulses) |
| $f_{air}$ | 0.3 | fixed split of solar/internal gains to air vs surfaces |

Resulting time constants (per design): $\tau_{fast} = C_{air}/(G_{win}+G_{int}) \approx$
**41 min** (matches grey-box identification of furnished rooms,
[Bacher & Madsen 2011](https://doi.org/10.1016/j.enbuild.2011.02.005): 0.5–2 h);
$\tau_{slow} \approx (C_{air}+C_{mass})/UA_{eff} \approx$ **70-80 h** → overnight
free-cool tail ≈ −0.3 K/h, inside the field corridor. This two-constant
structure — not any single τ — produces the observed heat-up/cooldown shapes.

**Not modeled, by intent:** air stratification and radiator-proximity effects (single
air temperature per room — the *device* sees a biased temperature via its sensor model
instead), moisture/latent loads, variable convection coefficients, furniture as a
separate third node, solar distribution by geometry (fixed split), door opening/closing
dynamics (constant $G_{door}$ = 15 W/K).

**Resolved (night-mass calibration):** the model originally used the ISO 13790
"heavy" convention $C_{mass}$ = 260 kJ/(m²K), which made multi-hour free cooling
run ≈ 2× faster than field records. Initialization, the synchronized-setback
protocol and the radiator storage were tested and eliminated as causes; a
weakly-coupled deep-mass third node was a null result. The corridor is met by the
strongly-coupled night-accessible capacity (450) plus the Schnellaufheizung boost
that keeps morning recovery fast (heatup-dynamics.md §6,
`sil/calibrate_deep_mass.py`, `sil/run_neighbor_test.py`).

## 3. The radiator: EN 442 characteristic with water/steel storage

- **Element-wise EN 442 law** $\dot Q_i \propto |\Delta T_i|^{1.24}$ over 5 elements —
  the emission *characteristic* is fully nonlinear and log-mean-consistent (validated to
  0.4–1.8 % against the exact integral, see radiator-modeling.md §4).
- **Dynamic energy balance**: each element stores heat in its water volume and lumped
  steel mass — 8 l + 30 kg per kW rating (1980s steel/DIN radiators) —
  $C_{rad} \approx 48$ kJ/K per kW, emission lag $\tau_e \approx$ **30–50 min** at
  operating overtemperature, longer as the radiator cools.

This storage is what produces the field-typical **setpoint overshoot** after the
morning boost (the stored heat is on the room side of the valve — no valve-side
controller can hold it back) and the **cushioned first cooldown hour** after the
evening setback; it also adds the phase lag that drives realistic TRV limit cycling
(radiator-modeling.md §3).

History: the radiator originally ran a *steady-state* energy balance because water
states at trickle flows destabilized the CS solver (building80s-parameters.md §8).
After the TRV leakage floor, forward-only flow and the steady-state pump removed that
failure mode, the storage was re-enabled when comparison with field recordings showed
the two missing signatures above — resolving the earlier documented caveat that
quasi-static emission underestimates limit cycles.

## 4. Valve and device timing

- The eTRV motor's 60 s full-stroke travel is enforced as a rate limit in the SIL
  harness (`sil/harness.py`, applied to every controller type). It used to be a
  2nd-order filter inside the FMU valve, but those filter states get entangled with
  the branch pressure drops by index reduction (dynamic state selection) once the
  radiators carry water states — the resulting state set broke the solver whenever
  valves moved at trickle flow. The flow–pressure network itself is algebraic
  (incompressible, no water hammer), forward-flow-only.
- Python-side (the device under test): 300 s firmware sampling, 0.1 mm backlash,
  sensor bias with 600 s lag, quantization/noise — these are *deliberately* the
  dominant "controller dynamics".

## 5. Distribution and plant

- **Boiler water mass 80 l** (state) + two-point burner relay (±5 K, min runtimes)
  → the 10–30 min supply sawtooth. The supervisory layer adds the era's
  **Schnellaufheizung** (+12 K on the heating curve inside a morning boost window
  until rooms recover, `sil/boiler.py`).
- **Riser water column, one 6 l volume per stack at the base** (state): transport lag
  of the supply front, with shaft heat loss. *Per-floor* transport lag and the return
  side are lumped away (mid-riser volumes destabilized the solver; the approximation
  delays all floors of a stack equally).
- Pump: steady-state volume, dissipation not added to the fluid (no pipe losses that
  could absorb it in the closed night loop).

## 6. The resulting time-scale hierarchy

| Scale | Mechanism | Modeled as |
|---|---|---|
| < 1 s | pressure/flow redistribution | algebraic |
| 60 s | valve stroke | rate limit (harness) |
| 5 min | eTRV firmware sampling | discrete (Python) |
| ≈ 8–25 min | riser transport, boiler mass + relay | 9 volumes + relay logic |
| ≈ 30–50 min | radiator emission lag (water + steel) | 5 states per radiator |
| ≈ 41 min | zone fast node (air + contents + surface layers) | state |
| ≈ 70–80 h | zone structural mass (night-accessible capacity) | state |

Each quasi-static simplification sits at least a factor ~3 below the next modeled
scale. The former borderline case — the radiator emission lag — is a modeled state
since the field-realism revision (§3); that the radiator and zone fast node share a
time scale is physical, and exactly the interaction that makes TRV loops hard. The
former slow-end gap (free cooling 2× faster than field records) is closed by the
night-mass calibration (§2, heatup-dynamics.md §6).

## References

- ISO 13790 / ISO 52016: interior heat-transfer convention, capacity classes,
  surface-layer capacitance.
- P. Bacher, H. Madsen: *Identifying suitable models for the heat dynamics of
  buildings*, Energy and Buildings 43 (2011).
  [doi:10.1016/j.enbuild.2011.02.005](https://doi.org/10.1016/j.enbuild.2011.02.005)
- H. Johra, P. Heiselberg: *Influence of internal thermal mass on the indoor thermal
  dynamics ... furniture*, Renewable and Sustainable Energy Reviews 69 (2017).
  [doi:10.1016/j.rser.2016.11.145](https://doi.org/10.1016/j.rser.2016.11.145)
- EN 442-2 and [Buildings.Fluid.HeatExchangers.Radiators.RadiatorEN442_2](https://simulationresearch.lbl.gov/modelica/releases/latest/help/Buildings_Fluid_HeatExchangers_Radiators.html)
  ([Wetter et al. 2014](https://doi.org/10.1080/19401493.2013.765506)).
- F. Tahersima et al.: *Stability-performance dilemma of hydronic radiators*, Energy
  and Buildings 64 (2013) — radiator gain at low flow, TRV limit cycling.
  [doi:10.1016/j.enbuild.2013.04.019](https://doi.org/10.1016/j.enbuild.2013.04.019)
