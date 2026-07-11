"""Thermostat controllers for the SIL loop.

Every controller implements  step(t, measurements) -> valve position [0..1].
This is the slot where adaptive / distributed control strategies (and later
ports of real electronic-thermostat firmware logic) plug in.
"""


class PIThermostat:
    """Baseline PI room thermostat acting on a radiator valve.

    Mirrors a simple electronic TRV: samples the room temperature, computes a
    valve position. Setpoint may be a constant or a callable t -> setpoint (K).
    """

    def __init__(self, temp_output: str, setpoint, kp=0.4, ti=1800.0, dt=60.0):
        self.temp_output = temp_output
        self.setpoint = setpoint if callable(setpoint) else (lambda t, sp=setpoint: sp)
        self.kp = kp
        self.ti = ti
        self.dt = dt
        self._integral = 0.0

    def step(self, t, measurements):
        e = self.setpoint(t) - measurements[self.temp_output]
        self._integral += e * self.dt
        u = self.kp * (e + self._integral / self.ti)
        # clamp with simple anti-windup
        if u > 1.0:
            self._integral -= e * self.dt
            u = 1.0
        elif u < 0.0:
            self._integral -= e * self.dt
            u = 0.0
        return u


class ScriptedValve:
    """Open-loop valve schedule, e.g. for hydraulic-coupling experiments.

    schedule: list of (start_time_s, valve_position) pairs, sorted ascending.
    """

    def __init__(self, schedule):
        self.schedule = schedule

    def step(self, t, measurements):
        pos = self.schedule[0][1]
        for start, value in self.schedule:
            if t >= start:
                pos = value
        return pos
