// Mock data shaped like the future run-store API.
// A real run will provide exactly these structures:
//   GET /runs/<id>/manifest   -> manifest
//   GET /runs/<id>/series     -> series (columnar arrays)
// so the components can later be rebound without structural changes.

const DAY = 86400;
const STEP = 300; // 5 min
const N_DAYS = 2;
const N = (N_DAYS * DAY) / STEP;

export const manifest = {
  id: "winter-week-eTRV-04",
  status: "running",
  progressDays: 3.4,
  durationDays: 7,
  building: { floors: 3, apartmentsPerFloor: 2 },
  scenario: { weather: "synthetic winter", cloudiness: 0.4, startDate: "2026-01-12" },
  apartments: [
    { id: 1, floor: 1, facade: "south", vacant: false, controller: "eTRV / SampledPI", schedule: "21 °C 6–22 h / 17 °C" },
    { id: 2, floor: 1, facade: "north", vacant: false, controller: "eTRV / SampledPI", schedule: "21 °C 8–20 h / 16 °C" },
    { id: 3, floor: 2, facade: "south", vacant: true, controller: "—", schedule: "vacant" },
    { id: 4, floor: 2, facade: "north", vacant: false, controller: "eTRV / SampledPI", schedule: "22 °C 7–23 h / 18 °C" },
    { id: 5, floor: 3, facade: "south", vacant: false, controller: "eTRV / SampledPI", schedule: "21 °C 6–21 h / 17 °C" },
    { id: 6, floor: 3, facade: "north", vacant: false, controller: "eTRV / SampledPI", schedule: "20 °C 9–18 h / 16 °C" },
  ],
  kpis: { discomfortKh: 312, overheatKh: 14, boilerKwh: 861, pumpKwh: 0.6, valveTravelStrokes: 148, valveMoves: 1355 },
  devices: {
    1: { zeroErrorUm: -78, sealEstUm: 40, travelMm: 61.2, moves: 262, adaptationAgeDays: 3.2 },
    2: { zeroErrorUm: -71, sealEstUm: 40, travelMm: 44.7, moves: 231, adaptationAgeDays: 3.2 },
    4: { zeroErrorUm: -80, sealEstUm: 50, travelMm: 52.9, moves: 301, adaptationAgeDays: 3.2 },
    5: { zeroErrorUm: -74, sealEstUm: 40, travelMm: 49.1, moves: 285, adaptationAgeDays: 3.2 },
    6: { zeroErrorUm: -79, sealEstUm: 40, travelMm: 40.3, moves: 276, adaptationAgeDays: 3.2 },
  },
};

function schedule(id, hour) {
  const s = {
    1: [21, 17, 6, 22],
    2: [21, 16, 8, 20],
    4: [22, 18, 7, 23],
    5: [21, 17, 6, 21],
    6: [20, 16, 9, 18],
  }[id];
  if (!s) return null;
  return hour >= s[2] && hour < s[3] ? s[0] : s[1];
}

function generate() {
  const time = [];
  const tOut = [];
  const solarSouth = [];
  const rooms = { 1: [], 2: [], 3: [], 4: [], 5: [], 6: [] };
  const valves = { 1: [], 2: [], 3: [], 4: [], 5: [], 6: [] };
  const qBoi = [];
  const tSup = [];
  const tRet = [];

  for (let k = 0; k < N; k++) {
    const t = k * STEP;
    const hour = (t % DAY) / 3600;
    time.push(t);
    const out = -2 + 4 * Math.sin((2 * Math.PI * (t - 10 * 3600)) / DAY);
    tOut.push(out);
    const sun = Math.max(0, Math.sin((Math.PI * (hour - 8.5)) / 8));
    solarSouth.push(1400 * sun * sun);

    let load = 0;
    for (const a of manifest.apartments) {
      const sp = schedule(a.id, hour);
      const south = a.facade === "south";
      if (sp === null) {
        rooms[a.id].push(12 + 0.8 * Math.sin((2 * Math.PI * (hour - 15)) / 24) + (south ? 0.9 * sun * sun : 0));
        valves[a.id].push(0);
        continue;
      }
      const recovery = Math.min(1, Math.max(0, (hour - 5.5) / 3.5));
      const night = hour < 6 || hour >= 22 ? 1 : 0;
      const base = night ? sp - 0.2 : sp - 1.6 * (1 - recovery) - 0.3;
      const solarBump = south ? 0.7 * sun * sun : 0.15 * sun * sun;
      rooms[a.id].push(Math.round((base + solarBump) * 100) / 100);
      const boost = hour >= 6 && hour < 10 ? 0.95 : 0.2 - 0.12 * solarBump;
      const v = night ? 0.08 + 0.1 * (k % 3 === 0 ? 1 : 0) : Math.max(0.02, boost);
      valves[a.id].push(Math.round(v * 100) / 100);
      load += v;
    }
    qBoi.push(Math.round(4.5 * load * 10) / 10);
    tSup.push(Math.round((35 + 30 * ((15 - out) / 25)) * 10) / 10);
    tRet.push(Math.round((36 + 2.5 * load) * 10) / 10);
  }
  return { time, tOut, solarSouth, rooms, valves, qBoi, tSup, tRet };
}

export const series = generate();
export const STEP_S = STEP;
