export default function KpiBoard({ kpis }) {
  const k = kpis || {};
  const fmt = (v, unit) => (v === undefined ? "—" : `${v} ${unit}`);
  const items = [
    { label: "discomfort", value: fmt(k.discomfortKh, "K·h") },
    { label: "overheating", value: fmt(k.overheatKh, "K·h") },
    { label: "boiler energy", value: fmt(k.boilerKwh, "kWh") },
    { label: "valve travel", value: fmt(k.valveTravelStrokes, "strokes") },
  ];
  return (
    <div className="card">
      <h2>KPIs — live, days 2+</h2>
      <div className="kpis">
        {items.map((k) => (
          <div className="kpi" key={k.label}>
            <div className="label">{k.label}</div>
            <div className="value">{k.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
