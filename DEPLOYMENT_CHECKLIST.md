# Theradash Deployment Checklist

Use this checklist to ensure a successful deployment of Theradash to production.

## Pre-Deployment Checklist

### AWS Account Setup
- [ ] AWS account created with appropriate permissions
- [ ] AWS CLI installed and configured (optional)
- [ ] SSH key pair created or available
- [ ] VPN IP range identified for security group

### Required Credentials
- [ ] Firebase service account JSON file obtained
- [ ] REDCap API token generated with read permissions
- [ ] Twilio account SID and auth token obtained
- [ ] Twilio phone number provisioned
- [ ] Domain name purchased (optional, for SSL)

### Local Preparation
- [ ] Repository cloned locally
- [ ] `.env.example` reviewed and understood
- [ ] Firebase credentials file downloaded

---

## AWS Infrastructure Setup

### EC2 Instance
- [ ] EC2 t2.medium instance launched
- [ ] Ubuntu 22.04 LTS AMI selected
- [ ] 20 GB gp3 storage configured
- [ ] Security group created with rules:
  - [ ] Port 22 (SSH) - Your IP or VPN range
  - [ ] Port 80 (HTTP) - Your IP or VPN range
  - [ ] Port 443 (HTTPS) - Your IP or VPN range
- [ ] Key pair selected
- [ ] Instance launched and running
- [ ] Elastic IP allocated and associated (recommended)
- [ ] Can SSH into instance successfully

### DNS Configuration (Optional)
- [ ] Route 53 hosted zone created
- [ ] A record pointing to Elastic IP
- [ ] Domain nameservers updated
- [ ] DNS propagation verified

---

## Application Deployment

### 1. Connect to Instance
```bash
ssh -i your-key.pem ubuntu@your-instance-ip
```
- [ ] Successfully connected to EC2 instance

### 2. System Update
```bash
sudo apt-get update && sudo apt-get upgrade -y
```
- [ ] System updated successfully

### 3. Clone Repository
```bash
cd ~
git clone <your-repository-url>
cd theradash
```
- [ ] Repository cloned successfully
- [ ] In theradash directory

### 4. Upload Firebase Credentials
From local machine:
```bash
scp -i your-key.pem firebase-credentials.json ubuntu@your-instance-ip:~/theradash/
```
- [ ] Firebase credentials uploaded
- [ ] File exists at `~/theradash/firebase-credentials.json`

### 5. Configure Environment
```bash
cp .env.example .env
nano .env
```

Required variables to configure:
- [ ] `SECRET_KEY` - Generated secure key
- [ ] `FIREBASE_CREDENTIALS_PATH=/home/ubuntu/theradash/firebase-credentials.json`
- [ ] `REDCAP_API_URL` - Your REDCap API endpoint
- [ ] `REDCAP_API_TOKEN` - Your REDCap API token
- [ ] `REDCAP_FILTER_LOGIC` - Participant selection logic
- [ ] `REDCAP_FORM_NAME` - REDCap form name
- [ ] `REDCAP_FIREBASE_ID_FIELD` - Field name for Firebase ID
- [ ] `REDCAP_RA_FIELD` - Field name for RA
- [ ] `USER_SELECTION_MODE` - Set to `redcap`, `uids`, or `both`
- [ ] `FIREBASE_UIDS` - If using `uids` or `both` mode
- [ ] `TWILIO_ACCOUNT_SID` - Twilio SID
- [ ] `TWILIO_AUTH_TOKEN` - Twilio token
- [ ] `TWILIO_FROM_NUMBER` - SMS sender (E.164 format)
- [ ] `TWILIO_ADMIN_NUMBERS` - Alert recipients
- [ ] `IP_PREFIX_ALLOWED` - Your VPN IP prefix (e.g., `10.0.0`)
- [ ] `REGISTRATION_KEY` - Secure registration key
- [ ] `RISK_SCORE_THRESHOLD` - Default 0.7
- [ ] `TIMEZONE` - Default America/New_York

### 6. Run Deployment Script
```bash
chmod +x deploy_aws.sh
./deploy_aws.sh
```
- [ ] Script executed successfully
- [ ] No errors in output
- [ ] All services started

### 7. Verify Services
```bash
sudo supervisorctl status theradash
sudo systemctl status nginx
crontab -l | grep cron_sync
```
- [ ] Theradash showing RUNNING
- [ ] Nginx showing active (running)
- [ ] Cron job installed

---

## Post-Deployment Configuration

### 1. Test Web Access
- [ ] Can access `http://your-instance-ip` in browser
- [ ] Login page loads correctly
- [ ] No 502/503 errors

### 2. Register Admin Account
- [ ] Navigate to `/register`
- [ ] Create admin account with username/email/password
- [ ] Use `REGISTRATION_KEY` from `.env`
- [ ] Registration successful
- [ ] Can login with credentials

### 3. Verify Firebase Connection
- [ ] Login to dashboard
- [ ] Click "Refresh Data" button
- [ ] Check browser console for errors
- [ ] Check logs: `tail -f ~/theradash/logs/gunicorn_error.log`
- [ ] Users appear in dashboard (or see appropriate message)

### 4. Verify REDCap Integration
- [ ] Dashboard shows REDCap participants
- [ ] Participant names and IDs display correctly
- [ ] "No Firebase ID" shows for participants without Firebase setup

### 5. Verify Automated Sync
```bash
cd ~/theradash
./check_cron_status.sh
```
- [ ] Cron job installed and active
- [ ] Recent sync runs visible in logs
- [ ] No errors in `logs/cron_sync.log`

### 6. Test SMS Alerts (Optional)
- [ ] Create a test high-risk message in Firebase
- [ ] Wait 2 minutes for sync
- [ ] Verify SMS received on admin phone number
- [ ] Or check Twilio logs for sent messages

### 7. Setup SSL Certificate (If Using Domain)
```bash
export DOMAIN_NAME=yourdomain.com
sudo sed -i "s/server_name _;/server_name $DOMAIN_NAME;/" /etc/nginx/sites-available/theradash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d $DOMAIN_NAME
```
- [ ] Domain name configured in Nginx
- [ ] Certbot SSL setup successful
- [ ] Can access via `https://yourdomain.com`
- [ ] SSL certificate valid

---

## Security Verification

### IP Filtering
- [ ] Try accessing from non-VPN IP (should get 403)
- [ ] Verify access works from VPN IP
- [ ] IP filtering is working correctly

### Admin Authentication
- [ ] Cannot access dashboard without login
- [ ] Redirected to login page when not authenticated
- [ ] Session persists across page refreshes

### Registration Key
- [ ] Cannot register without correct `REGISTRATION_KEY`
- [ ] Registration works with correct key

### File Permissions
```bash
ls -la ~/theradash/.env
ls -la ~/theradash/instance/
```
- [ ] `.env` file not world-readable
- [ ] `instance/` directory has correct permissions
- [ ] Firebase credentials file secure

---

## Monitoring Setup

### Log Files Check
```bash
ls -la ~/theradash/logs/
tail -f ~/theradash/logs/gunicorn_error.log
tail -f ~/theradash/logs/cron_sync.log
```
- [ ] Log directory exists
- [ ] Log files being created
- [ ] No critical errors in logs

### Database Check
```bash
ls -lh ~/theradash/instance/theradash.db
sqlite3 ~/theradash/instance/theradash.db "SELECT COUNT(*) FROM users;"
```
- [ ] Database file exists
- [ ] Database contains data
- [ ] Can query database successfully

### Backup Strategy
- [ ] Automated backup cron job configured (optional)
- [ ] Manual backup tested
- [ ] Backup location identified

---

## Performance Verification

### Response Times
- [ ] Dashboard loads in < 2 seconds
- [ ] User detail page loads quickly
- [ ] No timeout errors

### Resource Usage
```bash
top
df -h
```
- [ ] CPU usage reasonable (< 50% average)
- [ ] Memory usage acceptable (< 2GB)
- [ ] Disk space sufficient (> 10GB free)

### Concurrent Access Test
- [ ] Multiple admins can login simultaneously
- [ ] No database lock errors
- [ ] Sync continues to work with active users

---

## Documentation Verification

### Documentation Complete
- [ ] README.md reviewed
- [ ] AWS_DEPLOYMENT_GUIDE.md available
- [ ] ARCHITECTURE.md reviewed
- [ ] CRON_SETUP.md available
- [ ] All documentation accessible to team

### Team Training
- [ ] Admin users trained on dashboard usage
- [ ] Research assistants briefed on monitoring process
- [ ] Contact information for support documented

---

## Operational Readiness

### Runbook Prepared
- [ ] How to restart application
- [ ] How to check logs
- [ ] How to trigger manual sync
- [ ] How to add admin users
- [ ] Troubleshooting guide reviewed

### Maintenance Plan
- [ ] System update schedule defined (monthly recommended)
- [ ] Backup schedule defined
- [ ] Log rotation configured
- [ ] Monitoring alerts configured

### Contact Information
- [ ] Admin contact numbers in `TWILIO_ADMIN_NUMBERS`
- [ ] Emergency contact list prepared
- [ ] Escalation path defined

---

## Final Checks

### Smoke Test
- [ ] Login as admin
- [ ] View dashboard
- [ ] Click on a user cell
- [ ] View messages for a date
- [ ] Mark a message as reviewed
- [ ] Add a note to participant
- [ ] Manual sync works
- [ ] Logout and login again
- [ ] All features working

### Error Handling
- [ ] Test with invalid Firebase ID
- [ ] Test with missing REDCap participant
- [ ] Verify error messages are user-friendly
- [ ] Verify errors are logged

### Load Test (Optional)
- [ ] Sync with full dataset
- [ ] Multiple users accessing simultaneously
- [ ] System remains stable

---

## Production Go-Live

### Pre-Launch
- [ ] All checklist items completed
- [ ] Team notified of launch
- [ ] Support team ready

### Launch
- [ ] Application live and accessible
- [ ] Users can access successfully
- [ ] Data syncing properly
- [ ] Alerts working

### Post-Launch Monitoring (First 24 Hours)
- [ ] Check logs every 2 hours
- [ ] Verify syncs completing successfully
- [ ] Monitor for errors
- [ ] User feedback collected

### Post-Launch Monitoring (First Week)
- [ ] Daily log review
- [ ] Performance metrics collected
- [ ] User feedback addressed
- [ ] Any issues documented and resolved

---

## Success Criteria

Deployment is successful when:
- ✅ Application accessible via web browser
- ✅ Admin can login successfully
- ✅ Dashboard displays participants
- ✅ Firebase sync working
- ✅ REDCap integration working
- ✅ Automated sync running every 2 minutes
- ✅ SMS alerts being sent (if configured)
- ✅ No critical errors in logs
- ✅ Performance acceptable
- ✅ Security measures in place
- ✅ Team trained and ready

---

## Troubleshooting Reference

If anything fails, refer to:
1. **AWS_DEPLOYMENT_GUIDE.md** - Complete troubleshooting section
2. **Application logs** - `~/theradash/logs/`
3. **System logs** - `/var/log/syslog`
4. **Nginx logs** - `/var/log/nginx/`

Common issues:
- **403 Forbidden**: Check IP_PREFIX_ALLOWED in .env
- **502 Bad Gateway**: Check if Gunicorn is running
- **No data in dashboard**: Check Firebase credentials and REDCap config
- **Sync not running**: Check cron job with `crontab -l`

---

## Sign-Off

- [ ] Deployment completed by: _______________
- [ ] Date: _______________
- [ ] Reviewed by: _______________
- [ ] Production ready: YES / NO

**Notes:**
