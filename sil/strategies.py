"""Phase 3: adaptive eTRV control strategies (firmware upgrades under test).

Every strategy here respects the device constraints of thermostat.py: the
firmware sees only its own sampled, quantized, biased sensor, its own
commanded position and the clock. No plant-side signals.

Strategy 1 — BiasCompensatingThermostat (adaptive sensor-bias compensation)
---------------------------------------------------------------------------
The valve-mounted sensor reads high while the radiator is hot (bias tracks
radiator output with tau ~ 600 s), so the stock device chronically holds the
room ~1 K below setpoint — the dominant comfort penalty vs the ideal PI
(854 vs 410 K*h discomfort in the baseline comparison).

The firmware cannot see the bias directly, but the building physics make it
identifiable at every long valve closure (night setback):

  - the bias decays with tau ~ 10 min once the radiator is off,
  - the calibrated room cools at only ~0.2-0.3 K/h (docs/heatup-dynamics.md
    section 6) — an order of magnitude slower.

Night-anchor learning: at closure, remember the sensed temperature and the
filtered heat proxy u0; after the bias has settled (45 min), the remaining
sensed slope is the true room cooling. The excess drop over the settle
window is the bias that was present at closure:

    bias(t_close) ~ [Ts(0) - Ts(45min)] - late_rate * 45min
    k_hat <- (1-alpha) k_hat + alpha * bias / u0        (clamped)

Compensation: the wrapped control algorithm is fed
    T_comp = T_sensed - k_hat * u_filt
where u_filt is the sensor-lag-filtered heat proxy derived from the device's
own commanded opening through the known quick-opening insert shape (~81 %
flow at 30 % stroke). Everything else (sampling, deadband, backlash,
adaptation run) stays identical to the stock device for a clean A/B.
"""

from thermostat import ElectronicThermostat


class _CompensatedAlgorithm:
    """Shim between the device sensor pipeline and the wrapped algorithm:
    applies the learned bias compensation at every firmware sample."""

    def __init__(self, owner, inner):
        self.owner = owner
        self.inner = inner

    def step(self, t, T_sensed):
        return self.inner.step(t, self.owner._compensate(t, T_sensed))


class BiasCompensatingThermostat(ElectronicThermostat):
    def __init__(self, *args,
                 comp_alpha=0.5,        # learning rate per night anchor
                 comp_k_init=1.0,       # factory prior: rooms whose usage
                                        # pattern never grants a usable
                                        # closure (found: one bath) must
                                        # not run uncompensated; anchors
                                        # refine from here
                 comp_k_max=3.0,        # K, sanity clamp
                 # Anchor windows must span the RADIATOR STORAGE discharge,
                 # not just the 600 s sensor lag: after closure the valve
                 # body keeps tracking the stored-heat emission (tau_e ~
                 # 30-50 min). Fast-cooling small rooms reopen after only
                 # ~2.5 h, so the estimator must also work on PARTIAL
                 # decays: three equal windows over whatever closure is
                 # available; the window-drop differences form a geometric
                 # sequence in the bias decay, so the bias at closure is
                 # recoverable without waiting for full settling
                 # (Prony-style identification, see _finish_anchor).
                 anchor_min_s=5400.0,   # shortest usable closure (1.5 h)
                 anchor_max_s=9000.0,   # evaluate at the latest after 2.5 h
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.comp_alpha = comp_alpha
        self.k_hat = comp_k_init
        self.comp_k_max = comp_k_max
        self.anchor_min_s = anchor_min_s
        self.anchor_max_s = anchor_max_s

        self._u_filt = 0.0
        self._last_comp_t = None
        self._closed_since = None
        self._anchor = None       # dict: u0 + buffered (t, Ts) samples
        self.k_log = []           # (t, k_hat) after every anchor update
        self.comp_log = []        # (t, T_sensed, T_comp, u_filt)
        self.anchor_debug = []    # estimator internals per finished anchor

        # wrap the control algorithm with the compensation shim
        self.algorithm = _CompensatedAlgorithm(self, self.algorithm)

    # -- firmware-side heat proxy ------------------------------------------
    @staticmethod
    def _heat_proxy(position):
        """Radiator-output proxy from the commanded opening: quick-opening
        insert (~81 % flow at 30 % stroke) + saturating EN 442 emission
        make output rise steeply over the first third of the stroke."""
        return min(1.0, (max(0.0, position) / 0.30) ** 0.5)

    # -- called by the shim at every firmware sample -----------------------
    def _compensate(self, t, T_sensed):
        pos = self._position          # opening applied since the last sample
        self._update_anchor(t, T_sensed, pos)

        dt = 0.0 if self._last_comp_t is None else t - self._last_comp_t
        self._last_comp_t = t
        if dt > 0.0:
            self._u_filt += ((self._heat_proxy(pos) - self._u_filt)
                             * min(1.0, dt / self.sensor_tau))

        T_comp = T_sensed - self.k_hat * self._u_filt
        self.comp_log.append((t, T_sensed, T_comp, self._u_filt))
        # signed control error at this sample (used by battery policies)
        inner = self.algorithm.inner
        if hasattr(inner, "setpoint"):
            self.last_error_K = inner.setpoint(t) - T_comp
        return T_comp

    # -- night-anchor learning ---------------------------------------------
    def _update_anchor(self, t, T_sensed, pos):
        closed = pos <= 0.02
        if not closed:
            if self._anchor is not None:
                # closure ends: evaluate whatever decay we witnessed
                self._finish_anchor()
            self._closed_since = None
            return
        if self._closed_since is None:
            # closure begins: remember pre-closure heat level, buffer samples
            self._closed_since = t
            self._anchor = {"u0": self._u_filt, "samples": [(t, T_sensed)]}
            return
        if self._anchor is None:      # this closure already produced an update
            return
        self._anchor["samples"].append((t, T_sensed))
        if t - self._closed_since >= self.anchor_max_s:
            self._finish_anchor()     # long closure: no need to wait longer

    @staticmethod
    def _edge_mean(samples, t_want, half=600.0):
        """Mean reading around a window edge: averages the 0.1 K sensor
        quantization down to identification-grade resolution."""
        vals = [Ts for (ts, Ts) in samples if abs(ts - t_want) <= half]
        return sum(vals) / len(vals) if vals else \
            min(samples, key=lambda s: abs(s[0] - t_want))[1]

    def _finish_anchor(self):
        """Three-window bias identification on the buffered closure.

        Model: Ts(tau) = (T0 - r*tau) + b0*q(tau) with the bias decay
        q(tau) ~ exp(-tau/tau_b) (sensor lag + radiator storage, tau_b
        unknown). Split the closure into three equal windows with drops
        D1, D2, D3: the differences form a geometric sequence,
        (D2-D3)/(D1-D2) = rho = exp(-T/(3 tau_b)), so the bias at closure
        b0 = (D1-D2)/(1-rho)^2 is identifiable from a PARTIAL decay —
        no settling wait, which fast-cooling rooms never grant."""
        import math

        a, self._anchor = self._anchor, None
        samples = a["samples"]
        T = samples[-1][0] - samples[0][0]
        if T < self.anchor_min_s or a["u0"] < 0.15:
            return                    # too short / not identifiable
        # skip the S-shaped flat top of the double-lag decay (sensor lag on
        # top of the radiator discharge): after ~25 min the sensor-lag mode
        # is gone and the remainder decays near-single-exponentially
        skip = 1500.0
        t_start = samples[0][0] + skip
        T2 = samples[-1][0] - t_start
        half = min(600.0, T2 / 6)
        s0 = self._edge_mean(samples, t_start, half)
        s1 = self._edge_mean(samples, t_start + T2 / 3, half)
        s2 = self._edge_mean(samples, t_start + 2 * T2 / 3, half)
        s3 = self._edge_mean(samples, t_start + T2, half)
        d1, d2, d3 = s0 - s1, s1 - s2, s2 - s3
        g1, g2 = d1 - d2, d2 - d3
        if g1 <= 0.04:
            rho, b0 = None, 0.0       # no curvature: bias was already ~zero
        else:
            # physical bound: the storage decay tau_b stays well under
            # ~1.6 h, so rho <= 0.6 — also caps noise amplification
            rho = min(max(g2 / g1, 0.05), 0.60)
            b0 = min(g1 / (1.0 - rho) ** 2, 3.0)
            # DELIBERATELY NO back-extrapolation over the skipped flat top:
            # the zone fast node relaxes with tau ~ 41 min — spectrally
            # indistinguishable from the bias decay inside a closure — so
            # the estimator inevitably books some of the room's own sag
            # curvature as bias. Amplifying that (exp(skip/tau_b) factor)
            # drove every k_hat into the clamp and the rooms ~1 K ABOVE
            # setpoint on the generic building (ladder re-evaluation).
            # The at-skip estimate under-corrects by ~30 % by design:
            # a residual 0.3-0.4 K below setpoint is the safe failure mode.
        k_obs = min(max(b0, 0.0) / max(a["u0"], 0.15), self.comp_k_max)
        self.anchor_debug.append(
            {"t_h": samples[-1][0] / 3600, "T_h": T / 3600,
             "d": (round(d1, 3), round(d2, 3), round(d3, 3)),
             "rho": rho, "b0": round(b0, 3),
             "u0": round(a["u0"], 3), "k_obs": round(k_obs, 3)})
        self.k_hat += self.comp_alpha * (k_obs - self.k_hat)
        self.k_hat = min(max(self.k_hat, 0.0), self.comp_k_max)
        self.k_log.append((samples[-1][0], self.k_hat))


class BatteryAwareThermostat(BiasCompensatingThermostat):
    """Strategy 2 — battery-aware limit-cycle suppression, stacked on the
    bias compensation.

    Two firmware-only policies against the night/low-demand cycling that
    burns valve travel (the dominant battery cost):

    1. Comfort-scaled deadband: near setpoint (|e| <= near_band_K) a
       reposition must be worth `deadband_near` of stroke (vs the stock
       0.05); far from setpoint the stock fine deadband applies, so
       recovery control stays crisp. Near setpoint, fine positioning is
       futile anyway: the quick-opening insert squeezes all resolution
       into ~0.5 mm of travel and the radiator storage low-passes the
       result.
    2. Reopen dwell (anti-short-cycle, like the burner relay): after
       closing, do not reopen within `reopen_dwell_s` unless the room is
       genuinely cold (e > reopen_override_K) — the radiator's stored
       heat is still arriving during that window.
    """

    def __init__(self, *args, deadband_near=0.15, near_band_K=0.5,
                 reopen_dwell_s=900.0, reopen_override_K=0.5, **kwargs):
        super().__init__(*args, **kwargs)
        self.deadband_near = deadband_near
        self.near_band_K = near_band_K
        self.reopen_dwell_s = reopen_dwell_s
        self.reopen_override_K = reopen_override_K
        self._closed_at = None
        self.last_error_K = 0.0

    def _worth_moving(self, t, command):
        e = self.last_error_K
        # anti-short-cycle: freshly closed and not genuinely cold -> stay
        if (self._position == 0.0 and command > 0.0
                and self._closed_at is not None
                and t - self._closed_at < self.reopen_dwell_s
                and e < self.reopen_override_K):
            return False
        deadband = (self.deadband_near if abs(e) <= self.near_band_K
                    else self.position_deadband)
        move = (abs(command - self._position) >= deadband
                or (command in (0.0, 1.0) and command != self._position))
        if move and command == 0.0:
            self._closed_at = t
        return move


class RecoveryCoordinator:
    """The radio channel of a distributed eTRV swarm: every device reports
    its control deficit each firmware sample; the swarm exposes the worst
    recent deficit. No central intelligence — just a shared blackboard,
    which is exactly what commercial eTRV ecosystems (hub broadcast) offer."""

    def __init__(self, stale_s=900.0):
        self.stale_s = stale_s
        self._reports = {}

    def report(self, name, t, deficit):
        self._reports[name] = (t, deficit)

    def worst(self, t):
        vals = [d for (tr, d) in self._reports.values()
                if t - tr <= self.stale_s]
        return max(vals) if vals else 0.0


class ConsiderateRecoveryThermostat(BatteryAwareThermostat):
    """Strategy 4 — distributed considerate recovery, stacked on 1 + 2.

    In the as-built (scattered presetting rings) building, all valves open
    fully during morning recovery; the hydraulically favored rooms arrive
    first and keep drawing full flow while their PI slowly unwinds —
    starving the weak rooms (recovery-deficit spread 2.25 K in the
    balancing benchmark).

    Policy: once a device has essentially arrived (own deficit below
    own_arrived_K) while any peer still reports a deficit above
    peer_needy_K, it caps its opening at y_cap — releasing differential
    pressure to the laggards. The cap lifts (hysteresis) once the worst
    peer deficit falls below peer_release_K.

    FINAL EXPERIMENT VERDICT (run_coordinated_recovery.py, five rounds):
    with well-calibrated bias compensation on every device, greedy
    recovery beats considerate capping on all metrics (worst room at
    +3 h: 1.09 vs 1.75 K) — the boosted 1.3x plant resolves the
    contention itself, and capping arrived rooms only delays them. The
    apparent fairness problem of the earlier rounds was residual sensor
    bias in disguise. Kept as a documented negative result; the policy
    would only pay in plants without reheat margin (no boost, no
    oversizing) where recovery contention is genuinely binding.
    """

    def __init__(self, *args, coordinator=None, own_arrived_K=0.3,
                 peer_needy_K=0.8, peer_release_K=0.5, y_cap=0.25,
                 day_start_h=None, cap_window_h=3.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.coordinator = coordinator
        self.own_arrived_K = own_arrived_K
        self.peer_needy_K = peer_needy_K
        self.peer_release_K = peer_release_K
        self.y_cap = y_cap
        # capping only during the morning contention window: outside it a
        # never-arriving peer (e.g. badly under-learned bias) would keep
        # everyone capped all day (finding of the first experiment round)
        self.day_start_h = day_start_h
        self.cap_window_h = cap_window_h
        self._capping = False
        self.cap_time_s = 0.0        # diagnostic: total time spent capped
        self._last_shape_t = None

    def _compensate(self, t, T_sensed):
        T_comp = super()._compensate(t, T_sensed)
        if self.coordinator is not None:
            self.coordinator.report(self.temp_output, t, self.last_error_K)
        return T_comp

    def _shape_command(self, t, command):
        if self.coordinator is None:
            return command
        if self.day_start_h is not None:
            hour = (t % 86400.0) / 3600.0
            if not (self.day_start_h <= hour
                    < self.day_start_h + self.cap_window_h):
                self._capping = False
                self._last_shape_t = t
                return command
        worst = self.coordinator.worst(t)
        arrived = self.last_error_K < self.own_arrived_K
        if self._capping:
            self._capping = arrived and worst > self.peer_release_K
        else:
            self._capping = arrived and worst > self.peer_needy_K
        if self._capping:
            if self._last_shape_t is not None:
                self.cap_time_s += t - self._last_shape_t
            self._last_shape_t = t
            return min(command, self.y_cap)
        self._last_shape_t = t
        return command


class OptimalStartThermostat(BatteryAwareThermostat):
    """Strategy 3 — per-room adaptive optimal start, stacked on 1 + 2.

    The stock device reacts to the morning setpoint step at day start and
    arrives 1-2 h late (multi-time-constant recovery,
    docs/heatup-dynamics.md). This firmware advances its own setpoint step
    by a learned lead time and adapts it from each morning's measured
    arrival:

        lead <- clamp(lead + beta * (t_arrival - t_daystart), 0, lead_max)

    Arrival is detected on the device's own compensated temperature
    (crossing day_sp - arrival_margin). The central Schnellaufheizung and
    building dynamics are unknown to the device — whatever they do is
    absorbed into the learned lead.

    Construction differs from the other strategies: the device must own
    its setpoint schedule, so it takes the schedule tuple
    (day_sp, night_sp, day_start_h, day_end_h) and an algorithm factory.
    """

    def __init__(self, *args, schedule=None,
                 algorithm_factory=None,
                 lead_init_s=1800.0, lead_max_s=10800.0, lead_beta=0.5,
                 arrival_margin_K=0.2, **kwargs):
        if schedule is None or algorithm_factory is None:
            raise ValueError("schedule and algorithm_factory are required")
        self.day_sp_K = schedule[0] + 273.15
        self.night_sp_K = schedule[1] + 273.15
        self.day_start_h, self.day_end_h = schedule[2], schedule[3]
        self.lead_s = lead_init_s
        self.lead_max_s = lead_max_s
        self.lead_beta = lead_beta
        self.arrival_margin_K = arrival_margin_K
        self.lead_log = []            # (t, lead_s) after each morning
        self._arrival_day = -1        # last day with a recorded arrival

        super().__init__(*args, algorithm=algorithm_factory(self._setpoint),
                         **kwargs)

    def _setpoint(self, t):
        hour = (t % 86400.0) / 3600.0
        start_eff_h = self.day_start_h - self.lead_s / 3600.0
        return (self.day_sp_K if start_eff_h <= hour < self.day_end_h
                else self.night_sp_K)

    def _compensate(self, t, T_sensed):
        T_comp = super()._compensate(t, T_sensed)
        # morning arrival detection -> lead-time learning, once per day
        day = int(t // 86400.0)
        hour = (t % 86400.0) / 3600.0
        # accept arrivals only around the morning recovery itself — a solar
        # afternoon crossing must not be mistaken for a (very late) arrival
        in_morning = (self.day_start_h - self.lead_max_s / 3600.0 - 0.5
                      <= hour
                      < min(self.day_end_h, self.day_start_h + 4.0))
        if (day != self._arrival_day and in_morning
                and T_comp >= self.day_sp_K - self.arrival_margin_K):
            self._arrival_day = day
            t_target = day * 86400.0 + self.day_start_h * 3600.0
            err = min(t - t_target, 7200.0)   # bounded: late -> more lead
            self.lead_s = min(max(self.lead_s + self.lead_beta * err, 0.0),
                              self.lead_max_s)
            self.lead_log.append((t, self.lead_s))
        return T_comp
