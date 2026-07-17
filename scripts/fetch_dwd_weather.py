"""Fetch measured DWD weather for the TABULA season validation.

Station Rheinstetten 04177 (DWD reference station ~6 km south of
Karlsruhe): hourly air temperature + 10-minute global/diffuse radiation
from the DWD Climate Data Center open-data server (anonymous, CC BY 4.0,
attribution "Quelle: Deutscher Wetterdienst").

Output: data/weather/rheinstetten_2023-07_2024-06.csv with hourly
  time_utc, t_air_C, ghi_Wm2, dhi_Wm2
covering 2023-07-01 .. 2024-06-30 (full year for degree days; the season
simulation uses 2023-10-01 .. 2024-04-30).

Radiation gotcha: DWD stores 10-min sums in J/cm^2 per interval;
mean W/m^2 = value * 10000 / 600.
"""

import io
import re
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

BASE = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate"
STATION = "04177"
START, END = "2023-07-01", "2024-06-30 23:59"
OUT = Path(__file__).resolve().parents[1] / "data" / "weather"
OUT.mkdir(parents=True, exist_ok=True)


def list_dir(url):
    html = urllib.request.urlopen(url, timeout=60).read().decode()
    return re.findall(r'href="([^"]+\.zip)"', html)


def fetch_zip_txt(url):
    print(f"  fetching {url.rsplit('/', 1)[-1]} ...")
    raw = urllib.request.urlopen(url, timeout=300).read()
    zf = zipfile.ZipFile(io.BytesIO(raw))
    name = [n for n in zf.namelist() if n.startswith("produkt_")][0]
    return pd.read_csv(io.BytesIO(zf.read(name)), sep=";", skipinitialspace=True)


def station_files(subdir, tag):
    files = [f for f in list_dir(f"{BASE}/{subdir}/")
             if f"_{STATION}_" in f or f.endswith(f"_{STATION}_{tag}.zip")]
    return [f"{BASE}/{subdir}/{f}" for f in files]


def load_temperature():
    frames = []
    for sub in ("hourly/air_temperature/historical", "hourly/air_temperature/recent"):
        for url in station_files(sub, "akt"):
            df = fetch_zip_txt(url)
            df["time_utc"] = pd.to_datetime(df["MESS_DATUM"], format="%Y%m%d%H", utc=True)
            frames.append(df[["time_utc", "TT_TU"]])
    t = (pd.concat(frames).drop_duplicates("time_utc").set_index("time_utc")
         .sort_index().loc[START:END, "TT_TU"])
    t = t.mask(t <= -999).interpolate(limit=6)
    return t.rename("t_air_C")


def load_solar():
    frames = []
    for sub in ("10_minutes/solar/historical", "10_minutes/solar/recent",
                "10_minutes/solar/now"):
        try:
            urls = station_files(sub, "akt")
        except Exception:
            continue
        for url in urls:
            m = re.search(r"_(\d{8})_(\d{8})_hist", url)
            if m and (m.group(2) < "20230701" or m.group(1) > "20240630"):
                continue  # skip decade chunks outside the target year
            df = fetch_zip_txt(url)
            df["time_utc"] = pd.to_datetime(
                df["MESS_DATUM"].astype(str).str.slice(0, 12),
                format="%Y%m%d%H%M", utc=True)
            frames.append(df[["time_utc", "GS_10", "DS_10"]])
    s = (pd.concat(frames).drop_duplicates("time_utc").set_index("time_utc")
         .sort_index().loc[START:END])
    s = s.mask(s <= -999)
    # J/cm^2 per 10 min -> mean W/m^2, then hourly means
    w = s * 10000.0 / 600.0
    hourly = w.resample("1h").mean().interpolate(limit=6).fillna(0.0)
    return hourly.rename(columns={"GS_10": "ghi_Wm2", "DS_10": "dhi_Wm2"})


def main():
    print("DWD CDC download, station Rheinstetten 04177 (CC BY 4.0)")
    t = load_temperature()
    sol = load_solar()
    df = pd.concat([t, sol], axis=1).loc[START:END]
    df["ghi_Wm2"] = df["ghi_Wm2"].fillna(0.0)
    df["dhi_Wm2"] = df["dhi_Wm2"].clip(upper=df["ghi_Wm2"]).fillna(0.0)
    n_nan = int(df["t_air_C"].isna().sum())
    if n_nan:
        df["t_air_C"] = df["t_air_C"].interpolate().bfill().ffill()
    out = OUT / "rheinstetten_2023-07_2024-06.csv"
    df.to_csv(out, index_label="time_utc")
    print(f"wrote {out}: {len(df)} hours, {n_nan} temperature gaps interpolated")
    print(f"  T range {df.t_air_C.min():.1f} .. {df.t_air_C.max():.1f} degC, "
          f"GHI max {df.ghi_Wm2.max():.0f} W/m2")


if __name__ == "__main__":
    main()
