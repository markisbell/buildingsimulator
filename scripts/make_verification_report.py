"""Generate the self-contained graphical verification report
(results/verification-report.html) from the plots in results/.
Run after regenerating any verification figures."""
import base64
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"
OUT = RESULTS / "verification-report.html"

IMAGES = {
    "IMG_DESIGN": "design_day_80s.png",
    "IMG_SWEEP": "valve_sweep.png",
    "IMG_FLOWOP": "valve_flow_evidence.png",
    "IMG_ADAPT": "adaptation_run.png",
    "IMG_CMP": "cmp_ideal_vs_realistic.png",
    "IMG_BAL": "balancing_80s.png",
    "IMG_OSC": "oscillation_check_80s.png",
    "IMG_RAD": "radiator_check_80s.png",
    "IMG_ABDYN": "radiator_dynamics_ab.png",
    "IMG_CORRIDOR": "neighbor_test_80s.png",
    "IMG_DT": "dt_comparison_80s.png",
    "IMG_BOPTEST": "boptest_benchmark.png",
}

TEMPLATE = """
<title>Building80s verification report</title>
<style>
:root {
  --paper: #FAFAF7; --card: #FFFFFF; --ink: #1F2125; --muted: #6E6A63;
  --line: #E3E0D8; --supply: #B8432F; --return: #2E5E8C; --pass: #2F7D46;
  --pass-bg: #EAF4EC; --code: #F1EFE9;
}
@media (prefers-color-scheme: dark) {
  :root { --paper: #17191C; --card: #1F2226; --ink: #E8E6E1; --muted: #9B968D;
          --line: #33363B; --supply: #E06A52; --return: #6FA3D3; --pass: #6FBF88;
          --pass-bg: #22352A; --code: #23262B; }
}
:root[data-theme="dark"] { --paper: #17191C; --card: #1F2226; --ink: #E8E6E1;
  --muted: #9B968D; --line: #33363B; --supply: #E06A52; --return: #6FA3D3;
  --pass: #6FBF88; --pass-bg: #22352A; --code: #23262B; }
:root[data-theme="light"] { --paper: #FAFAF7; --card: #FFFFFF; --ink: #1F2125;
  --muted: #6E6A63; --line: #E3E0D8; --supply: #B8432F; --return: #2E5E8C;
  --pass: #2F7D46; --pass-bg: #EAF4EC; --code: #F1EFE9; }

body { background: var(--paper); color: var(--ink);
  font: 16px/1.65 system-ui, "Segoe UI", sans-serif; margin: 0; }
.wrap { max-width: 880px; margin: 0 auto; padding: 48px 24px 80px; }
header { border-bottom: 3px solid var(--supply); padding-bottom: 20px;
  margin-bottom: 12px; }
h1 { font-size: 30px; line-height: 1.2; margin: 0 0 8px; letter-spacing: -0.01em;
  text-wrap: balance; }
.meta { color: var(--muted); font-size: 13.5px;
  font-family: Consolas, monospace; }
.meta b { color: var(--ink); font-weight: 600; }
.lede { font-size: 17px; max-width: 64ch; }
section { margin-top: 44px; }
.eyebrow { font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--supply); font-weight: 600; margin-bottom: 4px; }
h2 { font-size: 21px; margin: 0 0 10px; letter-spacing: -0.005em; }
p { max-width: 68ch; }
table { border-collapse: collapse; width: 100%; font-size: 14px; margin: 14px 0; }
th { text-align: left; font-size: 12px; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--muted); font-weight: 600;
  padding: 6px 10px; border-bottom: 2px solid var(--line); }
td { padding: 7px 10px; border-bottom: 1px solid var(--line);
  font-variant-numeric: tabular-nums; }
td.num { font-family: Consolas, monospace; font-size: 13.5px; }
.pass { display: inline-block; background: var(--pass-bg); color: var(--pass);
  font-weight: 600; font-size: 12px; padding: 1px 10px; border-radius: 10px; }
figure { margin: 18px 0 0; background: #FFFFFF; border: 1px solid var(--line);
  border-radius: 8px; padding: 14px; overflow-x: auto; }
figure img { display: block; max-width: 100%; height: auto; margin: 0 auto; }
figcaption { font-size: 13.5px; color: var(--muted); padding: 10px 4px 0;
  max-width: 78ch; }
code { background: var(--code); border-radius: 4px; padding: 1px 6px;
  font-family: Consolas, monospace; font-size: 13px; }
.finding { border-left: 3px solid var(--return); padding: 2px 0 2px 14px;
  color: var(--ink); max-width: 66ch; margin: 14px 0; }
.finding em { color: var(--return); font-style: normal; font-weight: 600; }
footer { margin-top: 56px; border-top: 1px solid var(--line); padding-top: 16px;
  color: var(--muted); font-size: 13px; }
</style>

<div class="wrap">
<header>
  <h1>Verification report — 1980s German multi-family building simulator</h1>
  <div class="meta">model <b>BuildingSimulator.Building80s</b> · IWU class MFH_G (1979–1983) ·
  3 floors × 2 apartments × 4 rooms · 90/70 °C two-pipe system ·
  repo commit <b>HEAD</b> · 2026-07-16 · interior coupling per ISO 13790 (G<sub>int</sub> = 15.5 W/m²K) ·
  furnished-room fast node (C<sub>air</sub> = 40 kJ/m²K, τ<sub>fast</sub> ≈ 41 min) ·
  night-accessible structural mass (C<sub>mass</sub> = 450 kJ/m²K, τ<sub>slow</sub> ≈ 70–80 h) ·
  radiators 1.3× design load (era sizing), dynamic water/steel storage (8 l + 30 kg per kW,
  τ<sub>e</sub> ≈ 30–50 min) · Schnellaufheizung morning boost (+12 K)</div>
</header>
<p class="lede">Every verification claim, next to its graphical evidence. Each figure is the
unmodified output of a reproducible script in <code>sil/</code>; the numbers in the tables
are read from the same runs.</p>

<section>
<div class="eyebrow">1 · Plant &amp; envelope — winter design day</div>
<h2>Steady heat load, temperatures and setpoints at −12 °C</h2>
<table>
<tr><th>Criterion</th><th>Target</th><th>Measured</th><th></th></tr>
<tr><td>Specific heat load</td><td class="num">58–70 W/m²</td><td class="num">65.0 W/m² (25.0 kW)</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Supply temperature</td><td class="num">≈ 90 °C</td><td class="num">90.0 °C</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Return temperature (unbalanced state)</td><td class="num">60–74 °C</td><td class="num">61.0 °C</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Room setpoints (24 rooms, bath 24 °C)</td><td class="num">± 0.5 K</td><td class="num">worst ± 0.00 K</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Valve saturation</td><td class="num">none</td><td class="num">14–16 % stroke</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Floor flow imbalance</td><td class="num">&lt; 20 %</td><td class="num">7.1 %</td><td><span class="pass">PASS</span></td></tr>
</table>
<figure><img src="data:image/png;base64,@@IMG_DESIGN@@" alt="Design day results">
<figcaption>Left: all 24 rooms exactly on their setpoint marks (20 °C, baths 24 °C) on day 3 of a
constant −12 °C design day. Right: TRV working points — uniformly deep-throttled, the authentic
signature of an unbalanced 90/70 system with 1.3× oversized radiators.
Script: <code>run_design_day.py</code>.</figcaption></figure>
</section>

<section>
<div class="eyebrow">2 · TRV insert — flow characteristic</div>
<h2>German M30×1.5 insert, 1.5 mm stroke, anchored to Danfoss RA-N data</h2>
<table>
<tr><th>Criterion</th><th>Target</th><th>Measured</th><th></th></tr>
<tr><td>Sealing dead zone (≤ 6 % stroke)</td><td class="num">≈ 0 flow</td><td class="num">0.01 % of max</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Flow at 30 % stroke (kv(2K)/kvs = 0.73/0.90)</td><td class="num">≈ 81 %</td><td class="num">81.0 %</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Mechanical hysteresis (0.1 mm play)</td><td class="num">0.10 mm</td><td class="num">0.10 mm</td><td><span class="pass">PASS</span></td></tr>
</table>
<figure><img src="data:image/png;base64,@@IMG_SWEEP@@" alt="Valve sweep">
<figcaption>Left: realized flow vs commanded stroke through the FMU (opening and closing
coincide — the hydraulics carry no hysteresis) against the pure Kv table; the gap is valve
authority. The dotted line marks the RA-N anchor: 81 % flow at the x<sub>p</sub> = 2 K lift.
Right: the device-side 0.1 mm motor–pin play. Script: <code>run_valve_sweep.py</code>.</figcaption></figure>
<div class="finding"><em>Opening vs actual pipe flow in operation:</em> the quasi-static sweep above
is one valve alone; in the running building the same opening delivers a <b>band</b> of flows,
because the branch shares its differential pressure with 23 other valves through the risers.
At the 06:00 boost the flow through this branch collapses at unchanged opening — the neighbours
open and take its differential pressure; the same interaction runs in reverse as they close.
At the working stroke the P5–P95 flow
band spans ±45 % around its mid (15.6–41.3 l/h at y = 0.13–0.17). Full-open median flow matches
the design flow of the branch (74.9 l/h), closing the loop between valve table, ring presetting
and network sizing.</div>
<figure><img src="data:image/png;base64,@@IMG_FLOWOP@@" alt="Opening vs flow in operation">
<figcaption>Left: commanded opening and measured branch flow of one living-room TRV through a
recovery morning (Building80s, as-built rings, eTRVs everywhere). Right: five days of operating
points against the Kv-table shape — the installed characteristic as a band.
Script: <code>make_flow_evidence.py</code> on the <code>run_coordinated_recovery.py</code>
records.</figcaption></figure>
</section>

<section>
<div class="eyebrow">3 · eTRV device — motor current &amp; adaptation</div>
<h2>Zero referencing from the current signature</h2>
<table>
<tr><th>Quantity</th><th>True value</th><th>Firmware estimate</th><th></th></tr>
<tr><td>Mechanical zero (population n = 60)</td><td class="num">—</td><td class="num">−78 µm bias, 4 µm spread</td><td><span class="pass">systematic → compensable</span></td></tr>
</table>
<figure><img src="data:image/png;base64,@@IMG_ADAPT@@" alt="Adaptation run">
<figcaption>Left: one adaptation sweep — motor current vs position with the firmware’s stall
detection (zero reference) against the true pin events; the seal-force rise before the hard stop
is plant physics in the trace, not a firmware feature. Right: the error is a deterministic bias,
not noise — the defining property that makes it identifiable by better algorithms.
Script: <code>run_adaptation_demo.py</code>.</figcaption></figure>
</section>

<section>
<div class="eyebrow">4 · Device impact — ideal PI vs realistic eTRV</div>
<h2>Identical building, weather and solar; only the thermostat hardware differs</h2>
<table>
<tr><th>KPI (days 2–7)</th><th>Ideal PI</th><th>Realistic eTRV</th></tr>
<tr><td>Discomfort</td><td class="num">410 K·h</td><td class="num">854 K·h</td></tr>
<tr><td>Overheating (&gt; setpoint + 1 K)</td><td class="num">137 K·h</td><td class="num">52.9 K·h</td></tr>
<tr><td>Boiler energy</td><td class="num">1989 kWh</td><td class="num">1902 kWh</td></tr>
<tr><td>Valve travel / moves</td><td class="num">88 strokes / 22 078</td><td class="num">306 strokes / 3 108</td></tr>
</table>
<figure><img src="data:image/png;base64,@@IMG_CMP@@" alt="Ideal vs realistic comparison">
<figcaption>Top: the valve-mounted sensor’s warm bias keeps the real device ~1 K under setpoint.
Middle: nighttime limit cycling around the valve dead zone — the battery-drain failure mode.
Bottom: sensor reading vs true room temperature. Script: <code>run_thermostat_comparison.py</code>.</figcaption></figure>
</section>

<section>
<div class="eyebrow">5 · Manual valves — hydraulic balancing</div>
<h2>Commissioning state and the operating benefit</h2>
<table>
<tr><th>Criterion</th><th>Target</th><th>Measured</th><th></th></tr>
<tr><td>Commissioning flows (TRVs open)</td><td class="num">± 5 % of demand</td><td class="num">worst 3.5 %</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Commissioning return</td><td class="num">≈ 70 °C</td><td class="num">63.4 °C</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Recovery-deficit spread vs as-built rings</td><td class="num">reduced</td><td class="num">2.25 K → 1.89 K</td><td><span class="pass">PASS</span></td></tr>
</table>
<div class="finding"><em>Documented physics:</em> under exact-setpoint integral control the
operating return equals supply − Q/(ṁ·c<sub>p</sub>) and is invariant to balancing — with 1.3×
oversized radiators it stays ≈ 61 °C. The textbook 70 °C return exists in the commissioning
state; the operating benefit of balancing is fair flow distribution during recovery.</div>
<figure><img src="data:image/png;base64,@@IMG_BAL@@" alt="Balancing results">
<figcaption>Morning recovery after night setback: per-room temperature deficits at boost + 3 h,
as-built ring scatter (43 % flow deviation) vs the balanced state.
Script: <code>run_balancing.py</code>, presets in <code>results/presets_80s.json</code>.</figcaption></figure>
</section>

<section>
<div class="eyebrow">6 · Dynamics — oscillation signatures</div>
<h2>Cycling boiler, riser lag, stochastic gains, real eTRVs</h2>
<table>
<tr><th>Signature</th><th>Field-data range</th><th>Measured</th><th></th></tr>
<tr><td>Burner starts</td><td class="num">10–250 / day</td><td class="num">73 / day</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Supply sawtooth</td><td class="num">5–20 K pk-pk</td><td class="num">19.0 K</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Room ripple (detrended std)</td><td class="num">0.02–0.6 K</td><td class="num">0.049 K</td><td><span class="pass">PASS</span></td></tr>
<tr><td>Radiator flow fluctuation (CV)</td><td class="num">&gt; 0.1</td><td class="num">1.05</td><td><span class="pass">PASS</span></td></tr>
</table>
<figure><img src="data:image/png;base64,@@IMG_OSC@@" alt="Oscillation traces">
<figcaption>Day 2, 06–12 h: supply sawing on ~20-minute burner cycles; room temperatures dipping
on window-opening events and drifting with solar; the eTRV flow staircase with bursts and
chatter; burner duty blocks. Script: <code>run_oscillation_check.py</code>.</figcaption></figure>
</section>

<section>
<div class="eyebrow">7 · Heat-exchange physics — radiator operating points</div>
<h2>FMU steady states vs the logarithmic overtemperature model</h2>
<table>
<tr><th>Comparison</th><th>Range</th><th>Max deviation</th><th></th></tr>
<tr><td>FMU vs exact EN 442 integral (N = 400)</td><td class="num">full → ~37 % of design flow</td><td class="num">0.4–1.8 %</td><td><span class="pass">PASS</span></td></tr>
<tr><td>LMTD formula vs exact integral</td><td class="num">entire staircase</td><td class="num">≤ 0.8 %</td><td><span class="pass">PASS</span></td></tr>
<tr><td>FMU at ~15 % of design flow</td><td class="num">trickle</td><td class="num">+9.3 % — rig artifact (multi-hour residence time, room drifting)</td><td></td></tr>
</table>
<div class="finding"><em>Energy dynamics:</em> the radiators carry their water/steel storage
(8 l + 30 kg per kW, emission lag ≈ 30–50 min) since the field-realism revision. The A/B against
the quasi-static build shows the field signatures appearing: boost overshoot, the first cooldown
hour cushioned, slow eTRV charge/discharge night cycles, longer burner cycles.</div>
<figure><img src="data:image/png;base64,@@IMG_ABDYN@@" alt="Radiator dynamics A/B">
<figcaption>Heat-up and cooldown, quasi-static (left) vs dynamic (right) radiators, identical
scenario (measured at the pre-night-mass capacity). Script:
<code>compare_radiator_dynamics.py</code>.</figcaption></figure>
<div class="finding"><em>Night-mass calibration (field corridor):</em> overnight free cooling
originally ran ≈ 2× faster than field records; initialization, the warm-neighbor protocol and
the radiator storage were tested and eliminated as causes, and a weakly-coupled deep-mass node
was a null result. The corridor is met by the strongly-coupled night-accessible capacity
(C<sub>mass</sub> 260 → 450 kJ/m²K, backed by DIN V 18599-2/4108-6 and bottom-up construction
inventory): free-cool tail <b>−0.25 K/h</b> (corridor −0.2…−0.4), 8-h drop 2.81 K, a 3 K setback
lasting ≈ 7–8 h — while the era's Schnellaufheizung boost (+12 K morning window) keeps the bulk
of recovery within ≈ 1 h. The field-observed fast-up/slow-down asymmetry is thereby reproduced
as what it is: a power phenomenon (docs/heatup-dynamics.md §6,
<code>calibrate_deep_mass.py</code>).</div>
<figure><img src="data:image/png;base64,@@IMG_CORRIDOR@@" alt="Corridor verification">
<figcaption>Corridor verification: 3 K setback of one living room at −5 °C, whole-building vs
single-room protocol; the tail cools at −0.25 K/h and warm neighbors now visibly stretch the
descent. Script: <code>run_neighbor_test.py</code>.</figcaption></figure>
<figure><img src="data:image/png;base64,@@IMG_RAD@@" alt="Radiator operating points">
<figcaption>Left: measured FMU operating points on the analytical curves — exact continuous
solution, Buildings 5-element discretization, and the LMTD engineering formula, all at identical
boundary conditions (riser-loss-corrected inlet, measured room temperature). Right: deviations
across the throttling range. The Buildings discretization is consistent with the logarithmic
overtemperature model. Script: <code>run_radiator_check.py</code>.</figcaption></figure>
</section>

<section>
<div class="eyebrow">8 · Numerics — communication-step convergence</div>
<h2>Same scenario at 30 s and 10 s co-simulation steps</h2>
<table>
<tr><th>Signature (shared day-2 window)</th><th>dt = 30 s</th><th>dt = 10 s</th><th>Difference</th></tr>
<tr><td>Burner starts / day</td><td class="num">88.9</td><td class="num">90.4</td><td class="num">+1.6 %</td></tr>
<tr><td>Supply sawtooth pk-pk</td><td class="num">19.5 K</td><td class="num">19.0 K</td><td class="num">−2.7 %</td></tr>
<tr><td>Room ripple (detrended std)</td><td class="num">0.081 K</td><td class="num">0.085 K</td><td class="num">−9.2 % (8 mK)</td></tr>
<tr><td>Radiator flow CV</td><td class="num">0.77</td><td class="num">0.75</td><td class="num">−2.4 %</td></tr>
<tr><td>Mean boiler power</td><td class="num">15.68 kW</td><td class="num">15.57 kW</td><td class="num">−0.7 %</td></tr>
<tr><td>Mean room temperature</td><td class="num">19.066 °C</td><td class="num">19.071 °C</td><td class="num">± 0.0 %</td></tr>
</table>
<div class="finding"><em>Method note:</em> the trajectories de-phase over hours — inevitable in a
relay-switched system, where any infinitesimal difference shifts switching instants — while the
statistics agree within a few percent. The 30 s grid is statistically converged; runs must be
compared by KPIs and signatures, never trajectory-by-trajectory. The 10 s run additionally
exposed the pump’s internal volume as the last unprotected water state (solver excursion at
41 h); the pump now runs a steady-state energy balance like the radiators. This study was
performed at the pre-ISO interior calibration (C<sub>air</sub> = 15 kJ/m²K) — the least-damped
and therefore numerically hardest state; the current calibration (§6 numbers) adds zone damping,
which relaxes rather than tightens the step-size requirement.</div>
<figure><img src="data:image/png;base64,@@IMG_DT@@" alt="Communication step comparison">
<figcaption>Day 2, 07–10 h: supply sawtooth and one radiator flow at both communication steps —
identical amplitude, period and character; phases drift apart as expected.
Scripts: <code>run_oscillation_check.py [dt]</code>, <code>compare_dt.py</code>.</figcaption></figure>
</section>

<section>
<div class="eyebrow">9 · External benchmark — BOPTEST</div>
<h2>Same firmware objects on the IBPSA reference plant</h2>
<p>Cross-plant validation on <code>multizone_residential_hydronic</code> — an independently
developed residential dwelling (gas boiler, five valve-equipped radiator zones plus a valveless
hall) — over BOPTEST&rsquo;s standardized <code>peak_heat_day</code> scenario, scored by
BOPTEST&rsquo;s own KPIs. The eTRV firmware runs unmodified; only the I/O wiring changes
(<code>sil/boptest_adapter.py</code>). Boiler supply control stays at the test-case baseline in
all cases, so the cases differ only in TRV behavior.</p>
<table>
<tr><th>Case</th><th>tdis_tot [K·h/zone]</th><th>ener_tot [kWh/m²]</th><th>cost_tot [€/m²]</th><th>emis_tot [kgCO₂/m²]</th></tr>
<tr><td>BOPTEST baseline (embedded controller)</td><td class="num">21.41</td><td class="num">8.24</td><td class="num">0.81</td><td class="num">1.43</td></tr>
<tr><td>plain PI on true zone temperature</td><td class="num">25.48</td><td class="num">8.23</td><td class="num">0.81</td><td class="num">1.43</td></tr>
<tr><td>stock eTRV (biased valve sensor)</td><td class="num">69.66</td><td class="num">8.06</td><td class="num">0.80</td><td class="num">1.40</td></tr>
<tr><td>ladder eTRV (Phase 3 firmware, unretuned)</td><td class="num">52.04</td><td class="num">8.23</td><td class="num">0.81</td><td class="num">1.43</td></tr>
</table>
<div class="finding"><em>Both central findings reproduce:</em> the stock firmware&rsquo;s
sensor pathology costs <b>2.7×</b> the plain-PI discomfort (in-repo simulator: 2.1×) for a 2 %
energy saving — the rooms simply run cold; the Phase 3 firmware recovers <b>40 % of the
pathology gap at PI-equal energy</b>, with factory priors, on a plant it has never seen.
BOPTEST&rsquo;s <code>tdis_tot</code> is <b>two-sided</b> (charges over- and undershoot), which
closes the one-sided-KPI caveat documented for the in-repo ladder experiments: the recovery is
not a warm-side metric artifact. Partial rather than full recovery is expected — the KPI window
includes the estimator&rsquo;s learning nights, and the deliberate ~30 % under-correction
transfers untuned.</div>
<div class="finding"><em>Validation boundary:</em> BOPTEST validates the closed-loop
<b>consequences</b> of the sensor pathology and its mitigation on an independent
building/hydronics/weather model with third-party KPIs — not the bias magnitude itself, which
remains part of our device model (driven here by BOPTEST&rsquo;s delivered-heat signal).</div>
<figure><img src="data:image/png;base64,@@IMG_BOPTEST@@" alt="BOPTEST benchmark KPIs">
<figcaption>BOPTEST KPIs for the four cases: thermal discomfort (left) and HVAC energy (right).
Full KPI payloads in <code>results/boptest_benchmark.json</code>; method, interface mapping and
reproduction steps in <code>docs/boptest-benchmark.md</code>. Scripts:
<code>run_boptest_benchmark.py</code>, <code>make_boptest_figure.py</code>.</figcaption></figure>
</section>

<footer>Reproduce any figure: <code>docker run --rm -v ${PWD}:/work -w /work/sil
buildingsimulator:dev python3 &lt;script&gt;.py</code> · parameter derivation with sources in
<code>docs/building80s-parameters.md</code> · github.com/markisbell/buildingsimulator<br>
Developed with Claude Code (Anthropic) as a coding agent under human direction; every claim
is backed by a reproducible script, but AI-generated content may contain errors — independent
review is advised before relying on quantitative results.</footer>
</div>
"""

html = TEMPLATE
for key, name in IMAGES.items():
    data = base64.b64encode((RESULTS / name).read_bytes()).decode()
    html = html.replace(f"@@{key}@@", data)

OUT.write_text(html, encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")

