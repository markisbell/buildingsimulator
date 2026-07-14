"""Two-point boiler control (1980s on/off burner), as SIL supervisory logic.

The burner logic lives in Python — like the thermostats, it is firmware in
the loop. It drives the plant through the TSupSet FMU input: when firing,
the ideal heater chases a high setpoint (power-limited by QMax and slowed by
the boiler water mass); when off, the setpoint drops below any water
temperature so the heater delivers zero and the loop cools naturally.

Result: the supply temperature saws around the heating-curve target with
the hysteresis band and minimum runtimes of the era — the dominant
oscillation source visible in real building measurements.
"""


class Schnellaufheizung:
    """Boost supply overtemperature after night setback (era-authentic
    Aufheizoptimierung: DIN 4702-8 era controllers raised the curve during
    a morning boost window).

    Supervisory TSupSet controller: follows the outdoor-reset curve and,
    inside a window after the schedule's day start, lifts the target by
    boost_dK (capped) until the worst occupied room has recovered to
    within deficit_off of its setpoint. The window bound keeps the boost
    from latching on chronic device undershoot (eTRV sensor bias).

    Use directly as the "TSupSet" controller on smooth plants, or pass as
    booster= to TwoPointBoiler on relay plants.
    """

    def __init__(self, curve_fn, room_setpoints, day_start_h,
                 boost_dK=12.0, t_sup_max=363.15, max_boost_h=3.0,
                 deficit_off=0.3):
        # curve_fn: t -> curve target (K)
        # room_setpoints: dict TRoom-output-name -> callable t -> K
        self.curve_fn = curve_fn
        self.room_setpoints = room_setpoints
        self.day_start_h = day_start_h
        self.dK = boost_dK
        self.cap = t_sup_max
        self.max_boost_h = max_boost_h
        self.off_th = deficit_off
        self.boost_hours = 0.0  # diagnostic: total boosted time
        self._last_t = None
        self.initial_output = curve_fn(0.0)

    def target(self, t, measurements):
        hour = (t % 86400.0) / 3600.0
        in_window = self.day_start_h <= hour < self.day_start_h + self.max_boost_h
        deficit = max(sp(t) - measurements[name]
                      for name, sp in self.room_setpoints.items())
        boosting = in_window and deficit > self.off_th
        if boosting and self._last_t is not None:
            self.boost_hours += (t - self._last_t) / 3600.0
        self._last_t = t
        base = self.curve_fn(t)
        return min(base + (self.dK if boosting else 0.0), self.cap)

    # drop-in harness controller (smooth plant: TSupSet follows directly)
    step = target


class TwoPointBoiler:
    def __init__(self, target_fn,
                 hysteresis=10.0,     # K, total band around the curve target
                 min_on=240.0,        # s, minimum burner runtime
                 min_off=240.0,       # s, anti-short-cycle pause
                 overdrive=3.0,       # K above upper band while firing
                 booster=None):       # optional Schnellaufheizung
        self.target_fn = target_fn
        self.booster = booster
        self.hys = hysteresis
        self.min_on = min_on
        self.min_off = min_off
        self.overdrive = overdrive
        self._on = True
        self._t_switch = None
        self.n_starts = 0
        self.initial_output = 343.15  # start warm (harness init value)

    def step(self, t, measurements):
        t_sup = measurements["TSup"]
        target = (self.booster.target(t, measurements) if self.booster
                  else self.target_fn(t))
        upper = target + self.hys / 2.0
        lower = target - self.hys / 2.0
        if self._t_switch is None:
            self._t_switch = t

        if self._on:
            if t_sup >= upper and t - self._t_switch >= self.min_on:
                self._on = False
                self._t_switch = t
        else:
            if t_sup <= lower and t - self._t_switch >= self.min_off:
                self._on = True
                self._t_switch = t
                self.n_starts += 1

        # setpoint for the heater: chase past the band when firing, else idle
        return (upper + self.overdrive) if self._on else 273.15 + 10.0
