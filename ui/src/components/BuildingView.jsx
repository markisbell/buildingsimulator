function tempColor(t) {
  // 10 degC -> cool blue, 23 degC -> warm orange
  const x = Math.max(0, Math.min(1, (t - 10) / 13));
  const hue = 210 - 180 * x;
  return `hsl(${hue}, 62%, ${88 - 8 * x}%)`;
}

function Cell({ apt, temp, valve, selected, onSelect }) {
  return (
    <button
      className={`apt${selected ? " selected" : ""}`}
      style={{ background: tempColor(temp) }}
      onClick={() => onSelect(apt.id)}
    >
      <div className="meta">
        <strong>apt {apt.id}</strong>
        <span className={`tag ${apt.facade}`}>{apt.facade}</span>
        {apt.vacant && <span className="tag vacant">vacant</span>}
      </div>
      <span className="temp">{temp.toFixed(1)} °C</span>{" "}
      <span className="sp">{apt.schedule}</span>
      <div className="valvebar">
        <div style={{ width: `${Math.round(valve * 100)}%` }} />
      </div>
    </button>
  );
}

export default function BuildingView({ manifest, series, idx, selected, onSelect }) {
  const { floors, apartmentsPerFloor } = manifest.building;
  const rows = [];
  for (let f = floors; f >= 1; f--) {
    const apts = manifest.apartments.filter((a) => a.floor === f);
    rows.push(
      <div className="floor-row" key={f}>
        <div className="floor-label">{f}</div>
        {apts.map((a) => (
          <Cell
            key={a.id}
            apt={a}
            temp={series.rooms[a.id][idx]}
            valve={series.valves[a.id][idx]}
            selected={selected === a.id}
            onSelect={onSelect}
          />
        ))}
      </div>
    );
  }
  return <div>{rows}</div>;
}
