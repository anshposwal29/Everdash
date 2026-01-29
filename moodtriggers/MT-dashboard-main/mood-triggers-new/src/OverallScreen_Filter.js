// OverallScreen.js (PART 1/2)

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  User,
  CheckCircle,
  Circle,
  XCircle,
  ChevronLeft,
  ChevronRight,
  Loader2,
  MapPin,
  Activity,
  BatteryLow,
  RotateCcw
} from 'lucide-react';

import DayDetailScreen from './DayDetailScreen';
import ParticipantDetailScreen from './ParticipantDetailScreen';

const isLocal = process.env.REACT_APP_LOCAL === 'true';
const API_BASE_URL = isLocal
  ? "http://localhost:8000"
  : "http://34.27.101.10/api";
  
  
const ParticipantRow = React.memo(({ participant, dayHeaders, startDate, goToParticipantView, goToDayView }) => {
const currentWeek = (participant.weeklyCompliance || []).find(
  w => w.end_date === new Date(new Date(startDate).setDate(new Date(startDate).getDate() + 6))
    .toISOString().split('T')[0]
);


/** Parse 63 / "63" / "63%" */
const toPercentNumber = (v) => {
  if (v == null) return 0;
  const n = parseFloat(String(v).replace(/[^\d.-]/g, ''));
  return Number.isFinite(n) ? n : 0;
};

const colorFor = (pct) => {
  const p = toPercentNumber(pct);
  if (p >= 80) return '#006164';
  if (p >= 50) return '#EDA247';
  return '#DB4325';
};

/** Compliance pill */
const CompliancePill = ({ value }) => {
  const pct = toPercentNumber(value);
  const bg = colorFor(pct);

  return (
    <div className="compliance-cell" style={{ background: 'transparent', padding: 0 }}>
      <div
        style={{
          backgroundColor: bg,
          color: '#fff',
          width: '100%',
          height: '100%',
          borderRadius: '12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 700,
          lineHeight: 1,
          padding: '10px 0',
        }}
        title={`${pct}%`}
      >
        {pct}%
      </div>
    </div>
  );
};

const OverallScreen = () => {
  const [weekOffset, setWeekOffset] = useState(0);
  const [participants, setParticipants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [activeTab, setActiveTab] = useState("overall");
  const [participantId, setParticipantId] = useState("");
  const [selectedDate, setSelectedDate] = useState("");

  /** SORT + FILTER STATE */
  const [sortKey, setSortKey] = useState("weekly_ema"); // DEFAULT = EMA
  const [sortDir, setSortDir] = useState("desc");
  const [idFilter, setIdFilter] = useState("");

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  // Navigation
  const goToOverallView = () => {
    setParticipantId("");
    setSelectedDate("");
    setActiveTab("overall");
  };

  const goToParticipantView = (id) => {
    setParticipantId(id);
    setSelectedDate("");
    setActiveTab("participantDetail");
  };

  const goToDayView = (id, date) => {
    setParticipantId(id);
    setSelectedDate(date);
    setActiveTab("dayDetail");
  };

  /** Week range */
  const getWeekDateRange = (offset = 0) => {
    const today = new Date();

    const endDate = new Date(today);
    endDate.setDate(today.getDate() - 1 - offset * 7);
    endDate.setHours(23, 59, 59, 999);

    const startDate = new Date(endDate);
    startDate.setDate(endDate.getDate() - 6);
    startDate.setHours(0, 0, 0, 0);

    return {
      startDate: startDate.toISOString().split('T')[0],
      endDate: endDate.toISOString().split('T')[0],
      displayStartDate: startDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      displayEndDate: endDate.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    };
  };

  const { displayStartDate, displayEndDate, startDate } = getWeekDateRange(weekOffset);

  /** Fetch data */
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    const { startDate, endDate } = getWeekDateRange(weekOffset);

    try {
      const res = await fetch(`${API_BASE_URL}/overall_status?start_date=${startDate}&end_date=${endDate}`);
      if (!res.ok) throw new Error(`Server responded with ${res.status}`);

      const data = await res.json();

      const cleaned = data
        .filter(p => !p.excluded)
        .map(p => ({
          ...p,
          study_start_date: new Date(p.study_start_date)
        }));

      setParticipants(cleaned);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [weekOffset]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /** Day headers */
  const [y, m, d] = startDate.split('-').map(Number);
  const start = new Date(y, m - 1, d);

  const dayHeaders = Array.from({ length: 7 }, (_, i) => {
    const day = new Date(start);
    day.setDate(start.getDate() + i);
    return {
      isoDate: day.toISOString().split('T')[0],
      shortDay: day.toLocaleDateString('en-US', { weekday: 'short' }),
      shortDate: day.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    };
  });

  /** Average compliance */
  const averageOverallCompliance = (participants) => {
    const included = (participants || []).filter(
      p => !p.excluded && !p.id.startsWith("-")
    );

    if (included.length === 0) return 0;

    const total = included.reduce((sum, p) => sum + (p.overallCompliance || 0), 0);
    return Math.round(total / included.length);
  };

  /** FILTER + SORTED PARTICIPANTS */
  const processedParticipants = useMemo(() => {
    return participants
      .filter(p =>
        p.id.toLowerCase().includes(idFilter.toLowerCase())
      )
      .sort((a, b) => {
        const getVal = (p) => {
          if (sortKey === "overall") {
            return p.overallCompliance || 0;
          }

          const week = (p.weeklyCompliance || []).find(
            w => w.start_date === startDate
          );

          if (!week) return 0;

          if (sortKey === "weekly_ema") return week.weekly_compliance || 0;
          if (sortKey === "weekly_passive") return week.avg_passive_pct || 0;

          return 0;
        };

        const valA = getVal(a);
        const valB = getVal(b);

        return sortDir === "desc" ? valB - valA : valA - valB;
      });
  }, [participants, idFilter, sortKey, sortDir, startDate]);

  // ----- TAB ROUTING -----
  if (activeTab === "participantDetail") {
    return (
      <ParticipantDetailScreen
        participantId={participantId}
        idList={participants}
        goToOverallView={goToOverallView}
        goToParticipantView={goToParticipantView}
        goToDayView={goToDayView}
      />
    );
  }

  if (activeTab === "dayDetail") {
    return (
      <DayDetailScreen
        participantId={participantId}
        date={selectedDate}
        goToOverallView={goToOverallView}
        goToParticipantView={goToParticipantView}
        goToDayView={goToDayView}
      />
    );
  }

  const avgCompliance = averageOverallCompliance(participants);

  return (
    <div className="overall-screen">
      <h1 className="main-title">Participant Compliance Overview</h1>

      <div className="overall-compliance-header mb-8 text-center">
        <h2 className="text-4xl font-extrabold mb-2">
          Average Compliance: {avgCompliance}%
        </h2>
      </div>

      {/* WEEK NAV */}
      <div className="week-nav-wrapper">
        <button onClick={() => setWeekOffset(weekOffset + 1)} className="week-nav-button">
          <ChevronLeft size={20} /> Previous 7 Days
        </button>

        <span className="date-range-display">
          {displayStartDate} - {displayEndDate}
        </span>

        <button
          onClick={() => setWeekOffset(Math.max(0, weekOffset - 1))}
          disabled={weekOffset === 0}
          className="week-nav-button next-week-button"
        >
          Next 7 Days <ChevronRight size={20} />
        </button>
      </div>

      {loading && (
        <div className="message-container">
          <Loader2 className="animate-spin" size={40} />
          <p className="loading-text ml-4">Loading Compliance Data...</p>
        </div>
      )}

      {error && (
        <div className="message-container">
          <p className="error-text">{error}</p>
        </div>
      )}

      {!loading && !error && (
        <div className="table-wrapper custom-scrollbar">
          <div className="table-inner-container">

            {/* HEADER ROW */}
            <div className="header-row">
              <div className="header-cell header-participant-id">
                <input
                  type="text"
                  placeholder="Filter ID…"
                  value={idFilter}
                  onChange={(e) => setIdFilter(e.target.value)}
                  className="id-filter-input"
                />
              </div>

              {dayHeaders.map((d, index) => (
                <div key={index} className="header-cell header-daily-date">
                  <div>{d.shortDay}</div>
                  <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>
                    {d.shortDate}
                  </div>
                </div>
              ))}

              <div
                className="header-cell header-compliance-weekly clickable"
                onClick={() => toggleSort("weekly_passive")}
              >
                Weekly Passive {sortKey === "weekly_passive" ? (sortDir === "desc" ? "▲" : "▼") : ""}
              </div>

              <div
                className="header-cell header-compliance-weekly clickable"
                onClick={() => toggleSort("weekly_ema")}
              >
                Weekly <br /> EMA {sortKey === "weekly_ema" ? (sortDir === "desc" ? "▲" : "▼") : ""}
              </div>

              <div
                className="header-cell header-compliance-overall clickable"
                onClick={() => toggleSort("overall")}
              >
                Overall <br /> EMA {sortKey === "overall" ? (sortDir === "desc" ? "▲" : "▼") : ""}
              </div>
            </div>

            {/* DATA ROWS */}
            {processedParticipants.map(p => (
              <ParticipantRow
                key={p.id}
                participant={p}
                dayHeaders={dayHeaders}
                startDate={startDate}
                goToParticipantView={goToParticipantView}
                goToDayView={goToDayView}
              />
            ))}

          const ParticipantRow = React.memo(({ participant, dayHeaders, startDate, goToParticipantView, goToDayView }) => {
                const currentWeek = (participant.weeklyCompliance || []).find(
                  w => w.end_date === new Date(new Date(startDate).setDate(new Date(startDate).getDate() + 6))
                    .toISOString().split('T')[0]
                );

            return (
                <div className="participant-row">
                  <div
                    className="participant-id-cell cursor-pointer"
                    onClick={() => goToParticipantView(participant.id)}
                  >
                    <User size={16} />
                    <span className="ml-2">{participant.id}</span>
                  </div>
            
                  {dayHeaders.map((dayHeader, idx) => {
                    const dayDate = new Date(dayHeader.isoDate);
                    const studyStart = new Date(participant.study_start_date);
                    const completedThreshold = new Date(studyStart);
                    completedThreshold.setDate(studyStart.getDate() + 90);
            
                    let content = null;
            
                    if (dayDate < studyStart) {
                      content = "Not started";
                    } else if (dayDate > completedThreshold) {
                      content = "Completed";
                    } else {
                      const daily = (participant.dailyStatus || []).find(d => d.date === dayHeader.isoDate);
                      if (daily) {
                        content = (
                          <>
                            {daily.ema_done === 0 ? <XCircle color="#DB4325" size={24} /> :
                             daily.ema_done === 1 ? <CheckCircle color="#EDA247" size={24} /> :
                             daily.ema_done === 2 ? <CheckCircle color="#57C4AD" size={24} /> :
                             daily.ema_done === 3 ? <CheckCircle color="#006164" size={24} /> : null}
                          </>
                        );
                      }
                    }
            
                    return (
                      <div
                        key={idx}
                        className="daily-status-cell flex flex-col items-center justify-center cursor-pointer"
                        onClick={() =>
                          dayDate >= studyStart && dayDate <= completedThreshold && goToDayView(participant.id, dayHeader.isoDate)
                        }
                        style={
                          dayDate < studyStart || dayDate > completedThreshold
                            ? { color: "#A0A0A0", fontStyle: "italic" }
                            : {}
                        }
                        title={content && typeof content === 'string' ? content : ''}
                      >
                        {content}
                      </div>
                    );
                  })}
            
                  <CompliancePill value={currentWeek?.avg_passive_pct || 0} />
                  <CompliancePill value={currentWeek?.weekly_compliance || 0} />
                  <CompliancePill value={participant.overallCompliance || 0} />
                </div>
              );
            });

export default OverallScreen;

  
  
  
  
  
