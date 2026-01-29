// OverallScreen.js

import React, { useState, useEffect } from 'react';
// Removed BatteryCharging import as it's no longer used
import { FileText, CheckCircle, XCircle, ChevronLeft, ChevronRight, Sun } from 'lucide-react';

const API_BASE_URL = "http://localhost:8001"; // Ensure this matches your FastAPI port


const OverallScreen = () => {
    console.log("OverallScreen component is rendering!");
    const [weekOffset, setWeekOffset] = useState(0);
    const [participants, setParticipants] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [allParticipantIds, setAllParticipantIds] = useState([]);

    const getWeekDateRange = (offset) => {
        const today = new Date();
        const currentDayOfWeek = today.getDay(); 

        const startOfWeek = new Date(today);
        startOfWeek.setDate(today.getDate() - currentDayOfWeek - (offset * 7));
        startOfWeek.setHours(0, 0, 0, 0); 

        const endOfWeek = new Date(startOfWeek);
        endOfWeek.setDate(startOfWeek.getDate() + 6);
        endOfWeek.setHours(23, 59, 59, 999); 

        return {
            startDate: startOfWeek.toISOString().split('T')[0],
            endDate: endOfWeek.toISOString().split('T')[0],
            displayStartDate: startOfWeek.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
            displayEndDate: endOfWeek.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
        };
    };

    const fetchParticipantIds = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/participants`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            setAllParticipantIds(data);
        } catch (error) {
            console.error("Failed to fetch participant IDs:", error);
            setError("Failed to load participant data.");
        }
    };

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        const { startDate, endDate } = getWeekDateRange(weekOffset);

        if (allParticipantIds.length === 0) {
            setLoading(false);
            return; // No participants to fetch data for
        }

        const newParticipants = [];

        try {
            // Fetch Illuminance status for ALL participants first (since backend /daily_illuminance_status doesn't filter by participant)
            const allIlluminanceResponse = await fetch(`${API_BASE_URL}/daily_illuminance_status?start_date=${startDate}&end_date=${endDate}`);
            if (!allIlluminanceResponse.ok) throw new Error(`Illuminance status fetch failed: ${allIlluminanceResponse.status}`);
            const allIlluminanceData = await allIlluminanceResponse.json();
            // Create a map for quick lookup: { participant_id: { date: { illuminance_present: true/false } } }
            const illuminanceMap = new Map();
            allIlluminanceData.forEach(d => {
                if (!illuminanceMap.has(d.participant_id)) {
                    illuminanceMap.set(d.participant_id, new Map());
                }
                illuminanceMap.get(d.participant_id).set(d.date, { illuminance_present: d.illuminance_present });
            });


            for (const participantId of allParticipantIds) {
                // Fetch EMA status for the specific participant
                // --- CHANGED: Endpoint path to include participantId ---
                const emaResponse = await fetch(`${API_BASE_URL}/ema_status/${participantId}?start_date=${startDate}&end_date=${endDate}`);
                if (!emaResponse.ok) throw new Error(`EMA status fetch failed: ${emaResponse.status}`);
                const emaData = await emaResponse.json();

                const dailyStatusMap = new Map();

                // Populate with EMA data
                emaData.forEach(d => {
                    dailyStatusMap.set(d.date, {
                        date: d.date,
                        ema_done: d.ema_done,
                        illuminance_present: false // Default to false, will be updated by illuminance data if available
                    });
                });

                // Populate/update with Illuminance data for this participant
                const participantIlluminanceData = illuminanceMap.get(participantId) || new Map();
                for (const [date, data] of participantIlluminanceData.entries()) {
                    dailyStatusMap.set(date, {
                        ...dailyStatusMap.get(date), // Keep existing EMA status
                        date: date,
                        illuminance_present: data.illuminance_present
                    });
                }

                const weekData = [];
                let currentDay = new Date(startDate);
                while (currentDay <= new Date(endDate)) {
                    const dateStr = currentDay.toISOString().split('T')[0];
                    const status = dailyStatusMap.get(dateStr) || {
                        date: dateStr,
                        ema_done: false, // Default if no EMA data for the day
                        illuminance_present: false // Default if no Illuminance data for the day
                    };
                    weekData.push(status);
                    currentDay.setDate(currentDay.getDate() + 1);
                }

                // Fetch compliance data
                const complianceResponse = await fetch(`${API_BASE_URL}/compliance/${participantId}?start_date=${startDate}&end_date=${endDate}`);
                if (!complianceResponse.ok) throw new Error(`Compliance fetch failed: ${complianceResponse.status}`);
                const complianceData = await complianceResponse.json();
                
                const weeklyCompliance = complianceData.weekly_compliance;
                const overallCompliance = complianceData.overall_compliance;

                newParticipants.push({
                    id: participantId,
                    dailyStatus: weekData,
                    weeklyCompliance: weeklyCompliance,
                    overallCompliance: overallCompliance,
                });
            }
            setParticipants(newParticipants);

        } catch (err) {
            console.error("Failed to fetch data:", err);
            setError("Failed to load data. Please check the backend connection and database.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchParticipantIds();
    }, []);

    useEffect(() => {
        if (allParticipantIds.length > 0) {
            fetchData();
        }
    }, [weekOffset, allParticipantIds]);


    const handlePreviousWeek = () => {
        setWeekOffset(prev => prev + 1);
    };

    const handleNextWeek = () => {
        setWeekOffset(prev => Math.max(0, prev - 1));
    };

    const { displayStartDate, displayEndDate } = getWeekDateRange(weekOffset);

    const getComplianceColorClass = (compliance) => {
        if (compliance >= 80) return 'compliance-green';
        if (compliance >= 50) return 'compliance-yellow';
        return 'compliance-red';
    };

    return (
        <div className="overall-screen">
            <h1 className="main-title">Participant Overview</h1>

            <div className="week-nav-wrapper">
                <button
                    onClick={handlePreviousWeek}
                    className="week-nav-button"
                >
                    <ChevronLeft size={20} /> Previous Week
                </button>
                <div className="date-range-display">
                    {displayStartDate} - {displayEndDate}
                </div>
                <button
                    onClick={handleNextWeek}
                    className="week-nav-button next-week-button"
                    disabled={weekOffset === 0}
                >
                    Next Week <ChevronRight size={20} />
                </button>
            </div>

            {loading ? (
                <div className="message-container">
                    <div className="loading-text">Loading participant data...</div>
                </div>
            ) : error ? (
                <div className="message-container">
                    <div className="error-text">{error}</div>
                </div>
            ) : (
                <div className="table-wrapper custom-scrollbar">
                    <div className="table-inner-container">
                        {/* Header Row */}
                        <div className="header-row">
                            <div className="header-cell header-participant-id">Participant ID</div>
                            <div className="header-daily-status-container">
                                {/* Only show day of month for daily headers */}
                                {participants.length > 0 && participants[0].dailyStatus.map(day => (
                                    <div key={day.date} className="header-cell header-daily-date">
                                        {day.date.split('-')[2]}
                                    </div>
                                ))}
                            </div>
                            <div className="header-cell header-compliance-weekly">Weekly (%)</div>
                            <div className="header-cell header-compliance-overall">Overall (%)</div>
                        </div>

                        {/* Participant Rows */}
                        {participants.map(participant => (
                            <div key={participant.id} className="participant-row">
                                <div className="participant-id-cell">
                                    <FileText size={16} />
                                    {participant.id}
                                </div>
                                <div className="daily-status-row-container">
                                    {participant.dailyStatus.map(day => (
                                        <div
                                            key={`${participant.id}-${day.date}`}
                                            className="daily-status-cell"
                                        >
                                            {/* EMA Status Icon */}
                                            {day.ema_done ? (
                                                <CheckCircle className="ema-icon-green" size={18} />
                                            ) : (
                                                <XCircle className="ema-icon-red" size={18} />
                                            )}
                                            {/* Illuminance Status Icon - directly rendered, no extra wrapper */}
                                            {day.illuminance_present && <Sun className="illuminance-icon-yellow" size={16} />}
                                        </div>
                                    ))}
                                </div>
                                <div className={`compliance-cell weekly-compliance-cell ${getComplianceColorClass(participant.weeklyCompliance)}`}>
                                    <span>{participant.weeklyCompliance}%</span>
                                </div>
                                <div className={`compliance-cell ${getComplianceColorClass(participant.overallCompliance)}`}>
                                    <span>{participant.overallCompliance}%</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default OverallScreen;