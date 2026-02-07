import React, { useMemo, useState } from "react";


const mockUsers = [
  {
    id: "U001",
    daysInStudy: 90,
    lastDialogueAt: "2026-02-05T10:10:00",
    lastDialogueStatus: "active", // active/closed
    // risk = highest in last 2 weeks (mocked)
    risk2w: "high", // normal/mixed/high
    status: "needs review", // active / closed / needs review

    // Recent compliance (last 7 days) summarized into 3-level states
    // good / partial / missing
    compliance7d: { ema: "good", location: "partial", battery: "missing", accel: "good", gyro: "good" },
  },
  {
    id: "U002",
    daysInStudy: 57,
    lastDialogueAt: "2026-02-02T10:30:00",
    lastDialogueStatus: "closed",
    risk2w: "mixed",
    status: "active",
    compliance7d: { ema: "partial", location: "good", battery: "good", accel: "good", gyro: "partial" },
  },
  {
    id: "U003",
    daysInStudy: 12,
    lastDialogueAt: "2026-01-29T09:00:00",
    lastDialogueStatus: "active",
    risk2w: "normal",
    status: "active",
    compliance7d: { ema: "missing", location: "missing", battery: "partial", accel: "good", gyro: "good" },
  },
  {
    id: "U004",
    daysInStudy: 35,
    lastDialogueAt: "2026-01-25T21:45:00",
    lastDialogueStatus: "closed",
    risk2w: "high",
    status: "closed",
    compliance7d: { ema: "good", location: "good", battery: "good", accel: "partial", gyro: "missing" },
  },
];

function timeAgo(iso) {
  const dt = new Date(iso);
  const diffMs = Date.now() - dt.getTime();
  const diffH = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffH < 24) return `${diffH}h ago`;
  const diffD = Math.floor(diffH / 24);
  return `${diffD}d ago`;
}

function hoursSince(iso) {
  const dt = new Date(iso).getTime();
  return (Date.now() - dt) / (1000 * 60 * 60);
}

function lastDialogueColor(iso) {
  const h = hoursSince(iso);
  if (h <= 24) return "#1f7a1f";     // recent (today-ish)
  if (h <= 72) return "#b06b00";     // a few days
  return "#a11a1a";                  // stale
}

const riskRank = { normal: 0, mixed: 1, high: 2 };

// Google Calendar “Schedule” labels
function dateSectionLabel(iso) {
  const d = new Date(iso);
  const today = new Date();
  const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startOfThatDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.round((startOfToday - startOfThatDay) / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";

  // e.g., "Feb 3"
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ComplianceIcon({ label, value }) {
  // value: good | partial | missing
  const bg =
    value === "good" ? "#1f7a1f" :
    value === "partial" ? "#b06b00" :
    "#a11a1a";

  return (
    <span
      title={`${label}: ${value}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        marginRight: 10,
        fontSize: 12,
      }}
    >
      <span style={{ width: 10, height: 10, borderRadius: 999, background: bg, display: "inline-block" }} />
      <span style={{ opacity: 0.9 }}>{label}</span>
    </span>
  );
}
function ComplianceDot({ label, value }) {
  // value: good | partial | missing
  const bg =
    value === "good" ? "#1f7a1f" :
    value === "partial" ? "#b06b00" :
    "#a11a1a";

  return (
    <span
      title={`${label}: ${value}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        marginRight: 10,
        fontSize: 12,
      }}
    >
      <span
        style={{
          width: 10,
          height: 10,
          borderRadius: 999,
          background: bg,
          display: "inline-block",
        }}
      />
      <span style={{ opacity: 0.9 }}>{label}</span>
    </span>
  );
}

function ComplianceSummary({ c }) {
  const safe = (c && typeof c === "object") ? c : {};
  const get = (k) => safe[k] ?? "missing";

  return (
    <div style={{ display: "flex", flexWrap: "wrap" }}>
      <ComplianceDot label="EMA" value={get("ema")} />
      <ComplianceDot label="LOC" value={get("location")} />
      <ComplianceDot label="BAT" value={get("battery")} />
      <ComplianceDot label="ACC" value={get("accel")} />
      <ComplianceDot label="GYR" value={get("gyro")} />
    </div>
  );
}


export default function OverallListScreen() {
const [sortMode, setSortMode] = useState("recent"); // recent | risk | silence
  const users = useMemo(() => {
  const arr = [...mockUsers];

  arr.sort((a, b) => {
    if (sortMode === "recent") {
      return new Date(b.lastDialogueAt) - new Date(a.lastDialogueAt);
    }
    if (sortMode === "risk") {
      // Highest risk first; tie-break by recency
      const r = riskRank[b.risk2w] - riskRank[a.risk2w];
      if (r !== 0) return r;
      return new Date(b.lastDialogueAt) - new Date(a.lastDialogueAt);
    }
    // silence: longest since last dialogue first; tie-break by risk
    const s = hoursSince(b.lastDialogueAt) - hoursSince(a.lastDialogueAt);
    if (s !== 0) return s;
    return riskRank[b.risk2w] - riskRank[a.risk2w];
  });

  return arr;
}, [sortMode]);

  return (
    <div style={{ padding: 24 }}>
      <h1 style={{ marginBottom: 12 }}>Overall — Schedule Style</h1>
      <p style={{ marginTop: 0, marginBottom: 24, opacity: 0.8 }}>
        Default sorting: most recent dialogue
      </p>

    <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
  <button onClick={() => setSortMode("recent")} style={{ padding: "8px 12px" }}>
    Sort: Recent dialogue
  </button>
  <button onClick={() => setSortMode("risk")} style={{ padding: "8px 12px" }}>
    Sort: Risk (2w)
  </button>
  <button onClick={() => setSortMode("silence")} style={{ padding: "8px 12px" }}>
    Sort: Silence
  </button>
</div>


      <div style={{ border: "1px solid #ddd", borderRadius: 12, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "140px 120px 260px 180px 120px", padding: 12, fontWeight: 600, background: "#f6f6f6" }}>
          <div>ID</div>
          <div>Days</div>
          <div>Recent Compliance</div>
          <div>Last dialogue</div>
          <div>Risk</div>
        </div>

        {users.map((u) => (
  <div
    key={u.id}
    style={{
      display: "grid",
      gridTemplateColumns: "140px 120px 260px 180px 120px",
      padding: 12,
      borderTop: "1px solid #eee",
      alignItems: "center",
    }}
  >
    <div style={{ fontWeight: 600 }}>{u.id}</div>
    <div>{u.daysInStudy}</div>

    {/* Compliance icons */}
    <div>
      <ComplianceSummary c={u.compliance7d} />
    </div>

    {/* Last dialogue + status */}
    <div style={{ color: lastDialogueColor(u.lastDialogueAt) }}>
      {timeAgo(u.lastDialogueAt)}{" "}
      <span
        style={{
          marginLeft: 8,
          fontSize: 12,
          padding: "2px 8px",
          borderRadius: 999,
          border: "1px solid #ccc",
          color: "#111",
        }}
      >
        {u.lastDialogueStatus}
      </span>
    </div>

    {/* Risk (2 weeks) */}
    <div style={{ fontWeight: 600 }}>{u.risk2w}</div>
  </div>
))}
      </div>
    </div>
  );
}
