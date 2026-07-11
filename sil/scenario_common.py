"""Shared scenario definitions: weather, heating curve, occupancy schedules."""

import math

C2K = 273.15
DAY = 86400.0


def heating_curve(t_out_k: float) -> float:
    """Outdoor-reset supply setpoint (65 degC @ -10, 35 degC @ +15)."""
    t_out = t_out_k - C2K
    t_sup = 35.0 + (65.0 - 35.0) * (15.0 - t_out) / 25.0
    return min(max(t_sup, 35.0), 65.0) + C2K


def winter_weather(t: float) -> float:
    """Sinusoidal outdoor temperature: -2 degC mean, +/-4 K daily swing."""
    return C2K - 2.0 + 4.0 * math.sin(2.0 * math.pi * (t - 10.0 * 3600.0) / DAY)


def winter_exogenous(t: float) -> dict:
    t_out = winter_weather(t)
    return {"TOut": t_out, "TSupSet": heating_curve(t_out)}


def day_night_setpoint(day_sp, night_sp, day_start_h, day_end_h):
    def sp(t):
        hour = (t % DAY) / 3600.0
        return (day_sp if day_start_h <= hour < day_end_h else night_sp) + C2K
    return sp


# occupancy schedules per apartment; None = vacant
# (day setpoint degC, night setpoint degC, day start h, day end h)
SCHEDULES = {
    1: (21.0, 17.0, 6, 22),   # family, long day
    2: (21.0, 16.0, 8, 20),   # office workers
    3: None,                  # vacant
    4: (22.0, 18.0, 7, 23),   # warm preference
    5: (21.0, 17.0, 6, 21),
    6: (20.0, 16.0, 9, 18),   # away a lot
}


def default_orientations(n_apt):
    """Odd apartments face south (180 deg), even ones north (0 deg)."""
    return {i: (180.0 if i % 2 == 1 else 0.0) for i in range(1, n_apt + 1)}


def make_winter_scenario(n_apt, cloudiness=0.4, days=8):
    """Winter scenario with synthetic weather AND facade solar gains.
    Returns (exogenous_fn, solar_model)."""
    from solar import SolarGainModel
    sol = SolarGainModel(default_orientations(n_apt), days=days,
                         cloudiness=cloudiness)

    def exogenous(t):
        t_out = winter_weather(t)
        return {"TOut": t_out, "TSupSet": heating_curve(t_out), **sol.gains(t)}

    return exogenous, sol
