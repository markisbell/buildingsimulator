import { useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, Legend,
  ReferenceLine, ResponsiveContainer,
} from "recharts";

const COLORS = ["#2a78d6", "#1baf7a", "#555555", "#e34948", "#8a5ac2", "#c98500"];
const DAY = 86400;

function fmtDay(t) {
  return (t / DAY).toFixed(1);
}

export default function SeriesChart({ manifest, series, idx }) {
  const [tab, setTab] = useState("temps");

  const data = useMemo(() => {
    return series.time.map((t, k) => {
      const row = { t };
      for (const a of manifest.apartments) {
        row[`T${a.id}`] = series.rooms[a.id][k];
        row[`v${a.id}`] = series.valves[a.id][k];
      }
      row.tOut = series.tOut[k];
      row.qBoi = series.qBoi[k];
      row.tSup = series.tSup[k];
      row.tRet = series.tRet[k];
      return row;
    });
  }, [manifest, series]);

  const lines =
    tab === "temps"
      ? [
          ...manifest.apartments.map((a, i) => ({
            key: `T${a.id}`, name: `apt ${a.id}`, color: COLORS[i % COLORS.length],
            width: a.vacant ? 2.4 : 1.4,
          })),
          { key: "tOut", name: "outdoor", color: "#aaaaaa", width: 1 },
        ]
      : tab === "valves"
        ? manifest.apartments
            .filter((a) => !a.vacant)
            .map((a, i) => ({
              key: `v${a.id}`, name: `apt ${a.id}`, color: COLORS[i % COLORS.length], width: 1.2,
            }))
        : [
            { key: "qBoi", name: "boiler kW", color: "#2a78d6", width: 1.6 },
            { key: "tSup", name: "supply °C", color: "#c98500", width: 1.2 },
            { key: "tRet", name: "return °C", color: "#1baf7a", width: 1.2 },
          ];

  return (
    <div>
      <div className="tabs">
        {["temps", "valves", "plant"].map((k) => (
          <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>
            {k === "temps" ? "room temperatures" : k}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
          <XAxis
            dataKey="t"
            tickFormatter={fmtDay}
            stroke="#9b9a92"
            fontSize={11}
            label={{ value: "time / days", position: "insideBottomRight", offset: -2, fontSize: 11 }}
          />
          <YAxis stroke="#9b9a92" fontSize={11} domain={["auto", "auto"]} />
          <Tooltip
            labelFormatter={(t) => `day ${fmtDay(t)}`}
            formatter={(v) => (typeof v === "number" ? v.toFixed(2) : v)}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <ReferenceLine x={series.time[idx]} stroke="#e34948" strokeDasharray="4 3" />
          {lines.map((l) => (
            <Line
              key={l.key}
              dataKey={l.key}
              name={l.name}
              stroke={l.color}
              strokeWidth={l.width}
              dot={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
