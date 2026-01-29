
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text, exc
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
import pytz

import pandas as pd
from pathlib import Path
import json
from datetime import datetime
from datetime import timedelta, date
import pyrebase 
import ast 
import requests
import time

import os

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

# Local imports
import backend.credentials as credentials


### SQL Database connection
DB_USER = os.getenv("DB_USER", "hannah")
DB_PASSWORD = os.getenv("DB_PASSWORD", "moodtriggers2025")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "moodtriggers")


DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)



# Load mapping table from database
mapping_df = pd.read_sql(
    """
    SELECT old_id, new_id
    FROM participant_id_mapping
    """,
    con=engine
)

# Ensure string + zero-padded format
mapping_df["old_id"] = mapping_df["old_id"].astype(str).str.zfill(5)
mapping_df["new_id"] = mapping_df["new_id"].astype(str).str.zfill(5)

# Create lookup dict
id_map = dict(zip(mapping_df["old_id"], mapping_df["new_id"]))

##### Weekly Questionnaires ####

def run_weekly_pipeline():
  data = {
      'token': credentials.RedCap_token,
      'content': 'record',
      'action': 'export',
      'format': 'json',
      'type': 'flat',
      'csvDelimiter': '',
      'fields[0]': 'record_id',
      'forms[0]': 'w',
      'events[0]': '4_week_1_arm_1',
      'events[1]': '4_week_2_arm_1',
      'events[2]': '4_week_3_arm_1',
      'events[3]': '4_week_4_arm_1',
      'events[4]': '4_week_5_arm_1',
      'events[5]': '4_week_6_arm_1',
      'events[6]': '4_week_7_arm_1',
      'events[7]': '4_week_8_arm_1',
      'events[8]': '4_week_9_arm_1',
      'events[9]': '4_week_10_arm_1',
      'events[10]': '4_week_11_arm_1',
      'events[11]': '4_week_12_arm_1',
      'rawOrLabel': 'raw', #label
      'rawOrLabelHeaders': 'label',
      'exportCheckboxLabel': 'false',
      'exportSurveyFields': 'true',
      'exportDataAccessGroups': 'false',
      'returnFormat': 'json'
  }
  r = requests.post('https://redcap.dartmouth.edu/api/',data=data)
  
  weekly_q = pd.DataFrame(r.json())
  weekly_q["record_id"] = weekly_q["record_id"].apply(
      lambda x: str(x).zfill(5) if int(x) >= 0 else str(x)
  )

  # grouped = weekly_q.groupby(['record_id', 'redcap_event_name']).size().reset_index(name='n')
  # grouped['redcap_event_name'] = grouped['redcap_event_name'].str.extract(r'(\d+)$').astype(int)
  # grouped = grouped.pivot(index='record_id', columns='redcap_event_name', values='n')
  # grouped = grouped.reset_index()
  # grouped.index.name = None
  
  
  weekly_q["record_id"] = weekly_q["record_id"].astype(str).str.zfill(5)
  
  # Replace record_id where mapping exists
  weekly_q["record_id"] = weekly_q["record_id"].map(id_map).fillna(weekly_q["record_id"])
  
  # Processed / pivoted weekly data
  weekly_q.to_sql(
      name="weekly_data",
      con=engine,
      schema="public",
      if_exists="replace",
      index=False,
      method="multi"
  )

###### Post assessment #####
def run_post_assessment_pipeline():
  # Post assessment
  data = {
      'token': credentials.RedCap_token,
      'content': 'record',
      'action': 'export',
      'format': 'json',
      'type': 'flat',
      'csvDelimiter': '',
      'fields[0]': 'record_id',
      'forms[0]': 'p',
      'events[0]': '5_post_assessment_arm_1',
      'rawOrLabel': 'raw',
      'rawOrLabelHeaders': 'raw',
      'exportCheckboxLabel': 'false',
      'exportSurveyFields': 'false',
      'exportDataAccessGroups': 'false',
      'returnFormat': 'json'
  }
  r = requests.post('https://redcap.dartmouth.edu/api/',data=data)
  post_df = pd.DataFrame(r.json())
  
  
  # Replace record_id where mapping exists
  post_df["record_id"] = (
      post_df["record_id"]
      .map(id_map)
      .fillna(post_df["record_id"])
  )
  
  post_df.to_sql(
      name="post_assessment",
      con=engine,
      schema="public",
      if_exists="replace",   # change to "append" if needed
      index=False,
      method="multi"
  )

def main():

    run_weekly_pipeline()
    run_post_assessment_pipeline()


if __name__ == "__main__":
    main()
