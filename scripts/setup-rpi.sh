#!/bin/bash

# PrinterPrinter Raspberry Pi Setup Script
# This script automates the installation and configuration of PrinterPrinter on a Raspberry Pi
# Usage: curl -fsSL https://raw.githubusercontent.com/<user>/<repo>/<branch>/scripts/setup-rpi.sh | bash

# Ensure we're using bash (not sh)
if [ -z "$BASH_VERSION" ]; then
    exec bash "$0" "$@"
fi

set -e  # Exit on error
set -o pipefail  # Exit if any part of a pipeline fails

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration defaults
INSTALL_DIR="/opt/printerprinter"
SERVICE_NAME="printerprinter"
GITHUB_REPO="${GITHUB_REPO:-https://github.com/firstbuild/PrinterPrinter.git}"
BRANCH="${1:-main}"
VENV_DIR="${INSTALL_DIR}/venv"
DB_DIR="${INSTALL_DIR}/data"

# Functions
print_header() {
    echo -e "\n${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  $1"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

prompt_for_value() {
    local prompt_text="$1"
    local default_value="$2"
    local result=""
    
    # Try to read from terminal first, fall back to stdin if not available
    if [ -t 0 ]; then
        # Terminal is available
        if [ -z "$default_value" ]; then
            read -p "$(echo -e ${BLUE}?)$(echo -e ${NC}) $prompt_text: " result
        else
            read -p "$(echo -e ${BLUE}?)$(echo -e ${NC}) $prompt_text [$default_value]: " result
            result="${result:-$default_value}"
        fi
    else
        # No terminal, use default (for piped execution)
        if [ -z "$default_value" ]; then
            print_error "Cannot read interactive input (script was piped). Use Method 2 instead:"
            print_info "curl -fsSL https://raw.githubusercontent.com/firstbuild/PrinterPrinter/main/scripts/setup-rpi.sh -o /tmp/setup.sh && sudo bash /tmp/setup.sh"
            exit 1
        else
            result="$default_value"
            print_info "$prompt_text: $result (using default)"
        fi
    fi
    
    echo "$result"
}

prompt_yes_no() {
    local prompt_text="$1"
    local response=""
    
    # Check if terminal is available
    if [ ! -t 0 ]; then
        print_error "Cannot read interactive input (script was piped). Use Method 2 instead:"
        print_info "curl -fsSL https://raw.githubusercontent.com/firstbuild/PrinterPrinter/main/scripts/setup-rpi.sh -o /tmp/setup.sh && sudo bash /tmp/setup.sh"
        exit 1
    fi
    
    while true; do
        read -p "$(echo -e ${BLUE}?)$(echo -e ${NC}) $prompt_text (y/n): " response
        case "$response" in
            [yY]) return 0 ;;
            [nN]) return 1 ;;
            *) echo "Please answer y or n." ;;
        esac
    done
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

check_system_dependencies() {
    print_header "Checking System Dependencies"
    
    local missing_deps=()
    
    # Check for required commands
    for cmd in git python3 curl; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_deps+=("$cmd")
        else
            print_success "$cmd is installed"
        fi
    done
    
    # If missing dependencies, try to install them
    if [ ${#missing_deps[@]} -gt 0 ]; then
        print_warning "Missing dependencies: ${missing_deps[*]}"
        print_info "Attempting to install missing dependencies..."
        
        # Update package manager
        apt-get update || print_warning "Failed to update package lists"
        
        # Install each missing dependency
        for dep in "${missing_deps[@]}"; do
            case "$dep" in
                git)
                    apt-get install -y git || print_error "Failed to install git"
                    ;;
                python3)
                    apt-get install -y python3 python3-venv python3-dev || print_error "Failed to install python3"
                    ;;
                curl)
                    apt-get install -y curl || print_error "Failed to install curl"
                    ;;
            esac
        done
    fi
    
    # Verify Python version
    python3_version=$(python3 --version 2>&1 | awk '{print $2}')
    print_info "Python version: $python3_version"
}

detect_existing_installation() {
    if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/.env" ]; then
        return 0  # Installation exists
    else
        return 1  # No existing installation
    fi
}

gather_configuration() {
    print_header "PrinterPrinter Configuration"
    print_info "Please provide the following configuration details:"
    
    # Bambuddy Configuration
    print_info "Bambuddy Configuration"
    BAMBUDDY_HOST=$(prompt_for_value "Bambuddy host address" "bambuddy.local")
    BAMBUDDY_PORT=$(prompt_for_value "Bambuddy port" "8000")
    BAMBUDDY_API_TOKEN=$(prompt_for_value "Bambuddy API key")
    
    # Printer Configuration
    print_info "Printer Configuration"
    echo "Provide printer identifiers (serial numbers, IP addresses, or names)."
    echo "You can specify multiple printers separated by commas."
    PRINTER_IDENTIFIERS=$(prompt_for_value "Printer identifier(s)" "")
    
    # Brother Printer Configuration
    print_info "Brother Label Printer Configuration"
    BROTHER_PRINTER_IP=$(prompt_for_value "Brother printer IP address")
    
    LABEL_SIZE=$(prompt_for_value "Label size (e.g., 62x100, 62x29)" "62x100")
    
    # Pricing Configuration
    print_info "Pricing Configuration"
    read -p "$(echo -e ${BLUE}?)$(echo -e ${NC}) Show price on labels? [Y/n]: " price_response
    price_response="${price_response:-y}"  # Default to 'yes' if user just presses enter
    case "$price_response" in
        [yY]) 
            SHOW_PRICE="true"
            PRICE_PER_GRAM=$(prompt_for_value "Price per gram in USD" "0.10")
            ;;
        [nN]) 
            SHOW_PRICE="false"
            PRICE_PER_GRAM="0.10"
            ;;
        *) 
            print_warning "Invalid response, assuming yes"
            SHOW_PRICE="true"
            PRICE_PER_GRAM=$(prompt_for_value "Price per gram in USD" "0.10")
            ;;
    esac
    
    print_success "Configuration complete"
}

setup_repository() {
    print_header "Setting Up Repository"
    
    if detect_existing_installation; then
        print_info "Updating existing installation at $INSTALL_DIR"
        cd "$INSTALL_DIR"
        git fetch origin
        git checkout "$BRANCH"
        git pull origin "$BRANCH"
    else
        print_info "Creating new installation at $INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
        git clone -b "$BRANCH" "$GITHUB_REPO" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi
    
    print_success "Repository ready at $INSTALL_DIR"
}

setup_python_environment() {
    print_header "Setting Up Python Environment"
    
    cd "$INSTALL_DIR"
    
    # Create virtual environment
    if [ ! -d "$VENV_DIR" ]; then
        print_info "Creating Python virtual environment..."
        python3 -m venv "$VENV_DIR" 2>&1 | grep -v "^$" || true
        print_success "Virtual environment created"
    else
        print_info "Virtual environment already exists"
    fi
    
    # Install dependencies
    print_info "Installing Python dependencies..."
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    
    pip install --upgrade pip setuptools wheel >/dev/null 2>&1 || print_warning "pip upgrade had issues"
    pip install -e . >/dev/null 2>&1 || print_error "Failed to install project dependencies"
    
    print_success "Python dependencies installed"
}

create_env_file() {
    print_header "Creating Configuration File"
    
    local env_file="$INSTALL_DIR/.env"
    
    cat > "$env_file" << EOF
# PrinterPrinter Configuration
# Generated by setup-rpi.sh on $(date)

# Server Configuration
PRINTERPRINTER_HOST=0.0.0.0
PRINTERPRINTER_PORT=8080
PRINTERPRINTER_LOG_LEVEL=INFO
PRINTERPRINTER_DB_PATH=$DB_DIR/printerprinter.sqlite3

# Bambuddy Configuration
BAMBUDDY_BASE_URL=http://$BAMBUDDY_HOST:$BAMBUDDY_PORT
BAMBUDDY_API_TOKEN=$BAMBUDDY_API_TOKEN
BAMBUDDY_TIMEOUT_SECONDS=15
BAMBUDDY_AUTH_MODE=api_key_header
BAMBUDDY_AUTH_HEADER_NAME=X-API-Key
BAMBUDDY_JOBS_ENDPOINT=/api/v1/print-log/
BAMBUDDY_PRINTERS_ENDPOINT=/api/v1/printers/
BAMBUDDY_PRINTER_STATUS_ENDPOINT_TEMPLATE=/api/v1/printers/{printer_id}/status

# Polling Configuration
PRINTERPRINTER_POLL_INTERVAL_SECONDS=5

# Printer Selection (comma-separated identifiers)
PRINTERPRINTER_MONITORED_PRINTER_IDENTIFIERS=$PRINTER_IDENTIFIERS

# ========================================
# Brother Label Printer Configuration
# ========================================
BROTHER_ENABLED=true
BROTHER_MODEL=QL-820NWB

# Brother printer IP and port (e.g., tcp://192.168.1.100:9100)
BROTHER_PRINTER_URI=tcp://$BROTHER_PRINTER_IP:9100

# Label configuration
BROTHER_LABEL_SIZE=$LABEL_SIZE
BROTHER_CUT=true

# ========================================
# Pricing Configuration
# ========================================
SHOW_PRICE_ON_LABEL=$SHOW_PRICE
FILAMENT_PRICE_PER_GRAM=$PRICE_PER_GRAM
EOF
    
    chmod 644 "$env_file"
    print_success "Configuration file created at $env_file"
}

create_data_directory() {
    print_header "Setting Up Data Directory"
    
    mkdir -p "$DB_DIR"
    chmod 755 "$DB_DIR"
    
    print_success "Data directory ready at $DB_DIR"
}

create_systemd_service() {
    print_header "Creating Systemd Service"
    
    local service_file="/etc/systemd/system/${SERVICE_NAME}.service"
    
    cat > "$service_file" << EOF
[Unit]
Description=PrinterPrinter - Bambu Printer Label Daemon
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$VENV_DIR/bin/uvicorn printerprinter.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
StandardInput=null

[Install]
WantedBy=multi-user.target
EOF
    
    chmod 644 "$service_file"
    systemctl daemon-reload
    
    print_success "Systemd service created"
}

start_service() {
    print_header "Starting PrinterPrinter Service"
    
    print_info "Enabling service..."
    systemctl enable "$SERVICE_NAME" || print_error "Failed to enable service"
    
    print_info "Starting service..."
    systemctl start "$SERVICE_NAME" || print_error "Failed to start service"
    
    # Give the service a moment to start
    sleep 2
    
    # Check service status
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service is running"
    else
        print_error "Service failed to start. Check logs with: journalctl -u $SERVICE_NAME -n 50"
    fi
}

verify_installation() {
    print_header "Verifying Installation"
    
    cd "$INSTALL_DIR"
    
    # Check configuration file
    if [ -f ".env" ]; then
        print_success "Configuration file exists"
    else
        print_error "Configuration file not found"
    fi
    
    # Check virtual environment
    if [ -d "$VENV_DIR" ]; then
        print_success "Virtual environment exists"
    else
        print_error "Virtual environment not found"
    fi
    
    # Check service
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        print_success "Service is active"
    else
        print_warning "Service is not active"
    fi
    
    print_info "Service status:"
    systemctl status "$SERVICE_NAME" --no-pager || true
}

show_next_steps() {
    print_header "Installation Complete"
    
    print_info "PrinterPrinter has been installed and configured!"
    
    echo -e "\n${GREEN}Next Steps:${NC}"
    echo "1. Monitor logs:"
    echo "   journalctl -u $SERVICE_NAME -f"
    echo ""
    echo "2. Check health:"
    echo "   curl http://localhost:8080/health"
    echo ""
    echo "3. View printers:"
    echo "   curl http://localhost:8080/admin/printers"
    echo ""
    echo "4. View events:"
    echo "   curl http://localhost:8080/admin/events"
    echo ""
    echo "5. Manage service:"
    echo "   systemctl restart $SERVICE_NAME"
    echo "   systemctl stop $SERVICE_NAME"
    echo "   systemctl status $SERVICE_NAME"
    echo ""
    echo "Configuration file: $INSTALL_DIR/.env"
    echo "Log in: journalctl -u $SERVICE_NAME"
    echo ""
}

# Main execution
main() {
    print_header "PrinterPrinter Raspberry Pi Setup"
    
    # Check if stdin is a terminal (interactive mode)
    if [ ! -t 0 ]; then
        print_error "This script requires interactive input but was executed without a terminal."
        echo ""
        print_warning "You appear to be using piped execution (curl ... | sudo bash)"
        echo ""
        print_info "Use Method 2 instead for reliable interactive setup:"
        echo "  curl -fsSL https://raw.githubusercontent.com/firstbuild/PrinterPrinter/main/scripts/setup-rpi.sh -o /tmp/setup.sh"
        echo "  sudo bash /tmp/setup.sh"
        echo ""
        exit 1
    fi
    
    check_root
    check_system_dependencies
    
    if detect_existing_installation; then
        print_warning "PrinterPrinter is already installed at $INSTALL_DIR"
        if ! prompt_yes_no "Do you want to reconfigure the existing installation?"; then
            print_info "Using existing configuration"
            setup_repository
            setup_python_environment
            
            if prompt_yes_no "Restart the service?"; then
                systemctl restart "$SERVICE_NAME"
                print_success "Service restarted"
            fi
            
            verify_installation
            show_next_steps
            exit 0
        fi
    fi
    
    gather_configuration
    setup_repository
    create_data_directory
    setup_python_environment
    create_env_file
    create_systemd_service
    start_service
    verify_installation
    show_next_steps
}

# Handle script errors
trap 'print_error "Setup failed. Check the output above for details."; exit 1' ERR

# Run main function
main "$@"
