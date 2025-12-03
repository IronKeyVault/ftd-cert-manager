#!/bin/bash
set -e

echo "=========================================="
echo "FTD Certificate Manager Setup"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
   echo "Please do not run this script as root"
   exit 1
fi

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "Setting up in: $SCRIPT_DIR"
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Found Python $PYTHON_VERSION"
echo ""

# Check if certbot is installed
echo "Checking for certbot..."
if ! command -v certbot &> /dev/null; then
    echo "Warning: certbot is not installed"
    echo "Installing certbot..."
    sudo apt update
    sudo apt install -y certbot python3-certbot-dns-cloudflare
else
    echo "certbot is already installed"
fi
echo ""

# Create virtual environment
echo "Creating Python virtual environment..."
if [ -d "venv" ]; then
    echo "Virtual environment already exists, skipping..."
else
    python3 -m venv venv
    echo "Virtual environment created"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip
echo ""

# Install requirements
echo "Installing Python dependencies..."
pip install -r requirements.txt
echo ""

# Create directories
echo "Creating directories..."
mkdir -p certs
mkdir -p logs
mkdir -p scripts
mkdir -p systemd
echo "Directories created"
echo ""

# Set permissions
echo "Setting permissions..."
chmod 755 cert_manager.py
chmod 700 certs
chmod 755 logs
echo "Permissions set"
echo ""

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Creating .env file from .env.example..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo ".env file created. Please edit it with your configuration:"
        echo "  nano .env"
    else
        echo "Warning: .env.example not found"
    fi
else
    echo ".env file already exists"
fi
echo ""

# Create .gitignore if it doesn't exist
if [ ! -f ".gitignore" ]; then
    echo "Creating .gitignore..."
    cat > .gitignore << 'EOF'
# Environment variables
.env
.cloudflare-credentials

# Python
venv/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info/
dist/
build/

# Certificates and keys
certs/*.pem
certs/*.key
certs/*.crt
*.pem
*.key
*.crt

# Logs
logs/*.log

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
EOF
    echo ".gitignore created"
fi
echo ""

echo "=========================================="
echo "Setup completed successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit your .env file with your configuration:"
echo "   nano .env"
echo ""
echo "2. If using Cloudflare DNS, create .cloudflare-credentials:"
echo "   nano .cloudflare-credentials"
echo "   chmod 600 .cloudflare-credentials"
echo ""
echo "3. Test the certificate manager:"
echo "   source venv/bin/activate"
echo "   ./cert_manager.py"
echo ""
echo "4. Install systemd timer for automatic renewal:"
echo "   sudo cp systemd/ftd-cert-renew.service /etc/systemd/system/"
echo "   sudo cp systemd/ftd-cert-renew.timer /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable ftd-cert-renew.timer"
echo "   sudo systemctl start ftd-cert-renew.timer"
echo ""
