import { useCallback, useEffect, useRef, useState } from "react";
import { listRuns, fetchSeries, stopRun } from "./api.js";
import { manifest as mockManifest, series as mockSeries } from "./mock/run.js";
import BuildingView from "./components/BuildingView.jsx";
import PlantPanel from "./components/PlantPanel.jsx";
import KpiBoard from "./components/KpiBoard.jsx";
import SeriesChart from "./components/SeriesChart.jsx";
import DeviceInspector from "./components/DeviceInspector.jsx";
import TimeScrubber from "./components/TimeScrubber.jsx";
import Launcher from "./components/Launcher.jsx";
import Leaderboard from "./components/Leaderboard.jsx";

const POLL_MS = 5000;

export default function App() {
  const [runs, setRuns] = useState([]);
  const [runId, setRunId] = useState(null);
  const [manifest, setManifest] = useState(null);
  const [series, setSeries] = useState(null);
  const [source, setSource] = useState("loading");
  const [idx, setIdx] = useState(0);
  const [selected, setSelected] = useState(1);
  const [view, setView] = useState("run");
  const [showLauncher, setShowLauncher] = useState(false);
  const prevLen = useRef(0);

  const loadRun = useCallback(async (m) => {
    try {
      const s = await fetchSeries(m.id, m);
      setManifest(m);
      setSeries(s);
      setSource("api");
      const prev = prevLen.current; // capture before the async state updater runs
      prevLen.current = s.time.length;
      setIdx((old) =>
        prev === 0 || old >= prev - 1
          ? s.time.length - 1
          : Math.min(old, s.time.length - 1));
    } catch {
      setSource("error");
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const list = await listRuns();
      setRuns(list);
      if (!list.length) throw new Error("empty store");
      const m = list.find((r) => r.id === runId) || list[0];
      if (!runId) setRunId(m.id);
      await loadRun(m);
    } catch {
      // no server or empty store: demo with bundled mock data
      setManifest(mockManifest);
      setSeries(mockSeries);
      setSource("mock");
      setIdx(Math.floor(mockSeries.time.length * 0.77));
    }
  }, [runId, loadRun]);

  useEffect(() => {
    refresh();
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (source !== "api") return;
    const anyRunning = manifest?.status === "running"
      || runs.some((r) => r.status === "running");
    if (!anyRunning) return;
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [source, manifest, runs, refresh]);

  if (!manifest || !series || !series.time.length) {
    return <div className="app">loading run store…</div>;
  }
  const i = Math.min(idx, series.time.length - 1);

  return (
    <div className="app">
      <div className="header">
        <h1>buildingsimulator</h1>
        {source === "api" ? (
          <select value={runId || ""} onChange={(e) => setRunId(e.target.value)}
                  style={{ fontSize: 13, padding: "4px 8px" }}>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>{r.id}</option>
            ))}
          </select>
        ) : (
          <span style={{ color: "var(--text-2)" }}>run: {manifest.id}</span>
        )}
        <span className={`badge ${manifest.status === "running" ? "running" : ""}`}
              style={manifest.status !== "running" ? { background: "#eee", color: "#555" } : {}}>
          {manifest.status} · day {manifest.progressDays}/{manifest.durationDays}
        </span>
        {source === "mock" && (
          <span className="badge" style={{ background: "#fdecec", color: "#a32d2d" }}>
            mock data — run store unreachable
          </span>
        )}
        <span className="spacer" />
        <div className="tabs" style={{ marginBottom: 0 }}>
          <button className={view === "run" ? "active" : ""}
                  onClick={() => setView("run")}>run</button>
          <button className={view === "leaderboard" ? "active" : ""}
                  onClick={() => setView("leaderboard")}>leaderboard</button>
        </div>
        {manifest.status === "running" && source === "api" && (
          <button onClick={async () => { await stopRun(manifest.id); refresh(); }}>
            stop
          </button>
        )}
        <button onClick={() => setShowLauncher((v) => !v)}>new run</button>
        <button onClick={refresh}>refresh</button>
      </div>

      {showLauncher && (
        <Launcher nApt={manifest.apartments.length}
                  onLaunched={() => {
                    // manifest appears a few seconds after launch
                    refresh();
                    setTimeout(refresh, 4000);
                    setTimeout(refresh, 10000);
                  }}
                  onClose={() => setShowLauncher(false)} />
      )}

      {view === "leaderboard" ? (
        <Leaderboard runs={runs.length ? runs : [manifest]}
                     onOpen={(id) => { setRunId(id); setView("run"); }} />
      ) : (
      <>{/* run view */}

      <div className="grid">
        <div className="card">
          <h2>Building — air temperature and valve opening</h2>
          <BuildingView manifest={manifest} series={series} idx={i}
                        selected={selected} onSelect={setSelected} />
          <div className="footer-note">
            tint = zone temperature · bar = valve opening · click an apartment
            for the device inspector
          </div>
        </div>

        <div className="right-col">
          <PlantPanel series={series} idx={i} />
          <KpiBoard kpis={manifest.kpis} />
        </div>
      </div>

      <TimeScrubber series={series} idx={i} onChange={setIdx} />

      <div className="grid">
        <div className="card">
          <SeriesChart manifest={manifest} series={series} idx={i} />
        </div>
        <DeviceInspector manifest={manifest} aptId={selected} />
      </div>
      </>
      )}
    </div>
  );
}
