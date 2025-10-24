#!/bin/bash
# Check the status of the TheraChat cron job

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}TheraChat Cron Job Status${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Check if cron job exists
if crontab -l 2>/dev/null | grep -q "cron_sync.py"; then
    echo -e "${GREEN}✓ Cron job is installed${NC}\n"
    echo -e "${YELLOW}Current cron job:${NC}"
    crontab -l | grep "cron_sync.py"
    echo
else
    echo -e "${RED}✗ Cron job is NOT installed${NC}"
    echo -e "${YELLOW}Run ./setup_cron.sh to install it${NC}\n"
    exit 1
fi

# Check log file
LOG_FILE="/Users/mvh24011/theradash/logs/cron_sync.log"
if [ -f "$LOG_FILE" ]; then
    echo -e "${GREEN}✓ Log file exists${NC}"
    echo -e "${YELLOW}Last 5 sync runs:${NC}\n"
    grep "Starting automated sync" "$LOG_FILE" | tail -5
    echo

    # Check for recent errors
    RECENT_ERRORS=$(tail -100 "$LOG_FILE" | grep -i "error\|failed" | wc -l)
    if [ "$RECENT_ERRORS" -gt 0 ]; then
        echo -e "${YELLOW}⚠ Found $RECENT_ERRORS error(s) in recent logs${NC}"
        echo -e "${YELLOW}View errors with: tail -100 $LOG_FILE | grep -i error${NC}\n"
    else
        echo -e "${GREEN}✓ No recent errors found${NC}\n"
    fi
else
    echo -e "${YELLOW}⚠ Log file not found (cron may not have run yet)${NC}"
    echo -e "${YELLOW}Expected location: $LOG_FILE${NC}\n"
fi

# Check if script is executable
SCRIPT="/Users/mvh24011/theradash/cron_sync.py"
if [ -x "$SCRIPT" ]; then
    echo -e "${GREEN}✓ Sync script is executable${NC}\n"
else
    echo -e "${RED}✗ Sync script is NOT executable${NC}"
    echo -e "${YELLOW}Fix with: chmod +x $SCRIPT${NC}\n"
fi

# Check virtual environment
VENV="/Users/mvh24011/theradash/venv/bin/python"
if [ -f "$VENV" ]; then
    echo -e "${GREEN}✓ Virtual environment found${NC}\n"
else
    echo -e "${YELLOW}⚠ Virtual environment not found at expected location${NC}\n"
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Quick Commands${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "View live logs:    ${GREEN}tail -f $LOG_FILE${NC}"
echo -e "Test manually:     ${GREEN}cd /Users/mvh24011/theradash && ./venv/bin/python cron_sync.py${NC}"
echo -e "Edit cron jobs:    ${GREEN}crontab -e${NC}"
echo -e "Remove cron job:   ${GREEN}crontab -l | grep -v 'cron_sync.py' | crontab -${NC}"
echo
