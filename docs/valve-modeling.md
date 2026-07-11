# Radiator valve modeling — research notes and model mapping

**2026-07-11.** Basis for the TRV insert model in
[`ApartmentBranch.mo`](../modelica/BuildingSimulator/ApartmentBranch.mo) and the device
mechanics in [`sil/thermostat.py`](../sil/thermostat.py).

## 1. What real German TRV inserts look like (M30 × 1.5)

### Flow vs. stroke — quick-opening, not equal-percentage

Data anchor, Danfoss RA-N 15
([datasheet](https://assets.danfoss.com/documents/latest/101560/AI000086404260en-010201.pdf)):

| Quantity | Value | Meaning |
|---|---|---|
| kv at setting N, xp = 2 K | 0.73 m³/h | flow coefficient at the lift the head reaches 2 K below closing |
| kvs (maximum lift) | 0.90 m³/h | fully open |
| kv presetting 1…7 | 0.04 … 0.52 m³/h | preset ring throttles independent of stroke |

The kv value at setting N is stated per EN 215 at xp = 2 K. With typical RA head travel
of ~0.22 mm/K, the 2 K point corresponds to ~0.44 mm pin lift ≈ **30 % of the 1.5 mm
stroke — where the valve already passes kv/kvs = 0.73/0.90 ≈ 81 % of its full-open
flow.** The insert characteristic is therefore strongly *quick-opening*: nearly all flow
capacity develops in the first third of the stroke; the rest is saturation. (Heimeier
[V-exact II](https://climatecontrol.imiplc.com/product/v-exact-ii) shows the same
qualitative shape.) A textbook equal-percentage law — the default assumption in most
simulation libraries — has the *opposite* curvature (14 % flow at half stroke).

Consequences for control: very high plant gain near closing, most of the usable
resolution of an eTRV motor squeezed into ~0.5 mm of travel.

### Sealing dead zone

Flow starts only after the plug lifts clear of the elastomer seat seal — a dead band of
roughly 0.05–0.15 mm (~3–10 % of stroke). Below it the valve seals essentially tight
(unlike industrial valves with metal seats and ~1 % leakage).

### Hysteresis

Mechanical play between actuator, spindle and pin plus the viscoelastic seal produce an
opening/closing offset. EN 215 measures this as the hysteresis of the characteristic
curve (clause 6.4.1.7; test descriptions: [WSPLab](https://wsplab.de/en/services/heating-cooling-technology/thermostatic-radiator-valves)).
Our device model uses 0.1 mm play; at 0.22 mm/K head travel that is ~0.45 K equivalent —
inside the range certified heads exhibit.

## 2. Pressure dependency

1. **Orifice law.** Flow through the insert follows Q = kv(lift) · √Δp. This is the
   fundamental pressure dependency and is fully captured by the Buildings valve models
   (with regularization near Δp = 0).
2. **Installed characteristic / valve authority.** In the network, opening the valve
   drops its share of the differential pressure, distorting the effective
   characteristic. Design guidance calls for authority a = 0.3–0.5 at the critical
   radiator ([IHKS Fachjournal](https://www.ihks-fachjournal.de/fachartikel/download.php?title=auslegung-von-thermostatventilen)).
   Our design point: Δp_valve = 10 kPa of ~18 kPa branch total → a ≈ 0.55. Captured
   automatically by the pressure/flow network; visible in the valve sweep as the
   deviation between realized flow and the pure Kv table.
3. **Noise / operating limits.** Audible flow noise starts around Δp ≈ 20 kPa,
   whistling at 25–30 kPa ([SHKwissen](https://www.haustechnikdialog.de/SHKwissen/1785/Thermostatventil));
   Danfoss states satisfactory operation up to 30–35 kPa max. Our pump curve tops out
   at 1.5 × design ≈ 27 kPa (all valves closed), so the plant stays inside the
   realistic envelope; the dp bypass keeps the operating range lower in practice.
4. **Δp influence on the closing point** (EN 215 clause 6.4.1.8): the pressure force on
   the plug shifts the effective closing point at high Δp. *Not modeled* — small for
   motor-driven eTRVs (stiff drive vs. wax actuator), relevant mainly above the noise
   limit. Documented limitation.
5. **Pressure-independent valves** (Danfoss RA-DV "Dynamic Valve", IMI Eclipse,
   Oventrop Q-Tech): integrate a Δp regulator per insert, making flow independent of
   network pressure above ~10 kPa. Common in German retrofits. Interesting future
   variant: it largely *decouples* the riser interaction that distributed control
   otherwise has to handle — a useful counterfactual experiment.

## 3. Model mapping

| Physical effect | Where modeled | Parameter |
|---|---|---|
| Quick-opening characteristic incl. dead zone | FMU: `TwoWayTable` | `yCha`/`phiCha` in `ApartmentBranch` (anchor: 80 % flow at 30 % stroke) |
| Seat leakage ~0.04 % | FMU | `phiCha[1] = 4e-4` |
| Q = kv·√Δp, authority, riser interaction | FMU: pressure/flow network | `dpValve_nominal = 10 kPa`, `dpFixed = 2 kPa` |
| Motor travel time | FMU: actuator filter | `strokeTime = 60 s` |
| Backlash/hysteresis (0.1 mm ≈ 0.45 K) | Python device model | `backlash_mm` |
| Closing-point calibration error | Python device model | `calibration_offset_mm` |
| Presetting rings | not separate — `dpValve_nominal` sizing plays this role at design flow | — |
| Δp force on closing point | not modeled (limitation) | — |

Verification: `sil/run_valve_sweep.py` → `results/valve_sweep.png` (realized flow vs
stroke incl. dead zone, saturation and authority distortion; device hysteresis loop).

**Interaction found during verification:** switching from 1 % industrial-valve leakage
to rubber-seal-tight 0.04 % changed the plant's night behavior qualitatively. With all
valves closed, water only circulates pump → boiler → bypass; that loop is adiabatic in
the model (no pipe losses), so the pump dissipation heat that Buildings movers add to
the fluid by default accumulated without bound (T → 130 °C assert). Fixed with the
standard `addPowerToMedium=false` simplification. The honest long-term fix is modeling
distribution pipe heat losses — which are research-relevant anyway (riser losses,
return temperatures) and are on the roadmap.

## 4. Motor current model and adaptation run

The actuator model ([`sil/actuator.py`](../sil/actuator.py)) closes the loop between
firmware and mechanics. Pin load = return spring (preload + rate) + Coulomb friction +
elastomer seal stiffness once the plug enters the seal zone + hydraulic force
(Δp × seat area, ~0.2 N at 10 kPa — realistically invisible against the tens of
newtons of seal force, which the model reproduces). Motor current = baseline +
k · pin force, with noise and ADC quantization; the firmware never sees true positions
or forces, only its own encoder coordinate and this current signal.

`ElectronicThermostat.adaptation_run()` implements the commissioning routine of
commercial eTRVs: drive closed, detect the current knee (seal contact) and the stall
threshold, take the stall position as zero reference. Findings from the demo
(`sil/run_adaptation_demo.py`, `results/adaptation_run.png`):

- The zero estimate carries a **systematic ≈ −80 µm bias** (backlash minus seal
  compression at the stall threshold) with only ~4 µm noise spread. The naive
  "stall = zero" firmware convention therefore biases all commanded openings ~5 % of
  stroke low — a repeatable, identifiable error: a target for adaptive strategies.
- The knee-to-stall distance underestimates the true seal zone (40 µm vs 90 µm) due to
  conservative knee detection — same story.
- Each adaptation run costs ~1.9 mm valve travel (battery KPI) and ~75 s with the
  valve closed.

## 5. Sources

- [Danfoss RA-N valve bodies datasheet](https://assets.danfoss.com/documents/latest/101560/AI000086404260en-010201.pdf) — kv/kvs tables, xp = 2 K definition, max Δp
- [Danfoss RA-N radiator valves (overview)](https://assets.danfoss.com/documents/latest/107418/AI007486472573en-010201.pdf)
- [IMI Heimeier V-exact II](https://climatecontrol.imiplc.com/product/v-exakt-ii) · [datasheet (DE)](https://www.heiz24.de/mediafiles/pdf2/90_110_07--DBL-01-de.pdf)
- [IHKS Fachjournal: Auslegung von Thermostatventilen](https://www.ihks-fachjournal.de/fachartikel/download.php?title=auslegung-von-thermostatventilen) — authority 0.3–0.5, 20 kPa design limit
- [SHKwissen Thermostatventil](https://www.haustechnikdialog.de/SHKwissen/1785/Thermostatventil) — noise thresholds
- [WSPLab EN 215 testing](https://wsplab.de/en/services/heating-cooling-technology/thermostatic-radiator-valves) — hysteresis (6.4.1.7), Δp influence (6.4.1.8), characteristic curves
- [EN 215:2019](https://www.en-standard.eu/bs-en-215-2019-thermostatic-radiator-valves-requirements-and-test-methods/) — requirements and test methods
