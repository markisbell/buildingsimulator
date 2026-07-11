"""KPIs for comparing thermostat control strategies.

Conventions follow BOPTEST where applicable: discomfort is the time integral
of the temperature deviation below the active setpoint, in K*h; energy is
boiler thermal energy in kWh. Battery KPIs come from the thermostat objects.
"""

C2K = 273.15


def _after_warmup(df, t_start):
    """Rows after the warm-up day; short runs fall back to the full series."""
    d = df[df["time"] >= t_start]
    return d if len(d) >= 2 else df


def discomfort_kh(df, temp_col, setpoint_fn, t_start=86400.0):
    """Integral of (setpoint - T)+ in K*h for t >= t_start (skip warm-up day)."""
    d = _after_warmup(df, t_start)
    if len(d) < 2:
        return 0.0
    dt_h = (d["time"].iloc[1] - d["time"].iloc[0]) / 3600.0
    dev = [max(0.0, setpoint_fn(t) - T)
           for t, T in zip(d["time"], d[temp_col])]
    return sum(dev) * dt_h


def overheat_kh(df, temp_col, setpoint_fn, tol=1.0, t_start=86400.0):
    """Integral of (T - setpoint - tol)+ in K*h — overheating, e.g. from
    solar gains the controller fails to reject."""
    d = _after_warmup(df, t_start)
    if len(d) < 2:
        return 0.0
    dt_h = (d["time"].iloc[1] - d["time"].iloc[0]) / 3600.0
    dev = [max(0.0, T - setpoint_fn(t) - tol)
           for t, T in zip(d["time"], d[temp_col])]
    return sum(dev) * dt_h


def boiler_energy_kwh(df, t_start=86400.0):
    d = _after_warmup(df, t_start)
    hours = (d["time"].iloc[-1] - d["time"].iloc[0]) / 3600.0
    return d["QBoi"].mean() * hours / 1000.0


def pump_energy_kwh(df, t_start=86400.0):
    d = _after_warmup(df, t_start)
    hours = (d["time"].iloc[-1] - d["time"].iloc[0]) / 3600.0
    return d["PPum"].mean() * hours / 1000.0


def battery_kpis(thermostats):
    """Total valve travel (full strokes) and move count across all devices."""
    travel = sum(th.travel for th in thermostats)
    moves = sum(th.n_moves for th in thermostats)
    return travel, moves
