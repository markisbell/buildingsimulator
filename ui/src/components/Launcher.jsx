import { useState } from "react";
import { launchRun } from "../api.js";

export default function Launcher({ nApt, onLaunched, onClose }) {
  const [name, setName] = useState("experiment");
  const [controller, setController] = useState("realistic");
  const [days, setDays] = useState(7);
  const [cloudiness, setCloudiness] = useState(0.4);
  const [vacant, setVacant] = useState([3]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const toggleVacant = (i) =>
    setVacant((v) => (v.includes(i) ? v.filter((x) => x !== i) : [...v, i]));

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await launchRun({
        name,
        controller,
        durationDays: Number(days),
        cloudiness: Number(cloudiness),
        vacant,
      });
      onLaunched();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <h2>Launch a run</h2>
      <div className="launch-grid">
        <label>
          name
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          thermostat
          <select value={controller} onChange={(e) => setController(e.target.value)}>
            <option value="realistic">realistic eTRV</option>
            <option value="ideal">ideal PI</option>
          </select>
        </label>
        <label>
          duration / days
          <input type="number" min="1" max="30" value={days}
                 onChange={(e) => setDays(e.target.value)} />
        </label>
        <label>
          cloudiness: {Number(cloudiness).toFixed(1)}
          <input type="range" min="0" max="1" step="0.1" value={cloudiness}
                 onChange={(e) => setCloudiness(e.target.value)} />
        </label>
      </div>
      <div style={{ margin: "10px 0", fontSize: 13 }}>
        vacant apartments:{" "}
        {Array.from({ length: nApt }, (_, k) => k + 1).map((i) => (
          <label key={i} style={{ marginRight: 10 }}>
            <input type="checkbox" checked={vacant.includes(i)}
                   onChange={() => toggleVacant(i)} /> {i}
          </label>
        ))}
      </div>
      {error && <div style={{ color: "#a32d2d", fontSize: 13, marginBottom: 8 }}>{error}</div>}
      <button onClick={submit} disabled={busy}>
        {busy ? "starting…" : "start run"}
      </button>{" "}
      <button onClick={onClose}>cancel</button>
    </div>
  );
}
