function tempColor(t) {
  // 10 degC -> cool blue, 23 degC -> warm orange
  const x = Math.max(0, Math.min(1, (t - 10) / 13));
  const hue = 210 - 180 * x;
  return `hsl(${hue}, 62%, ${88 - 8 * x}%)`;
}

function Cell({ apt, temp, valve, selected, onSelect, compact }) {
  return (
    <button
      className={`apt${selected ? " selected" : ""}`}
      style={{ background: tempColor(temp), padding: compact ? "6px 8px" : undefined }}
      onClick={() => onSelect(apt.id)}
    >
      <div className="meta">
        <strong>{apt.room || `apt ${apt.id}`}</strong>
        {!compact && <span className={`tag ${apt.facade}`}>{apt.facade}</span>}
        {apt.vacant && <span className="tag vacant">vacant</span>}
      </div>
      <span className="temp" style={compact ? { fontSize: 15 } : undefined}>
        {temp.toFixed(1)} °C
      </span>{" "}
      {!compact && <span className="sp">{apt.schedule}</span>}
      <div className="valvebar">
        <div style={{ width: `${Math.round(valve * 100)}%` }} />
      </div>
    </button>
  );
}

export default function BuildingView({ manifest, series, idx, selected, onSelect }) {
  const { floors } = manifest.building;
  const perFloor = Math.max(
    ...Array.from({ length: floors }, (_, i) =>
      manifest.apartments.filter((a) => a.floor === i + 1).length));
  const compact = perFloor > 3;
  const rows = [];
  for (let f = floors; f >= 1; f--) {
    const apts = manifest.apartments.filter((a) => a.floor === f);
    rows.push(
      <div className="floor-row" key={f}
           style={{ gridTemplateColumns: `28px repeat(${perFloor}, 1fr)` }}>
        <div className="floor-label">{f}</div>
        {apts.map((a) => (
          <Cell
            key={a.id}
            apt={a}
            temp={series.rooms[a.id][idx]}
            valve={series.valves[a.id][idx]}
            selected={selected === a.id}
            onSelect={onSelect}
            compact={compact}
          />
        ))}
      </div>
    );
  }
  return <div>{rows}</div>;
}
