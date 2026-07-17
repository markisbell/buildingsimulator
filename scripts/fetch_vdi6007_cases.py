"""Extract VDI 6007-1 test cases 1-7 from the open-source AixLib
implementation (RWTH-EBC/AixLib, BSD-3) into data/vdi6007/cases.json.

Per case: the guideline's lumped VDI-network parameters, the excitation
tables (gains / outdoor temperature / window solar / heater setpoint), the
embedded reference trajectories (hourly means, days 1/10/60), and the
parameters of OUR 2R2C zone derived by the documented network reduction:

  1. Build the VDI resistive network: air A, interior surface I, exterior
     surface E (massless), storage nodes CI/CE, outdoor O. Edges:
     A-I hConInt*AInt, A-E hConExt*AExt, I-E radiative star (series of
     hRad*AInt, hRad*AExt), I-CI 1/RInt, E-CE 1/RExt,
     CE-O 1/(RExtRem + 1/(hConOut*AExt)).
  2. Kron-eliminate the massless surface nodes exactly ->
     G_int = g(A,CI) + g(A,CE)  (air <-> storage coupling; the star path
     air->I->E->CE is thereby included, not dropped).
  3. Lump CI + CE -> C_mass (the 2-state -> 1-storage-state reduction).
  4. Preserve the exact steady-state air->out transmission G_ss (from
     eliminating ALL internal nodes): G_wall = 1/(1/G_ss - 1/G_int).

The window in TC5 transmits solar only (AWin=0): no G_win path in TC1-7.
"""

import json
import re
import urllib.request
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "data" / "vdi6007"
OUT.mkdir(parents=True, exist_ok=True)
RAW = ("https://raw.githubusercontent.com/RWTH-EBC/AixLib/main/AixLib/"
       "ThermalZones/ReducedOrder/Validation/VDI6007/TestCase{n}.mo")
H_CON_OUT = 25.0  # W/(m2 K), outdoor film in the test rigs (hConWall=25*AExt)

# which excitation goes where (verified against each TestCase's connects)
WIRING = {
    1: {"intGai": [("conv", 1)]},
    2: {"intGai": [("rad", 1)]},
    3: {"intGai": [("conv", 1)]},
    4: {"intGai": [("rad", 1)]},
    5: {"intGai": [("rad", 1), ("conv", 2), ("conv", 3)],
        "outdoor": True, "solar": True},
    6: {"intGai": [("rad", 1)], "heater": 2.0e4},   # ideal (stiff PI)
    7: {"intGai": [("rad", 1)], "heater": 500.0},   # power-capped
}
REFERENCE_IS_POWER = {6, 7}


def parse_scalar(src, key):
    m = re.search(rf"\b{key}\s*=\s*\{{?([-\d.eE]+)\}}?", src)
    return float(m.group(1)) if m else None


def kron_reduce(lap, keep):
    """Exact elimination of the nodes not in `keep` from a Laplacian."""
    drop = [i for i in range(lap.shape[0]) if i not in keep]
    a = lap[np.ix_(keep, keep)]
    b = lap[np.ix_(keep, drop)]
    d = lap[np.ix_(drop, drop)]
    return a - b @ np.linalg.solve(d, b.T)


def laplacian(edges, n):
    lap = np.zeros((n, n))
    for i, j, g in edges:
        lap[i, i] += g
        lap[j, j] += g
        lap[i, j] -= g
        lap[j, i] -= g
    return lap


def map_params(p):
    """VDI two-element network -> our 2R2C zone (see module docstring)."""
    A, I, E, CI, CE, O = range(6)
    star = 1.0 / (1.0 / (p["hRad"] * p["AInt"]) + 1.0 / (p["hRad"] * p["AExt"]))
    edges = [
        (A, I, p["hConInt"] * p["AInt"]),
        (A, E, p["hConExt"] * p["AExt"]),
        (I, E, star),
        (I, CI, 1.0 / p["RInt"]),
        (E, CE, 1.0 / p["RExt"]),
        (CE, O, 1.0 / (p["RExtRem"] + 1.0 / (H_CON_OUT * p["AExt"]))),
    ]
    lap = laplacian(edges, 6)
    red = kron_reduce(lap, [A, CI, CE, O])       # eliminate surfaces I, E
    g_int = -red[0, 1] - red[0, 2]               # air <-> both storages
    ss = kron_reduce(lap, [A, O])                # everything internal out
    g_ss = -ss[0, 1]                             # exact steady transmission
    g_wall = 1.0 / (1.0 / g_ss - 1.0 / g_int)
    return {"C_mass": round(p["CInt"] + p["CExt"], 1),
            "G_int": round(g_int, 3), "G_wall": round(g_wall, 3),
            "G_win": 0.0, "G_ss_exact": round(g_ss, 3),
            "T_start": p["T_start"]}


def parse_table(src, name):
    # confine the search to the component's own block: everything between
    # `name(` and its trailing `annotation (Placement` — a global non-greedy
    # search would steal the NEXT component's offset (e.g. the reference
    # table's 273.15 K leaking into the gain tables)
    start = src.find(f"{name}(")
    if start < 0:
        return None
    block = src[start:src.index("annotation", start)]
    m = re.search(r"table=\[(.*?)\]", block, re.S)
    if not m:
        return None
    rows = [[float(x) for x in row.split(",")]
            for row in m.group(1).replace("\n", " ").split(";") if row.strip()]
    off = re.search(r"offset=\{([-\d.eE]+)\}", block)
    return {"rows": rows, "offset": float(off.group(1)) if off else 0.0}


def main():
    cases = {}
    for n in range(1, 8):
        src = urllib.request.urlopen(RAW.format(n=n), timeout=60).read().decode()
        zone = re.search(r"RC\.TwoElements\s+thermalZoneTwoElements\((.*?)\"Thermal zone\"",
                         src, re.S).group(1)
        p = {k: parse_scalar(zone, k) for k in
             ("hConExt", "hConInt", "hRad", "RExt", "RExtRem", "CExt",
              "RInt", "CInt", "AExt", "AInt", "T_start", "gWin",
              "ratioWinConRad")}
        atrans = parse_scalar(zone, "ATransparent")

        mapped = map_params(p)

        thr = float(re.search(r"threShold=([\d.]+)", src).group(1))
        case = {
            "vdi_params": p,
            "mapped": mapped,
            "wiring": {k: v for k, v in WIRING[n].items() if k != "intGai"},
            "gains_map": WIRING[n]["intGai"],
            "reference_is_power": n in REFERENCE_IS_POWER,
            "threshold": thr,
            "intGai": parse_table(src, "intGai"),
            "reference": parse_table(src, "reference"),
        }
        if WIRING[n].get("outdoor"):
            case["outdoorTemp"] = parse_table(src, "outdoorTemp")
        if WIRING[n].get("solar"):
            case["solarWindow"] = parse_table(src, "tableSolRadWindow")
            case["A_transparent"] = atrans
            gb = re.search(r"g_sunblind\(k=([\d.]+)\)", src)
            th = re.search(r"greaterThreshold1?\(\s*threshold=([\d.]+)", src)
            if gb and th:
                case["sunblind"] = {"g": float(gb.group(1)),
                                    "threshold": float(th.group(1))}
        if "heater" in WIRING[n]:
            case["setTemp"] = parse_table(src, "setTemp")
            case["heaterQ"] = WIRING[n]["heater"]
        cases[str(n)] = case
        ref_n = len(case["reference"]["rows"])
        print(f"TC{n}: G_int={mapped['G_int']:.1f} "
              f"G_wall={mapped['G_wall']:.2f} "
              f"(G_ss={mapped['G_ss_exact']:.2f}) "
              f"C_mass={mapped['C_mass']/1e6:.2f}e6, "
              f"{ref_n} reference points, threshold {thr}")

    out = OUT / "cases.json"
    out.write_text(json.dumps({
        "source": "RWTH-EBC/AixLib main, ThermalZones/ReducedOrder/"
                  "Validation/VDI6007 (BSD-3-Clause)",
        "note": "reference trajectories are hourly means for days 1/10/60; "
                "temperature offsets degC->K in 'offset'",
        "h_con_out": H_CON_OUT,
        "cases": cases}, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
