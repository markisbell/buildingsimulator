import { useState } from "react";
import { manifest, series } from "./mock/run.js";
import BuildingView from "./components/BuildingView.jsx";
import PlantPanel from "./components/PlantPanel.jsx";
import KpiBoard from "./components/KpiBoard.jsx";
import SeriesChart from "./components/SeriesChart.jsx";
import DeviceInspector from "./components/DeviceInspector.jsx";
import TimeScrubber from "./components/TimeScrubber.jsx";

export default function App() {
  // start the scrubber at midday of day 2 (solar asymmetry visible)
  const [idx, setIdx] = useState(Math.floor(series.time.length * 0.77));
  const [selected, setSelected] = useState(1);

  return (
    <div className="app">
      <div className="header">
        <h1>buildingsimulator</h1>
        <span style={{ color: "var(--text-2)" }}>run: {manifest.id}</span>
        <span className="badge running">
          {manifest.status} · day {manifest.progressDays}/{manifest.durationDays}
        </span>
        <span className="spacer" />
        <button>pause</button>
        <button>new run</button>
      </div>

      <div className="grid">
        <div className="card">
          <h2>Building — air temperature and valve opening</h2>
          <BuildingView
            manifest={manifest}
            series={series}
            idx={idx}
            selected={selected}
            onSelect={setSelected}
          />
          <div className="footer-note">
            tint = facade (south / north) · bar = valve opening · click an
            apartment for the device inspector
          </div>
        </div>

        <div className="right-col">
          <PlantPanel series={series} idx={idx} />
          <KpiBoard kpis={manifest.kpis} />
        </div>
      </div>

      <TimeScrubber series={series} idx={idx} onChange={setIdx} />

      <div className="grid">
        <div className="card">
          <SeriesChart manifest={manifest} series={series} idx={idx} />
        </div>
        <DeviceInspector manifest={manifest} series={series} aptId={selected} />
      </div>
    </div>
  );
}
