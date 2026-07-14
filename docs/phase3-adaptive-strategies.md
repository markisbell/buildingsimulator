# Phase 3 — Adaptive eTRV control strategies: results

The research phase this simulator was built for: can the comfort and battery
penalties of realistic electronic radiator thermostats be recovered by better
firmware — individually (adaptive) and collectively (distributed)? Four
strategies were built as a **cumulative ladder**, each evaluated on the
identical scenario against two fixed baselines, and one distributed strategy
was taken through a five-round experiment on the room-resolved 1980s building.

**Ground rules.** Every strategy is pure firmware: a device sees only its own
sampled (300 s), quantized (0.1 K), radiator-biased sensor, its own commanded
position, and the clock (`sil/thermostat.py`). Distributed strategies may
additionally use the hub broadcast channel that commercial eTRV ecosystems
provide (a shared blackboard, no central intelligence). Nothing reads
plant-side signals.

**Baselines** (generic 6-apartment building, 7-day winter with solar and
occupancy schedules, two-point-free supply with Schnellaufheizung boost,
`sil/run_thermostat_comparison.py`):

- *ideal PI* — a hardware-free controller reading the true room temperature:
  the upper bound no device can beat;
- *stock eTRV* — the full device-pathology model: valve-mounted sensor bias,
  sampling, deadband, backlash, quick-opening insert.

## 1. The ladder at a glance

| KPI (days 2–7) | ideal PI | stock eTRV | + bias comp | + battery | + opt-start |
|---|---|---|---|---|---|
| Discomfort (K·h) | 409.7 | 853.5 | 563.8 | 586.8 | **440.4** |
| Overheating (K·h) | 137.2 | 52.9 | 97.3 | 94.1 | 119.8 |
| Boiler energy (kWh) | 1988.7 | 1902.0 | 1988.9 | 1978.7 | 2018.4 |
| Valve travel (strokes/wk) | — | 305.8 | 274.3 | **241.0** | 261.2 |
| Valve moves (count/wk) | — | 3108 | 2386 | **1216** | 1337 |

Three firmware upgrades take a realistic eTRV from **double** the ideal-PI
discomfort to **within 7.5 %** of it, while halving the battery-relevant move
count at the middle rung. The honest costs stay visible: comfort costs energy
(boiler consumption returns to the ideal-PI level once rooms actually reach
setpoint), and optimal start buys on-time arrivals with pre-start overheating
(119.8 K·h — still below the ideal PI's own 137.2).

Every rung exploits a physical time scale verified earlier in the project:

| Strategy | Exploited physics | Where verified |
|---|---|---|
| Bias compensation | sensor-bias decay (τ ≈ 10 min) vs calibrated room cooling (−0.25 K/h) — separable at closures | heatup-dynamics.md §6 |
| Battery policies | radiator storage still arriving after a close (τ_e ≈ 30–50 min); quick-opening stroke resolution | radiator-modeling.md §3, valve-modeling.md |
| Optimal start | multi-time-constant recovery no single slope predicts | heatup-dynamics.md §§1–4 |
| Considerate recovery | riser interaction: flow at fixed opening is a ±29 % band | valve-modeling.md §3 |

## 2. Rung 1 — adaptive sensor-bias compensation

The valve-mounted sensor reads high while the radiator is hot; the stock
device chronically holds the room ~1–1.5 K below setpoint — the dominant
penalty. The firmware cannot see the bias, but it can *catch it in the act*:
at every long valve closure the bias decays within tens of minutes while the
calibrated room loses only ~0.2 K/h. The excess sensed-temperature drop over
the closure is the bias that was present; one gain update per closure
(`BiasCompensatingThermostat`, `sil/strategies.py`). Compensation is applied
through a lag-filtered heat proxy computed from the device's own commanded
opening via the known quick-opening insert shape.

![Adaptive bias compensation](figures/adaptive_bias.png)

*Fig. 1 — Top: true room temperature, stock vs adaptive, days 5–7 (the stock
plateau sits 1.5 K under setpoint; the adaptive one at −0.3…−0.5 K). Middle:
the learned gain converging within ~2 nights. Bottom: per-day discomfort
falling toward the ideal-PI bound as learning progresses.*

Result: discomfort **853.5 → 563.8 K·h** (65 % of the stock penalty
recovered) with travel *down* (compensation reduces hunting) and the energy
cost on display.

## 3. Rung 2 — battery-aware limit-cycle suppression

Two policies against the night cycling that burns valve travel:
a **comfort-scaled deadband** (near setpoint a move must be worth 15 % of
stroke instead of 5 % — fine positioning there is futile anyway, the insert
squeezes all resolution into ~0.5 mm and the radiator storage low-passes the
result) and a **reopen dwell** (after closing, no reopen for 15 min unless
the room is genuinely cold: the radiator's stored heat is still arriving).

Result: **moves halved** (2386 → 1216), travel 274 → 241 strokes/week, for
+23 K·h discomfort.

## 4. Rung 3 — per-room adaptive optimal start

The stock device reacts to the morning setpoint step and arrives 1–2 h late
(the multi-time-constant recovery documented in heatup-dynamics.md). This
firmware advances its own setpoint step by a lead time learned from each
morning's measured arrival on its *own compensated sensor* — bounded updates,
solar-crossing guard, the central boost simply absorbed into the learned lead.

![Strategy ladder](figures/strategy_ladder.png)

*Fig. 2 — Top: day-6 morning; the optimal-start device begins climbing at
~04:30 and crosses the day-start line at 19.3 °C, arriving with the boosted
ideal PI, while the previous rung is still 2 K away. Bottom: valve travel
down the ladder.*

Leads converge per room and per usage pattern: south living rooms ≈ 95 min,
the warm-preference apartment ≈ 45 min. Full-ladder discomfort: **440.4 K·h**
vs the ideal PI's 409.7.

## 5. Rung 4 — distributed considerate recovery (a documented negative)

**Question:** in the as-built 1980s building (scattered presetting rings,
43 % flow deviation), greedy morning recovery lets hydraulically favored
rooms starve the weak ones. Can arrived devices *yield* — cap their opening
during contention, freeing differential pressure for laggards — coordinated
only through the hub blackboard (`RecoveryCoordinator`)?

**Five experiment rounds** (`sil/run_coordinated_recovery.py`, Building80s,
as-built rings, whole-building setback, day-6 boost, greedy vs considerate
with identical seeds), each round a finding:

1. **The bias floor drowns fairness metrics.** Devices satisfied on biased
   sensors never truly arrive; no threshold is reachable. Fairness can only
   be measured above converged bias learning.
2. **The radiator storage corrupts the anchor.** The valve body tracks the
   stored-heat discharge (τ_e ≈ 30–50 min), so identification windows sized
   to the 600 s sensor lag learn k̂ ≈ 0 on 90/70 era radiators. *The same
   radiators that are hardest to control are hardest to calibrate against* —
   the most transferable finding of the phase for real firmware.
3. **Unconditional yielding is fragile.** One never-arriving peer (a device
   that could not learn) keeps the whole swarm capped all day. Coordination
   needs contention windows.
4. **Identification must work on partial decays.** Fast-cooling rooms reopen
   ~2–2.5 h after setback and never grant a settling wait. The final
   estimator: three equal windows over whatever closure exists — the window
   drops form a geometric sequence in the bias decay, so the bias at closure
   is recoverable (Prony-style); window edges averaged against the 0.1 K
   quantization; the S-shaped double-lag flat top skipped and
   back-extrapolated with the measured decay ratio. Verified by a two-plant
   unit probe (`sil/test_strategies.py`) including a 1.5 h partial closure.
5. **A factory prior closes the tail.** One bath's usage pattern never
   grants a usable closure; devices now ship k̂ = 1.0 and refine. With that,
   18–20 of 24 rooms arrive within 0.75 K (from 9–10), min k̂ 1.4–1.6.

**Verdict:** with well-calibrated devices, **greedy beats considerate on
every metric** (worst room at +3 h: 1.09 vs 1.75 K; arrivals 20 vs 18) — the
boosted, 1.3×-sized plant resolves the contention itself, and capping arrived
rooms only delays them. The apparent hydraulic fairness problem of the early
rounds was residual sensor bias in disguise. The policy is retained as a
documented negative result; it would pay only in plants without reheat margin
(no boost, no oversizing), where recovery contention is genuinely binding.

![Coordinated recovery](figures/coordinated_recovery.png)

*Fig. 3 — Final round: per-room deficit trajectories and arrival
distributions, greedy vs considerate, plus the supply relay/boost traces
confirming both variants saw identical plant behavior.*

The hydraulic interaction the strategy targeted is real and quantified — the
installed valve characteristic in operation is a **band** (±29 % flow at the
working stroke, flow collapse at unchanged opening when the neighbours open
at the boost; valve-modeling.md §3, `scripts/make_flow_evidence.py`) — it is
simply not the binding constraint of this building's recoveries once sensing
is healthy.

## 6. What Phase 3 established

1. **The device penalty is mostly recoverable in firmware.** No hardware
   change: 93 % of the comfort gap closed, moves halved, all trades explicit.
2. **Every effective strategy is a physics exploit.** The ladder worked
   because each rung leaned on a verified, documented time scale — and the
   one strategy that ignored where the bottleneck actually was (rung 4)
   returned a negative.
3. **Identifiability is a plant property.** Sensor-bias learning lives or
   dies by the radiator's thermal storage and the room's usage pattern;
   robust estimators (partial-decay identification + factory priors) are
   mandatory, not optional.
4. **Measure against the honest bound.** The ideal-PI baseline kept every
   claim calibrated: no strategy "beats physics", and costs (energy,
   pre-start overheating) surface instead of hiding.

Numbers in this document were measured at the revision of each rung's
evaluation run (rungs 1–3 with the original anchor estimator; rung 4 with the
hardened one). Re-evaluating the generic-building ladder with the final
firmware is queued follow-up work; the hardened estimator and factory prior
can only improve rungs 1–3.

## Reproduction

| Result | Script |
|---|---|
| Ladder rung 1 | `sil/run_adaptive_bias.py` |
| Ladder rungs 2–3 + table | `sil/run_strategy_ladder.py` |
| Rung 4 fairness experiment | `sil/run_coordinated_recovery.py` |
| Estimator unit probe | `sil/test_strategies.py` |
| Opening-vs-flow evidence | `scripts/make_flow_evidence.py` |

All runs land in the run store (`runs/`) and the leaderboard; baselines are
the `cmp_ideal` / `cmp_realistic` runs of `sil/run_thermostat_comparison.py`.

## References

- Device model and constraints: [thermostat.py](../sil/thermostat.py),
  [valve-modeling.md](valve-modeling.md) (motor current, adaptation run,
  backlash), [radiator-modeling.md](radiator-modeling.md) §3 (storage).
- Building physics the strategies exploit:
  [heatup-dynamics.md](heatup-dynamics.md),
  [dynamics-assumptions.md](dynamics-assumptions.md),
  [building80s-parameters.md](building80s-parameters.md).
- Optimal-start lineage: Seem (1989); Armstrong, Hancock & Seem, ASHRAE
  Transactions 98(1), 1992.
- TRV loop stability at low flows: F. Tahersima et al., Energy and Buildings
  64 (2013), [doi:10.1016/j.enbuild.2013.04.019](https://doi.org/10.1016/j.enbuild.2013.04.019).
