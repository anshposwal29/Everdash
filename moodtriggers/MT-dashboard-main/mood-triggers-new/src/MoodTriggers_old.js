// MoodTriggers.js
import React, { useState, useEffect } from 'react';
import { Users, Download, BarChart2, CheckCircle, XCircle, ChevronLeft, ChevronRight } from 'lucide-react';

// IMPORTANT: Import RawDataScreen
import RawDataScreen from './RawDataScreen';

// IMPORTANT: Import OverallScreen - ADD THIS LINE
import OverallScreen from './OverallScreen'; // Ensure this path is correct

// REMOVE: getDummyDatesWithBatteryData function - This logic is now in OverallScreen.js or handled by your backend
// REMOVE: generateParticipantOverallData function - This logic is now in OverallScreen.js or handled by your backend
// REMOVE: MissingBatteryDot function - This logic is now in OverallScreen.js
// REMOVE: getComplianceColor function - This logic is now in OverallScreen.js
// REMOVE: getDayName function - This logic is now in OverallScreen.js

const MoodTriggers = () => {
    // State for managing active tab/screen
    const [activeTab, setActiveTab] = useState('overall'); // 'overall', 'rawData', or 'export'

    // REMOVE: All state related to OverallScreen functionality as it's now in OverallScreen.js
    // const [weekOffset, setWeekOffset] = useState(0);
    // const [participants, setParticipants] = useState([]);
    // const [loading, setLoading] = useState(true);
    // const [error, setError] = useState(null);

    // REMOVE: This useEffect and its contents, as the fetching logic is now in OverallScreen.js
    // useEffect(() => {
    //     const fetchOverallData = async () => {
    //         // ... (existing fetching logic moved to OverallScreen.js)
    //     };
    //     fetchOverallData();
    // }, [weekOffset]);

    // REMOVE: getWeekDateRange function - This logic is now in OverallScreen.js
    // REMOVE: getComplianceColorClass function - This logic is now in OverallScreen.js

    const [participantId, setParticipantId] = useState('');
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [sensingTypes] = useState([
        'Location',
        'AngV', // Gyroscope
        'Acc', // Accelerometer
        'Light', // Light Sensor (Illuminance)
        'Battery',
        'EMA_response' // User Survey Responses
    ]);
    const [selectedExportTypes, setSelectedExportTypes] = useState([]);
    const [loadingExport, setLoadingExport] = useState(false);
    const [exportError, setExportError] = useState(null);


    const handleExportTypeChange = (event) => {
        const { value, checked } = event.target;
        setSelectedExportTypes(prev =>
            checked ? [...prev, value] : prev.filter(type => type !== value)
        );
    };

    const handleAllExportTypesChange = (event) => {
        if (event.target.checked) {
            setSelectedExportTypes(sensingTypes);
        } else {
            setSelectedExportTypes([]);
        }
    };

    const handleExportSubmit = async (event) => {
        event.preventDefault();
        setLoadingExport(true);
        setExportError(null);

        try {
            const queryParams = new URLSearchParams({
                participant_id: participantId,
                start_date: startDate,
                end_date: endDate,
                sensing_types: selectedExportTypes.join(',')
            }).toString();

            const response = await fetch(`http://localhost:8001/export_data?${queryParams}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `data_export_${participantId}_${startDate}_to_${endDate}.zip`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);

        } catch (err) {
            console.error("Failed to export data:", err);
            setExportError(err.message);
        } finally {
            setLoadingExport(false);
        }
    };

    // REMOVE: goToPreviousWeek and goToNextWeek functions - now in OverallScreen.js

    // REMOVE: displayStartDate and displayEndDate - now in OverallScreen.js


    return (
        <div className="min-h-screen bg-gray-100">
            <header className="bg-white shadow-sm">
                <nav className="container mx-auto px-4 py-4 flex justify-between items-center">
                    <div className="text-2xl font-bold text-gray-800">MoodTriggers Dashboard</div>
                    <div className="flex space-x-4">
                        <button
                            onClick={() => setActiveTab('overall')}
                            className={`flex items-center px-4 py-2 rounded-md text-sm font-medium ${activeTab === 'overall' ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-200'}`}
                        >
                            <Users size={20} className="mr-2" /> Overall
                        </button>
                        <button
                            onClick={() => setActiveTab('rawData')}
                            className={`flex items-center px-4 py-2 rounded-md text-sm font-medium ${activeTab === 'rawData' ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-200'}`}
                        >
                            <BarChart2 size={20} className="mr-2" /> Raw Data
                        </button>
                        <button
                            onClick={() => setActiveTab('export')}
                            className={`flex items-center px-4 py-2 rounded-md text-sm font-medium ${activeTab === 'export' ? 'bg-blue-600 text-white' : 'text-gray-700 hover:bg-gray-200'}`}
                        >
                            <Download size={20} className="mr-2" /> Export
                        </button>
                    </div>
                </nav>
            </header>

            <main className="container mx-auto px-4 py-8">
                {activeTab === 'overall' && (
                    // Render the OverallScreen component when activeTab is 'overall'
                    <OverallScreen />
                )}

                {activeTab === 'rawData' && (
                    // Render the RawDataScreen component when activeTab is 'rawData'
                    <RawDataScreen />
                )}

                {activeTab === 'export' && (
                    <div className="export-data-section bg-white p-6 rounded-lg shadow-md">
                        <h2 className="text-2xl font-bold text-gray-800 mb-4">Export Data</h2>
                        <form onSubmit={handleExportSubmit}>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                                <div>
                                    <label htmlFor="participantId" className="block text-sm font-medium text-gray-700">
                                        Participant ID:
                                    </label>
                                    <input
                                        type="text"
                                        id="participantId"
                                        value={participantId}
                                        onChange={(e) => setParticipantId(e.target.value)}
                                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                                        placeholder="e.g., P001"
                                        required
                                    />
                                </div>
                                <div>
                                    <label htmlFor="startDate" className="block text-sm font-medium text-gray-700">
                                        Start Date:
                                    </label>
                                    <input
                                        type="date"
                                        id="startDate"
                                        value={startDate}
                                        onChange={(e) => setStartDate(e.target.value)}
                                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                                        required
                                    />
                                </div>
                                <div>
                                    <label htmlFor="endDate" className="block text-sm font-medium text-gray-700">
                                        End Date:
                                    </label>
                                    <input
                                        type="date"
                                        id="endDate"
                                        value={endDate}
                                        onChange={(e) => setEndDate(e.target.value)}
                                        className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
                                        required
                                    />
                                </div>
                            </div>

                            <div className="mb-4">
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Select Data Types for Export:
                                </label>
                                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                                    {sensingTypes.map(type => (
                                        <div key={type} className="flex items-center">
                                            <input
                                                type="checkbox"
                                                id={`export-${type}`}
                                                value={type}
                                                checked={selectedExportTypes.includes(type)}
                                                onChange={handleExportTypeChange}
                                                className="form-checkbox h-5 w-5 text-indigo-600 rounded-md focus:ring-indigo-500"
                                            />
                                            <label htmlFor={`export-${type}`} className="ml-2 text-base text-gray-900">
                                                {type}
                                            </label>
                                        </div>
                                    ))}
                                </div>
                                <div className="flex items-center mt-3">
                                    <input
                                        type="checkbox"
                                        id="selectAllExport"
                                        checked={selectedExportTypes.length === sensingTypes.length}
                                        onChange={handleAllExportTypesChange}
                                        className="form-checkbox h-5 w-5 text-purple-600 rounded-md focus:ring-purple-500"
                                    />
                                    <label htmlFor="selectAllExport" className="ml-2 text-base text-gray-900">
                                        All Sensing Types
                                    </label>
                                </div>

                                <div className="text-center pt-6">
                                    <button
                                        type="submit"
                                        className="bg-teal-600 hover:bg-teal-700 text-white font-bold py-3 px-12 rounded-full shadow-lg transform transition-all duration-300 hover:scale-105 focus:outline-none focus:ring-4 focus:ring-teal-500 focus:ring-opacity-50 disabled:opacity-50 disabled:cursor-not-allowed"
                                        disabled={loadingExport}
                                    >
                                        {loadingExport ? 'Exporting...' : 'Submit'}
                                    </button>
                                    {exportError && (
                                        <p className="text-red-500 text-sm mt-2">{exportError}</p>
                                    )}
                                </div>
                            </div>
                        </form>
                    </div>
                )}
            </main>
        </div>
    );
};

export default MoodTriggers;