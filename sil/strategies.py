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
