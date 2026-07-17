"""TABULA season validation, part 2: aggregate the season run and compare
against the TABULA/IWU archetype statistics for MFH 1979-1983 (MFH_G,
DE.N.MFH.07.Gen).

Comparison targets (per m2 heated living area and year, German reference
climate; TABULA DE brochure, IWU 2015, p. 113):
  net space heat demand, standard calculation   139.8 kWh/(m2 a)
  net space heat, 'typical measured consumption' level  115.2 kWh/(m2 a)
The measured level embeds the empirically calibrated adaptation factor
(~0.82 at this consumption level; prebound effect).

The simulated season (2023-10-01..2024-04-30, Rheinstetten weather) is
annualized and climate-adjusted with degree-day ratios (GTZ 20/15,
VDI 3807): season -> full weather year -> long-term German reference
(GTZ_ref = 3883 K d/a, VDI 3807-1 German mean; sensitivity reported).

Outputs: results/tabula_season.json, results/tabula_season.png
Usage:  analyze_tabula_season.py [tag]      (default: full)
"""

import gzip
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
WEATHER_CSV = ROOT / "data" / "weather" / "rheinstetten_2023-07_2024-06.csv"

C2K = 273.15
DAY = 86400.0
A_HEATED = 384.0          # m2 heated living area (6 apartments x 64 m2)
N_ZON = 24
GTZ_REF = 3883.0          # K d/a, long-term German mean GTZ 20/15 (VDI 3807-1)
TABULA = {"net_standard": 139.8, "net_measured_level": 115.2}  # kWh/(m2 a)
T0_UTC = pd.Timestamp("2023-09-30 23:00:00", tz="UTC")


def gtz_20_15(daily_mean_c):
    """Gradtagszahl 20/15 (VDI 3807): sum of (20 - Tm) over days Tm < 15."""
    heat_days = daily_mean_c[daily_mean_c < 15.0]
    return float((20.0 - heat_days).sum())


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "full"
    with gzip.open(RESULTS / f"tabula_season_{tag}.csv.gz", "rt") as fh:
        df = pd.read_csv(fh)
    meta = json.loads((RESULTS / f"tabula_season_{tag}.meta.json").read_text())

    # -- energies ------------------------------------------------------
    dt_h = float(np.median(np.diff(df["time"]))) / 3600.0
    e_boi_kwh = df["QBoi"].sum() * dt_h / 1000.0
    qrad_cols = [f"QRad[{k}]" for k in range(1, N_ZON + 1)]
    e_rad_kwh = df[qrad_cols].to_numpy().sum() * dt_h / 1000.0
    q_boi_spec = e_boi_kwh / A_HEATED
    q_rad_spec = e_rad_kwh / A_HEATED

    # -- degree days from the measured weather year --------------------
    w = pd.read_csv(WEATHER_CSV, parse_dates=["time_utc"], index_col="time_utc")
    daily = w["t_air_C"].resample("1D").mean()
    season_end = T0_UTC + pd.Timedelta(days=meta["days"])
    gtz_season = gtz_20_15(daily.loc[T0_UTC:season_end])
    gtz_year = gtz_20_15(daily)
    # out-of-season heating share (nan on short smoke-test chunks)
    annualize = gtz_year / gtz_season if gtz_season > 0 else float("nan")
    to_ref = GTZ_REF / gtz_year                # site year -> German reference

    q_annual_site = q_boi_spec * annualize
    q_annual_ref = q_annual_site * to_ref
    q_rad_annual_ref = q_rad_spec * annualize * to_ref

    # -- energy signature ----------------------------------------------
    day_idx = (df["time"] // DAY).astype(int)
    sig = pd.DataFrame({
        "tout_c": df.groupby(day_idx)["TOut"].mean() - C2K,
        "p_kw": df.groupby(day_idx)["QBoi"].mean() / 1000.0})
    heat = sig[sig["tout_c"] < 15.0]
    if len(heat) < 5:
        heat = sig                       # smoke-test chunks: fit everything
    slope, icept = np.polyfit(heat["tout_c"], heat["p_kw"], 1)
    t_limit = -icept / slope     # heating-limit temperature of the fit
    ua_eff = -slope * 1000.0     # W/K effective (incl. gains offset)

    # -- room temperatures (plausibility) -------------------------------
    troom_cols = [f"TRoom[{k}]" for k in range(1, N_ZON + 1)]
    t_mean = float(df[troom_cols].mean().mean()) - C2K

    res = {
        "run": meta,
        "season": {
            "e_boiler_kwh": round(e_boi_kwh, 0),
            "e_radiators_kwh": round(e_rad_kwh, 0),
            "q_boiler_spec_kwh_m2": round(q_boi_spec, 1),
            "q_radiators_spec_kwh_m2": round(q_rad_spec, 1),
            "distribution_loss_pct": round(100 * (1 - e_rad_kwh / e_boi_kwh), 1),
            "mean_room_temp_c": round(t_mean, 2),
            "burner_starts_per_day": round(meta["burner_starts"] / meta["days"], 1),
            "boost_h_per_day": round(meta["boost_hours"] / meta["days"], 2),
        },
        "degree_days": {
            "gtz_20_15_season_Kd": round(gtz_season, 0),
            "gtz_20_15_site_year_Kd": round(gtz_year, 0),
            "gtz_20_15_reference_Kd": GTZ_REF,
            "annualization_factor": round(annualize, 3),
            "site_to_reference_factor": round(to_ref, 3),
        },
        "energy_signature": {
            "slope_kw_per_k": round(slope, 3),
            "ua_effective_w_per_k": round(ua_eff, 0),
            "heating_limit_c": round(t_limit, 1),
        },
        "tabula_comparison": {
            "q_annual_site_climate_kwh_m2": round(q_annual_site, 1),
            "q_annual_reference_climate_kwh_m2": round(q_annual_ref, 1),
            "q_radiators_annual_reference_kwh_m2": round(q_rad_annual_ref, 1),
            "tabula_net_standard_kwh_m2": TABULA["net_standard"],
            "tabula_net_measured_level_kwh_m2": TABULA["net_measured_level"],
            "vs_standard_pct": round(100 * q_annual_ref / TABULA["net_standard"], 1),
            "vs_measured_level_pct": round(
                100 * q_annual_ref / TABULA["net_measured_level"], 1),
        },
    }
    (RESULTS / "tabula_season.json").write_text(json.dumps(res, indent=1))

    # -- figure: signature + monthly bars -------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    ax1.scatter(sig["tout_c"], sig["p_kw"], s=12, alpha=0.55, color="#2E5E8C",
                label="daily means")
    xs = np.linspace(heat["tout_c"].min(), t_limit, 50)
    ax1.plot(xs, slope * xs + icept, color="#B8432F", lw=1.6,
             label=f"fit: {ua_eff:.0f} W/K, limit {t_limit:.1f} °C")
    ax1.set_xlabel("daily mean outdoor temperature / °C")
    ax1.set_ylabel("daily mean boiler power / kW")
    ax1.set_title("Energy signature, season 2023/24")
    ax1.legend(fontsize=8)

    day_dates = (T0_UTC + pd.to_timedelta(sig.index * DAY, unit="s")
                 ).tz_convert("Etc/GMT-1")
    e_day = sig["p_kw"] * 24.0 / A_HEATED           # kWh/(m2 day)
    e_month = e_day.groupby(day_dates.strftime("%Y-%m")).sum()
    ax2.bar(range(len(e_month)), e_month.to_numpy(), color="#8a8577")
    ax2.set_xticks(range(len(e_month)), [m[2:] for m in e_month.index],
                   fontsize=8)
    ax2.set_ylabel("boiler heat / kWh/(m² month)")
    ax2.set_title(f"Season {q_boi_spec:.0f} kWh/m² → "
                  f"{q_annual_ref:.0f} kWh/(m²·a) @ ref. climate")
    for ax in (ax1, ax2):
        ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(RESULTS / "tabula_season.png", dpi=150)

    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
