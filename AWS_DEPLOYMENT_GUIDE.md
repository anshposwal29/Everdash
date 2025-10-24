# Theradash AWS Deployment Guide

This guide provides step-by-step instructions for deploying Theradash on an AWS EC2 t2.medium instance.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [AWS Setup](#aws-setup)
3. [Deployment Steps](#deployment-steps)
4. [Post-Deployment Configuration](#post-deployment-configuration)
5. [Monitoring and Maintenance](#monitoring-and-maintenance)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required AWS Resources
- AWS account with EC2 access
- VPN or static IP range for secure access
- (Optional) Route 53 domain for HTTPS setup

### Required Files Before Deployment
- Firebase service account credentials JSON file
- REDCap API token
- Twilio account credentials

### Local Machine Requirements
- SSH client
- Git
- Text editor

---

## AWS Setup

### Step 1: Launch EC2 Instance

1. **Sign in to AWS Console** and navigate to EC2

2. **Launch Instance** with these specifications:
   - **AMI**: Ubuntu Server 22.04 LTS (HVM), SSD Volume Type
   - **Instance Type**: t2.medium
     - 2 vCPUs
     - 4 GiB RAM
     - Moderate network performance
   - **Storage**: 20 GB gp3 (General Purpose SSD)

3. **Configure Instance Details**:
   - Enable Auto-assign Public IP
   - (Optional) Add to VPC if you have one configured

4. **Create/Select Security Group** with these rules:

   | Type | Protocol | Port Range | Source | Description |
   |------|----------|------------|--------|-------------|
   | SSH | TCP | 22 | Your IP or VPN range | SSH access |
   | HTTP | TCP | 80 | Your IP or VPN range | Web access |
   | HTTPS | TCP | 443 | Your IP or VPN range | Secure web access |

   **Important**: Restrict source to your institution's VPN IP range for security

5. **Create/Select Key Pair**
   - Create new key pair or use existing
   - Download `.pem` file and store securely
   - Set permissions: `chmod 400 your-key.pem`

6. **Launch Instance** and wait for status checks to pass

### Step 2: Assign Elastic IP (Recommended)

1. Navigate to **Elastic IPs** in EC2 console
2. Click **Allocate Elastic IP address**
3. Select the IP and click **Associate Elastic IP address**
4. Choose your instance and associate

This ensures your instance keeps the same IP even after restarts.

### Step 3: Configure DNS (Optional but Recommended)

If using a domain name:

1. Navigate to **Route 53**
2. Create hosted zone for your domain
3. Create an **A Record** pointing to your Elastic IP
4. Update your domain registrar's nameservers to Route 53's nameservers

---

## Deployment Steps

### Step 1: Connect to Your Instance

```bash
ssh -i your-key.pem ubuntu@your-instance-ip
```

### Step 2: Update System

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### Step 3: Clone Repository

```bash
cd ~
git clone https://github.com/your-username/theradash.git
cd theradash
```

**Note**: If using a private repository, set up SSH keys or use HTTPS with credentials.

### Step 4: Upload Firebase Credentials

From your **local machine**, upload the Firebase service account JSON:

```bash
scp -i your-key.pem firebase-credentials.json ubuntu@your-instance-ip:~/theradash/
```

### Step 5: Configure Environment Variables

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit the `.env` file:
```bash
nano .env
```

3. Configure all required variables:

```bash
# Flask Configuration
SECRET_KEY=your-generated-secret-key-here
DATABASE_URL=sqlite:///instance/theradash.db

# Firebase Configuration
FIREBASE_CREDENTIALS_PATH=/home/ubuntu/theradash/firebase-credentials.json

# REDCap Configuration
REDCAP_API_URL=https://your-redcap-instance.com/api/
REDCAP_API_TOKEN=your-redcap-api-token
REDCAP_FILTER_LOGIC=[your_field]='1'
REDCAP_FORM_NAME=your_form_name
REDCAP_FIREBASE_ID_FIELD=firebase_id
REDCAP_RA_FIELD=research_assistant

# User Selection Mode
USER_SELECTION_MODE=redcap  # Options: 'redcap', 'uids', or 'both'
# FIREBASE_UIDS=uid1,uid2,uid3  # Only if using 'uids' or 'both' mode

# Twilio Configuration (for SMS alerts)
TWILIO_ACCOUNT_SID=your-twilio-account-sid
TWILIO_AUTH_TOKEN=your-twilio-auth-token
TWILIO_FROM_NUMBER=+1234567890
TWILIO_ADMIN_NUMBERS=+1234567890,+0987654321

# Security Configuration
IP_PREFIX_ALLOWED=10.0.0  # Your VPN IP prefix (first 3 octets)
REGISTRATION_KEY=your-secure-registration-key

# Application Settings
RISK_SCORE_THRESHOLD=0.7
TIMEZONE=America/New_York
```

4. Save and exit (Ctrl+X, Y, Enter in nano)

### Step 6: Run Automated Deployment

```bash
chmod +x deploy_aws.sh
./deploy_aws.sh
```

The script will:
- Install all system dependencies
- Create Python virtual environment
- Install Python packages
- Initialize the database
- Configure Gunicorn (production WSGI server)
- Setup Supervisor (process manager)
- Configure Nginx (reverse proxy)
- Setup SSL with Let's Encrypt (if domain provided)
- Install automated sync cron job
- Configure firewall

**Duration**: Approximately 5-10 minutes

### Step 7: Verify Deployment

1. **Check application status**:
```bash
sudo supervisorctl status theradash
```
Should show: `theradash RUNNING`

2. **Check Nginx status**:
```bash
sudo systemctl status nginx
```
Should show: `active (running)`

3. **Check cron job**:
```bash
./check_cron_status.sh
```
Should show: Cron job installed and recent sync runs

4. **Test web access**:
Open browser and navigate to: `http://your-instance-ip`

---

## Post-Deployment Configuration

### Step 1: Register First Admin Account

1. Open the application in your browser
2. Click "Register"
3. Enter username, email, and password
4. Enter the `REGISTRATION_KEY` from your `.env` file
5. Submit registration

### Step 2: Verify Firebase Connection

1. Login with your admin account
2. Navigate to the dashboard
3. Click "Sync Data" button
4. Verify that users and conversations are loading

### Step 3: Test SMS Alerts (Optional)

1. Ensure `TWILIO_ADMIN_NUMBERS` includes your phone number
2. Create a test high-risk message in Firebase Firestore
3. Wait for sync (max 2 minutes)
4. Verify SMS alert is received

### Step 4: Setup SSL Certificate (If Not Done During Deployment)

If you have a domain but didn't configure it during deployment:

```bash
# Update Nginx config with your domain
sudo nano /etc/nginx/sites-available/theradash
# Change: server_name _; to server_name yourdomain.com;

# Test and reload Nginx
sudo nginx -t
sudo systemctl reload nginx

# Run Certbot
sudo certbot --nginx -d yourdomain.com
```

Follow the prompts to complete SSL setup.

---

## Monitoring and Maintenance

### Viewing Logs

**Application Logs**:
```bash
# Gunicorn error log
tail -f ~/theradash/logs/gunicorn_error.log

# Gunicorn access log
tail -f ~/theradash/logs/gunicorn_access.log

# Supervisor logs
tail -f ~/theradash/logs/supervisor_error.log
```

**Nginx Logs**:
```bash
sudo tail -f /var/log/nginx/theradash_access.log
sudo tail -f /var/log/nginx/theradash_error.log
```

**Cron Job Logs**:
```bash
tail -f ~/theradash/logs/cron_sync.log
```

### Managing the Application

**Restart Application**:
```bash
sudo supervisorctl restart theradash
```

**Stop Application**:
```bash
sudo supervisorctl stop theradash
```

**Start Application**:
```bash
sudo supervisorctl start theradash
```

**View Application Status**:
```bash
sudo supervisorctl status theradash
```

### Updating the Application

```bash
cd ~/theradash
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo supervisorctl restart theradash
```

### Database Backup

**Manual Backup**:
```bash
cd ~/theradash/instance
sqlite3 theradash.db ".backup 'theradash_backup_$(date +%Y%m%d_%H%M%S).db'"
```

**Automated Daily Backup** (add to crontab):
```bash
crontab -e
```

Add this line:
```
0 2 * * * cd /home/ubuntu/theradash/instance && sqlite3 theradash.db ".backup 'theradash_backup_\$(date +\%Y\%m\%d).db'" && find . -name "theradash_backup_*.db" -mtime +7 -delete
```

This backs up daily at 2 AM and keeps 7 days of backups.

### Monitoring Disk Space

```bash
df -h
```

If running low on space:
```bash
# Clean old log files
find ~/theradash/logs -name "*.log" -mtime +30 -delete

# Clean old database backups
find ~/theradash/instance -name "theradash_backup_*.db" -mtime +30 -delete
```

### System Updates

**Monthly maintenance**:
```bash
sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get autoremove -y
```

---

## Troubleshooting

### Application Won't Start

1. **Check supervisor status**:
```bash
sudo supervisorctl status theradash
```

2. **Check logs**:
```bash
tail -50 ~/theradash/logs/supervisor_error.log
tail -50 ~/theradash/logs/gunicorn_error.log
```

3. **Common issues**:
   - Missing `.env` file: Copy from `.env.example`
   - Database not initialized: Run `python3 app.py` manually once
   - Port already in use: Check if another process is using port 8000

### Can't Access Website

1. **Check Nginx status**:
```bash
sudo systemctl status nginx
```

2. **Test Nginx configuration**:
```bash
sudo nginx -t
```

3. **Check Security Group**:
   - Verify ports 80/443 are open in AWS Security Group
   - Verify source IP restrictions allow your IP

4. **Check firewall**:
```bash
sudo ufw status
```

### Firebase Connection Issues

1. **Verify credentials file exists**:
```bash
ls -l ~/theradash/firebase-credentials.json
```

2. **Check environment variable**:
```bash
cd ~/theradash && source venv/bin/activate
python3 -c "from config import Config; print(Config.FIREBASE_CREDENTIALS_PATH)"
```

3. **Test Firebase connection manually**:
```bash
cd ~/theradash && source venv/bin/activate
python3 -c "from services.firebase_service import get_users; print(get_users())"
```

### Sync Not Working

1. **Check cron job installed**:
```bash
crontab -l | grep cron_sync
```

2. **Check cron logs**:
```bash
tail -50 ~/theradash/logs/cron_sync.log
```

3. **Run sync manually**:
```bash
cd ~/theradash && source venv/bin/activate
python3 cron_sync.py
```

4. **Verify user selection mode**:
```bash
cd ~/theradash && source venv/bin/activate
python3 -c "from config import Config; print(f'Mode: {Config.USER_SELECTION_MODE}')"
```

### High CPU or Memory Usage

1. **Check resource usage**:
```bash
top
# Press 'q' to quit
```

2. **Reduce Gunicorn workers**:
```bash
nano ~/theradash/gunicorn_config.py
# Change: workers = multiprocessing.cpu_count() * 2 + 1
# To: workers = 2
sudo supervisorctl restart theradash
```

3. **Consider upgrading instance type** if consistently high

### SSL Certificate Issues

1. **Renew certificate manually**:
```bash
sudo certbot renew
```

2. **Check certificate status**:
```bash
sudo certbot certificates
```

3. **Auto-renewal** should be configured by certbot. Test it:
```bash
sudo certbot renew --dry-run
```

### Database Locked Errors

SQLite can have concurrency issues with many simultaneous writes:

1. **Quick fix** - restart application:
```bash
sudo supervisorctl restart theradash
```

2. **Long-term solution** - consider PostgreSQL for production:
   - Launch RDS PostgreSQL instance
   - Update `DATABASE_URL` in `.env`
   - Install psycopg2: `pip install psycopg2-binary`
   - Re-initialize database

---

## Performance Optimization

### For Higher Traffic

1. **Upgrade instance type**: t2.medium → t2.large or t3.large

2. **Increase Gunicorn workers**:
```bash
nano ~/theradash/gunicorn_config.py
# Increase workers value
sudo supervisorctl restart theradash
```

3. **Add Redis for session storage**:
```bash
sudo apt-get install redis-server
pip install flask-session redis
```

4. **Enable Nginx caching** for static files (already configured)

5. **Consider using PostgreSQL** instead of SQLite for better concurrency

### For Multiple Instances

1. **Use Application Load Balancer** (ALB)
2. **Deploy to Auto Scaling Group**
3. **Use RDS for shared database**
4. **Use ElastiCache for session storage**

---

## Security Best Practices

1. **Keep software updated**:
```bash
sudo apt-get update && sudo apt-get upgrade -y
```

2. **Monitor logs for suspicious activity**:
```bash
sudo tail -f /var/log/nginx/theradash_access.log
```

3. **Regularly rotate secrets**:
   - Update `SECRET_KEY` periodically
   - Rotate API tokens when staff changes
   - Update `REGISTRATION_KEY` after initial setup

4. **Enable AWS CloudWatch** monitoring

5. **Setup AWS CloudTrail** for API auditing

6. **Use IAM roles** instead of AWS access keys when possible

7. **Enable AWS GuardDuty** for threat detection

8. **Backup regularly** (see Database Backup section)

---

## Cost Estimation

**Monthly AWS Costs** (approximate):

| Resource | Specification | Estimated Cost |
|----------|--------------|----------------|
| EC2 t2.medium | 2 vCPU, 4 GB RAM | $30-35/month |
| EBS Storage | 20 GB gp3 | $2/month |
| Elastic IP | 1 address | $0 (free when attached) |
| Data Transfer | < 1 GB/month | $0 (free tier) |
| Route 53 (optional) | Hosted zone + queries | $0.50-1/month |
| **Total** | | **$32-38/month** |

**Notes**:
- Costs may vary by region
- Free tier eligible for new AWS accounts (first 12 months)
- Snapshot backups add $0.05/GB-month

---

## Support and Resources

### Documentation
- Main README: `/README.md`
- Project Summary: `/PROJECT_SUMMARY.md`
- Cron Setup: `/CRON_SETUP.md`
- Implementation Notes: `/IMPLEMENTATION_NOTES.md`

### Logs Location
- Application: `~/theradash/logs/`
- Nginx: `/var/log/nginx/`
- System: `/var/log/syslog`

### Useful Commands Cheat Sheet
```bash
# Application Management
sudo supervisorctl status theradash
sudo supervisorctl restart theradash
sudo supervisorctl stop theradash
sudo supervisorctl start theradash

# View Logs
tail -f ~/theradash/logs/gunicorn_error.log
tail -f ~/theradash/logs/cron_sync.log
sudo tail -f /var/log/nginx/theradash_error.log

# Nginx Management
sudo systemctl status nginx
sudo systemctl restart nginx
sudo nginx -t

# Database Backup
cd ~/theradash/instance && sqlite3 theradash.db ".backup backup.db"

# Check Cron Status
cd ~/theradash && ./check_cron_status.sh

# Update Application
cd ~/theradash && git pull && source venv/bin/activate && pip install -r requirements.txt && sudo supervisorctl restart theradash
```

---

## Next Steps After Deployment

1. ✅ Register admin account
2. ✅ Verify Firebase sync working
3. ✅ Test SMS alerts
4. ✅ Review security group rules
5. ✅ Setup monitoring/alerts
6. ✅ Configure automated backups
7. ✅ Document admin procedures
8. ✅ Train staff on dashboard usage

---

## Questions or Issues?

If you encounter issues not covered in this guide:
1. Check application logs first
2. Review error messages carefully
3. Consult the troubleshooting section
4. Contact your development team
