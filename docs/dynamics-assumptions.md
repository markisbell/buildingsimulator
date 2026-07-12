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
| Radiator | — | element chain (steady-state energy balance) |
| Valve/actuator | opening filter (60 s stroke) | flow–pressure relation |
| Hydraulic network | — | algebraic pressure/flow solution |
| Distribution | riser water column (1 per stack), boiler water mass | pipes, return side, pump volume |
| Devices (Python) | sensor-bias lag, integrators, relay states | — |

## 2. The room: 2R2C with a deliberately "thick" fast node

$$C_{air}\dot T_{air} = \dot Q_{conv} + G_{int}(T_{mass}-T_{air}) + G_{win}(T_{out}-T_{air}) + f_{air}\dot Q_{gain} + G_{door}(T_{hall}-T_{air})$$
$$C_{mass}\dot T_{mass} = \dot Q_{rad} + G_{int}(T_{air}-T_{mass}) + G_{wall}(T_{out}-T_{mass}) + (1-f_{air})\dot Q_{gain} + G_{vert}\Delta T_{stack}$$

| Parameter | Value | Assumption it encodes |
|---|---|---|
| $C_{air}$ | 40 kJ/(m²K)·A | the fast node is **not bare air** (×13 multiplier): furniture, contents and interior surface layers move with the air (EnergyPlus multiplier practice 1–20; ISO 52016 surface-layer capacitance; [Johra & Heiselberg 2017](https://doi.org/10.1016/j.rser.2016.11.145)) |
| $C_{mass}$ | 260 kJ/(m²K)·A | ISO 13790 "heavy" class — the *effective* storage participating in daily cycles, not the full masonry mass |
| $G_{int}$ | 15.5 W/(m²K)·A | ISO 13790 convention $h_{is}\!\cdot\!A_t = 3.45 \times 4.5\,A_{floor}$ — combined convective+radiative surface film, constant (no $h(\Delta T)$ or airflow dependence) |
| $G_{win}, G_{wall}$ | per IWU U-values | infiltration constant at n = 0.7 h⁻¹ (no wind/stack effects, no window-opening geometry — openings appear as negative gain pulses) |
| $f_{air}$ | 0.3 | fixed split of solar/internal gains to air vs surfaces |

Resulting time constants (per design): $\tau_{fast} = C_{air}/(G_{win}+G_{int}) \approx$
**41 min** (matches grey-box identification of furnished rooms,
[Bacher & Madsen 2011](https://doi.org/10.1016/j.enbuild.2011.02.005): 0.5–2 h);
$\tau_{slow} \approx (C_{air}+C_{mass})/UA_{eff} \approx$ **40 h**. This two-constant
structure — not any single τ — produces the observed heat-up/cooldown shapes.

**Not modeled, by intent:** air stratification and radiator-proximity effects (single
air temperature per room — the *device* sees a biased temperature via its sensor model
instead), moisture/latent loads, variable convection coefficients, furniture as a
separate third node, solar distribution by geometry (fixed split), door opening/closing
dynamics (constant $G_{door}$ = 15 W/K).

## 3. The radiator: quasi-static emission on a nonlinear characteristic

- **Element-wise EN 442 law** $\dot Q_i \propto |\Delta T_i|^{1.24}$ over 5 elements —
  the emission *characteristic* is fully nonlinear and log-mean-consistent (validated to
  0.3–1.8 % against the exact integral, see radiator-modeling.md §3).
- **Steady-state energy balance**: the water/steel storage
  ($\approx$ 6 kg water per kW rating, τ of order 5–15 min at design flow) carries **no
  state**. The radiator output follows its boundary conditions instantly.

Justification and consequence: the neglected radiator lag is a fraction of
$\tau_{fast}$ = 41 min, and the *supply-side* lags that shape what the radiator sees are
retained upstream (riser column, boiler mass). The honest caveat: a missing emission lag
makes the valve→room loop slightly *faster/cleaner* than reality, so simulated TRV limit
cycles are, if anything, mildly **underestimated** — conservative for claims about
oscillation problems, optimistic by a small margin for controller stability margins.
(The original motivation was numerical: water states at trickle flows destabilized the
CS solver — building80s-parameters.md §8.)

## 4. Valve and device timing

- FMU-side: opening moves through a 60 s stroke filter (eTRV motor); the flow–pressure
  network is algebraic (incompressible, no water hammer), forward-flow-only.
- Python-side (the device under test): 300 s firmware sampling, 0.1 mm backlash,
  sensor bias with 600 s lag, quantization/noise — these are *deliberately* the
  dominant "controller dynamics".

## 5. Distribution and plant

- **Boiler water mass 80 l** (state) + two-point burner relay (±5 K, min runtimes)
  → the 10–30 min supply sawtooth.
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
| 60 s | valve stroke | 1st-order filter (FMU) |
| 5 min | eTRV firmware sampling | discrete (Python) |
| ≈ 8–25 min | riser transport, boiler mass + relay | 9 volumes + relay logic |
| ≈ 41 min | zone fast node (air + contents + surface layers) | state |
| ≈ 40 h | zone structural mass | state |

Each quasi-static simplification sits at least a factor ~3 below the next modeled
scale, except the radiator emission lag (§3), which is the one documented borderline
case.

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
