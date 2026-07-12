"""Stochastic internal gains and window-opening events per room.

Precomputed, seeded profiles (reproducible experiments) for the Building80s
room pattern [living, bedroom, kitchen, bath] x 2 apartments per floor:

- living: evening occupancy block with smoothed noise
- bedroom: night occupancy (sleeping persons)
- kitchen: cooking bursts around noon and early evening
- bath: short morning/evening usage bursts
- all rooms: low-level appliance noise and 1-2 window-opening events per
  day (cold-air pulse modeled as a negative gain)
"""

import numpy as np

RES = 60.0  # s
DAY = 86400.0


def _smooth(x, n=15):
    kernel = np.ones(n) / n
    return np.convolve(x, kernel, mode="same")


class InternalGains:
    def __init__(self, n_zones, days=3, seed=1):
        rng = np.random.default_rng(seed)
        steps = int(days * DAY / RES)
        self._t = np.arange(steps) * RES
        hour = (self._t % DAY) / 3600.0
        self._g = np.zeros((n_zones + 1, steps))

        for k in range(1, n_zones + 1):
            room = (k - 1) % 4  # 0 living, 1 bed, 2 kitchen, 3 bath
            g = np.zeros(steps)
            if room == 0:
                g += np.where((hour >= 17) | (hour < 0), 0.0, 0.0)
                g += np.where((hour >= 17) & (hour < 23),
                              150 + _smooth(rng.normal(0, 60, steps)), 0.0)
                g += np.where((hour >= 7) & (hour < 17),
                              30 + _smooth(rng.normal(0, 15, steps)), 0.0)
            elif room == 1:
                g += np.where((hour >= 22) | (hour < 7), 120.0, 10.0)
            elif room == 2:
                for d in range(days):
                    for center, power in ((12.0, 600.0), (18.5, 700.0)):
                        start = d * DAY + (center + rng.normal(0, 0.5)) * 3600
                        dur = rng.uniform(15, 40) * 60
                        mask = (self._t >= start) & (self._t < start + dur)
                        g[mask] += power
                g += 20
            else:
                for d in range(days):
                    for center in (6.8, 21.3):
                        start = d * DAY + (center + rng.normal(0, 0.4)) * 3600
                        dur = rng.uniform(10, 20) * 60
                        mask = (self._t >= start) & (self._t < start + dur)
                        g[mask] += 500
            # appliance noise
            g += np.abs(_smooth(rng.normal(15, 10, steps)))
            # window opening: 1-2 events/day, cold-air pulse
            for d in range(days):
                for _ in range(rng.integers(1, 3)):
                    start = d * DAY + rng.uniform(6, 22) * 3600
                    dur = rng.uniform(5, 12) * 60
                    mask = (self._t >= start) & (self._t < start + dur)
                    g[mask] -= rng.uniform(300, 600)
            self._g[k] = g

    def gains(self, t):
        idx = min(int(t / RES), self._g.shape[1] - 1)
        return {k: float(self._g[k, idx]) for k in range(1, self._g.shape[0])}
