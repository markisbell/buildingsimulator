export default function DeviceInspector({ manifest, aptId }) {
  const apt = manifest.apartments.find((a) => a.id === aptId);
  const dev = (manifest.devices || {})[aptId];

  return (
    <div className="card">
      <h2>Device inspector — apartment {aptId}</h2>
      {apt.vacant ? (
        <p style={{ color: "var(--text-2)", fontSize: 13 }}>
          Vacant apartment: no thermostat installed. Zone temperature is held
          up only by neighbour heat through floor and ceiling.
        </p>
      ) : !dev ? (
        <p style={{ color: "var(--text-2)", fontSize: 13 }}>
          No device diagnostics for this run (ideal controller, or run still
          in progress — diagnostics are written when the run finishes).
        </p>
      ) : (
        <table className="kv">
          <tbody>
            <tr>
              <td>controller</td>
              <td>{apt.controller}</td>
            </tr>
            <tr>
              <td>schedule</td>
              <td>{apt.schedule}</td>
            </tr>
            <tr>
              <td>zero estimate error</td>
              <td>{dev.zeroErrorUm} µm</td>
            </tr>
            <tr>
              <td>seal estimate</td>
              <td>{dev.sealEstUm} µm</td>
            </tr>
            <tr>
              <td>last adaptation</td>
              <td>{dev.adaptationAgeDays} days ago</td>
            </tr>
            <tr>
              <td>valve travel / moves</td>
              <td>
                {dev.travelMm.toFixed(1)} mm / {dev.moves}
              </td>
            </tr>
          </tbody>
        </table>
      )}
      <div className="footer-note">
        planned: sensor-vs-true temperature strip, adaptation current trace,
        battery estimate, trigger adaptation run
      </div>
    </div>
  );
}
