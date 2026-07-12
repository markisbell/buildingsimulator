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


class TwoPointBoiler:
    def __init__(self, target_fn,
                 hysteresis=10.0,     # K, total band around the curve target
                 min_on=240.0,        # s, minimum burner runtime
                 min_off=240.0,       # s, anti-short-cycle pause
                 overdrive=3.0):      # K above upper band while firing
        self.target_fn = target_fn
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
        target = self.target_fn(t)
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
