# Standard library imports
import os
import sys
import io
import json
import random
import logging
import zipfile
import mimetypes
from datetime import datetime, timedelta
from collections import defaultdict
import sqlite3
import ssl
import requests

# Email-related imports
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.message import EmailMessage
import email

# Third-party imports
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text, exc
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
import pytz

# Local imports
import credentials
import config

def prepare_email(participant_number,first_name, df):

    participant_data = df[df['participant_id'] == participant_number]
    
    if not participant_data.empty:
        study_start_date = participant_data['study_start_date'].iloc[0]
        overall_percentage = participant_data['overall_compliance'].iloc[0]
    else:
        raise ValueError(f"No non-excluded participant found with ID {participant_id}")

    
    participant_data['date'] = pd.to_datetime(participant_data['date'], errors='coerce')
    participant_data['day_name'] = participant_data['date'].dt.strftime('%a')
   
    participant_data['date'] = participant_data['date'].dt.date

    
    participant_data['Total_cap'] = participant_data['ema_done'].clip(upper=config.EMA_promts)


    if not participant_data.empty:
        last_week_percentage = round(participant_data['Total_cap'].sum() / (len(participant_data) * config.EMA_promts) * 100)
    else:
        last_week_percentage = 0
        
    end_date = pd.to_datetime(study_start_date) + pd.Timedelta(days= config.Study_length)
    
   

        
    # ========== 3. setup ==========
    env = Environment(loader=FileSystemLoader('.'))
    template = env.from_string("""
    <html>
    <head>
        <style>
            body {
                font-family: "Segoe UI", Arial, sans-serif;
                margin: 2em;
                color: #2c3e50;
                line-height: 1.6;
                font-size: 12px; 
    
            }
            .highlight {
                color: #27ae60;
                font-weight: bold;
                font-size: 1.1em;
            }
            .center {
                text-align: center;
            }
            .streak {
                color: #e67e22;
                font-weight: bold;
            }
            .emoji {
                font-size: 1.3em;
            }
            .section {
                margin-top: 1.5em;
            }
            .footer {
                margin-top: 2em;
                font-size: 0.9em;
                color: #7f8c8d;
            }
            h2, h3 {
                color: #34495e;
            }
        </style>
    </head>
    <body>
        <h2>Hi {{first_name}} 👋,</h2>
    
        <h3>Thank you for joining our study! We’re so glad you’re here!
        </h3>
    
        <div class="section">
            <p>Here’s a quick snapshot of how you’re doing so far:</p>
            <p class="highlight">📊 Overall Completion Rate: {{ percentage }}%</p>
            <p class="highlight">📅 Last Week Compliance: {{ last_week_percentage }}%</p>
            <p class="streak">🔥 Keep it up!</p>
        </div>
    
        <div class="section">
            <p>🗓️ <strong>Your Week at a Glance:</strong></p>
            <pre>{{ week_summary }}</pre>
        </div>
    
        <div class="section">
            <p>{{ motivation_block | safe }}</p>
        </div>
    
        <div class="section">
            <p>🧠 Every single response helps us for our research. Your contribution truly matters.</p>
            <p class="highlight">📅 Daily Questionnaires End Date: {{end_date}}</p>
        </div>
    
        <div class="section footer">
            <p>Got questions or need help? We’re here for you!</p>
            <p>📧 <a href="mailto:{{email}}">{{email}}</a></p>
            <p>📞 {{phone}}</p>
        </div>
    </body>
    </html>
    
    """)
    
    # ========== 4. Generate emails ==========
    # Calculate completion %
    ema = config.EMA_promts
    # Prepare last 7 days
    last_7 = participant_data.sort_values('date').tail(7)
    day_messages = []
    streak = 0
    for _, row in last_7.iterrows():
        count = int(row['Total_cap'])
        day =  f"{row['day_name']} {row['date']}"
        if count == config.EMA_promts:
            streak += 1
            emoji = "🔥" * streak
            if streak == 1:
                msg = f"{day}: {emoji} All completed."
            else:
                msg = f"{day}: {emoji} All completed. {streak}-Day Streak!"
        elif count > 0:
            streak = 0 
            msg =  f"{day}: " + "✅" * count + "☐" *  (config.EMA_promts - count)+ f" ({count}/{ema})"
        else:
            streak = 0
            msg = f"{day}: " + "☐" * ema + f" (0/{ema})"
        day_messages.append(msg)
    week_summary = "\n".join(day_messages)

    import random

# ========== 4. Generate motivational messages ==========
    low_completion_texts = [
        """
        <div class="section">
            <p class="emoji">💡 You're off to a solid start!</p>
            <p>Even a few surveys a day make a huge difference in our study!</p>
            <p>You're making an impact!</p>
        </div>
        """,
        """
        <div class="section">
            <p class="emoji">🌱 Every Questionnaire Matters!</p>
            <p>Every completed questionnaire helps us learn more.</p>
            <p>You're contributing to science—thank you!</p>
        </div>
        """,
        """
        <div class="section">
            <p class="emoji">✨ Keep Pushing Forward</p>
            <p>Missing a survey is okay—just keep going. Each response counts!</p>
        </div>
        """
    ]
    
    import random

    # ---------- Motivation texts ----------
    high_completion_texts = [
        f"""
        <div class="section">
            <p class="emoji">🚀 Amazing effort!</p>
            <p>You’re really keeping up! Completing surveys helps us improve the study.</p>
            {"<p>Keep it going to earn your extra bonus.</p>" if config.Bonus_enabled else ""}
        </div>
        """,
        """
        <div class="section">
            <p class="emoji">🎉 Fantastic!</p>
            <p>Your dedication is inspiring. Completing surveys helps advance research! Plus, at the end of the study, you’ll receive a personalized report summarizing your symptoms and experiences, just for you.</p>
        </div>
        """,
        f"""
        <div class="section">
            <p class="emoji">🏆 Excellent work!</p>
            <p>You're making a meaningful contribution. Keep up the great progress!</p>
            {f"<p>If you complete over <strong>{config.Bonus_threshold}%</strong> of the surveys, you'll earn an extra <strong>${config.Bonus_amount}</strong> bonus!</p>" if config.Bonus_enabled else ""}
        </div>
        """
    ]
    
    low_completion_texts = [
        """
        <div class="section">
            <p class="emoji">💪 Keep trying!</p>
            <p>Completing more surveys helps us improve the study. Every bit counts!</p>
        </div>
        """,
        """
        <div class="section">
            <p class="emoji">⏳ Almost there!</p>
            <p>You're making progress — try to complete a few more surveys this week.</p>
        </div>
        """
    ]
    
    # ---------- Select motivation block ----------
    if last_week_percentage < 65:
        motivation_block = random.choice(low_completion_texts)
    else:
        motivation_block = random.choice(high_completion_texts)
    
    # ---------- Render HTML ----------
    html_out = template.render(
        percentage=overall_percentage,
        last_week_percentage=last_week_percentage,
        week_summary=week_summary,
        first_name=first_name,
        end_date=end_date,
        motivation_block=motivation_block,
        email=config.Study_email,
        phone=config.Study_phone,
        ema=config.EMA_promts
    )


    print(f"✅ Email body generated")


    return html_out
  
  


def get_email(participant_number, RedCap_token):
    data = {
        'token': RedCap_token,
        'content': 'record',
        'action': 'export',
        'format': 'json',
        'type': 'flat',
        'csvDelimiter': '',
        'fields[0]': config.RedCap_ID_field,
        'fields[1]': config.RedCap_email_field,
        'fields[2]': config.RedCap_firstname_field,
        'rawOrLabel': 'label',
        'rawOrLabelHeaders': 'label',
        'exportCheckboxLabel': 'false',
        'exportSurveyFields': 'false',
        'exportDataAccessGroups': 'false',
        'returnFormat': 'json'
    }
    r = requests.post('https://redcap.dartmouth.edu/api/',data=data)
    r = pd.DataFrame(r.json())
    
    # RedCap
    r = r[r[config.RedCap_ID_field].astype(int) == int(participant_number)]
    
    # Helper to get first non-empty value from a column
    def first_nonempty(df, col):
        return df[col][df[col].astype(str).str.strip().astype(bool)].iloc[0]
    
    # Extract data dynamically
    first_name = first_nonempty(r, config.RedCap_firstname_field)
    email = first_nonempty(r, config.RedCap_email_field)

    return first_name, email

def send_email(email_sender,email_receiver, email_cc, subject, body,email_password, is_html=True):
    em = EmailMessage()
    
    em["From"] = email.utils.formataddr((config.sender_text, email_sender))  
    em["To"] = email_receiver
    em["Subject"] = subject
    em["Cc"] = email_cc
    
    if is_html:
        em.add_alternative(body, subtype='html')
    else:
        em.set_content(body)
    
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
            smtp.login(email_sender, email_password)
            smtp.sendmail(email_sender, [email_receiver] + email_cc.split(','), em.as_string())
        print(f"✅ Email successfully sent to {email_receiver}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email to {email_receiver}. Error: {e}")
        return False


def load_participant_data():
    # ---------------------------
    # Database connection
    # ---------------------------
    DB_USER = config.DB_USER
    DB_PASSWORD = config.DB_PASSWORD
    DB_HOST = config.DB_HOST
    DB_PORT = config.DB_PORT
    DB_NAME = config.DB_NAME

    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

    # ---------------------------
    # Query data
    # ---------------------------
    query = text("""
        SELECT participant_id,
               daily_status_list,
               study_start_date,
               overall_compliance,
               excluded
        FROM overall_status_cache
        WHERE excluded = FALSE;
    """)

    with engine.connect() as conn:
        results = conn.execute(query).fetchall()
        df = pd.DataFrame(results, columns=[
            'participant_id', 
            'daily_status_list', 
            'study_start_date',
            'overall_compliance',
            'excluded'
        ])

    # ---------------------------
    # Filter participants
    # ---------------------------
    today = datetime.today().date()

    # Exclude participant_ids starting with "-"
    df = df[~df["participant_id"].astype(str).str.startswith("-")]

    # Exclude participants with study_end_date before today
    df["study_start_date"] = pd.to_datetime(df["study_start_date"]).dt.date
    df = df[df["study_start_date"]+ timedelta(days=config.Study_length) >= today ]

    # If no participants remain
    if df.empty:
        return pd.DataFrame()  # or return "excluded"

    # ---------------------------
    # Expand daily_status_list
    # ---------------------------
    start_dt = datetime.today().date() - timedelta(days=7)
    end_dt = datetime.today().date() - timedelta(days=1)
    full_dates = pd.date_range(start=start_dt, end=end_dt).date

    rows = []

    for _, row in df.iterrows():
        daily_list = row['daily_status_list'] or []  # handle None
        for d in full_dates:
            existing = next((item for item in daily_list if item['date'] == d.isoformat()), None)
            if not existing:
                existing = {"date": d.isoformat(), "ema_done": False, "passive_data_missing": True}

            rows.append({
                "participant_id": row["participant_id"],
                "study_start_date": row["study_start_date"],
                "overall_compliance": row["overall_compliance"],
                **existing
            })

    return pd.DataFrame(rows)

if __name__ == "__main__":
    # database conn
    DB_USER = config.DB_USER
    DB_PASSWORD = config.DB_PASSWORD
    DB_HOST = config.DB_HOST
    DB_PORT = config.DB_PORT
    DB_NAME = config.DB_NAME
    
    
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    
    
    # --- Step 1: Fetch SQL data ---
    query = text("""
        SELECT participant_id,
               daily_status_list,
               study_start_date,
               overall_compliance
        FROM overall_status_cache
        WHERE excluded = FALSE;
    """)
    
    with engine.connect() as conn:
        results = conn.execute(query).fetchall()
        df = pd.DataFrame(results, columns=['participant_id', 'daily_status_list', 'study_start_date', 'overall_compliance'])
    
    # Convert JSON strings to lists
    df['daily_status_list'] = df['daily_status_list'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    
    # --- Step 2: Create full date range ---
    start_dt = datetime.today().date() - timedelta(days=7)
    end_dt = datetime.today().date() - timedelta(days=1)
    full_dates = pd.date_range(start=start_dt, end=end_dt).date
    
    # --- Step 3: Expand daily_status_list into rows ---
    rows = []
    for _, row in df.iterrows():
        for d in full_dates:
            # Find existing entry for this date
            existing = next((item for item in row['daily_status_list'] if item['date'] == d.isoformat()), None)
            if not existing:
                existing = {"date": d.isoformat(), "ema_done": False, "passive_data_missing": True}
            rows.append({
                "participant_id": row["participant_id"],
                "study_start_date": row["study_start_date"],
                "overall_compliance": row["overall_compliance"],
                **existing
            })
    
    
    RedCap_token = credentials.RedCap_token
    df = pd.DataFrame(rows)

    print(df.head())
    first_name, emailadr = get_email(participant_number, RedCap_token)
    
    print(emailadr)
    print(first_name)
    
   
    

    html_out = prepare_email(participant_number,first_name,df)
    print(html_out)
    
    
    email_sender = config.email_sender
    email_cc = config.email_cc
    email_password = credentials.email_password
    email_receiver = emailadr
    #email_receiver = 'langener95@gmail.com' # I PUT MY OWN EMAIL FOR TESTING, THIS WILL BE REPLACED 
    
    
    subject = config.subject

    send_email(email_sender, email_receiver, email_cc, subject, html_out,email_password, is_html=True)
        






