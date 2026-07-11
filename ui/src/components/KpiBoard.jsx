export default function KpiBoard({ kpis }) {
  const items = [
    { label: "discomfort", value: `${kpis.discomfortKh} K·h` },
    { label: "overheating", value: `${kpis.overheatKh} K·h` },
    { label: "boiler energy", value: `${kpis.boilerKwh} kWh` },
    { label: "valve travel", value: `${kpis.valveTravelStrokes} strokes` },
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
