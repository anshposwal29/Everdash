# MoodTriggers Dashboard — Backend & Frontend Overview

## Updates Log

2025-12-16: updated a lot of functionality between the overall/participant/day screens. merged changes with main

2025-12-02: added crude display of participant overview. needs optimization, but functional display mostly complete. includes export of all of participant's data plus buttons to click through participants.

2025-12-1: updated dayDetailScreen so that it's mostly complete. fixed latency issues with plots. 

2025-11-24: updated timestamps in SQL database to include raw_date_string (raw_date), local timestamp (date), UTC timestamp (date_utc), and timezone (timezone). changes made to mtrevamp_H.py file

2025-11-18: added clickable days within overallScreen table. goes to a new page (dayDetailScreen.js) with day summary data for the participant plus an easy export button to export data for that one participant on that date. 

2025-11-10: updated issue with timestamps in overall_backend.py (line 65)

⚠️ *Note:* So far the variable "local" is not set to "yes" and needs to be changed in the files manually. I want to implement an easier way than changing it in X different files.

2025-11-11: updated the variable local logic to require a .env.local file (saved in .gitignore) in the project root which defines true/false if computer is local (REACT_APP_LOCAL = true/false). The frontend files will pull the variable from the .env.local file setting for that computer's configuration. A variable will also need to be added to the credentials file (local = True/False) for the backend.

## 🖥️ Backend (`/backend`)

## Main Files

-   **`mtrevamp_H.py`** → *Downloads data from Firebase and stores it in SQL*

    -   Will run daily to pull raw sensor data from Firebase.

    -   Creates SQL tables for each sensor type (e.g., accelerometer, gyroscope, etc.).

-   **`overall_backend.py`** → *Generates overview summary data*

    -   Will run daily to process the raw sensor data.

    -   Builds the `daily_status_cache` table used by the dashboard’s “Overview” page.

    -   ⚠️ *Note:* If you run this script multiple times, you may need to delete the database. I think this can happen when `study_start_date` changes if not all participant data has been downloaded yet (causing duplicate entries), but I need to double check that.

-   **`main.py`** → *FastAPI backend for data access and export*

    -   A FastAPI app that lets you get participant info, daily sensor data, and overall progress from a PostgreSQL database.

        Example endpoint (remote):

        (For troubleshooting it can help to look at the output to see if mistake happens in backend or frontend)

        ```         
        https://104.197.140.156/api/overall_status?start_date=2025-10-01&end_date=2025-10-16
        ```

        *(You might not need `/api/` when running locally and also the address.)*

> Other backend files are currently not in use.

### Running the Backend (Changes should be directly reflected in front end)

```         
cd /var/www/MoodTriggersDashboardv2/backend
source ../venv/bin/activate
git pull origin AnnaTest

python3 mtrevamp_H.py
python3 overall_backend.py
python3 main.py
```

### 

### Frontend (mood-triggers-new)

## 💻 Frontend (`/mood-triggers-new`)

### Main Files

-   **`/src` folder:** Contains JSON files for all screens.

-   **`OverallScreen.js`** → Builds the “Overview” page.

    -   When adding the ability to click on participants, this is the main file to update.

    -   You may need to create a new screen component for detailed participant views.

-   **`RawDataScreen.js`** → Displays raw sensor data.

-   **`MoodTriggers.js`** → *(TO DO: Add description of main app entry point here. I have not changed this file yet so I'm not entirely sure when/ if we need to touch it)*

### Building the Frontend (needs to be run so changes are visible)

```         
git pull origin AnnaTest
cd mood-triggers-new
npm run build
```
