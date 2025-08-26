#!/usr/bin/bash
# ROC (Remote OBS Controller) Installation Script
# Author: Aidan A. Bradley
# Version: 3.0.0b
#
# Enhanced installer with:
# - Improved error handling and rollback
# - Better progress tracking
# - Configuration validation
# - Service health checks
# - Post-install verification

set -euo pipefail

# Colors and formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

# Installation configuration
ROC_VERSION="1.0.1"
ROC_USER="roc"
ROC_HOME="/opt/roc"
ROC_CONFIG_DIR="/etc/roc"
ROC_LOG_DIR="/var/log/roc"
INSTALL_LOG="$ROC_LOG_DIR/roc_install.log"
SYSTEMD_SERVICE_DIR="/etc/systemd/system"
TEMP_INSTALL_DIR="/tmp/roc-install-$$"
INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Installation state tracking
INSTALL_STEP=0
TOTAL_STEPS=15
ROLLBACK_ACTIONS=()

# Enhanced logging with progress tracking
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    echo -e "$timestamp [$level] $message" | tee -a "$INSTALL_LOG" 2>/dev/null || echo "$timestamp [$level] $message"
    
    case "$level" in
        "ERROR")   echo -e "${RED}❌ ERROR: $message${NC}" ;;
        "SUCCESS") echo -e "${GREEN}✅ SUCCESS: $message${NC}" ;;
        "WARNING") echo -e "${YELLOW}⚠️  WARNING: $message${NC}" ;;
        "INFO")    echo -e "${BLUE}ℹ️  INFO: $message${NC}" ;;
        "STEP")    echo -e "${PURPLE}📋 STEP $INSTALL_STEP/$TOTAL_STEPS: $message${NC}" ;;
        "PROGRESS") echo -e "${CYAN}⚡ $message${NC}" ;;
    esac
}

error() { 
    log "ERROR" "$@"
    rollback_installation
    exit 1
}

success() { log "SUCCESS" "$@"; }
warning() { log "WARNING" "$@"; }
info() { log "INFO" "$@"; }
step() { 
    install_step=$((INSTALL_STEP + 1)) || true
    log "STEP" "$@"
}
progress() { log "PROGRESS" "$@"; }

# Progress bar function
show_progress() {
    local current=$1
    local total=$2
    local description="$3"
    
    local percentage=$((current * 100 / total))
    local completed=$((current * 40 / total))
    local remaining=$((40 - completed))
    
    printf "\r${CYAN}[%s%s] %d%% - %s${NC}" \
        "$(printf "%${completed}s" | tr ' ' '=')" \
        "$(printf "%${remaining}s" | tr ' ' '-')" \
        "$percentage" \
        "$description"
    
    if [[ $current -eq $total ]]; then
        echo
    fi
}

# Rollback system
add_rollback_action() {
    ROLLBACK_ACTIONS+=("$1")
}

rollback_installation() {
    if [[ ${#ROLLBACK_ACTIONS[@]} -eq 0 ]]; then
        return
    fi
    
    warning "Installation failed, performing rollback..."
    
    # Execute rollback actions in reverse order
    for ((i=${#ROLLBACK_ACTIONS[@]}-1; i>=0; i--)); do
        local action="${ROLLBACK_ACTIONS[$i]}"
        progress "Rollback: $action"
        eval "$action" || warning "Rollback action failed: $action"
    done
    
    warning "Rollback completed"
}

# Enhanced system detection
detect_system() {
    step "Detecting system configuration"
    
    # OS Detection
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS_NAME="$NAME"
        OS_VERSION="$VERSION_ID"
        DISTRO="$ID"
    else
        error "Cannot detect operating system"
    fi
    
    # Architecture detection
    ARCH=$(uname -m)
    KERNEL_VERSION=$(uname -r)
    
    # Hardware detection
    CPU_CORES=$(nproc)
    TOTAL_RAM=$(free -h | awk '/^Mem:/ {print $2}')
    AVAILABLE_SPACE=$(df -h / | awk 'NR==2 {print $4}')
    
    info "System: $OS_NAME $OS_VERSION ($ARCH)"
    info "Kernel: $KERNEL_VERSION"
    info "Hardware: $CPU_CORES cores, $TOTAL_RAM RAM, $AVAILABLE_SPACE free"
    
    # Check minimum requirements
    local min_ram_gb=2
    local ram_gb=$(free -g | awk '/^Mem:/ {print $2}')
    if [[ $ram_gb -lt $min_ram_gb ]]; then
        warning "System has less than ${min_ram_gb}GB RAM, performance may be impacted"
    fi
    
    success "System detection completed"
}

# Enhanced privilege check
check_privileges() {
    step "Verifying installation privileges"
    
    if [[ $EUID -ne 0 ]]; then
        error "This installer must be run as root (use sudo)"
    fi
    
    # Check for required commands
    local required_commands=("systemctl" "curl" "git" "make" "gcc")
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            error "Required command not found: $cmd"
        fi
    done
    
    success "Privilege verification completed"
}

# Enhanced directory creation with proper permissions
create_directory_structure() {
    step "Creating ROC directory structure"
    
    local directories=(
        "$ROC_HOME:$ROC_USER:$ROC_USER:755"
        "$ROC_HOME/bin:$ROC_USER:$ROC_USER:755"
        "$ROC_HOME/modules:$ROC_USER:$ROC_USER:755"
        "$ROC_HOME/venv:$ROC_USER:$ROC_USER:755"
        "$ROC_HOME/logs:$ROC_USER:$ROC_USER:755"
        "$ROC_CONFIG_DIR:root:$ROC_USER:750"
        "$ROC_CONFIG_DIR/backups:$ROC_USER:$ROC_USER:755"
        "$ROC_LOG_DIR:$ROC_USER:$ROC_USER:755"
        "$ROC_LOG_DIR/cameras:$ROC_USER:$ROC_USER:755"
        "/tmp/roc:$ROC_USER:$ROC_USER:755"
    )
    
    for dir_info in "${directories[@]}"; do
        IFS=':' read -r dir owner group perms <<< "$dir_info"
        
        mkdir -p "$dir"
        chown "$owner:$group" "$dir"
        chmod "$perms" "$dir"
        
        add_rollback_action "rm -rf '$dir'"
        progress "Created: $dir"
    done
    
    success "Directory structure created"
}

# Enhanced user creation with proper groups
create_roc_user() {
    step "Creating ROC system user"
    
    if id "$ROC_USER" &>/dev/null; then
        info "User $ROC_USER already exists"
    else
        # Create user with specific settings
        useradd \
            --system \
            --home-dir "$ROC_HOME" \
            --shell /bin/bash \
            --comment "ROC System User" \
            --create-home \
            "$ROC_USER"
        
        add_rollback_action "userdel -r '$ROC_USER'"
        success "Created system user: $ROC_USER"
    fi
    
    # Add to required groups
    local groups=("video" "audio" "dialout")
    for group in "${groups[@]}"; do
        if getent group "$group" >/dev/null; then
            usermod -a -G "$group" "$ROC_USER"
            progress "Added $ROC_USER to group: $group"
        else
            warning "Group $group does not exist, skipping"
        fi
    done
    
    success "ROC user configuration completed"
}

# Enhanced dependency installation with version checking
install_system_dependencies() {
    step "Installing system dependencies"
    
    progress "Updating package repositories..."
    
    case "$DISTRO" in
        "ubuntu"|"debian")
            export DEBIAN_FRONTEND=noninteractive
            apt-get update -qq || error "Failed to update package repositories"
            
            local packages=(
                "python3>=3.8"
                "python3-pip"
                "python3-venv"
                "python3-dev"
                "git"
                "curl"
                "wget"
                "build-essential"
                "linux-headers-$(uname -r)"
                "dkms"
                "ffmpeg"
                "v4l-utils"
                "pkg-config"
                "libssl-dev"
                "libffi-dev"
                "libjpeg-dev"
                "libpng-dev"
                "systemd"
                "rsync"
                "htop"
                "iotop"
                "nethogs"
            )
            
            # Install packages with progress tracking
            local total_packages=${#packages[@]}
            for i in "${!packages[@]}"; do
                local package="${packages[$i]}"
                show_progress $((i+1)) $total_packages "Installing $package"
                
                if ! apt-get install -y "$package" >/dev/null 2>&1; then
                    warning "Failed to install package: $package"
                fi
            done
            echo
            
            add_rollback_action "apt-get autoremove -y"
            ;;
            
        "centos"|"rhel"|"fedora")
            local pkg_manager
            if command -v dnf >/dev/null 2>&1; then
                pkg_manager="dnf"
            else
                pkg_manager="yum"
            fi
            
            $pkg_manager update -y -q || error "Failed to update package repositories"
            
            local packages=(
                "python3"
                "python3-pip"
                "python3-devel"
                "git"
                "curl"
                "wget"
                "gcc"
                "gcc-c++"
                "make"
                "kernel-devel"
                "dkms"
                "ffmpeg"
                "v4l-utils"
                "openssl-devel"
                "libffi-devel"
                "libjpeg-turbo-devel"
                "libpng-devel"
                "systemd"
                "rsync"
                "htop"
                "iotop"
            )
            
            local total_packages=${#packages[@]}
            for i in "${!packages[@]}"; do
                local package="${packages[$i]}"
                show_progress $((i+1)) $total_packages "Installing $package"
                
                if ! $pkg_manager install -y "$package" >/dev/null 2>&1; then
                    warning "Failed to install package: $package"
                fi
            done
            echo
            ;;
            
        "arch")
            pacman -Sy --noconfirm --quiet || error "Failed to update package repositories"
            
            local packages=(
                "python"
                "python-pip"
                "git"
                "curl"
                "wget"
                "base-devel"
                "linux-headers"
                "dkms"
                "ffmpeg"
                "v4l-utils"
                "openssl"
                "libffi"
                "libjpeg-turbo"
                "libpng"
                "systemd"
                "rsync"
                "htop"
                "iotop"
            )
            
            pacman -S --noconfirm --quiet "${packages[@]}" || error "Failed to install packages"
            ;;
            
        *)
            error "Unsupported distribution: $DISTRO"
            ;;
    esac
    
    success "System dependencies installed"
}

# Enhanced Python environment setup
setup_python_environment() {
    step "Setting up Python environment"
    
    # Create virtual environment
    progress "Creating Python virtual environment..."
    sudo -u "$ROC_USER" python3 -m venv "$ROC_HOME/venv"
    add_rollback_action "rm -rf '$ROC_HOME/venv'"
    
    # Upgrade pip and install wheel
    progress "Upgrading pip and setuptools..."
    sudo -u "$ROC_USER" "$ROC_HOME/venv/bin/pip" install --upgrade pip setuptools wheel
    
    # Install Python dependencies
    progress "Installing Python packages..."
    
    local python_packages=(
        "asyncio-mqtt>=0.11.0"
        "websockets>=10.0"
        "aiohttp>=3.8.0"
        "selenium>=4.0.0"
        "beautifulsoup4>=4.10.0"
        "requests>=2.28.0"
        "psutil>=5.8.0"
        "PyYAML>=6.0"
        "python-dateutil>=2.8.0"
        "pillow>=9.0.0"
        "numpy>=1.21.0"
        "opencv-python>=4.5.0"
    )
    
    local total_packages=${#python_packages[@]}
    for i in "${!python_packages[@]}"; do
        local package="${python_packages[$i]}"
        show_progress $((i+1)) $total_packages "Installing Python package: $package"
        
        if ! sudo -u "$ROC_USER" "$ROC_HOME/venv/bin/pip" install "$package" >/dev/null 2>&1; then
            warning "Failed to install Python package: $package"
        fi
    done
    echo
    
    success "Python environment configured"
}

# Enhanced v4l2loopback installation with checksum verification
install_v4l2loopback() {
    step "Installing custom v4l2loopback module"
    
    local repo_url="https://github.com/aab18011/v4l2loopback"
    local install_dir="$TEMP_INSTALL_DIR/v4l2loopback"
    
    # Remove existing module if loaded
    if lsmod | grep -q v4l2loopback; then
        progress "Removing existing v4l2loopback module..."
        rmmod v4l2loopback || true
    fi
    
    # Clone repository
    progress "Cloning v4l2loopback repository..."
    git clone --depth 1 "$repo_url" "$install_dir" || error "Failed to clone v4l2loopback repository"
    
    # Build module
    progress "Building v4l2loopback module..."
    cd "$install_dir"
    
    make clean >/dev/null 2>&1 || true
    make -j"$CPU_CORES" || error "Failed to build v4l2loopback"
    
    # Install module
    progress "Installing v4l2loopback module..."
    make install || error "Failed to install v4l2loopback"
    depmod -a
    
    # Configure module loading
    progress "Configuring v4l2loopback for persistent loading..."
    
    cat > /etc/modprobe.d/roc-v4l2loopback.conf << 'EOF'
# ROC v4l2loopback configuration
options v4l2loopback devices=16
EOF
    
    cat > /etc/modules-load.d/roc-v4l2loopback.conf << 'EOF'
# Load v4l2loopback at boot
v4l2loopback
EOF
    
    # Load module
    progress "Loading v4l2loopback module..."
    modprobe v4l2loopback devices=16
    
    # Verify installation
    if ! lsmod | grep -q v4l2loopback; then
        error "v4l2loopback module failed to load"
    fi
    
    local device_count=$(ls /dev/video* 2>/dev/null | wc -l)
    info "Created $device_count video loopback devices"
    
    add_rollback_action "rmmod v4l2loopback"
    add_rollback_action "rm -f /etc/modprobe.d/roc-v4l2loopback.conf"
    add_rollback_action "rm -f /etc/modules-load.d/roc-v4l2loopback.conf"
    
    success "v4l2loopback installation completed"
}

# Enhanced file installation with integrity checking
install_roc_files() {
    step "Installing ROC application files"
    
    local script_dir="$INSTALLER_DIR" # Had to change to this because it was originally stuck in the /tmp/ dir we setup earlier
    
    # File mappings: source:destination:permissions (updated to match attached files)
    local files=(
        "roc_bootstrap.py:$ROC_HOME/bin/roc_bootstrap.py:755"
        "roc_main.py:$ROC_HOME/bin/roc_main.py:755"
        "roc_scene_engine.py:$ROC_HOME/bin/roc_scene_engine.py:755"
    )
    
    local total_files=${#files[@]}
    for i in "${!files[@]}"; do
        IFS=':' read -r src dst perms <<< "${files[$i]}"
        show_progress $((i+1)) $total_files "Installing: $src"
        
        if [[ -f "$script_dir/$src" ]]; then
            cp "$script_dir/$src" "$dst"
            chmod "$perms" "$dst"
            chown "$ROC_USER:$ROC_USER" "$dst"
            
            # Verify file integrity
            if [[ ! -f "$dst" ]]; then
                error "Failed to install file: $dst"
            fi
            
            add_rollback_action "rm -f '$dst'"
        else
            warning "Source file not found: $script_dir/$src"
        fi
    done
    echo
    
    # Create management script
    progress "Creating ROC management script..."
    cat > /usr/local/bin/roc << 'EOF'
#!/bin/bash
# ROC Management Script v1.0.1

ROC_HOME="/opt/roc"
ROC_USER="roc"

show_usage() {
    cat << 'USAGE'
ROC (Remote OBS Controller) Management Tool

Usage: roc <command> [options]

Commands:
  start      Start ROC service
  stop       Stop ROC service  
  restart    Restart ROC service
  status     Show service status
  logs       Show live logs
  config     Run configuration manager
  test       Test ROC installation
  health     Show system health
  metrics    Show performance metrics
  cameras    List camera status
  rules      Show scene rules status

Options:
  -v, --verbose    Enable verbose output
  -q, --quiet      Suppress output
  -f, --force      Force operation
  
Examples:
  roc start           # Start the ROC service
  roc logs -f         # Follow logs in real-time
  roc status --verbose # Show detailed status
USAGE
}

case "${1:-}" in
    start)
        echo "🚀 Starting ROC service..."
        systemctl start roc.service
        systemctl status roc.service --no-pager --lines=0
        ;;
    stop)
        echo "🛑 Stopping ROC service..."
        systemctl stop roc.service
        ;;
    restart)
        echo "🔄 Restarting ROC service..."
        systemctl restart roc.service
        systemctl status roc.service --no-pager --lines=0
        ;;
    status)
        systemctl status roc.service --no-pager
        ;;
    logs)
        if [[ "${2:-}" == "-f" ]] || [[ "${2:-}" == "--follow" ]]; then
            journalctl -u roc.service -f --no-pager
        else
            journalctl -u roc.service --no-pager -n 50
        fi
        ;;
    config)
        echo "🔧 Opening ROC configuration manager..."
        sudo -u "$ROC_USER" "$ROC_HOME/venv/bin/python" "$ROC_HOME/bin/roc_config.py"
        ;;
    test)
        echo "🧪 Testing ROC installation..."
        sudo -u "$ROC_USER" "$ROC_HOME/venv/bin/python" "$ROC_HOME/bin/roc_bootstrap.py" --test-mode
        ;;
    health)
        echo "❤️  ROC System Health Check"
        echo "=========================="
        
        # Service status
        if systemctl is-active --quiet roc.service; then
            echo "✅ Service: Running"
        else
            echo "❌ Service: Stopped"
        fi
        
        # Video devices
        #local - this was removed from the line below because it was misused. Needs attention to ensure no security flaws.
        video_devices=$(ls /dev/video* 2>/dev/null | wc -l)
        echo "📹 Video devices: $video_devices"
        
        # Log file sizes
        echo "📝 Log sizes:"
        du -sh /var/log/roc/* 2>/dev/null || echo "  No logs found"
        
        # System resources
        echo "💾 System resources:"
        echo "  CPU: $(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)% used"
        echo "  RAM: $(free -h | awk '/^Mem:/ {printf "%.1f GB used / %.1f GB total", $3/1, $2/1}')"
        echo "  Disk: $(df -h / | awk 'NR==2 {print $5 " used"}')"
        ;;
    metrics)
        echo "📊 ROC Performance Metrics"
        echo "=========================="
        
        if [[ -f "/tmp/roc/metrics.json" ]]; then
            cat /tmp/roc/metrics.json | python3 -m json.tool
        else
            echo "No metrics available. Ensure ROC is running."
        fi
        ;;
    cameras)
        echo "📹 Camera Status"
        echo "==============="
        
        if [[ -f "/tmp/roc/camera_status.json" ]]; then
            cat /tmp/roc/camera_status.json | python3 -m json.tool
        else
            echo "No camera status available. Ensure ROC is running."
        fi
        ;;
    rules)
        echo "🎬 Scene Rules Status"
        echo "===================="
        
        if [[ -f "/tmp/roc/rule_status.json" ]]; then
            cat /tmp/roc/rule_status.json | python3 -m json.tool
        else
            echo "No rule status available. Ensure ROC is running."
        fi
        ;;
    -h|--help|help)
        show_usage
        ;;
    "")
        show_usage
        ;;
    *)
        echo "❌ Unknown command: $1"
        echo "Use 'roc --help' for usage information"
        exit 1
        ;;
esac
EOF
    
    chmod 755 /usr/local/bin/roc
    add_rollback_action "rm -f /usr/local/bin/roc"
    
    success "ROC application files installed"
}

# Enhanced systemd service creation
create_systemd_service() {
    step "Creating systemd service"
    
    progress "Generating service configuration..."
    
    cat > "$SYSTEMD_SERVICE_DIR/roc.service" << EOF
[Unit]
Description=Remote OBS Controller (ROC) v${ROC_VERSION}
Documentation=https://github.com/aab18011/roc-system
After=network-online.target graphical-session.target
Wants=network-online.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=exec
User=$ROC_USER
Group=$ROC_USER
WorkingDirectory=$ROC_HOME

# Main execution
ExecStart=$ROC_HOME/venv/bin/python $ROC_HOME/bin/roc_bootstrap.py
ExecReload=/bin/kill -HUP \$MAINPID
ExecStop=/bin/kill -TERM \$MAINPID

# Restart configuration
Restart=always
RestartSec=10
TimeoutStartSec=60
TimeoutStopSec=30

# Output configuration
StandardOutput=journal
StandardError=journal
SyslogIdentifier=roc

# Environment variables
Environment=HOME=$ROC_HOME
Environment=PYTHONPATH=$ROC_HOME/bin
Environment=PYTHONUNBUFFERED=1
Environment=ROC_LOG_LEVEL=INFO

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$ROC_HOME $ROC_LOG_DIR $ROC_CONFIG_DIR /tmp/roc /dev/video*

# Resource limits
LimitNOFILE=65536
MemoryMax=2G
CPUQuota=200%

[Install]
WantedBy=multi-user.target
EOF

    add_rollback_action "rm -f '$SYSTEMD_SERVICE_DIR/roc.service'"
    
    # Reload systemd and enable service
    progress "Configuring service startup..."
    systemctl daemon-reload || error "Failed to reload systemd"
    systemctl enable roc.service || error "Failed to enable ROC service"
    
    success "Systemd service created and enabled"
}

# Enhanced configuration setup
setup_initial_configuration() {
    step "Setting up initial configuration"
    
    progress "Creating configuration templates..."
    
    # Main configuration
    cat > "$ROC_CONFIG_DIR/config.json" << EOF
{
  "meta": {
    "version": "$ROC_VERSION",
    "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "modified": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "description": "ROC Configuration - Enhanced Setup"
  },
  "system": {
    "debug_mode": false,
    "auto_install": true,
    "max_cameras": 16,
    "field_number": 1,
    "log_level": "INFO",
    "phase2_script": "$ROC_HOME/bin/roc_main.py"
  },
  "network": {
    "gateway_timeout": 3,
    "wan_dns_servers": ["8.8.8.8", "1.1.1.1", "208.67.222.222", "9.9.9.9"],
    "wan_timeout": 5,
    "connection_retry_limit": 5,
    "connection_retry_delay": 2,
    "max_backoff_delay": 30,
    "use_exponential_backoff": true
  },
  "obs": {
    "host": "127.0.0.1",
    "port": 4455,
    "password": "",
    "websocket_timeout": 10,
    "reconnect_attempts": 5,
    "scenes": {
      "default": "Default Scene",
      "break": "Break Scene",
      "game": "Game Scene", 
      "breakout": "Breakout Scene",
      "interview": "Interview Scene"
    }
  },
  "cameras": {
    "config_file": "$ROC_CONFIG_DIR/cameras.json",
    "test_ports": [1935, 554, 80, 8080, 8000],
    "stream_types": ["main", "ext", "sub"],
    "connection_timeout": 3,
    "discovery_method": "arp_scan",
    "rtsp_test_enabled": true
  },
  "scoreboard": {
    "servers": {
      "field1": "192.168.1.200:8080"
    },
    "scan_timeout": 2,
    "reconnect_throttle": 5,
    "polling_interval": 0.1
  },
  "scene_switching": {
    "rules_file": "$ROC_CONFIG_DIR/scene_rules.json",
    "min_scene_duration": 2.0,
    "enable_breakout_sequence": true,
    "enable_camera_rotation": false
  }
}
EOF
    
    chown "$ROC_USER:$ROC_USER" "$ROC_CONFIG_DIR/config.json"
    chmod 640 "$ROC_CONFIG_DIR/config.json"
    
    # Empty cameras configuration
    echo '{"cameras": []}' > "$ROC_CONFIG_DIR/cameras.json"
    chown "$ROC_USER:$ROC_USER" "$ROC_CONFIG_DIR/cameras.json"
    chmod 640 "$ROC_CONFIG_DIR/cameras.json"
    
    success "Initial configuration created"
}

# Installation verification
verify_installation() {
    step "Verifying installation"
    
    local verification_errors=()
    
    # Check user exists
    progress "Checking user account..."
    if ! id "$ROC_USER" >/dev/null 2>&1; then
        verification_errors+=("User $ROC_USER does not exist")
    fi
    
    # Check directories
    progress "Checking directories..."
    local required_dirs=("$ROC_HOME" "$ROC_CONFIG_DIR" "$ROC_LOG_DIR")
    for dir in "${required_dirs[@]}"; do
        if [[ ! -d "$dir" ]]; then
            verification_errors+=("Directory missing: $dir")
        fi
    done
    
    # Check Python environment
    progress "Checking Python environment..."
    if [[ ! -f "$ROC_HOME/venv/bin/python" ]]; then
        verification_errors+=("Python virtual environment missing")
    fi
    
    # Check v4l2loopback
    progress "Checking v4l2loopback..."
    if ! lsmod | grep -q v4l2loopback; then
        verification_errors+=("v4l2loopback module not loaded")
    fi
    
    # Check systemd service
    progress "Checking systemd service..."
    if ! systemctl is-enabled roc.service >/dev/null 2>&1; then
        verification_errors+=("ROC service not enabled")
    fi
    
    # Check FFmpeg
    progress "Checking FFmpeg..."
    if ! command -v ffmpeg >/dev/null 2>&1; then
        verification_errors+=("FFmpeg not installed")
    fi
    
    # Report results
    if [[ ${#verification_errors[@]} -eq 0 ]]; then
        success "Installation verification passed"
        return 0
    else
        error "Installation verification failed:"
        for err in "${verification_errors[@]}"; do
            echo "  ❌ $err"
        done
        return 1
    fi
}

# Interactive configuration
interactive_configuration() {
    step "Running interactive configuration"
    
    echo
    echo "${BOLD}${CYAN}ROC Interactive Configuration${NC}"
    echo "${CYAN}===============================${NC}"
    echo
    
    # OBS Configuration
    echo "${YELLOW}OBS WebSocket Configuration:${NC}"
    read -p "OBS Host IP [127.0.0.1]: " obs_host
    obs_host=${obs_host:-127.0.0.1}
    
    read -p "OBS WebSocket Port [4455]: " obs_port
    obs_port=${obs_port:-4455}
    
    read -s -p "OBS WebSocket Password (leave empty if none): " obs_password
    echo
    
    # Field Configuration
    echo
    echo "${YELLOW}Field Configuration:${NC}"
    read -p "Field Number [1]: " field_number
    field_number=${field_number:-1}
    
    # Scoreboard Configuration
    echo
    echo "${YELLOW}Scoreboard Configuration:${NC}"
    read -p "Scoreboard IP:Port for Field $field_number [192.168.1.200:8080]: " scoreboard_url
    scoreboard_url=${scoreboard_url:-192.168.1.200:8080}
    
    # Camera Discovery
    echo
    echo "${YELLOW}Camera Discovery:${NC}"
    echo "1) ARP scan (recommended - faster)"
    echo "2) Network brute force (slower but thorough)"
    echo "3) Skip automatic discovery"
    read -p "Choose discovery method [1]: " discovery_choice
    discovery_choice=${discovery_choice:-1}
    
    case $discovery_choice in
        1) discovery_method="arp_scan"
           network_base=""
           ;;
        2) discovery_method="brute_force"
           read -p "Enter network prefix (e.g., 192.168.1): " network_base
           ;;
        3) discovery_method="config_only"
           network_base=""
           ;;
        *) discovery_method="arp_scan"
           network_base=""
           ;;
    esac

    progress "Updating configuration file..."
    sudo -u "$ROC_USER" "$ROC_HOME/venv/bin/python" -c "
import json
config_path = '$ROC_CONFIG_DIR/config.json'
with open(config_path, 'r') as f:
    data = json.load(f)
data['obs']['host'] = '$obs_host'
data['obs']['port'] = $obs_port
data['obs']['password'] = '$obs_password'
data['system']['field_number'] = $field_number
data['scoreboard']['servers']['field$field_number'] = '$scoreboard_url'
data['cameras']['discovery_method'] = '$discovery_method'
if '$network_base':
    data['cameras']['network_base'] = '$network_base'
data['meta']['modified'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open(config_path, 'w') as f:
    json.dump(data, f, indent=4)
"
    success "Configuration updated"
}

# Main installation process
main() {
    mkdir -p "$ROC_LOG_DIR"
    touch "$INSTALL_LOG"
    chmod 644 "$INSTALL_LOG"
    trap rollback_installation ERR INT TERM

    check_privileges
    detect_system
    create_roc_user
    create_directory_structure
    install_system_dependencies
    install_v4l2loopback
    setup_python_environment
    install_roc_files
    setup_initial_configuration
    interactive_configuration
    create_systemd_service

    if verify_installation; then
        success "ROC installation completed successfully!"
        echo
        echo "${GREEN}Next steps:${NC}"
        echo "  - Start ROC: roc start"
        echo "  - Check status: roc status"
        echo "  - View logs: roc logs"
        echo "  - Run configuration: roc config"
        echo
        read -p "Would you like to start ROC now? (y/n) " start_now
        if [[ "${start_now,,}" == "y" ]]; then
            roc start
        fi
    else
        error "Installation verification failed"
    fi

    rm -rf "$TEMP_INSTALL_DIR"
}

main "$@"
