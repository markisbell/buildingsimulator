// Run-store API client. Falls back to the bundled mock when unreachable.
// The adapter converts raw FMU columns (Kelvin, watts) into the shapes the
// components consume (degC, kW, per-apartment dicts).

const API = import.meta.env.VITE_API_URL || "http://localhost:8010/api";
const C2K = 273.15;

export async function listRuns() {
  const res = await fetch(`${API}/runs`);
  if (!res.ok) throw new Error(`runs list: ${res.status}`);
  return res.json();
}

export async function fetchSeries(runId, manifest, stride = 5) {
  const res = await fetch(`${API}/runs/${runId}/series?stride=${stride}`);
  if (!res.ok) throw new Error(`series: ${res.status}`);
  return adaptSeries(await res.json(), manifest);
}

export function adaptSeries(cols, manifest) {
  const rooms = {};
  const valves = {};
  for (const a of manifest.apartments) {
    rooms[a.id] = (cols[`TRoom[${a.id}]`] || []).map((v) => v - C2K);
    valves[a.id] = cols[`yVal[${a.id}]`] || [];
  }
  const firstSouth = manifest.apartments.find((a) => a.facade === "south");
  return {
    time: cols.time || [],
    tOut: (cols.TOut || []).map((v) => v - C2K),
    solarSouth: firstSouth ? cols[`QGain[${firstSouth.id}]`] || [] : [],
    rooms,
    valves,
    qBoi: (cols.QBoi || []).map((v) => v / 1000),
    tSup: (cols.TSup || []).map((v) => v - C2K),
    tRet: (cols.TRet || []).map((v) => v - C2K),
  };
}
