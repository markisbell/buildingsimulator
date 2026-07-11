"""Solar gains through windows, per apartment facade.

Uses pvlib for sun position, clear-sky irradiance (Ineichen) and the
transposition onto vertical facades. A cloudiness factor scales the beam
component (synthetic weather, consistent with the synthetic TOut sinusoid);
measured weather files (EPW/DWD TRY) can replace the clear-sky model later
via pvlib.iotools without changing the interface.

Gain per apartment: POA irradiance on its facade x window area x g-value
x frame/shading factor.
"""

import numpy as np
import pandas as pd
import pvlib

# Karlsruhe
LATITUDE = 49.0069
LONGITUDE = 8.4037
ALTITUDE = 115.0
TZ = "Etc/GMT-1"


class SolarGainModel:
    """Precomputes facade gain time series for a simulation horizon.

    orientations: dict apartment index (1-based) -> facade azimuth in degrees
                  (180 = south, 0 = north, 90 = east, 270 = west)
    """

    def __init__(self, orientations,
                 start="2026-01-12",
                 days=8,
                 window_area_m2=8.0,
                 g_value=0.6,
                 frame_shading=0.7,
                 cloudiness=0.4,
                 resolution_s=300):
        self.orientations = orientations
        times = pd.date_range(start=start, periods=days * 86400 // resolution_s,
                              freq=f"{resolution_s}s", tz=TZ)
        self._t = np.arange(len(times)) * float(resolution_s)

        loc = pvlib.location.Location(LATITUDE, LONGITUDE, tz=TZ,
                                      altitude=ALTITUDE)
        solpos = loc.get_solarposition(times)
        clearsky = loc.get_clearsky(times, model="ineichen")
        # cloudiness scales beam strongly, diffuse mildly
        dni = clearsky["dni"] * (1.0 - cloudiness)
        dhi = clearsky["dhi"] * (1.0 - 0.3 * cloudiness)
        ghi = dni * np.cos(np.radians(solpos["apparent_zenith"])).clip(lower=0) + dhi

        factor = window_area_m2 * g_value * frame_shading
        self._gains = {}
        for i, azimuth in orientations.items():
            poa = pvlib.irradiance.get_total_irradiance(
                surface_tilt=90.0, surface_azimuth=azimuth,
                solar_zenith=solpos["apparent_zenith"],
                solar_azimuth=solpos["azimuth"],
                dni=dni, ghi=ghi, dhi=dhi)
            self._gains[i] = (poa["poa_global"].fillna(0.0).clip(lower=0.0)
                              * factor).to_numpy()

    def gains(self, t: float) -> dict:
        """FMU input dict {'QGain[i]': W} at simulation time t (s from start)."""
        return {f"QGain[{i}]": float(np.interp(t, self._t, g))
                for i, g in self._gains.items()}

    def peak_w(self, i: int) -> float:
        return float(self._gains[i].max())
