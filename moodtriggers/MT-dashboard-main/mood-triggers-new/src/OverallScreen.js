// OverallScreen.js
import React, { useState, useEffect, useCallback } from 'react';
import { User, CheckCircle, Circle, XCircle, ChevronLeft, ChevronRight, Loader2, MapPin, Activity, BatteryLow, RotateCcw } from 'lucide-react';
import DayDetailScreen from './DayDetailScreen';
import ParticipantDetailScreen from './ParticipantDetailScreen';

const isLocal = process.env.REACT_APP_LOCAL === 'true';
const API_BASE_URL = isLocal ? "http://localhost:8000" : "http://34.44.141.225/api";

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

/** Paint compliance pill */
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

  // Navigation functions
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

  // Legend component
  const DailyStatusLegend = () => {
    const emaItems = [
      { icon: <CheckCircle color="#006164" size={16} />, label: "3 EMAs" },
      { icon: <CheckCircle color="#57C4AD" size={16} />, label: "2 EMAs" },
      { icon: <CheckCircle color="#EDA247" size={16} />, label: "1 EMA" },
      { icon: <XCircle color="#DB4325" size={16} />, label: "None" },
    ];

    const sensorItems = [

      { icon: <MapPin color="#222222" size={16} />, label: "Location" },
      { icon: <BatteryLow color="#222222" size={16} />, label: "Battery" },
      { icon: <Activity color="#222222" size={16} />, label: "Accelerometer" },
      { icon: <RotateCcw color="#222222" size={16} />, label: "Gyroscope" },
    ];

    const passiveColorItems = [
      { icon: <Circle fill="#006164" stroke="#006164" size={14} />, label: "≥12h" },
      { icon: <Circle fill="#EDA247" stroke="#EDA247" size={14} />, label: "<12h" },
      { icon: <Circle fill="#DB4325" stroke="#DB4325" size={14} />, label: "Missing" },
    ];

    return (
      <table className="legend-table text-sm mt-4 mb-4 w-full">
        <tbody>
          <tr>
            {emaItems.map((item, idx) => (
              <td key={idx} className="px-3 py-1 flex items-center gap-1 whitespace-nowrap">
                {item.icon} <span>{item.label}</span>
              </td>
            ))}
          </tr>
          <tr>
            {sensorItems.map((item, idx) => (
              <td key={idx} className="px-3 py-1 flex items-center gap-1 whitespace-nowrap">
                {item.icon} <span>{item.label}</span>
              </td>
            ))}
          </tr>
          <tr>
            {passiveColorItems.map((item, idx) => (
              <td key={idx} className="px-3 py-1 flex items-center gap-1 whitespace-nowrap">
                {item.icon} <span>{item.label}</span>
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    );
  };

  // Week range calculation
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

  // Fetch participants
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
        .map(p => ({ ...p, study_start_date: new Date(p.study_start_date) }))
        .sort((a, b) => b.study_start_date - a.study_start_date);

      setParticipants(cleaned);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [weekOffset]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Day headers for table
  const { displayStartDate, displayEndDate, startDate } = getWeekDateRange(weekOffset);
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

  // Average overall compliance
  const averageOverallCompliance = (participants) => {
    const included = (participants || []).filter(p => !p.excluded && !p.id.startsWith("-"));
    if (included.length === 0) return 0;
    const total = included.reduce((sum, p) => sum + (p.overallCompliance || 0), 0);
    return Math.round(total / included.length);
  };

  // --- Conditional rendering for tabs ---
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

  // Default: overall view
  const avgCompliance = averageOverallCompliance(participants);
  return (
    <div className="overall-screen">
      <h1 className="main-title">Participant Compliance Overview</h1>
      <div className="overall-compliance-header mb-8 text-center">
        <h2 className="text-4xl font-extrabold mb-2">Average EMA Compliance: {avgCompliance}%</h2>
      </div>

      <div className="week-nav-wrapper">
        <button onClick={() => setWeekOffset(weekOffset + 1)} className="week-nav-button">
          <ChevronLeft size={20} /> Previous 7 Days
        </button>
        <span className="date-range-display">{displayStartDate} - {displayEndDate}</span>
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
          <Loader2 className="animate-spin text-blue-500" size={40} />
          <p className="loading-text ml-4">Loading Compliance Data...</p>
        </div>
      )}

      {error && <div className="message-container"><p className="error-text">{error}</p></div>}

      <DailyStatusLegend />

      {!loading && !error && (
        <div className="table-wrapper custom-scrollbar" style={{ "--num-days": dayHeaders.length }}>
          <div className="table-inner-container">
            <div className="header-row">
              <div className="header-cell header-participant-id">Participant</div>
              <div className="header-cell header-compliance-overall">Days <br /> in Study</div>
              {dayHeaders.map((d, i) => (
                <div key={i} className="header-cell header-daily-date">
                  <div>{d.shortDay}</div>
                  <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>{d.shortDate}</div>
                </div>
              ))}
              <div className="header-cell header-compliance-weekly">Weekly <br /> EMA</div>
              <div className="header-cell header-compliance-overall">Overall <br /> EMA</div>
               <div className="header-cell header-compliance-weekly">Weekly <br /> Passive </div>
                <div className="header-cell header-compliance-weekly">Overall <br /> Passive </div>
            </div>

            {participants
              .slice()
              .sort((a, b) => {
                const now = new Date();
                const aOld = now - new Date(a.study_start_date) > 90 * 24 * 60 * 60 * 1000;
                const bOld = now - new Date(b.study_start_date) > 90 * 24 * 60 * 60 * 1000;
                if (aOld && !bOld) return 1;
                if (!aOld && bOld) return -1;
                const weekA = (a.weeklyCompliance || []).find(w => w.start_date === startDate);
                const weekB = (b.weeklyCompliance || []).find(w => w.start_date === startDate);
                return (weekA?.weekly_compliance || 0) - (weekB?.weekly_compliance || 0);
              })
              .map((participant) => {
                const currentWeek = (participant.weeklyCompliance || []).find(
                  w => w.end_date === new Date(new Date(startDate).setDate(new Date(startDate).getDate() + 6)).toISOString().split('T')[0]
                );

                // Compute days in study
                const studyStart = new Date(participant.study_start_date);
                const today = new Date();
                const studyDayMax = 90;
                const daysInStudy = Math.min(studyDayMax,Math.floor((today - studyStart) / (1000 * 60 * 60 * 24)));
            
                return (
                  <div key={participant.id} className="participant-row">
                    {/* Participant ID */}
                    <div
                      className="participant-id-cell cursor-pointer"
                      onClick={() => goToParticipantView(participant.id)}
                      title={`Click to view details for ${participant.id}`}
                    >
                      <User size={16} />
                      <span className="ml-2">{participant.id}</span>
                    </div>
                    {/* Days in Study column */}
                    <div
                      className="daily-status-cell"
                      title={`Days since study start: ${daysInStudy}`}
                    >
                      {daysInStudy}
                    </div>
                    {/* Daily status cells */}
                    {dayHeaders.map((dayHeader, idx) => {
                      const dayDate = new Date(dayHeader.isoDate);
                      const studyStart = new Date(participant.study_start_date);
                      const completedThreshold = new Date(studyStart);
                      completedThreshold.setDate(studyStart.getDate() + 90);

                      let content = null;
                      let title = "";

                      if (dayDate < studyStart) {
                        content = "Not started";
                        title = "Study not started";
                      } else if (dayDate > completedThreshold) {
                        content = "Completed";
                        title = "Study completed";
                      } else {
                        const daily = (participant.dailyStatus || []).find(d => d.date === dayHeader.isoDate);
                        if (daily) {
                          content = (
                            <>
                              {daily.ema_done === 0 ? <XCircle color="#DB4325" size={24} /> :
                               daily.ema_done === 1 ? <CheckCircle color="#EDA247" size={24} /> :
                               daily.ema_done === 2 ? <CheckCircle color="#57C4AD" size={24} /> :
                               daily.ema_done === 3 ? <CheckCircle color="#006164" size={24} /> : null}

                              <div className="flex items-center space-x-1">
                                {daily.location !== undefined && <MapPin color={daily.location >= 12 ? "#006164" : daily.location > 0 ? "#EDA247" : "#DB4325"} size={18} />}
                                {daily.battery !== undefined && <BatteryLow color={daily.battery >= 12 ? "#006164" : daily.battery > 0 ? "#EDA247" : "#DB4325"} size={18} />}
                                {daily.accelerometer !== undefined && <Activity color={daily.accelerometer >= 12 ? "#006164" : daily.accelerometer > 0 ? "#EDA247" : "#DB4325"} size={18} />}
                                {daily.angular_velocity !== undefined && <RotateCcw color={daily.angular_velocity >= 12 ? "#006164" : daily.angular_velocity > 0 ? "#EDA247" : "#DB4325"} size={16} />}
                              </div>
                            </>
                          );
                          title = `Click to view details for ${participant.id} on ${dayHeader.isoDate}`;
                        }
                      }

                      return (
                        <div
                          key={idx}
                          className="daily-status-cell flex flex-col items-center justify-center cursor-pointer"
                          title={title}
                          onClick={() => dayDate >= studyStart && dayDate <= completedThreshold && goToDayView(participant.id, dayHeader.isoDate)}
                          style={content === "Not started" || content === "Completed" ? { color: "#A0A0A0", fontStyle: "italic" } : {}}
                        >
                          {content}
                        </div>
                      );
                    })}

                    <CompliancePill value={currentWeek?.weekly_compliance || 0} />
                    <CompliancePill value={participant.overallCompliance || 0} />
                    <CompliancePill value={currentWeek?.avg_passive_pct || 0} />
                    <CompliancePill value={participant.overallPassive || 0} />
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
};

export default OverallScreen;