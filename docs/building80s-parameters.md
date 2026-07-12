# German 1980s multi-family building — parameter derivation

**Target:** typical West German MFH, construction period 1979-1983 (WSchV '77 era),
IWU/TABULA class **MFH_G / DE.N.MFH.07** — 3 stories, 2 apartments per floor
(Zweispänner), masonry (perforated brick / calcium silicate), reinforced concrete
ceilings, flat roof, strong thermal bridges. Original two-pipe heating with 90/70 °C
design and TRVs (mandatory since 1978 per EnEG '76 / HeizAnlV).

## 1. Envelope U-values (IWU Deutsche Gebäudetypologie, class 1979-1983, MFH)

| Component | U / W/(m²K) | Source |
|---|---|---|
| External wall | **0.80** | [IWU U-value overview](https://www.heizlast.de/images/stories/heizlastberechnung/U-WerteGebudetypologie.pdf), [typology report](https://www.iwu.de/fileadmin/publikationen/gebaeudebestand/episcope/2015_IWU_LogaEtAl_Deutsche-Wohngebäudetypologie.pdf) |
| Windows (double insulating glazing) | **2.57** | ditto |
| Flat roof / top ceiling | **0.44** | ditto |
| Basement ceiling | **0.67** (b = 0.5 to unheated cellar) | ditto |
| Thermal bridges | +10 % on opaque UA | era of "strong thermal bridges" (IWU class description) |
| Infiltration | n = 0.7 h⁻¹ | window leakage typical for the era |

## 2. Geometry — apartment and rooms (3-Zimmer-Wohnung, 64 m² heated, 2.5 m rooms)

Each apartment spans the building depth; living and bedroom face **south**, kitchen and
bath **north**; gable-wall share assigned to living/bedroom (end-of-building units).

| Room | Area m² | Facade | Window m² | Ext. wall m² (incl. gable share) |
|---|---|---|---|---|
| Living | 24 | S | 4.6 | 7.4 + 10 |
| Bedroom | 16 | S | 2.8 | 5.2 + 8 |
| Kitchen | 10 | N | 1.8 | 5.7 |
| Bath | 6 | N | 0.8 | 4.2 |
| Hall (no radiator) | 8 | — | — | — (couples rooms, loses to 15 °C stairwell) |

## 3. Derived room conductances (mid floor, W/K)

G_win = U_win·A_win + 0.34·n·V (windows + infiltration, to air node)
G_wall = 1.1 · U_wall·A_wall (+ floor position extras, to mass node)

| Room | G_win | G_wall mid | + ground (cellar, b=0.5) | + top (roof) |
|---|---|---|---|---|
| Living | 26.1 | 15.3 | +8.8 | +11.6 |
| Bedroom | 16.7 | 11.6 | +5.9 | +7.7 |
| Kitchen | 10.6 | 5.0 | +3.7 | +4.8 |
| Bath | 5.6 | 3.7 | +2.2 | +2.9 |

Thermal mass (ISO 13790 "heavy"): C_mass = 260 kJ/(m²K)·A; air+furnishing
C_air = 15 kJ/(m²K)·A. Air↔surfaces G_int = 9 W/(m²K)·A. Room-hall doors 15 W/K each;
hall→stairwell 10 W/K at 15 °C. Vertical slab coupling 1.7 W/(m²K)·A per stack.

## 4. Design loads and radiator sizing (DIN-style, -12 °C, rooms 20 °C, bath 24 °C)

Room design load = (G_win + G_wall,total)·ΔT. Radiators **90/70/20** (era practice),
sized at load × 1.15:

| Room | Ground W | Mid W | Top W |
|---|---|---|---|
| Living | 1850 | 1550 | 1950 |
| Bedroom | 1250 | 1050 | 1350 |
| Kitchen | 700 | 550 | 750 |
| Bath | 500 | 400 | 500 |

Building totals: design load ≈ **21.5 kW** over 384 m² heated → **56 W/m²**, inside the
expected corridor for this class. (Rules of thumb quote
[70-100 W/m² for 70s/80s buildings](https://www.schramm.de/684-577-wie-viel-kw-heizung-pro-qm-altbau/);
those cover smaller buildings with more envelope per m² and include reserves — a
bottom-up DIN-style calculation for a compact MFH lands lower, cf.
[Heizlast im Bestand](https://www.haustec.de/heizung/waermeerzeugung/wie-funktioniert-eigentlich-eine-heizlast-im-bestand).)
Installed radiator power ≈ 24.8 kW.

## 5. Hydronics

Two-pipe system, **one riser per room stack** (8 risers), taps per floor; TRV inserts as
modeled (RA-N-like quick-opening, 1.5 mm stroke); valve design Δp 10 kPa, branch fixed
2 kPa, riser segments 300 Pa each; boiler 90/70 with outdoor-reset curve reaching 90 °C
at -12 °C; constant-speed pump; Δp bypass.

## 6. Verification results (winter design day, -12 °C constant, no solar)

Run: `sil/run_design_day.py` → `results/design_day_80s.png`, 3-day simulation,
ideal PI per room (plant verification, device effects excluded), day 3 evaluated.

| Criterion | Target | Result | |
|---|---|---|---|
| Specific heat load | 52-62 W/m² | **56.1 W/m² (21.5 kW)** — matches the §4 derivation | PASS |
| Supply temperature | ~90 °C at -12 °C | **90.0 °C** | PASS |
| Return temperature | 60-74 °C (unbalanced) | **63.9 °C** | PASS* |
| Room setpoints | ±0.5 K, bath 24 °C | worst room **+0.00 K** (all 24 rooms) | PASS |
| Valve saturation | 10-95 % | **16-18 %**, no saturation | PASS |
| Floor flow imbalance | < 20 % | **2.9 %** | PASS |

*The return sits below the textbook 66-74 °C band — the authentic fingerprint of an
**unbalanced** system without presetting: the 1.15× oversized radiators plus the
quick-opening TRV characteristic find equilibrium at ~17 % stroke and reduced flow,
stretching the water-side ΔT (90/64 instead of 90/70). Also for this reason the TRVs
self-balance the risers (imbalance only 2.9 %). Reproducing the *balanced* design state
(return ≈ 70 °C, valves at 40-70 %) requires the era's manual tuning hardware —
radiator presetting rings and riser balancing valves — which is planned as the next
model extension and will serve as the tuned baseline for control-strategy comparisons.

Typical winter day (-5 ± 3 °C, clear-sky solar): rooms hold setpoints, south rooms
peak +0.1 K under ~2 kW window gains (ideal PI rejects fully), boiler modulates
6.1-18.5 kW — `results/typical_day_80s.png`.

## 7. Manual valves and hydraulic balancing

Presetting rings (5 kPa at design flow, per radiator branch) and riser balancing
valves (2 kPa, per riser base) are modeled as linear valves with **FMU inputs**
`yPreset[k]` / `yBalance[s]` — set once per run like a technician's setting, tunable
without recompiling (OpenModelica exports bound parameters as non-settable
`calculatedParameter`, so inputs are the reliable channel). `sil/run_balancing.py`
implements the measurement-based proportional method with damped iteration
(y ∝ (m_demand/m)^0.4; undamped updates oscillate because the branches couple through
the pump operating point).

**Balancing target and results:** rings are set to the *demand* flow (design load over
the 20 K spread = radiator flow / 1.15). Verified (all PASS):

- Commissioning state (TRVs open): flows within **3.4 %** of demand, return **69.7 °C**
  — the textbook 90/70 picture.
- Steady operation unchanged: 56.1 W/m², rooms at setpoint ±0.0 K — and return stays
  ~64 °C, because under exact-setpoint (integral) control return = supply − Q/(ṁ·cp)
  is **invariant to balancing**; the textbook 70 °C operating return implicitly assumes
  P-control offsets or non-oversized radiators.
- Operating benefit = fair flow distribution when all TRVs demand maximum: with
  realistic as-built ring scatter (49 % flow deviation), morning-recovery deficit
  spread across rooms is 2.11 K; after balancing 1.64 K
  (`results/balancing_80s.png`). The self-consistently sized network itself is
  near-balanced (4.5 % all-open) — real imbalance enters through the as-built ring
  positions, which the seeded scatter represents.

Baseline states for control experiments: **as-built** (scattered rings), **open rings**
(idealized-unbalanced), **balanced** (`results/presets_80s.json`).

## 8. Oscillation realism and radiator validation

Real measurement traces oscillate; the model now reproduces the mechanisms
(`sil/run_oscillation_check.py`, all criteria PASS, `results/oscillation_check_80s.png`):

- **Two-point boiler** (`sil/boiler.py`, SIL supervisory logic through `TSupSet`):
  ±5 K hysteresis, 4-min minimum runtimes, 80 l boiler water mass → supply sawtooth
  19 K pk-pk, 89 burner starts/day (~3.7/h, era-typical).
- **Riser water columns** (6 l per stack base, shaft losses 6 W/K) → transport lag of
  the supply front.
- **Stochastic internal gains** (`sil/gains.py`, seeded): occupancy blocks, cooking and
  bath bursts, appliance noise, 1-2 window-opening cold pulses per room and day
  → room ripple 0.09 K (detrended std), radiator flow CV 0.79 with the eTRV
  staircase/chatter pattern of field data.

Numerical robustness at trickle flows required: forward-only flow in branches and
risers, lumped stack-base volumes (mid-riser volumes destabilize), radiator
**steady-state energy balance** (dynamics live in zone masses, boiler and riser
volumes), TRV dead-zone leakage floor 0.15-0.3 %.

**Radiator operating points** (`sil/run_radiator_check.py`,
`results/radiator_check_80s.png`): steady FMU points across a TRV staircase agree with
the exact continuous EN 442 solution within **0.6-1.8 %** from 145 % down to ~50 % of
design flow (systematic +1-2 % from the two-node zone: the radiant fraction sees the
warmer mass node). The apparent +10.7 % at ~20 % flow is a rig artifact (multi-hour
residence time, room still drifting). The **LMTD formula agrees with the exact
integral within 0.8 % everywhere** — the Buildings 5-element discretization is
consistent with the logarithmic-overtemperature model across the throttling range.
