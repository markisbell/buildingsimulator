"""Electronic radiator thermostat (eTRV) device model.

Wraps any control algorithm with the constraints of a real battery-powered
valve thermostat (Danfoss Ally / eQ-3 / Homematic class devices):

- sampled control      the algorithm runs every `sample_interval` seconds,
                       not continuously (radio + battery budget)
- valve-mounted sensor the temperature sensor sits on the valve body next to
                       the radiator: it reads high when the radiator is hot.
                       Modeled as a first-order-lagged bias proportional to
                       radiator output, plus quantization and noise
- actuation deadband   the motor only repositions when the commanded change
                       exceeds `position_deadband` (every move costs battery)
- valve mechanics      German M30x1.5 TRV inserts have a 1.5 mm pin stroke.
                       Between the motor command and the actual pin position
                       sits mechanical play (spindle backlash + elastomer,
                       default 0.1 mm): the pin only follows once the play is
                       taken up, so opening and closing curves differ. An
                       optional calibration offset models a device that has
                       mislocated the closing point
- travel accounting    total valve travel and move count are recorded as
                       battery-consumption KPIs

The wrapped algorithm sees only what the real device firmware would see:
the corrupted, sampled temperature. `algorithm.step(t, T_sensed_K) -> [0..1]`.
Note the flow *characteristic* (sealing dead zone, steep rise, saturation)
lives in the FMU (plant hydraulics); this module models only the device.
"""

import numpy as np


class SampledPI:
    """PI algorithm as it would run in thermostat firmware (sampled)."""

    def __init__(self, setpoint, kp=0.4, ti=1800.0):
        self.setpoint = setpoint if callable(setpoint) else (lambda t, sp=setpoint: sp)
        self.kp = kp
        self.ti = ti
        self._integral = 0.0
        self._last_t = None

    def step(self, t, T_sensed):
        dt = 0.0 if self._last_t is None else t - self._last_t
        self._last_t = t
        e = self.setpoint(t) - T_sensed
        self._integral += e * dt
        u = self.kp * (e + self._integral / self.ti)
        if u > 1.0:
            self._integral -= e * dt
            u = 1.0
        elif u < 0.0:
            self._integral -= e * dt
            u = 0.0
        return u


class ElectronicThermostat:
    """Realistic eTRV wrapper, drop-in compatible with the SIL harness
    (step(t, measurements) -> valve position).

    temp_output / q_rad_output: FMU output names for the zone temperature
    and the radiator heat output of this apartment.
    """

    def __init__(self, temp_output, q_rad_output, algorithm,
                 q_rad_nominal=4500.0,
                 sample_interval=300.0,
                 position_deadband=0.05,
                 sensor_bias_max=2.0,      # K above room at full radiator output
                 sensor_tau=600.0,         # s, lag of the bias (metal head heats slowly)
                 sensor_resolution=0.1,    # K
                 sensor_noise_std=0.05,    # K
                 stroke_mm=1.5,            # pin stroke of German M30x1.5 inserts
                 backlash_mm=0.10,         # mechanical play motor <-> pin
                 calibration_offset_mm=0.0,  # error in the device's closing-point estimate
                 seed=0):
        self.temp_output = temp_output
        self.q_rad_output = q_rad_output
        self.algorithm = algorithm
        self.q_rad_nominal = q_rad_nominal
        self.sample_interval = sample_interval
        self.position_deadband = position_deadband
        self.sensor_bias_max = sensor_bias_max
        self.sensor_tau = sensor_tau
        self.sensor_resolution = sensor_resolution
        self.sensor_noise_std = sensor_noise_std
        self.stroke_mm = stroke_mm
        self._play = backlash_mm / stroke_mm       # normalized play width
        self._offset = calibration_offset_mm / stroke_mm
        self._rng = np.random.default_rng(seed)

        self._bias = 0.0
        self._position = 0.0   # firmware's commanded motor position
        self._pin = 0.0        # actual valve pin position (after play)
        self._last_sample = None
        self._last_t = None

        # battery KPIs
        self.travel = 0.0
        self.n_moves = 0
        # diagnostic log: (t, T_true, T_sensed)
        self.sensor_log = []

    @property
    def travel_mm(self):
        return self.travel * self.stroke_mm

    def _pin_position(self):
        """Mechanical play: the pin follows the motor only once the play
        is taken up, so opening and closing paths differ (hysteresis)."""
        target = self._position + self._offset
        half = self._play / 2.0
        if target - self._pin > half:
            self._pin = target - half
        elif self._pin - target > half:
            self._pin = target + half
        return min(1.0, max(0.0, self._pin))

    def _sense(self, t, T_true, q_rad):
        # lagged bias toward the radiator-output-proportional target
        dt = 0.0 if self._last_t is None else t - self._last_t
        target = self.sensor_bias_max * max(0.0, q_rad) / self.q_rad_nominal
        if dt > 0.0:
            self._bias += (target - self._bias) * min(1.0, dt / self.sensor_tau)
        raw = T_true + self._bias + self._rng.normal(0.0, self.sensor_noise_std)
        return round(raw / self.sensor_resolution) * self.sensor_resolution

    def step(self, t, measurements):
        T_sensed = self._sense(t, measurements[self.temp_output],
                               measurements[self.q_rad_output])
        self._last_t = t

        if self._last_sample is None or t - self._last_sample >= self.sample_interval:
            self._last_sample = t
            self.sensor_log.append((t, measurements[self.temp_output], T_sensed))
            command = self.algorithm.step(t, T_sensed)
            # reposition only if worth the battery (or hitting an end stop)
            if (abs(command - self._position) >= self.position_deadband
                    or (command in (0.0, 1.0) and command != self._position)):
                self.travel += abs(command - self._position)
                self.n_moves += 1
                self._position = command
        return self._pin_position()
