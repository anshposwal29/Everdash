import React, { useCallback, useEffect, useState } from 'react';
import DayDetailScreen from './DayDetailScreen';

const isLocal = process.env.REACT_APP_LOCAL === 'true';
let API_BASE_URL;

if (isLocal) {
  API_BASE_URL = "http://localhost:8000";
} else {
  API_BASE_URL = "http://34.44.141.225/api"; // the public VM IP via Apache reverse proxy
}

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
];

const LOW_ACTIVITY_SENSORS = new Set([
  "battery",
  "light",
  "location",
  "accelerometer",
  "angular_velocity",
]);

export default function ParticipantDetailScreen({ participantId, idList, goToOverallView, goToParticipantView, goToDayView }) {
  const [newParticipantId, setNewParticipantId] = useState(""); // for changing participant ID
  const [excluded, setExcluded] = useState(false); 
  const [status, setStatus] = useState("");
  const [summaryLoading, setSummaryLoading] = useState(false); // replaces the old `loading` that was used for the summary
  const [updateLoading, setUpdateLoading] = useState(false);   // only for the Update button
  const [excludeLoading, setExcludeLoading] = useState(false); // for excluding participant IDs

  const [currentParticipantId, setCurrentParticipantId] = useState(() => participantId || "");

  const getCellClass = (sensor, value) => {
    if (!LOW_ACTIVITY_SENSORS.has(sensor) || typeof value !== "number") {
      return "";
    }
    if (value <= 6) return "activity-level-1";   // very low
    if (value <= 12) return "activity-level-2";   // low
    return "";
  };


  // --- Track current participant index ---
  const [currentIndex, setCurrentIndex] = useState(() => {
    return idList?.indexOf(currentParticipantId);
  });

  // --- Keep index in sync if parent changes `id` ---
  useEffect(() => {
    if (!idList || idList.length === 0) return;
    const idx = idList.indexOf(currentParticipantId);
    if (idx !== -1) {
      setCurrentIndex(idx);
    }
  }, [currentParticipantId, idList]);

  // --- Navigation helpers ---
  const abortRef = React.useRef(null);

  const changeParticipantBy = useCallback(
    (offset) => {
      if (!idList || idList.length === 0) return;

      // Abort in-flight request BEFORE changing participant
      abortRef.current?.abort();

      const nextIdx = currentIndex + offset;
      if (nextIdx >= 0 && nextIdx < idList.length) {
        setCurrentIndex(nextIdx);
        setCurrentParticipantId(idList[nextIdx].id);
      }
    },
    [currentIndex, idList]
  );

  const goPrev = useCallback(() => changeParticipantBy(-1), [changeParticipantBy]);
  const goNext = useCallback(() => changeParticipantBy(1), [changeParticipantBy]);

// update participant ID
  const handleUpdate = async (e) => {
    e.preventDefault();
    if (!newParticipantId.trim()) return;
    setUpdateLoading(true);
    setStatus("");

    try {
      const res = await fetch(`${API_BASE_URL}/update-participant-id`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ old_id: currentParticipantId, new_id: newParticipantId.trim() }),
      });

      const data = await res.json();
      if (data.success) {
        // 1️⃣ Overwrite the old id inside the *local* idList copy
        // (the parent component most likely passed a reference, so mutating it
        //  will keep the original ordering for the rest of the app)
        if (Array.isArray(idList) && currentIndex !== -1) {
          idList[currentIndex] = newParticipantId.trim(); // ← overwrite in‑place
        }
        // 2️⃣ Update the component state so the UI reflects the new id
        setCurrentParticipantId(newParticipantId.trim());

        setStatus(
          `Participant ID updated successfully: ${currentParticipantId} → ${newParticipantId.trim()}`
        );
        setNewParticipantId(""); // clear the input field
      } else {
        setStatus(`Error: ${data.error}`);
      }
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    } finally {
      setUpdateLoading(false);
    }
  };

  const handleExcludeToggle = async () => {
    setExcludeLoading(true);
    setStatus("");

    try {
      const res = await fetch(`${API_BASE_URL}/update-participant-exclude`, {
        method: "POST", // or PATCH
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ participant_id: currentParticipantId, excluded: !excluded }),
      });
      const data = await res.json();
      if (data.success) {
        setExcluded(!excluded);
        setStatus(
          `Participant ${currentParticipantId} is now ${!excluded ? "excluded" : "included"} in overview`
        );
      } else {
        setStatus(`Error: ${data.error}`);
      }
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    } finally {
      setExcludeLoading(false);
    }
  };

/////////////////////////////////////////////////////////////////////////////////////////////////

    const [activeTab, setActiveTab] = useState("participant");
    const [selectedDate, setSelectedDate] = useState("");

  // make participant data table
  const [summaryData, setSummaryData] = useState([]);
  const [error, setError] = useState(null);

  const formatYMD = useCallback((d) => {
    const yy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return `${yy}-${mm}-${dd}`;
  }, []);


useEffect(() => {
  if (!currentParticipantId) return;

  const controller = new AbortController();
  abortRef.current = controller;

  let isActive = true; // 🔑 track latest request

  const fetchSummary = async () => {
    setSummaryLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams({
        participant_id: currentParticipantId.trim(),
        // sensing_types: SENSING_TYPES.join(","),
      });

      const res = await fetch(
        `${API_BASE_URL}/participant_summary?${params.toString()}`,
        { signal: controller.signal }
      );

      if (!res.ok) throw new Error(`Backend responded ${res.status}`);
      const data = await res.json();

      if (isActive && !controller.signal.aborted) {
        setSummaryData(data);
      }
    } catch (err) {
      if (err.name !== "AbortError" && isActive) {
        console.error("Failed to fetch participant summary:", err);
        setError(err.message || "Failed to fetch participant summary");
      }
    } finally {
      if (isActive && !controller.signal.aborted) {
        setSummaryLoading(false);
      }
    }
  };

  fetchSummary();

  return () => {
    isActive = false;
    controller.abort();
    abortRef.current = null;
  };
}, [currentParticipantId]);

  const COLUMN_ORDER = [
    "pid",
    "study_start_date",
    "date",
    "ema_done",
    "ema_avg_response_time",
    "battery",
    "location",
    "accelerometer",
    "angular_velocity",
    "light",
    "screen_events",
    "phone",
    "sms",
    "app_usage",
    "passive_data_missing",
    "passive_available_pct"
  ];
  const COLUMN_LABELS = {
    pid: "Participant ID",
    //study_start_date: "Start Date",
    sms: "SMS",
    date: "Date",
    light: "Light",
    phone: "Phone",
    battery: "Battery",
    ema_done: "EMAs Completed",
    location: "Location",
    app_usage: "App Usage",
    accelerometer: "Accelerometer",
    screen_events: "Screen Events",
    angular_velocity: "Gyroscope",
    ema_avg_response_time: "Average EMA Response",
  };
  const HIDDEN_KEYS = new Set(["study_start_date", "passive_data_missing","passive_available_pct"]);
  const orderedKeys = (() => {
    if (!summaryData || summaryData.length === 0) return [];
    const dataKeys = Object.keys(summaryData[0]);
    // Keep only keys that exist in the data
    const ordered = COLUMN_ORDER.filter((key) => dataKeys.includes(key));
    // Optional: add any remaining keys not in the column order
    const remaining = dataKeys.filter((key) => !COLUMN_ORDER.includes(key));
    return [...ordered, ...remaining];
  })();

  // Export data for specific participant and date
  const [exportLoading, setExportLoading] = useState(false);
  const [exportError, setExportError] = useState(null);

  const handleExportDayData = async () => {
    setExportLoading(true);
    setExportError(null);

    try {
      const today = new Date();
      // Use the SAME participant + all date values
      const queryParams = new URLSearchParams({
        participant_id: currentParticipantId.trim(),
        // start_date: "auto",
        // end_date: formatYMD(today),
        sensing_types: [...SENSING_TYPES, "User Survey Responses"].join(",")  // export all displayed types
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
      a.download = `participant_${currentParticipantId}_all_data.zip`;
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

  if (activeTab === "participant") {
    return (
      <div className="p-6 bg-gray-50 min-h-screen">
        {/* Back button */}
        <button onClick={() => goToOverallView()} className="mb-4 text-blue-600 underline">
          &larr; Back to Overview
        </button>
        <button
          onClick={handleExportDayData}
          title={`That was easy`}
          disabled={exportLoading}
          className="mb-4 ml-4 px-3 py-2 bg-green-600 text-white rounded shadow hover:bg-green-700 disabled:opacity-50"
        >
          {exportLoading ? "Exporting..." : "Export Participant’s Data"}
        </button>

        {exportError && (
          <p className="text-red-600 mt-2">{exportError}</p>
        )}
        <div className="flex items-center mb-4 space-x-4">
          <button
            onClick={goPrev}
            aria-label="Previous participant"
            className="px-3 py-2 bg-gray-200 rounded hover:bg-gray-300"
          >
            ← Previous participant
          </button>
          <button
            onClick={goNext}
            aria-label="Next participant"
            className="px-3 py-2 bg-gray-200 rounded hover:bg-gray-300 ml-4"
          >
            Next participant →
          </button>
        </div>

        {/* Header */}
        <h2 className="text-2xl font-bold mb-2">Participant: {currentParticipantId}</h2>
        
         <h3 className="text-2xl font-bold mb-4 mt-6">Change Participant ID</h3>
         
        <div className="mb-4 p-4 border-l-4 border-blue-600 bg-blue-50 rounded-md">
            <p className="font-semibold text-gray-800 mb-2">
              ⚠ Important: How to handle participant numbers
            </p>
          
            <div className="text-sm text-gray-700 space-y-3">
              <div>
                <span className="font-medium">Option 1) Participant restarted (only uses new number)</span>
                <ul className="list-disc list-inside ml-5 mt-1">
                  <li>Step 1: Recode “old” number to negative number (e.g., 00034 → -00034)</li>
                  <li>Step 2: Exclude negative coded number from overview</li>
                </ul>
              </div>
          
              <div>
                <span className="font-medium">Option 2) Participant reinstalled the app (uses both numbers)</span>
                <ul className="list-disc list-inside ml-5 mt-1">
                  <li>Step 1: Recode “new” number to participant number</li>
                </ul>
              </div>
            </div>
          </div>
        

        {/* Form to update participant ID */}
        <form onSubmit={handleUpdate} className="max-w-md mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            New Participant ID:
          </label>
          <input
            type="text"
            value={newParticipantId}
            onChange={(e) => setNewParticipantId(e.target.value)}
            className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2 mb-2"
            placeholder="e.g., 03088"
            required
            disabled={updateLoading}
          />
          <button
            type="submit"
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 flex items-center justify-center"
            disabled={updateLoading}
          >
            {updateLoading && (
              <svg
                className="animate-spin h-5 w-5 mr-2 text-white"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                ></circle>
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v8H4z"
                ></path>
              </svg>
            )}
            {updateLoading ? "Updating..." : "Update Participant ID"}
          </button>
        </form>
        
        {/* Checkbox to exclude/include participant */}
        
        <h3 className="text-2xl font-bold mb-4 mt-6">Exclude Participant</h3>
        <div className="mb-4">
          <label className="inline-flex items-center space-x-2">
            <input
              type="checkbox"
              checked={excluded}
              onChange={handleExcludeToggle}
              disabled={excludeLoading}
              className="form-checkbox h-5 w-5 text-blue-600"
            />
            <span>Exclude from overview</span>
          </label>
        </div>
      

        {/* Status message */}
        {status && (
          <p className="mt-2 text-sm text-gray-800">
            {status}
          </p>
        )} 

        {/* Participant summary table header */}
        <h2 className="text-2xl font-bold mb-4 mt-6">Data Summary</h2>
        {summaryData.length > 0 && summaryData[0].study_start_date && (
          <p>
            <strong>Study Start Date:</strong> {summaryData[0].study_start_date}
          </p>
        )}

        <p> Click on a date to view the participant's data by day.</p>
        <p><strong>Units:</strong></p>
          <ul>
            <li>Sensors: number of unique hours with data</li>
            <li>Average EMA Response Time: seconds</li>
          </ul>

        {/* Legend */}
        <div className="legend flex items-center space-x-4 mb-2">
          <div className="flex flex-row items-center space-x-1">
            <div className="legend-box activity-level-legend-2"></div>
            <span>Low Activity (6 &lt; hours &le; 12)</span>
          </div>
          <div className="flex flex-row items-center space-x-1">
            <div className="legend-box activity-level-legend-1"></div>
            <span>Very Low Activity (hours ≤ 6)</span>
          </div>
        </div>

        {/* Loading / error / empty states */}
        {summaryLoading && <p>Loading summary...</p>}
        {error && <p className="text-red-600">{error}</p>}
        {!summaryLoading && !error && summaryData.length === 0 && <p>No data available.</p>}

        {/* Summary table */}

        {!summaryLoading && !error && summaryData.length > 0 && (
          <div className="overflow-x-auto">
            <table className="custom-table">
              <thead className="custom-thead">
                <tr className="custom-tr">
                  {orderedKeys.filter((key) => !HIDDEN_KEYS.has(key)).map((key) => (
                    <th key={key} className="custom-th">
                      {COLUMN_LABELS[key] ?? key}
                    </th>
                  ))}
                </tr>
              </thead> 
              <tbody>
                {summaryData.map((row, idx) => (
                  <tr key={idx} className="custom-tr-even centered-cell">
                    {orderedKeys.filter((key) => !HIDDEN_KEYS.has(key)).map((key) => {
                      let value = row[key];
                      let displayValue = value;
                      if (value && typeof value === "object") {
                        displayValue = JSON.stringify(value);
                      }
                      // Make the Date column clickable
                      if (key === "date") {
                        return (
                          <td
                            key={key}
                            className="daily-status-cell flex flex-col items-center space-y-1 cursor-pointer custom-td"
                            onClick={() => goToDayView(row.pid, value)}
                          >
                            {displayValue ?? "—"}
                          </td>
                        );
                      }
                      // Regular cell
                      const cellClass =
                        LOW_ACTIVITY_SENSORS.has(key)
                          ? getCellClass(key, Number(value))
                          : "";
                      return (
                        <td key={key} className={`custom-td ${cellClass}`}>
                          {value ?? "—"}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }
}