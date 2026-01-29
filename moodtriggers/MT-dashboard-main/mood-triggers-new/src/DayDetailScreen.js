
import React, { useCallback, useEffect, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';

const isLocal = process.env.REACT_APP_LOCAL === 'true';
const API_BASE_URL = isLocal ? "http://localhost:8000" : "http://34.44.141.225/api";

const PALETTE = [
  '#4CAF50', '#FFD700', '#8A2BE2', '#E2725B', '#4682B4', 
  '#CD5C5C', '#DA70D6', '#20B2AA', '#007ACC', '#FFA040'
];

const SENSING_TYPES = [
  'Battery',
  'Light',
  'Location',
  'Accelerometer',
  'Gyroscope',
  'Screen Events',
  'Phone',
  'SMS',
  'App Usage',
  'User Survey Responses'
];

// create a consistent color mapping for types
const TYPE_COLOR = {};
SENSING_TYPES.forEach((t, i) => {
  TYPE_COLOR[t] = PALETTE[i % PALETTE.length];
});

// add this grouping & color map near your constants
const GROUPS = [
  ["Battery"],
  ["Accelerometer", "Gyroscope"],
  ["Light"],
  ["Location"],
  ["Screen Events"],
  ["Phone", "SMS", "App Usage"],
  ["User Survey Responses"]
];

export default function DayDetailScreen({ participantId, date, goToOverallView, goToParticipantView, goToDayView, onDateChange }) {
  // instead of using `date` directly, manage local date state
  const [currentDate, setCurrentDate] = useState(() => {const d = date ? new Date(date + "T00:00:00") : new Date(); return d;});
  const [plotData, setPlotData] = useState([]);
  const [plotLoading, setPlotLoading] = useState(false);
  const [plotError, setPlotError] = useState(null);

  const [emaData, setEmaData] = useState([]);
  const [emaLoading, setEmaLoading] = useState(false);
  const [emaError, setEmaError] = useState(null);

useEffect(() => {
  if (date) {
    const parsed = new Date(date + "T00:00:00");
    console.log("useEffect parsed date:", parsed);
    setCurrentDate(parsed);
  }
}, [date]);


  const formatYMD = useCallback((d) => {
    const yy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yy}-${mm}-${dd}`;
  }, []);

  const changeDateBy = useCallback(
    (days) => {
      const next = new Date(currentDate);
      next.setDate(next.getDate() + days);
      setCurrentDate(next);
      onDateChange?.(formatYMD(next));
    },
    [currentDate, onDateChange, formatYMD]
  );

  const goPrev = useCallback(() => changeDateBy(-1), [changeDateBy]);
  const goNext = useCallback(() => changeDateBy(1), [changeDateBy]);

  // finds when no data for sensor
  function isChartEmpty(data, types) {
    if (!data || data.length === 0) return true;
    return !data.some(row => types.some(t => row[t] !== null && row[t] !== undefined)
    );
  }
function NoDataOverlay() {
  return (
    <div className="no-data-overlay">
      <span>No Data</span>
    </div>
  );
}


  // --- Fetch Plot Data ---
  useEffect(() => {
    const fetchPlotData = async () => {
      setPlotLoading(true);
      setPlotError(null);

      try {
        const params = new URLSearchParams({
          participant_id: participantId.trim(),
          start_date: formatYMD(currentDate),
          end_date: formatYMD(currentDate),
          sensing_types: SENSING_TYPES.join(",")
        });

        const res = await fetch(`${API_BASE_URL}/sensing_data_dayDetail?${params.toString()}`);
        if (!res.ok) throw new Error(`Backend responded ${res.status}`);
        const data = await res.json();

        // Flatten into timestamp-indexed map
        const expandedMap = {};
        data.forEach(dayEntry => {
          SENSING_TYPES.forEach(type => {
            const values = dayEntry[type] || [];
            values.forEach(v => {
              const ts = new Date(v.ts);
              const label = ts.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
              if (!expandedMap[label]) {
                expandedMap[label] = { timestamp: label };
                SENSING_TYPES.forEach(t => expandedMap[label][t] = null);
              }
              expandedMap[label][type] = v.val;
            });
          });
        });

        const expandedArray = Object.values(expandedMap).sort((a, b) => a.timestamp.localeCompare(b.timestamp));
        setPlotData(expandedArray);
      } catch (err) {
        console.error("Plot data fetch failed:", err);
        setPlotError(err.message || "Failed to fetch plot data");
      } finally {
        setPlotLoading(false);
      }
    };

    fetchPlotData();
  }, [participantId, currentDate]);

//////////////////////////////////////////////////////////////////////////////////////////////////////////
  // --- Fetch EMA Responses ---
  useEffect(() => {
    const fetchEMAData = async () => {
      setEmaLoading(true);
      setEmaError(null);

      try {
        const paramsEMA = new URLSearchParams({
          participant_id: participantId.trim(),
          start_date: formatYMD(currentDate),
          end_date: formatYMD(currentDate),
          sensing_types: "All EMA Responses"
        });

        const resEMA = await fetch(`${API_BASE_URL}/sensing_data_dayDetail?${paramsEMA.toString()}`);
        if (!resEMA.ok) throw new Error(`Backend responded ${resEMA.status}`);
        const dataEMA = await resEMA.json();

        // Flatten all EMA responses
        const allResponses = [];
        dataEMA.forEach(dayEntry => {
          (dayEntry["All EMA Responses"] || []).forEach(r => allResponses.push(r));
        });

        // setEmaData(allResponses);
        // Sort by SurveyID first, then by QuestionNumber
        const sorted = [...allResponses].sort((a, b) => {
          const sA = Number(a.SurveyID) || 0;
          const sB = Number(b.SurveyID) || 0;

          if (sA !== sB) return sA - sB;

          const qA = Number(a.QuestionNumber) || 0;
          const qB = Number(b.QuestionNumber) || 0;

          return qA - qB;
        });

        setEmaData(sorted);
      } catch (err) {
        console.error("EMA fetch failed:", err);
        setEmaError(err.message || "Failed to fetch EMA data");
      } finally {
        setEmaLoading(false);
      }
    };

    fetchEMAData();
  }, [participantId, currentDate]);

  //////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Export data for specific participant and date
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState(null);

  const handleExportDayData = async () => {
    setExportLoading(true);
    setExportError(null);

    try {
      // Use the SAME participant + date values already passed into this screen
      const queryParams = new URLSearchParams({
        participant_id: participantId.trim(),
        start_date: formatYMD(currentDate),
        end_date: formatYMD(currentDate),
        sensing_types: SENSING_TYPES.join(",")  // export all displayed types
      });
      console.log(queryParams.toString())
      const response = await fetch(`${API_BASE_URL}/export_data?${queryParams.toString()}`);

      if (!response.ok) {
        const text = await response.text();
        throw new Error(`Export failed with status ${response.status}: ${text}`);
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);

      const a = document.createElement("a");
      a.href = url;
      a.download = `participant_${participantId}_data_${formatYMD(currentDate)}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

    } catch (err) {
      console.error("Export error:", err);
      setExportError(err.message);
    } finally {
      setExportLoading(false);
    }
  };

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <button onClick={goToOverallView} className="mb-4 text-blue-600 underline">
        &larr; Back to Overview
      </button>
      <button
        onClick={handleExportDayData}
        title={`That was easy`}
        disabled={exportLoading}
        className="mb-4 ml-4 px-3 py-2 bg-green-600 text-white rounded shadow hover:bg-green-700 disabled:opacity-50"
      >
        {exportLoading ? "Exporting..." : "Export This Day’s Data"}
      </button>
    <div>
      <button onClick={() => goToParticipantView(participantId)} className="mb-4 text-blue-600 underline">
        &larr; Back to Participant View
      </button>
    </div>
      

      {exportError && (
        <p className="text-red-600 mt-2">{exportError}</p>
      )}
      <div className="flex items-center mb-4 space-x-4">
        <button
          onClick={goPrev}
          aria-label="Previous day"
          className="px-3 py-2 bg-gray-200 rounded hover:bg-gray-300"
        >
          ← Previous Day
        </button>
        <button
          onClick={goNext}
          aria-label="Next day"
          className="px-3 py-2 bg-gray-200 rounded hover:bg-gray-300 ml-4"
        >
          Next Day →
        </button>
      </div>
      <h2 className="text-2xl font-bold mb-2" style={{ fontFamily: 'Comic Sans MS, Comic Sans, cursive' }}>
        Participant Day Details
      </h2>
      <p className="mb-4">
        Participant: <strong>{participantId}</strong> | Date: <strong>{formatYMD(currentDate)}</strong>
      </p>
      
      {/* --- Plot Section --- */}
      <div className="bg-white p-6 rounded-lg shadow-md mb-6">
        {plotLoading ? (
          <p className="text-gray-500 text-lg text-center">Loading plot data...</p>
        ) : plotError ? (
          <p className="text-red-500 text-lg text-center">{plotError}</p>
        ) : plotData.length > 0 ? (
          <div className="space-y-6">
          {GROUPS.map((group, gi) => {
            const metricsMap = {
              Battery: "avg percent",
              Accelerometer: "avg magnitude",
              Gyroscope: "avg magnitude",
              Light: "avg illuminance",
              Location: "avg altitude",
              "Screen Events": "count",
              Phone: "count",
              SMS: "count",
              "App Usage": "count",
              "User Survey Responses": "avg response time",
            };

            const groupMetric =
              group.length > 1
                ? `${group.join(", ")}: ${metricsMap[group[0]]}`
                : `${group[0]}: ${metricsMap[group[0]]}`;

            const empty = isChartEmpty(plotData, group);

            return (
              <div key={gi} className="chart-container">
                {/* Title */}
                <h3 className="text-lg font-medium mb-1">{groupMetric}</h3>
                <div className="relative">
                  <ResponsiveContainer width="100%" height={160}>
                    <LineChart data={plotData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="timestamp" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      {group.map(type => (
                        <Line
                          key={type}
                          type="monotone"
                          dataKey={type}
                          stroke={TYPE_COLOR[type] || "#8884d8"}
                          activeDot={{ r: 6 }}
                          strokeWidth={2}
                          connectNulls
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                  {/* Conditionally render the overlay when 'empty' is true */}
                  {empty && <NoDataOverlay />}
                </div>
              </div>
            );
          })}
          </div>
        ) : (
          <p className="text-gray-500 text-lg text-center">No plot data available.</p>
        )}
      </div>

      {/* --- EMA Table Section --- */}
      <h3 className="text-2xl font-bold mb-2">EMA Responses</h3>
      <div className="overflow-y-auto bg-white p-4 rounded-lg shadow-md" style={{ maxHeight: "450px", overflowY: "auto" }}>
        {emaLoading ? (
          <p>Loading EMA responses...</p>
        ) : emaError ? (
          <p>Error: {emaError}</p>
        ) : emaData.length === 0 ? (
          <p>No EMA responses found for this day.</p>
        ) : (
          <table className="custom-table">
            <thead className="custom-thead">
              <tr className="custom-tr">
                <th className="custom-th">Timestamp</th>
                <th className="custom-th">Survey ID</th>
                <th className="custom-th">Questionnaire Type</th>
                <th className="custom-th">Question Number</th>
                <th className="custom-th">Question Text</th>
                <th className="custom-th">Response</th>
              </tr>
            </thead>

            <tbody>
              {emaData.map((row, idx) => (
                <tr key={idx} className="custom-tr-even">
                  <td className="custom-td">{new Date(row.Timestamp).toISOString().slice(0, 19).replace("T", " ")}</td>
                  <td className="custom-td">{row.SurveyID}</td>
                  <td className="custom-td">{row.QuestionnaireType}</td>
                  <td className="custom-td">{row.QuestionNumber}</td>
                  <td className="custom-td">{row.QuestionText}</td>
                  <td className="custom-td">{row.Response}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
