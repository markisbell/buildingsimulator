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
                 comp_alpha=0.4,        # learning rate per night anchor
                 comp_k_init=0.0,       # K bias at full heat proxy, initial
                 comp_k_max=3.0,        # K, sanity clamp
                 anchor_settle_s=2700.0,   # bias fully decayed after this
                 anchor_slope_s=1800.0,    # window to measure true cooling
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.comp_alpha = comp_alpha
        self.k_hat = comp_k_init
        self.comp_k_max = comp_k_max
        self.anchor_settle_s = anchor_settle_s
        self.anchor_slope_s = anchor_slope_s

        self._u_filt = 0.0
        self._last_comp_t = None
        self._closed_since = None
        self._anchor = None       # state of the running night anchor
        self.k_log = []           # (t, k_hat) after every anchor update
        self.comp_log = []        # (t, T_sensed, T_comp, u_filt)

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
            self._closed_since = None
            self._anchor = None
            return
        if self._closed_since is None:
            # closure begins: remember pre-closure heat level and reading
            self._closed_since = t
            self._anchor = {"Ts0": T_sensed, "u0": self._u_filt}
            return
        if self._anchor is None:      # this closure already produced an update
            return

        elapsed = t - self._closed_since
        a = self._anchor
        if "Ts_settle" not in a:
            if elapsed >= self.anchor_settle_s:
                a["Ts_settle"], a["t_settle"] = T_sensed, t
            return
        if t - a["t_settle"] < self.anchor_slope_s:
            return

        # bias settled; the remaining slope is true room cooling
        late_rate = (a["Ts_settle"] - T_sensed) / (t - a["t_settle"])  # K/s
        true_drop = max(0.0, late_rate) * self.anchor_settle_s
        bias_est = (a["Ts0"] - a["Ts_settle"]) - true_drop
        if a["u0"] >= 0.15 and bias_est > -0.2:  # identifiable, sane anchor
            k_obs = max(0.0, bias_est) / max(a["u0"], 0.15)
            self.k_hat += self.comp_alpha * (k_obs - self.k_hat)
            self.k_hat = min(max(self.k_hat, 0.0), self.comp_k_max)
        self.k_log.append((t, self.k_hat))
        self._anchor = None           # one update per closure


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
