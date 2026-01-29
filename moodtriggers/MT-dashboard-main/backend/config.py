############################################
#****** Study Configuration Script *******#
############################################
### Notes:
# overall_backend.py: DONE, besides passive sensing
# Weekly_Email.py: DONE
# mtrevamp_H.py: DONE
# main.py: DONE

############### SQL DATABASE ###############

# We could just give it a generic name, I'm adding it here for completness

DB_USER = "hannah"
DB_PASSWORD = "moodtriggers2025"
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "moodtriggers"


# SQL database names > assume that those don't change (e.g., ema_responses_final3)

############ Study ##########################
Study_length = 90

################### EMA ####################
EMA_promts = 3

############## Passive Sensing #################
# To do: overall_backend.py

############# Firebase #####################

# config: see credentials
MT_BASE_PREFIX = "studyIDs/"

############## VM ######################
Public_IP = "http://34.44.141.225/"
Internal_IP = "http://10.128.0.2"

############### Weekly Email ###############
# Email Body
Display_email = True
Study_email = "Sensing.Study@dartmouth.edu"
Study_phone = "(603) 646-7110"
Bonus_enabled = True
Bonus_threshold = 90
Bonus_amount= "$30"

# RedCap
RedCap_ID_field = "record_id"
RedCap_email_field = "email"
RedCap_firstname_field = "name_first"

# Sending
sender_text = "NO REPLY - Sensing Study Dartmouth"
email_sender = 'no.reply.sensing.study@gmail.com'
email_cc = "sensing.study@dartmouth.edu"
subject = "💪 Sensing Study: Weekly Compliance"

