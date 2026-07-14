"""Calibration study for the night-time zone thermal mass (see
docs/heatup-dynamics.md section 6: model free-cools ~2x faster than the
field corridor of -0.2..-0.4 K/h).

Pure-Python RC model of the 80s living room (S, mid floor), synchronized
whole-building free-cool (neighbor/hall terms vanish), radiator water/steel
discharge included as a decaying source.

Three results, in order:
1. A weakly-coupled dead-end "deep mass" third node CANNOT fix the night
   rate: across C_deep = 300-600 kJ/m2K and G_deep = 2-8 W/m2K the 8-h drop
   improves by < 0.6 K. The deep node only absorbs heat as fast as the mass
   node falls below it, and that differential stays < 1 K all night.
2. The night rate is set by the STRONGLY-COUPLED capacity: raising C_mass
   puts the tail into the field corridor (C_mass = 450 kJ/m2K -> hours-4-8
   rate -0.28 K/h). Physically defensible bottom-up: two half-thickness
   concrete slabs (~430 kJ/m2K) + masonry wall shares are all within the
   ~10-14 cm that heat penetrates in 8 h; the ISO 13790 class values are
   monthly-method conventions at the low end for this construction.
3. More strongly-coupled mass alone would also slow the morning recovery
   (3 K never completes at 1.5 kW net). With boost power >= 2.3 kW the
   recovery time (~1.4 h) becomes nearly independent of C_mass — the
   field-observed asymmetry (fast heat-up, slow cooldown) is a POWER
   phenomenon, which the era solved with Schnellaufheizung (boost supply
   overtemperature after setback). Linear RC networks alone cannot produce
   the asymmetry: their time constants are the same in both directions.

  python sil/calibrate_deep_mass.py     (numpy only)
"""
import numpy as np

A = 24.0                      # m2, living room
C_AIR = 40e3 * A              # J/K
G_INT = 15.5 * A              # W/K
G_WIN = 26.1                  # W/K, air -> outdoor
G_WALL = 15.3                 # W/K, mass -> outdoor (mid floor)
T_OUT = -5.0
E_RAD = 3.4e6                 # J, radiator water/steel discharge after closure
TAU_RAD = 3600.0              # s
DT = 60.0


def simulate_freecool(c_mass, c_deep=0.0, g_deep=0.0, hours=12.0):
    Ta, Tm, Td = 20.0, 19.6, 19.6
    out = np.empty((int(hours * 3600 / DT), 2))
    for i in range(len(out)):
        t = i * DT
        q = (E_RAD / TAU_RAD) * np.exp(-t / TAU_RAD)
        dTa = (G_INT * (Tm - Ta) + G_WIN * (T_OUT - Ta) + 0.65 * q) / C_AIR
        dTm = (G_INT * (Ta - Tm) + G_WALL * (T_OUT - Tm)
               + (g_deep * (Td - Tm) if c_deep else 0.0) + 0.35 * q) / c_mass
        dTd = g_deep * (Tm - Td) / c_deep if c_deep else 0.0
        Ta, Tm, Td = Ta + dTa * DT, Tm + dTm * DT, Td + dTd * DT
        out[i] = (t / 3600.0, Ta)
    return out


def simulate_heatup(c_mass, q_in, hours=10.0):
    """Recovery from a setback state at constant net radiator power;
    time until the air node has climbed 3 K."""
    Ta, Tm = 17.0, 18.0
    for i in range(int(hours * 3600 / DT)):
        dTa = (G_INT * (Tm - Ta) + G_WIN * (T_OUT - Ta) + 0.65 * q_in) / C_AIR
        dTm = (G_INT * (Ta - Tm) + G_WALL * (T_OUT - Tm) + 0.35 * q_in) / c_mass
        Ta, Tm = Ta + dTa * DT, Tm + dTm * DT
        if Ta >= 20.0:
            return i * DT / 3600.0
    return np.inf


def metrics(tr):
    t, T = tr[:, 0], tr[:, 1]

    def rate(h0, h1):
        m = (t >= h0) & (t <= h1)
        return np.polyfit(t[m], T[m], 1)[0]

    return rate(0, 1), rate(4, 8), T[0] - T[np.searchsorted(t, 8.0)]


CM0 = 260e3 * A
r1, r48, d8 = metrics(simulate_freecool(CM0))
print(f"reference 2R2C (C_mass=260): h1 {r1:+.2f} | h4-8 {r48:+.2f} K/h | "
      f"8h drop {d8:.2f} K | heatup 3K at 1.5 kW: "
      f"{simulate_heatup(CM0, 1500):.2f} h")

print("\n1) dead-end deep node (null result): 8-h drop stays ~4.0-4.4 K")
for cd in (300, 600):
    for gd in (2.0, 8.0):
        _, r, d = metrics(simulate_freecool(CM0, cd * 1e3 * A, gd * A))
        print(f"   C_deep={cd} kJ/m2K, G_deep={gd:g} W/m2K: "
              f"tail {r:+.2f} K/h, 8h drop {d:.2f} K")

print("\n2) strongly-coupled C_mass sweep (target tail -0.2..-0.4 K/h):")
for cm in (260, 370, 450, 500, 550):
    r1, r48, d8 = metrics(simulate_freecool(cm * 1e3 * A))
    print(f"   C_mass={cm}: h1 {r1:+.2f} | tail {r48:+.2f} K/h | "
          f"8h drop {d8:.2f} K")

print("\n3) recovery time (3 K) vs boost power — the up/down asymmetry is a"
      "\n   power phenomenon (era: Schnellaufheizung):")
print("   C_mass    1.7 kW   2.0 kW   2.3 kW   2.6 kW   2.9 kW")
for cm in (260, 450, 500):
    row = [simulate_heatup(cm * 1e3 * A, q) for q in
           (1700, 2000, 2300, 2600, 2900)]
    print(f"   {cm:5d}   " + "  ".join(f"{v:6.2f} h" if np.isfinite(v)
                                       else "   inf " for v in row))

print("\nchosen: C_mass = 450 kJ/(m2K)*A_floor (tail -0.28 K/h, corridor"
      "\n-0.2..-0.4) + Schnellaufheizung boost so recovery stays ~1.5 h.")
