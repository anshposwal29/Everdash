import React, { useState } from "react";
import { Mail, Users, CheckCircle } from "lucide-react";

const isLocal = process.env.REACT_APP_LOCAL === "true";
const API_BASE_URL = isLocal
  ? "http://localhost:8000"
  : "http://34.44.141.225/api";

export default function SendEmails() {
  const [participants, setParticipants] = useState([]);
  const [selectedParticipant, setSelectedParticipant] = useState(null);
  const [previewHtml, setPreviewHtml] = useState(null);

  const [loadingParticipants, setLoadingParticipants] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);

  const [successMessage, setSuccessMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [sentParticipants, setSentParticipants] = useState(new Set());


  // ===============================
  // Fetch participants
  // ===============================
  async function fetchParticipants() {
    setLoadingParticipants(true);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      const res = await fetch(`${API_BASE_URL}/unique_participants_email`);
      const data = await res.json();
      setParticipants(data);
    } catch {
      setErrorMessage("❌ Failed to load participants.");
    } finally {
      setLoadingParticipants(false);
    }
  }

  // ===============================
  // Preview email
  // ===============================
  async function previewEmail(id) {
    setSelectedParticipant(id);
    setLoadingPreview(true);
    setPreviewHtml(null);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      const res = await fetch(
        `${API_BASE_URL}/preview_email?participant_id=${id}`
      );
      const data = await res.json();
      setPreviewHtml(data.html);
    } catch {
      setErrorMessage("❌ Failed to load email preview.");
    } finally {
      setLoadingPreview(false);
    }
  }

  // ===============================
  // Send email
  // ===============================
  async function sendEmail() {
    if (!selectedParticipant) return;

    const confirmed = window.confirm(
      `Send this email to participant ${selectedParticipant}?`
    );
    if (!confirmed) return;

    setSendingEmail(true);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      await fetch(`${API_BASE_URL}/send_email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ participant_id: selectedParticipant })
      });
      setSentParticipants(prev => new Set(prev).add(selectedParticipant));
      setSuccessMessage(`✅ Email sent for participant ${selectedParticipant}`);
    } catch {
      setErrorMessage("❌ Failed to send email.");
    } finally {
      setSendingEmail(false);
    }
  }

  return (
    <div className="p-6 mx-auto w-full">

      {/* Header */}
      <h1 className="text-3xl font-bold text-gray-800 mb-6 flex items-center gap-3">
        <Mail className="w-8 h-8 text-blue-600" />
         Weekly Email Sender
      </h1>

      {/* Messages */}
      {successMessage && (
        <div className="mb-4 p-3 rounded bg-green-100 text-green-800 flex items-center gap-2">
          <CheckCircle size={18} />
          {successMessage}
        </div>
      )}

      {errorMessage && (
        <div className="mb-4 p-3 rounded bg-red-100 text-red-800">
          {errorMessage}
        </div>
      )}

      {/* Main Layout */}
      <div class="container-email">
      
        {/* LEFT PANEL */}
        <div class="left-panel-email">
        <h2 className="text-sm font-semibold text-gray-600 mb-2">Participants</h2>
        
        
        
          <button
            onClick={fetchParticipants}
            disabled={loadingParticipants}
            className={`mb-4 w-full flex items-center justify-center gap-2 px-4 py-2 rounded text-white transition
              ${loadingParticipants
                ? "bg-blue-300 cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-700"}
            `}
          >
            <Users size={18} />
            {loadingParticipants ? "Loading…" : "Load participants"}
          </button>
          
           <p className="text-xs text-gray-500 mb-2">
            Click on the participant number to preview and send their email.
          </p>
      
      
          
      
          <div className="space-y-1 overflow-y-auto flex-1">
            {participants.map((id) => (
              <div
                key={id}
                onClick={() => previewEmail(id)}
                className={`cursor-pointer p-2 rounded text-sm transition flex items-center justify-between
                  ${selectedParticipant === id
                    ? "bg-blue-100 border border-blue-400"
                    : "bg-gray-100 hover:bg-gray-200 hover:shadow-sm"}
                `}
              >
                <span>Participant: {id}</span>
                {sentParticipants.has(id) && (
                  <CheckCircle size={16} className="text-green-600" title="Email sent" />
                )}
              </div>

              
            ))}
          </div>
        </div>
      
        {/* RIGHT PANEL */}
        <div class="right-panel-email">
          <h2 className="text-xl font-semibold mb-2">Email Preview</h2>
      
          {!selectedParticipant && <p className="text-gray-500 text-sm">Select a participant to preview their email.</p>}
      
          {loadingPreview && <p className="text-gray-500 text-sm mt-2">⏳ Loading preview…</p>}
      
          {previewHtml && (
            <div className="flex flex-col flex-1">
              <p className="text-sm text-gray-500 mb-2">
                Preview for participant <strong>{selectedParticipant}</strong>
              </p>
              <div className="mt-4 flex justify-end">
                <button
                  disabled={sendingEmail}
                  onClick={sendEmail}
                  className={`px-5 py-2 rounded text-white transition
                    ${sendingEmail
                      ? "bg-green-300 cursor-not-allowed"
                      : "bg-green-600 hover:bg-green-700"}
                  `}
                >
                  {sendingEmail ? "Sending…" : "Send Email"}
                </button>
              
              <div className="flex flex-col flex-1">
      
              <iframe
                title="Email preview"
                srcDoc={previewHtml}
                className="flex-1 w-full border rounded bg-white"
                allow="fullscreen"
                width="80%"
                height="730px"
              />
              
              </div>

    
              </div>
            </div>
          )}
        </div>
      
      </div>

    </div>
  );
}
