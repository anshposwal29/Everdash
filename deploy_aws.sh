#!/bin/bash

###############################################################################
# Theradash AWS EC2 Deployment Script
#
# This script automates the deployment of Theradash on an AWS EC2 t2.medium
# instance running Ubuntu 22.04 LTS.
#
# Prerequisites:
#   - Fresh Ubuntu 22.04 LTS EC2 instance
#   - SSH access to the instance
#   - Security group allowing ports 80 and 443
#
# Usage:
#   ./deploy_aws.sh
#
# Author: Theradash Team
# Last Updated: October 2025
###############################################################################

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/home/ubuntu/theradash"
APP_USER="ubuntu"
PYTHON_VERSION="3.8"
DOMAIN_NAME="${DOMAIN_NAME:-}"  # Optional: set via environment variable

###############################################################################
# Helper Functions
###############################################################################

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should NOT be run as root. Run as ubuntu user with sudo privileges."
        exit 1
    fi
}

###############################################################################
# Installation Steps
###############################################################################

install_system_dependencies() {
    print_status "Installing system dependencies..."
    sudo apt-get update
    sudo apt-get install -y \
        python3.8 \
        python3.8-venv \
        python3-pip \
        nginx \
        supervisor \
        git \
        sqlite3 \
        certbot \
        python3-certbot-nginx \
        build-essential \
        libssl-dev \
        libffi-dev \
        python3-dev

    print_status "System dependencies installed successfully"
}

setup_application() {
    print_status "Setting up application directory..."

    # Application should already be cloned/deployed to APP_DIR
    if [ ! -d "$APP_DIR" ]; then
        print_error "Application directory $APP_DIR does not exist!"
        print_error "Please clone the repository to $APP_DIR first"
        exit 1
    fi

    cd "$APP_DIR"

    # Create virtual environment
    print_status "Creating Python virtual environment..."
    python3.8 -m venv venv
    source venv/bin/activate

    # Upgrade pip
    print_status "Upgrading pip..."
    pip install --upgrade pip

    # Install Python dependencies
    print_status "Installing Python dependencies..."
    pip install -r requirements.txt
    pip install gunicorn  # Production WSGI server

    # Create necessary directories
    print_status "Creating necessary directories..."
    mkdir -p instance logs

    # Set permissions
    print_status "Setting permissions..."
    sudo chown -R $APP_USER:$APP_USER "$APP_DIR"
    chmod +x setup_cron.sh check_cron_status.sh

    print_status "Application setup complete"
}

configure_environment() {
    print_status "Configuring environment variables..."

    if [ ! -f "$APP_DIR/.env" ]; then
        print_warning ".env file not found. Creating from template..."
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"

        # Generate a random secret key
        SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
        sed -i "s/your-secret-key-here/$SECRET_KEY/" "$APP_DIR/.env"

        print_warning "IMPORTANT: Edit $APP_DIR/.env and configure all required values:"
        print_warning "  - FIREBASE_CREDENTIALS_PATH"
        print_warning "  - REDCAP_API_URL and REDCAP_API_TOKEN"
        print_warning "  - TWILIO credentials"
        print_warning "  - IP_PREFIX_ALLOWED"
        print_warning "  - REGISTRATION_KEY"

        read -p "Press Enter after you have configured .env file..."
    else
        print_status ".env file already exists"
    fi
}

initialize_database() {
    print_status "Initializing database..."
    cd "$APP_DIR"
    source venv/bin/activate

    # Run a quick Python script to initialize the database
    python3 << EOF
from app import app, db
with app.app_context():
    db.create_all()
    print("Database initialized successfully")
EOF

    print_status "Database initialized"
}

configure_gunicorn() {
    print_status "Configuring Gunicorn..."

    cat > "$APP_DIR/gunicorn_config.py" << 'EOF'
import multiprocessing

# Gunicorn configuration file
bind = "127.0.0.1:8000"
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = "/home/ubuntu/theradash/logs/gunicorn_access.log"
errorlog = "/home/ubuntu/theradash/logs/gunicorn_error.log"
loglevel = "info"

# Process naming
proc_name = "theradash"

# Server mechanics
daemon = False
pidfile = "/home/ubuntu/theradash/gunicorn.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
EOF

    print_status "Gunicorn configured"
}

configure_supervisor() {
    print_status "Configuring Supervisor..."

    sudo tee /etc/supervisor/conf.d/theradash.conf > /dev/null << EOF
[program:theradash]
command=/home/ubuntu/theradash/venv/bin/gunicorn -c /home/ubuntu/theradash/gunicorn_config.py app:app
directory=/home/ubuntu/theradash
user=ubuntu
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true
stderr_logfile=/home/ubuntu/theradash/logs/supervisor_error.log
stdout_logfile=/home/ubuntu/theradash/logs/supervisor_access.log
environment=PATH="/home/ubuntu/theradash/venv/bin"
EOF

    # Reload supervisor
    sudo supervisorctl reread
    sudo supervisorctl update

    print_status "Supervisor configured and started"
}

configure_nginx() {
    print_status "Configuring Nginx..."

    # Backup default nginx config
    if [ -f /etc/nginx/sites-enabled/default ]; then
        sudo mv /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/default.bak
    fi

    # Create nginx configuration
    sudo tee /etc/nginx/sites-available/theradash > /dev/null << 'EOF'
server {
    listen 80;
    server_name _;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Logging
    access_log /var/log/nginx/theradash_access.log;
    error_log /var/log/nginx/theradash_error.log;

    # Max upload size
    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /static {
        alias /home/ubuntu/theradash/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

    # Enable the site
    sudo ln -sf /etc/nginx/sites-available/theradash /etc/nginx/sites-enabled/

    # Test nginx configuration
    sudo nginx -t

    # Restart nginx
    sudo systemctl restart nginx
    sudo systemctl enable nginx

    print_status "Nginx configured and restarted"
}

setup_ssl() {
    if [ -z "$DOMAIN_NAME" ]; then
        print_warning "No domain name provided. Skipping SSL setup."
        print_warning "To setup SSL later, run: sudo certbot --nginx -d your-domain.com"
        return
    fi

    print_status "Setting up SSL with Let's Encrypt for $DOMAIN_NAME..."

    # Update nginx config with domain name
    sudo sed -i "s/server_name _;/server_name $DOMAIN_NAME;/" /etc/nginx/sites-available/theradash
    sudo nginx -t
    sudo systemctl reload nginx

    # Run certbot
    sudo certbot --nginx -d "$DOMAIN_NAME" --non-interactive --agree-tos --email admin@${DOMAIN_NAME}

    print_status "SSL configured successfully"
}

setup_cron() {
    print_status "Setting up automated sync cron job..."
    cd "$APP_DIR"
    bash setup_cron.sh
    print_status "Cron job configured"
}

configure_firewall() {
    print_status "Configuring firewall..."

    # Enable UFW if not already enabled
    sudo ufw --force enable

    # Allow SSH, HTTP, and HTTPS
    sudo ufw allow 22/tcp
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp

    # Show status
    sudo ufw status

    print_status "Firewall configured"
}

print_summary() {
    echo ""
    echo "=========================================================================="
    echo -e "${GREEN}Theradash Deployment Complete!${NC}"
    echo "=========================================================================="
    echo ""
    echo "Application Status:"
    echo "  - Application Directory: $APP_DIR"
    echo "  - Database: $APP_DIR/instance/theradash.db"
    echo "  - Logs: $APP_DIR/logs/"
    echo ""
    echo "Services:"
    echo "  - Gunicorn: Running via Supervisor"
    echo "  - Nginx: Running on port 80/443"
    echo "  - Cron: Syncing every 2 minutes"
    echo ""
    echo "Useful Commands:"
    echo "  - Check app status: sudo supervisorctl status theradash"
    echo "  - Restart app: sudo supervisorctl restart theradash"
    echo "  - View logs: tail -f $APP_DIR/logs/gunicorn_error.log"
    echo "  - Check cron: cd $APP_DIR && ./check_cron_status.sh"
    echo "  - View nginx logs: sudo tail -f /var/log/nginx/theradash_error.log"
    echo ""
    echo "Next Steps:"
    echo "  1. Access the application at http://$(curl -s ifconfig.me)"
    if [ -n "$DOMAIN_NAME" ]; then
        echo "     or https://$DOMAIN_NAME"
    fi
    echo "  2. Register an admin account using the REGISTRATION_KEY from .env"
    echo "  3. Monitor logs for any errors"
    echo "  4. Verify Firebase sync is working"
    echo ""
    echo "Security Reminders:"
    echo "  - Ensure AWS Security Group limits access to your VPN IP range"
    echo "  - Keep .env file secure (contains API keys)"
    echo "  - Regularly update system: sudo apt-get update && sudo apt-get upgrade"
    echo "  - Monitor logs for unauthorized access attempts"
    echo ""
    echo "=========================================================================="
}

###############################################################################
# Main Execution
###############################################################################

main() {
    print_status "Starting Theradash AWS Deployment..."
    echo ""

    check_root

    # Run installation steps
    install_system_dependencies
    setup_application
    configure_environment
    initialize_database
    configure_gunicorn
    configure_supervisor
    configure_nginx
    setup_ssl
    setup_cron
    configure_firewall

    # Print summary
    print_summary
}

# Run main function
main
