const DAY = 86400;

function clock(t) {
  const day = Math.floor(t / DAY) + 1;
  const h = Math.floor((t % DAY) / 3600);
  const m = Math.floor((t % 3600) / 60);
  return `day ${day} · ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export default function TimeScrubber({ series, idx, onChange }) {
  return (
    <div className="scrub">
      <span className="clock">{clock(series.time[idx])}</span>
      <input
        type="range"
        min={0}
        max={series.time.length - 1}
        value={idx}
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <span style={{ fontSize: 12, color: "var(--text-3)" }}>
        scrub through the run — building view and plant follow
      </span>
    </div>
  );
}
