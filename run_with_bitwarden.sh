#!/bin/bash
"""
Wrapper script to run cert_manager.py with Bitwarden credentials
This script unlocks Bitwarden vault and runs cert_manager.py with credentials from Bitwarden
"""

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}FTD Certificate Manager - Bitwarden Integration${NC}"
echo "=================================================="

# Check if bw CLI is installed
if ! command -v bw &> /dev/null; then
    echo -e "${RED}Error: Bitwarden CLI (bw) is not installed${NC}"
    echo "Install it with one of the following methods:"
    echo "  - npm install -g @bitwarden/cli"
    echo "  - snap install bw"
    echo "  - Download from: https://bitwarden.com/download/"
    exit 1
fi

echo -e "${GREEN}✓${NC} Bitwarden CLI found: $(bw --version)"

# Check if already logged in
if ! bw login --check &> /dev/null; then
    echo -e "${YELLOW}Not logged into Bitwarden${NC}"
    echo "Please login to Bitwarden:"
    bw login
fi

echo -e "${GREEN}✓${NC} Logged into Bitwarden"

# Check if vault is unlocked
if ! bw unlock --check &> /dev/null; then
    echo -e "${YELLOW}Vault is locked${NC}"
    echo "Please enter your master password to unlock:"
    
    # Unlock and capture session key
    export BW_SESSION=$(bw unlock --raw)
    
    if [ -z "$BW_SESSION" ]; then
        echo -e "${RED}Failed to unlock Bitwarden vault${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓${NC} Vault unlocked successfully"
else
    # Already unlocked, get session
    echo -e "${GREEN}✓${NC} Vault already unlocked"
    
    # Try to get existing session from environment
    if [ -z "$BW_SESSION" ]; then
        echo -e "${YELLOW}BW_SESSION not set, requesting new unlock${NC}"
        export BW_SESSION=$(bw unlock --raw)
    fi
fi

# Sync vault (optional, ensures latest data)
echo "Syncing Bitwarden vault..."
bw sync --session "$BW_SESSION" > /dev/null 2>&1 || echo -e "${YELLOW}Warning: Vault sync failed, using cached data${NC}"

echo ""
echo -e "${GREEN}Running Certificate Manager...${NC}"
echo "================================"

# Run cert_manager.py with Bitwarden session
# The script will automatically fetch credentials from Bitwarden
sudo -E BW_SESSION="$BW_SESSION" venv/bin/python cert_manager.py "$@"

# Capture exit code
EXIT_CODE=$?

# Lock vault for security (optional)
if [ "$BITWARDEN_AUTO_LOCK" = "true" ]; then
    echo ""
    echo "Locking Bitwarden vault..."
    bw lock
    echo -e "${GREEN}✓${NC} Vault locked"
fi

# Clear session from environment
unset BW_SESSION

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✓ Certificate Manager completed successfully${NC}"
else
    echo ""
    echo -e "${RED}✗ Certificate Manager failed with exit code: $EXIT_CODE${NC}"
fi

exit $EXIT_CODE
