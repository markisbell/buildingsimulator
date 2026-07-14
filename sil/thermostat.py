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
                       An actuator model (actuator.py) sits between firmware
                       and pin: mechanical play (0.1 mm), a true mechanical
                       zero the firmware does not know, and a motor-current
                       measurement (force through spring, seal contact and
                       friction, with noise and ADC quantization)
- adaptation run       on first activation (auto_adapt) the firmware drives
                       the valve closed, watches the current trace for the
                       seal-contact knee and the stall threshold, and takes
                       the stall position as its zero reference - exactly
                       like commercial eTRVs after mounting
- travel accounting    total valve travel and move count are recorded as
                       battery-consumption KPIs

The wrapped algorithm sees only what the real device firmware would see:
the corrupted, sampled temperature. `algorithm.step(t, T_sensed_K) -> [0..1]`.
Note the flow *characteristic* (sealing dead zone, steep rise, saturation)
lives in the FMU (plant hydraulics); this module models only the device.
"""

import numpy as np

from actuator import ValveActuator


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
                 dp_output=None,           # FMU output with valve dp (hydraulic force)
                 q_rad_nominal=4500.0,
                 sample_interval=300.0,
                 position_deadband=0.05,
                 sensor_bias_max=2.0,      # K above room at full radiator output
                 sensor_tau=600.0,         # s, lag of the bias (metal head heats slowly)
                 sensor_resolution=0.1,    # K
                 sensor_noise_std=0.05,    # K
                 auto_adapt=True,          # adaptation run on first activation
                 stall_ma=45.0,            # firmware stall-detection threshold
                 knee_delta_ma=8.0,        # firmware knee detection above baseline
                 actuator=None,            # ValveActuator (default one is created)
                 seed=0):
        self.temp_output = temp_output
        self.q_rad_output = q_rad_output
        self.dp_output = dp_output
        self.algorithm = algorithm
        self.q_rad_nominal = q_rad_nominal
        self.sample_interval = sample_interval
        self.position_deadband = position_deadband
        self.sensor_bias_max = sensor_bias_max
        self.sensor_tau = sensor_tau
        self.sensor_resolution = sensor_resolution
        self.sensor_noise_std = sensor_noise_std
        self.auto_adapt = auto_adapt
        self.stall_ma = stall_ma
        self.knee_delta_ma = knee_delta_ma
        self.actuator = actuator or ValveActuator(seed=seed + 1000)
        self._rng = np.random.default_rng(seed)

        self._bias = 0.0
        self._position = 0.0   # firmware's commanded opening (0..1)
        self._last_sample = None
        self._last_t = None
        self._adapt_until = None
        self.adaptation = None  # diagnostics of the last adaptation run

        # battery KPIs (move count; travel comes from the actuator)
        self.n_moves = 0
        # diagnostic log: (t, T_true, T_sensed)
        self.sensor_log = []

    @property
    def travel_mm(self):
        return self.actuator.travel_mm

    @property
    def travel(self):
        """Valve travel in full strokes (for kpi.battery_kpis)."""
        return self.actuator.travel_mm / self.actuator.stroke_mm

    def adaptation_run(self, t, dp_pa=0.0):
        """Drive closed, watch the motor current, take the stall position as
        the zero reference — the commissioning routine of commercial eTRVs."""
        act = self.actuator
        trace, duration = act.close_until_stall(stall_ma=self.stall_ma, dp_pa=dp_pa)
        currents = [i for _, i in trace]
        positions = [p for p, _ in trace]
        n_base = max(3, len(trace) // 4)
        baseline = float(np.median(currents[:n_base]))
        knee_mm = None
        run = 0
        for pos, i in trace:
            run = run + 1 if i > baseline + self.knee_delta_ma else 0
            if run >= 3:
                knee_mm = pos
                break
        act.zero_est_mm = positions[-1]  # firmware zero := stall position
        self._position = 0.0
        self._adapt_until = t + duration
        self.n_moves += 1
        self.adaptation = {
            "t": t,
            "duration_s": duration,
            "baseline_ma": baseline,
            "knee_mm": knee_mm,
            "stall_mm": positions[-1],
            "zero_error_mm": act.zero_est_mm - act.true_zero_mm,
            "seal_est_mm": (knee_mm - positions[-1]) if knee_mm else None,
            "trace": trace,
        }
        return self.adaptation

    def _sense(self, t, T_true, q_rad):
        # lagged bias toward the radiator-output-proportional target
        dt = 0.0 if self._last_t is None else t - self._last_t
        target = self.sensor_bias_max * max(0.0, q_rad) / self.q_rad_nominal
        if dt > 0.0:
            self._bias += (target - self._bias) * min(1.0, dt / self.sensor_tau)
        raw = T_true + self._bias + self._rng.normal(0.0, self.sensor_noise_std)
        return round(raw / self.sensor_resolution) * self.sensor_resolution

    def step(self, t, measurements):
        dp = measurements.get(self.dp_output, 0.0) if self.dp_output else 0.0
        T_sensed = self._sense(t, measurements[self.temp_output],
                               measurements[self.q_rad_output])
        self._last_t = t

        # commissioning: locate the mechanical zero before controlling
        if self.auto_adapt and self.adaptation is None:
            self.adaptation_run(t, dp_pa=dp)
        if self._adapt_until is not None:
            if t < self._adapt_until:
                return self.actuator.pin_fraction()  # motor still traveling
            self._adapt_until = None

        if self._last_sample is None or t - self._last_sample >= self.sample_interval:
            self._last_sample = t
            self.sensor_log.append((t, measurements[self.temp_output], T_sensed))
            command = self._shape_command(t, self.algorithm.step(t, T_sensed))
            # reposition only if worth the battery (or hitting an end stop)
            if self._worth_moving(t, command):
                self.n_moves += 1
                self._position = command
                return self.actuator.command_opening(command, dp_pa=dp)
        return self.actuator.pin_fraction()

    def _worth_moving(self, t, command):
        """Battery policy: is this reposition worth a motor move? Stock
        firmware: fixed deadband, end stops always honored. Strategies
        (sil/strategies.py) override this."""
        return (abs(command - self._position) >= self.position_deadband
                or (command in (0.0, 1.0) and command != self._position))

    def _shape_command(self, t, command):
        """Command-shaping hook between algorithm and battery policy —
        stock firmware passes through; coordination strategies
        (sil/strategies.py) override this."""
        return command
