import React from 'react';
import ReactDOM from 'react-dom/client';
import './MoodTriggers.css'; // Import the CSS file specific to MoodTriggers
import MoodTriggers from './MoodTriggers'; // Import your main MoodTriggers component

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <MoodTriggers />
  </React.StrictMode>
);
