#!/bin/bash
# Setup script for installing the TheraChat sync cron job
# This script helps you configure automatic syncing every 2 minutes

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}TheraChat Cron Job Setup${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Get absolute paths
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PYTHON_PATH=$(which python3)
CRON_SCRIPT="${SCRIPT_DIR}/cron_sync.py"
LOG_DIR="${SCRIPT_DIR}/logs"
LOG_FILE="${LOG_DIR}/cron_sync.log"

# Create logs directory if it doesn't exist
mkdir -p "$LOG_DIR"

echo -e "${YELLOW}Project Directory:${NC} $SCRIPT_DIR"
echo -e "${YELLOW}Python Path:${NC} $PYTHON_PATH"
echo -e "${YELLOW}Log File:${NC} $LOG_FILE\n"

# Check if venv exists
if [ -d "${SCRIPT_DIR}/venv" ]; then
    PYTHON_PATH="${SCRIPT_DIR}/venv/bin/python"
    echo -e "${GREEN}✓ Found virtual environment${NC}"
    echo -e "${YELLOW}Using Python:${NC} $PYTHON_PATH\n"
fi

# Create the cron job command
CRON_COMMAND="*/2 * * * * cd ${SCRIPT_DIR} && ${PYTHON_PATH} ${CRON_SCRIPT} >> ${LOG_FILE} 2>&1"

echo -e "${YELLOW}Cron job to be installed:${NC}"
echo -e "${BLUE}$CRON_COMMAND${NC}\n"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "cron_sync.py"; then
    echo -e "${YELLOW}⚠ A cron job for cron_sync.py already exists.${NC}"
    echo -e "Current cron jobs:\n"
    crontab -l | grep "cron_sync.py"
    echo
    read -p "Do you want to replace it? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}Installation cancelled.${NC}"
        exit 1
    fi
    # Remove old cron job
    crontab -l | grep -v "cron_sync.py" | crontab -
    echo -e "${GREEN}✓ Old cron job removed${NC}\n"
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_COMMAND") | crontab -

echo -e "${GREEN}✓ Cron job installed successfully!${NC}\n"

# Test the script
echo -e "${BLUE}Testing the sync script...${NC}"
cd "$SCRIPT_DIR"
$PYTHON_PATH "$CRON_SCRIPT"

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✓ Test run completed successfully!${NC}\n"
else
    echo -e "\n${RED}✗ Test run failed. Please check the output above.${NC}\n"
    exit 1
fi

# Display current cron jobs
echo -e "${BLUE}Current cron jobs:${NC}"
crontab -l
echo

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}\n"

echo -e "${YELLOW}The sync will now run automatically every 2 minutes.${NC}\n"

echo -e "${YELLOW}Useful commands:${NC}"
echo -e "  View logs:           ${BLUE}tail -f ${LOG_FILE}${NC}"
echo -e "  View cron jobs:      ${BLUE}crontab -l${NC}"
echo -e "  Remove cron job:     ${BLUE}crontab -e${NC} (then delete the line)"
echo -e "  Test manually:       ${BLUE}cd ${SCRIPT_DIR} && ${PYTHON_PATH} ${CRON_SCRIPT}${NC}\n"
