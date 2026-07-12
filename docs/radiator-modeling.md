# Radiator modeling — formulation, parameters, and validation

The radiators use `Buildings.Fluid.HeatExchangers.Radiators.RadiatorEN442_2`
([model documentation](https://simulationresearch.lbl.gov/modelica/releases/latest/help/Buildings_Fluid_HeatExchangers_Radiators.html);
library: [Wetter et al. 2014](https://doi.org/10.1080/19401493.2013.765506)).

## 1. Formulation: element-wise EN 442 power law

The water path is discretized into $N = 5$ elements. Each element $i$ transfers

$$\dot Q_i \;=\; \frac{UA}{N}\,\mathrm{sign}(\Delta T_i)\,\lvert\Delta T_i\rvert^{\,n},
\qquad n = 1.24,$$

on its **local** overtemperature $\Delta T_i = T_{w,i} - T_{room}$, split into a
convective share $(1-f_{rad})$ delivered to the zone **air node** and a radiant share
$f_{rad} = 0.35$ delivered to the zone **mass node** (surfaces). $UA$ is calibrated
implicitly at initialization so the element chain reproduces the rating point exactly.

This is neither the arithmetic-mean simplification nor an explicit logarithmic-mean
formula: because the discretization resolves the falling water-temperature profile, the
effective mean overtemperature *emerges from integration* and converges to the exact
continuous solution of $\dot m c_p\, dT = -UA'\,(T - T_{room})^n\, dx$.

## 2. Parameters in this project

| Parameter | Generic building | Building80s | Rationale |
|---|---|---|---|
| Rating $T_a/T_b/T_{air}$ | 60/40/20 °C | **90/70, room design temp** (20 °C, bath 24 °C) | era-correct sizing; rating at the room's own design temperature avoids the EN 442 derating error for the 24 °C bath |
| $\dot Q_{nom}$ | 4.5 kW/apartment | per room from the §4 load tables × 1.15, incl. hall-door loss | docs/building80s-parameters.md |
| $n$ | 1.24 | 1.24 | EN 442-2 typical panel-radiator exponent |
| $f_{rad}$ | 0.35 | 0.35 | Buildings default; radiant share → mass node |
| Energy balance | dynamic | **steady-state** | radiator water states at trickle flows destabilize the CS solver; thermal lag lives in zone masses, boiler and riser volumes (§8 of the parameter doc) |
| Flow direction | forward-only | forward-only | pump-driven branches; removes reverse-mixing states |

## 3. Validation: operating points vs the logarithmic overtemperature model

`sil/run_radiator_check.py` sweeps one radiator (living room, floor 2, rating 1541 W at
90/70/20) through a nine-step TRV staircase in the FMU and compares every measured
steady operating point — at identical boundary conditions, including the riser-loss
corrected inlet temperature — against three analytical references:

- **exact**: continuous solution with $N = 400$ elements, UA calibrated at the rating point;
- **LMTD**: $\dot Q = \dot Q_{nom}\,\big(\Delta\theta_{log}/\Delta\theta_{log,nom}\big)^{n}$
  with $\Delta\theta_{log} = (T_{sup}-T_{ret})\,/\,\ln\!\frac{T_{sup}-T_{room}}{T_{ret}-T_{room}}$,
  solved simultaneously with $\dot Q = \dot m c_p (T_{sup}-T_{ret})$;
- **5-element**: a Python replica of the Buildings discretization.

![Radiator operating points vs analytical models](figures/radiator_check_80s.png)

*Fig. 1 — Left: measured FMU points on the three analytical curves. Right: deviations
across the throttling range.*

| Comparison | Range | Max deviation |
|---|---|---|
| FMU vs exact integral | 145 % → ~50 % of design flow | **0.6–1.8 %** |
| LMTD vs exact integral | entire staircase | **≤ 0.8 %** |
| FMU at ~20 % of design flow | trickle | +10.7 % — rig artifact* |

The systematic +1–2 % of the FMU stems from the two-node zone: the radiant fraction
sees the (slightly warmer) mass node, while the analytical rig uses the measured air
temperature as the single room temperature. *The low-flow point is dominated by the
measurement conditions (multi-hour radiator residence time; the room still drifting
during the 2-hour hold), not by the radiator equations.

**Conclusion:** the Buildings 5-element discretization is consistent with the
logarithmic-overtemperature model over the full TRV throttling range; the operating
points of the verified building sit on the analytical characteristic.

## 4. Why this matters at low flows

At deep throttling the water-side spread widens and the radiator gain
$\partial\dot Q/\partial\dot m$ becomes very large — the mechanism behind the classic
TRV limit-cycling at low demand
([Tahersima et al. 2013](https://doi.org/10.1016/j.enbuild.2013.04.019)) and one root of
the oscillation signatures documented in
[building80s-parameters.md §8](building80s-parameters.md). Arithmetic-mean radiator
models overpredict output in exactly this regime; the discretized/log-mean formulation
does not.

## References

- EN 442-2: *Radiators and convectors — Part 2: Test methods and rating*.
- M. Wetter, W. Zuo, T.S. Nouidui, X. Pang: *Modelica Buildings library*, Journal of
  Building Performance Simulation 7(4), 2014.
  [doi:10.1080/19401493.2013.765506](https://doi.org/10.1080/19401493.2013.765506)
- F. Tahersima, J. Stoustrup, H. Rasmussen: *An analytical solution for
  stability-performance dilemma of hydronic radiators*, Energy and Buildings 64 (2013).
  [doi:10.1016/j.enbuild.2013.04.019](https://doi.org/10.1016/j.enbuild.2013.04.019)
- Heat-up phase behavior building on this model: [heatup-dynamics.md](heatup-dynamics.md).
