import { useMemo, useState } from "react";

const COLUMNS = [
  { key: "discomfortKh", label: "discomfort K·h" },
  { key: "overheatKh", label: "overheat K·h" },
  { key: "boilerKwh", label: "boiler kWh" },
  { key: "pumpKwh", label: "pump kWh" },
  { key: "valveTravelStrokes", label: "travel strokes" },
  { key: "valveMoves", label: "moves" },
];

function controllerOf(m) {
  const a = (m.apartments || []).find((x) => !x.vacant);
  return a ? a.controller : "—";
}

export default function Leaderboard({ runs, onOpen }) {
  const [sortKey, setSortKey] = useState("discomfortKh");
  const [asc, setAsc] = useState(true);
  const [perDay, setPerDay] = useState(true);

  // KPIs integrate over the evaluated days (duration minus warm-up day),
  // so runs of different length only compare fairly per day
  const evalDays = (m) => Math.max(1, (m.durationDays || 1) - 1);
  const value = (m, key) => {
    const v = m.kpis?.[key];
    if (v === undefined) return undefined;
    return perDay ? v / evalDays(m) : v;
  };

  const sorted = useMemo(() => {
    const val = (m) =>
      sortKey === "name" ? m.id : value(m, sortKey) ?? Infinity;
    return [...runs].sort((a, b) =>
      (val(a) > val(b) ? 1 : -1) * (asc ? 1 : -1));
  }, [runs, sortKey, asc, perDay]); // eslint-disable-line react-hooks/exhaustive-deps

  // best (lowest) finished value per KPI column
  const best = useMemo(() => {
    const b = {};
    for (const c of COLUMNS) {
      const vals = runs
        .filter((m) => m.status === "finished")
        .map((m) => value(m, c.key))
        .filter((v) => v !== undefined);
      if (vals.length) b[c.key] = Math.min(...vals);
    }
    return b;
  }, [runs, perDay]); // eslint-disable-line react-hooks/exhaustive-deps

  const header = (key, label) => (
    <th key={key}
        onClick={() => (key === sortKey ? setAsc(!asc) : (setSortKey(key), setAsc(true)))}
        style={{ cursor: "pointer" }}>
      {label} {sortKey === key ? (asc ? "▲" : "▼") : ""}
    </th>
  );

  return (
    <div className="card">
      <h2>KPI leaderboard — lower is better, best value highlighted</h2>
      <label style={{ fontSize: 13, color: "var(--text-2)" }}>
        <input type="checkbox" checked={perDay}
               onChange={(e) => setPerDay(e.target.checked)} /> per evaluated
        day (fair across different run lengths)
      </label>
      <table className="lb">
        <thead>
          <tr>
            {header("name", "run")}
            <th>thermostat</th>
            <th>status</th>
            {COLUMNS.map((c) => header(c.key, c.label))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((m) => (
            <tr key={m.id} onClick={() => onOpen(m.id)} style={{ cursor: "pointer" }}>
              <td>{m.id}</td>
              <td>{controllerOf(m)}</td>
              <td>{m.status}{m.status === "running" ? ` (${m.progressDays}d)` : ""}</td>
              {COLUMNS.map((c) => {
                const v = value(m, c.key);
                const isBest = v !== undefined && v === best[c.key];
                return (
                  <td key={c.key} className={isBest ? "best" : ""}>
                    {v === undefined ? "—"
                      : v.toLocaleString(undefined, { maximumFractionDigits: 1 })}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="footer-note">click a column header to sort, a row to open the run</div>
    </div>
  );
}
