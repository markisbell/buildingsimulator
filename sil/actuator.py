"""eTRV valve actuator: DC motor + gearbox + spindle driving the TRV pin.

Simulates what the firmware cannot directly see (true pin position, true
mechanical zero, pin force) and what it can measure (motor position in its
own coordinates, motor current with noise and ADC quantization).

Coordinates
-----------
motor_mm   spindle position in motor/encoder coordinates (firmware-visible)
pin        true pin lift as fraction of stroke: 0 = hard stop (seal fully
           compressed), matching the FMU valve table coordinate
true_zero  motor_mm coordinate of the hard stop — UNKNOWN to firmware;
           the adaptation run estimates it from the current signature

Pin force model (quasi-static, closing direction positive)
-----------------------------------------------------------
- return spring: preload + rate * compression (insert spring pushes pin out)
- seal contact: steep elastomer stiffness once the plug enters the seal zone
  (pin below seal_zone_mm); this is what the current knee detects
- Coulomb friction
- hydraulic force: dp across valve * seat area — order 0.1-1 N, far below
  the seal force, i.e. realistically invisible in the current signal
"""

import numpy as np


class ValveActuator:

    def __init__(self,
                 stroke_mm=1.5,
                 backlash_mm=0.10,
                 seal_zone_mm=0.09,        # matches the FMU dead zone (6 % of stroke)
                 spring_preload_n=30.0,
                 spring_rate_n_mm=15.0,
                 seal_stiffness_n_mm=1500.0,
                 friction_n=3.0,
                 seat_diameter_mm=5.0,
                 current_base_ma=8.0,      # electronics + no-load gear losses
                 ma_per_n=0.28,            # torque->current through gear and spindle
                 current_noise_ma=0.8,
                 adc_resolution_ma=0.5,
                 speed_mm_s=0.025,         # full stroke in 60 s
                 initial_zero_error_mm=0.3,
                 seed=0):
        self.stroke_mm = stroke_mm
        self.backlash_mm = backlash_mm
        self.seal_zone_mm = seal_zone_mm
        self.spring_preload_n = spring_preload_n
        self.spring_rate_n_mm = spring_rate_n_mm
        self.seal_stiffness_n_mm = seal_stiffness_n_mm
        self.friction_n = friction_n
        self.seat_area_m2 = np.pi * (seat_diameter_mm / 2 * 1e-3) ** 2
        self.current_base_ma = current_base_ma
        self.ma_per_n = ma_per_n
        self.current_noise_ma = current_noise_ma
        self.adc_resolution_ma = adc_resolution_ma
        self.speed_mm_s = speed_mm_s
        self._rng = np.random.default_rng(seed)

        # true mechanical zero in motor coordinates; firmware starts with an
        # estimate that is wrong by initial_zero_error_mm (mounting tolerance)
        self.true_zero_mm = 5.0 + self._rng.uniform(-0.2, 0.2)
        self.zero_est_mm = self.true_zero_mm + initial_zero_error_mm

        self._motor_mm = self.zero_est_mm + stroke_mm  # starts "fully open"
        self._pin_contact_mm = self._motor_mm          # play contact point
        self.travel_mm = 0.0

    # ------------------------------------------------------------------ #
    # true mechanics (not firmware-visible)
    # ------------------------------------------------------------------ #
    def _pin_mm(self):
        """True pin lift above hard stop, from the play contact point."""
        return min(max(self._pin_contact_mm - self.true_zero_mm, 0.0),
                   self.stroke_mm)

    def pin_fraction(self):
        """True pin lift 0..1 — the FMU valve-table input."""
        return self._pin_mm() / self.stroke_mm

    def _move_motor(self, target_mm):
        """Move spindle, taking up mechanical play before the pin follows."""
        delta = target_mm - self._motor_mm
        self.travel_mm += abs(delta)
        self._motor_mm = target_mm
        if self._motor_mm < self._pin_contact_mm - self.backlash_mm:
            self._pin_contact_mm = self._motor_mm + self.backlash_mm
        elif self._motor_mm > self._pin_contact_mm:
            self._pin_contact_mm = self._motor_mm

    def pin_force_n(self, closing, dp_pa=0.0):
        pin = self._pin_mm()
        f = self.spring_preload_n + self.spring_rate_n_mm * (self.stroke_mm - pin)
        if pin < self.seal_zone_mm:
            f += self.seal_stiffness_n_mm * (self.seal_zone_mm - pin)
        f += self.friction_n if closing else -self.friction_n
        f += dp_pa * self.seat_area_m2  # 10 kPa -> ~0.2 N: negligible vs seal
        return max(f, 0.0)

    # ------------------------------------------------------------------ #
    # firmware-visible interface
    # ------------------------------------------------------------------ #
    def measure_current_ma(self, closing, dp_pa=0.0):
        i = self.current_base_ma + self.ma_per_n * self.pin_force_n(closing, dp_pa)
        i += self._rng.normal(0.0, self.current_noise_ma)
        return round(i / self.adc_resolution_ma) * self.adc_resolution_ma

    def command_opening(self, fraction, dp_pa=0.0):
        """Move to an opening (0..1) in FIRMWARE coordinates, i.e. relative
        to the estimated zero. Returns the true pin fraction reached."""
        target = self.zero_est_mm + fraction * self.stroke_mm
        self._move_motor(target)
        return self.pin_fraction()

    def close_until_stall(self, stall_ma=45.0, step_mm=0.01, dp_pa=0.0):
        """Adaptation sweep: drive closing in encoder steps, record the
        current trace, stop at the stall threshold. Returns
        (trace, duration_s); trace rows are (motor_mm, current_mA)."""
        trace = []
        start = self._motor_mm
        # sweep at most one stroke past the estimated zero (safety limit)
        limit = self.zero_est_mm - self.stroke_mm
        over = 0
        while self._motor_mm > limit:
            self._move_motor(self._motor_mm - step_mm)
            i = self.measure_current_ma(closing=True, dp_pa=dp_pa)
            trace.append((self._motor_mm, i))
            over = over + 1 if i >= stall_ma else 0
            if over >= 2:
                break
        return trace, abs(self._motor_mm - start) / self.speed_mm_s
