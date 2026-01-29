// RawDataScreen.js
import React, { useState } from 'react';
import { BarChart2 } from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts';


const isLocal = process.env.REACT_APP_LOCAL === 'true';
// /////////////////////////

let API_BASE_URL;

// if (local === "yes") {
if (isLocal) {
  API_BASE_URL = "http://localhost:8000";
} else {
  API_BASE_URL = "http://34.44.141.225/api"; // the public VM IP via Apache reverse proxy
}


const PALETTE = [
  '#4CAF50', '#FFD700', '#8A2BE2', '#FF4500',
  '#4682B4', '#DA70D6', '#20B2AA', '#A0522D'
];

const SENSING_TYPES = [
    'Location',
    'Gyroscope',          // angv
    'Accelerometer',
    'Light',              // <- was 'Light Sensor'
    'Battery',
    'User Survey Responses',
    'Phone',
    'SMS',
    'App Usage'
  ];
  

export default function RawDataScreen() {
  const [participantId, setParticipantId] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [selectedGraphTypes, setSelectedGraphTypes] = useState([]);
  const [displayedData, setDisplayedData] = useState([]);
  const [showGraph, setShowGraph] = useState(false);
  const [loadingData, setLoadingData] = useState(false);
  const [dataError, setDataError] = useState(null);

  const handleSensingTypeChange = (e) => {
    const { value, checked } = e.target;
    setSelectedGraphTypes(prev =>
      checked ? [...prev, value] : prev.filter(t => t !== value)
    );
  };

  const handleAllToggle = (e) => {
    if (e.target.checked) setSelectedGraphTypes(SENSING_TYPES);
    else setSelectedGraphTypes([]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    await fetchData();
  };

  async function fetchData() {
    setLoadingData(true);
    setDataError(null);
    setShowGraph(false);

    try {
      const params = new URLSearchParams();
      params.append('participant_id', (participantId || '').trim());
      params.append('start_date', startDate); // type=date returns YYYY-MM-DD
      params.append('end_date', endDate);
      params.append('sensing_types', selectedGraphTypes.join(','));

      const res = await fetch(`${API_BASE_URL}/sensing_data?${params.toString()}`);
      if (!res.ok) throw new Error(`Backend responded ${res.status}`);

      const data = await res.json();
      // Backend returns rows like:
      // { name: 'YYYY-MM-DD', 'Battery': 62.5, 'Accelerometer': 3.2, 'Phone': 4, 'SMS': 10, 'App Usage': 123.0, ... }
      // Normalize to { timestamp: 'YYYY-MM-DD', ... } for the chart XAxis:
      const normalized = Array.isArray(data)
        ? data.map(r => ({ timestamp: r.name, ...r }))
        : [];

      setDisplayedData(normalized);
      setShowGraph(true);
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setDataError(err.message || 'Failed to fetch');
    } finally {
      setLoadingData(false);
    }
  }

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <h1 className="text-3xl font-bold text-gray-800 mb-6 flex items-center">
        <BarChart2 className="mr-3 text-purple-600" size={32} /> Raw Data Visualization
      </h1>

      <form onSubmit={handleSubmit} className="bg-white p-6 rounded-lg shadow-md mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700">Participant ID:</label>
            <input
              type="text"
              value={participantId}
              onChange={(e) => setParticipantId(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
              placeholder="e.g., 00029"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">Start Date:</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">End Date:</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2"
              required
            />
          </div>
        </div>

        <label className="block text-sm font-medium text-gray-700 mb-2">Select Graph Types:</label>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 mb-3">
          {SENSING_TYPES.map(type => (
            <div key={type} className="flex items-center">
              <input
                type="checkbox"
                id={type}
                value={type}
                checked={selectedGraphTypes.includes(type)}
                onChange={handleSensingTypeChange}
                className="form-checkbox h-5 w-5 text-indigo-600 rounded-md focus:ring-indigo-500"
              />
              <label htmlFor={type} className="ml-2 text-base text-gray-900">{type}</label>
            </div>
          ))}
        </div>

        <div className="flex items-center mb-4">
          <input
            type="checkbox"
            id="selectAll"
            checked={selectedGraphTypes.length === SENSING_TYPES.length}
            onChange={handleAllToggle}
            className="form-checkbox h-5 w-5 text-purple-600 rounded-md focus:ring-purple-500"
          />
          <label htmlFor="selectAll" className="ml-2 text-base text-gray-900">Select All</label>
        </div>

        <div className="text-center">
          <button
            type="submit"
            className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-md shadow-lg transition-transform transform hover:scale-105 disabled:opacity-50"
            disabled={loadingData}
          >
            {loadingData ? 'Loading...' : 'Update Graph'}
          </button>
          {dataError && <p className="text-red-500 text-sm mt-2">{dataError}</p>}
        </div>
      </form>

      <div className="bg-white p-6 rounded-lg shadow-md">
        {showGraph && displayedData.length > 0 ? (
          <ResponsiveContainer width="100%" height={420}>
            <LineChart data={displayedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" />
              {/* backend day label normalized to 'timestamp' above */}
              <XAxis dataKey="timestamp" />
              <YAxis />
              <Tooltip />
              <Legend />
              {selectedGraphTypes.map((type, i) => (
                <Line
                  key={type}
                  type="monotone"
                  dataKey={type}
                  stroke={PALETTE[i % PALETTE.length]}
                  activeDot={{ r: 6 }}
                  strokeWidth={2}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : !loadingData && !dataError && (
          <p className="text-gray-500 text-lg text-center">
            Enter filters and click &apos;Update Graph&apos; to see the data.
          </p>
        )}
      </div>
    </div>
  );
}


