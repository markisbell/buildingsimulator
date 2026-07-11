export default function PlantPanel({ series, idx }) {
  return (
    <div className="card">
      <h2>Plant</h2>
      <table className="kv">
        <tbody>
          <tr>
            <td>boiler power</td>
            <td>{series.qBoi[idx].toFixed(1)} kW</td>
          </tr>
          <tr>
            <td>supply / return</td>
            <td>
              {series.tSup[idx].toFixed(1)} / {series.tRet[idx].toFixed(1)} °C
            </td>
          </tr>
          <tr>
            <td>outdoor</td>
            <td>{series.tOut[idx].toFixed(1)} °C</td>
          </tr>
          <tr>
            <td>solar, south facade</td>
            <td>{Math.round(series.solarSouth[idx])} W</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
