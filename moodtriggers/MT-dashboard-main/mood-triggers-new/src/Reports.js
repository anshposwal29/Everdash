import React, { useState } from "react";
import { FileText, Loader } from "lucide-react";

const isLocal = process.env.REACT_APP_LOCAL === 'true';
const API_BASE_URL = isLocal
  ? "http://localhost:8000"
  : "http://34.44.141.225/api";

export default function ReportsPanel() {
  // Compensation Report state
  const [compParticipant, setCompParticipant] = useState("");
  const [compGoogleTakeout, setCompGoogleTakeout] = useState(false);
  const [compLoading, setCompLoading] = useState(false);
  const [compSuccess, setCompSuccess] = useState("");

  // Feedback Report state
  const [feedParticipant, setFeedParticipant] = useState("");
  const [feedLoading, setFeedLoading] = useState(false);
  const [feedSuccess, setFeedSuccess] = useState("");

  // Compensation Report GET (binary download)
  const handleCompensationSubmit = async () => {
    if (!compParticipant) {
      alert("Please enter a participant number for Compensation Report.");
      return;
    }

    setCompLoading(true);
    setCompSuccess("");

    try {
      const response = await fetch(
        `${API_BASE_URL}/compensation-report/${compParticipant}?google_takeout=${compGoogleTakeout}`,
        { method: "GET" }
      );

      if (!response.ok) throw new Error("API request failed");

      // Read response as a blob (binary)
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);

      // Create temporary link to download
      const a = document.createElement("a");
      a.href = url;
      a.download = `Compensation_Report_${compParticipant}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      setCompSuccess("Compensation report downloaded successfully!");
    } catch (error) {
      console.error(error);
      alert("Failed to generate compensation report.");
    } finally {
      setCompLoading(false);
    }
  };

  // Feedback Report 
  const handleFeedbackSubmit = async () => {
    if (!feedParticipant) {
      alert("Please enter a participant number for Feedback Report.");
      return;
    }
  
    setFeedLoading(true);
    setFeedSuccess("");
    
    try {
      const response = await fetch(
        `${API_BASE_URL}/feedback-report/${feedParticipant}`,
        { method: "GET" }
      );
  
      if (!response.ok) throw new Error("API request failed");
  
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
  
      const a = document.createElement("a");
      a.href = url;
      a.download = `Feedback_Report_${feedParticipant}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
  
      setFeedSuccess("Feedback report downloaded successfully!"); // ✅ updated
    } catch (error) {
      console.error(error);
      alert("Failed to generate feedback report.");
    } finally {
      setFeedLoading(false); // ✅ updated
    }
  };

  return (
    <div className="space-y-6">
      {/* Compensation Report */}
      <div className="p-4 bg-white rounded-md shadow-md w-full max-w-md">
        <h2 className="flex items-center text-xl font-semibold mb-4">
          <FileText size={24} className="mr-2 text-blue-600" />
          Generate Compensation Report
        </h2>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Participant Number
          </label>
          <input
            type="text"
            value={compParticipant}
            onChange={(e) => setCompParticipant(e.target.value)}
            placeholder="Enter participant number"
            className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring focus:border-blue-300"
          />
        </div>

        <div className="mb-4 flex items-center">
          <input
            id="compGoogleTakeout"
            type="checkbox"
            checked={compGoogleTakeout}
            onChange={() => setCompGoogleTakeout(!compGoogleTakeout)}
            className="h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
          />
          <label htmlFor="compGoogleTakeout" className="ml-2 block text-sm text-gray-700">
            Google Takeout
          </label>
        </div>

        <button
          onClick={handleCompensationSubmit}
          disabled={compLoading}
          className={`flex items-center justify-center w-full px-4 py-2 rounded-md text-white transition-colors ${
            compLoading ? "bg-blue-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {compLoading ? <Loader className="animate-spin mr-2" size={20} /> : <FileText size={20} className="mr-2" />}
          {compLoading ? "Generating..." : "Generate"}
        </button>

        {compSuccess && <p className="mt-3 text-green-600 font-medium">{compSuccess}</p>}
      </div>

      {/* Feedback Report */}
      <div className="p-4 bg-white rounded-md shadow-md w-full max-w-md">
        <h2 className="flex items-center text-xl font-semibold mb-4">
          <FileText size={24} className="mr-2 text-blue-600" />
          Generate Feedback Report
        </h2>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Participant Number
          </label>
          <input
            type="text"
            value={feedParticipant}
            onChange={(e) => setFeedParticipant(e.target.value)}
            placeholder="Enter participant number"
            className="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring focus:border-blue-300"
          />
        </div>

        <button
          onClick={handleFeedbackSubmit}
          disabled={feedLoading}
          className={`flex items-center justify-center w-full px-4 py-2 rounded-md text-white transition-colors ${
            feedLoading ? "bg-blue-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
          }`}
        >
          {feedLoading ? <Loader className="animate-spin mr-2" size={20} /> : <FileText size={20} className="mr-2" />}
          {feedLoading ? "Generating..." : "Generate"}
        </button>

        {feedSuccess && <p className="mt-3 text-green-600 font-medium">{feedSuccess}</p>}
      </div>
    </div>
  );
}
