#!/usr/bin/env python3
"""
ROC (Remote OBS Controller) Startup System - Phase 1 Bootstrap (Enhanced)
Author: Aidan A. Bradley
Version: 1.0.1

Enhanced version with:
- Improved camera discovery using ARP tables
- Retry logic with exponential backoff
- Better checksum management
- Configuration validation
- Network resilience improvements
"""

import os
import sys
import json
import time
import socket
import hashlib
import logging
import subprocess
import urllib.request
import urllib.error
import re
import threading
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import importlib.util

# Constants
SCRIPT_DIR = Path(__file__).parent.absolute()
CONFIG_DIR = Path("/etc/roc")
LOG_DIR = Path("/var/log/roc")
TEMP_DIR = Path("/tmp/roc")
VENV_DIR = Path("/opt/roc/venv")

# Known checksums for v4l2loopback versions
V4L2_CHECKSUMS = {
    "custom_v1.0": "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
    "official_0.12.7": "fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321"
}

# Default configuration with enhanced settings
DEFAULT_CONFIG = {
    "meta": {
        "version": "1.0.1",
        "created": None,
        "modified": None,
        "description": "ROC Configuration - Enhanced Bootstrap"
    },
    "system": {
        "debug_mode": False,
        "auto_install": True,
        "max_cameras": 16,
        "field_number": 1,
        "log_level": "INFO",
        "phase2_script": "/opt/roc/bin/roc_main.py"
    },
    "network": {
        "gateway_timeout": 3,
        "wan_dns_servers": ["8.8.8.8", "1.1.1.1", "208.67.222.222", "9.9.9.9"],
        "wan_timeout": 5,
        "connection_retry_limit": 5,
        "connection_retry_delay": 2,
        "max_backoff_delay": 30,
        "use_exponential_backoff": True
    },
    "v4l2loopback": {
        "module_name": "v4l2loopback",
        "devices_needed": 16,
        "custom_checksum": V4L2_CHECKSUMS["custom_v1.0"],
        "official_checksum": V4L2_CHECKSUMS["official_0.12.7"],
        "repo_url": "https://github.com/aab18011/v4l2loopback",
        "install_path": "/usr/src/v4l2loopback",
        "preferred_version": "custom"
    },
    "ffmpeg": {
        "required_codecs": ["libx264", "aac", "librtmp", "h264"],
        "min_version": "4.0.0",
        "required_formats": ["rtmp", "hls", "mp4"]
    },
    "cameras": {
        "config_file": "/etc/roc/cameras.json",
        "test_ports": [1935, 554, 80, 8080, 8000],
        "stream_types": ["main", "ext", "sub"],
        "connection_timeout": 3,
        "discovery_method": "arp_scan",  # "brute_force" or "arp_scan" or "config_only"
        "common_camera_ips": [],  # User can specify known camera ranges
        "rtsp_test_enabled": True
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
    "scoreboard": {
        "servers": {
            "field1": "192.168.1.200:8080"
        },
        "scan_timeout": 2,
        "reconnect_throttle": 5,
        "polling_interval": 0.1,
        "change_detection": True
    }
}

class NetworkRetryManager:
    """Manages network retries with exponential backoff."""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config['network']
        self.logger = logger
        
    def retry_with_backoff(self, func, *args, **kwargs):
        """Execute function with retry logic and exponential backoff."""
        max_retries = self.config['connection_retry_limit']
        base_delay = self.config['connection_retry_delay']
        max_delay = self.config['max_backoff_delay']
        use_exponential = self.config['use_exponential_backoff']
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                    
                if use_exponential:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                else:
                    delay = base_delay
                    
                self.logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
                time.sleep(delay)
                
        raise Exception(f"All {max_retries} attempts failed")

class EnhancedCameraDiscovery:
    """Enhanced camera discovery using multiple methods."""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config['cameras']
        self.logger = logger
        
    def get_arp_table(self) -> List[Dict[str, str]]:
        """Parse ARP table for active network devices."""
        try:
            # Try different ARP commands
            arp_commands = [
                ["arp", "-a"],
                ["ip", "neigh", "show"],
                ["cat", "/proc/net/arp"]
            ]
            
            arp_entries = []
            
            for cmd in arp_commands:
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        arp_entries = self._parse_arp_output(result.stdout, cmd[0])
                        if arp_entries:
                            break
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    continue
                    
            self.logger.info(f"Found {len(arp_entries)} entries in ARP table")
            return arp_entries
            
        except Exception as e:
            self.logger.error(f"Failed to get ARP table: {e}")
            return []
            
    def _parse_arp_output(self, output: str, command: str) -> List[Dict[str, str]]:
        """Parse ARP command output based on command type."""
        entries = []
        
        if command == "arp":
            # Parse "arp -a" output: hostname (192.168.1.1) at aa:bb:cc:dd:ee:ff [ether] on eth0
            pattern = r'\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([a-fA-F0-9:]{17})'
        elif command == "ip":
            # Parse "ip neigh" output: 192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
            pattern = r'^(\d+\.\d+\.\d+\.\d+)\s+.*lladdr\s+([a-fA-F0-9:]{17})'
        elif command == "cat":
            # Parse /proc/net/arp: IP address HW type Flags HW address Mask Device
            lines = output.strip().split('\n')[1:]  # Skip header
            for line in lines:
                parts = line.split()
                if len(parts) >= 4 and parts[2] != '0x0':  # Skip incomplete entries
                    entries.append({
                        'ip': parts[0],
                        'mac': parts[3],
                        'interface': parts[5] if len(parts) > 5 else 'unknown'
                    })
            return entries
        else:
            return []
            
        for line in output.split('\n'):
            match = re.search(pattern, line)
            if match:
                entries.append({
                    'ip': match.group(1),
                    'mac': match.group(2),
                    'interface': 'unknown'
                })
                
        return entries
        
    def test_camera_ports(self, ip: str) -> List[int]:
        """Test camera-specific ports on an IP address."""
        open_ports = []
        test_ports = self.config['test_ports']
        timeout = self.config['connection_timeout']
        
        for port in test_ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                result = sock.connect_ex((ip, port))
                sock.close()
                
                if result == 0:
                    open_ports.append(port)
                    
            except Exception as e:
                self.logger.debug(f"Port test failed for {ip}:{port} - {e}")
                
        return open_ports
        
    def test_rtsp_stream(self, ip: str, port: int = 554) -> bool:
        """Test if RTSP stream is available."""
        if not self.config['rtsp_test_enabled']:
            return False
            
        try:
            # Basic RTSP OPTIONS request
            rtsp_url = f"rtsp://{ip}:{port}/"
            
            # Use ffprobe to test RTSP stream
            result = subprocess.run([
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_streams", "-timeout", "3", rtsp_url
            ], capture_output=True, text=True, timeout=5)
            
            return result.returncode == 0
            
        except Exception as e:
            self.logger.debug(f"RTSP test failed for {ip}:{port} - {e}")
            return False
            
    def discover_cameras_arp(self) -> List[Dict[str, Any]]:
        """Discover cameras using ARP table method."""
        self.logger.info("Discovering cameras using ARP table scan...")
        
        arp_entries = self.get_arp_table()
        cameras_found = []
        
        # Test each IP in ARP table
        for entry in arp_entries:
            ip = entry['ip']
            mac = entry['mac']
            
            self.logger.debug(f"Testing camera ports on {ip} (MAC: {mac})")
            open_ports = self.test_camera_ports(ip)
            
            if open_ports:
                camera_info = {
                    "ip": ip,
                    "mac": mac,
                    "interface": entry.get('interface', 'unknown'),
                    "open_ports": open_ports,
                    "rtsp_available": self.test_rtsp_stream(ip) if 554 in open_ports else False,
                    "detected_at": time.time(),
                    "discovery_method": "arp_scan"
                }
                cameras_found.append(camera_info)
                self.logger.info(f"Camera found: {ip} (MAC: {mac}, ports: {open_ports})")
                
        return cameras_found
        
    def discover_cameras_brute_force(self, network_base: str) -> List[Dict[str, Any]]:
        """Discover cameras using brute force network scan."""
        self.logger.info(f"Discovering cameras using brute force scan of {network_base}.0/24...")
        
        cameras_found = []
        
        # Use threading for faster scanning
        def scan_ip(ip_suffix):
            ip = f"{network_base}.{ip_suffix}"
            open_ports = self.test_camera_ports(ip)
            
            if open_ports:
                camera_info = {
                    "ip": ip,
                    "mac": "unknown",
                    "interface": "unknown",
                    "open_ports": open_ports,
                    "rtsp_available": self.test_rtsp_stream(ip) if 554 in open_ports else False,
                    "detected_at": time.time(),
                    "discovery_method": "brute_force"
                }
                cameras_found.append(camera_info)
                self.logger.info(f"Camera found: {ip} (ports: {open_ports})")
                
        # Scan in parallel
        threads = []
        for i in range(1, 255):
            thread = threading.Thread(target=scan_ip, args=(i,))
            thread.start()
            threads.append(thread)
            
            # Limit concurrent threads
            if len(threads) >= 20:
                for t in threads:
                    t.join()
                threads = []
                
        # Wait for remaining threads
        for thread in threads:
            thread.join()
            
        return cameras_found

class ROCBootstrap:
    """Enhanced ROC Bootstrap with improved reliability."""
    
    def __init__(self):
        self.setup_logging()
        self.config = self.load_or_create_config()
        self.startup_log = []
        self.critical_errors = []
        self.warnings = []
        self.retry_manager = NetworkRetryManager(self.config, self.logger)
        self.camera_discovery = EnhancedCameraDiscovery(self.config, self.logger)
        
    def setup_logging(self):
        """Configure comprehensive logging system."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        log_format = '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler(LOG_DIR / "roc_startup.log"),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("="*60)
        self.logger.info("ROC Enhanced Bootstrap System Starting")
        self.logger.info("="*60)
        
    def load_or_create_config(self) -> Dict[str, Any]:
        """Load existing configuration or create default with timestamps."""
        config_file = CONFIG_DIR / "config.json"
        current_time = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
        
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    
                # Merge with defaults and update modified time
                config = self.merge_config(DEFAULT_CONFIG, config)
                config['meta']['modified'] = current_time
                
                # Save updated config
                with open(config_file, 'w') as f:
                    json.dump(config, f, indent=4)
                    
                self.logger.info(f"Loaded and updated configuration from {config_file}")
                return config
                
            except Exception as e:
                self.logger.error(f"Failed to load config: {e}. Using defaults.")
                
        # Create default configuration
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        config = DEFAULT_CONFIG.copy()
        config['meta']['created'] = current_time
        config['meta']['modified'] = current_time
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=4)
            
        self.logger.info(f"Created default configuration at {config_file}")
        return config
        
    def merge_config(self, default: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge user config with defaults."""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.merge_config(result[key], value)
            else:
                result[key] = value
        return result
        
    def log_status(self, component: str, status: str, details: str = ""):
        """Log component status for summary report."""
        entry = {
            "component": component,
            "status": status,
            "details": details,
            "timestamp": time.time()
        }
        self.startup_log.append(entry)
        
        if status == "CRITICAL_ERROR":
            self.critical_errors.append(entry)
        elif status == "WARNING":
            self.warnings.append(entry)
            
    def check_wan_connectivity_enhanced(self) -> bool:
        """Enhanced WAN connectivity check with retry logic."""
        self.logger.info("Checking WAN connectivity with enhanced retry logic...")
        
        dns_servers = self.config['network']['wan_dns_servers']
        timeout = self.config['network']['wan_timeout']
        successful_tests = 0
        
        for dns_server in dns_servers:
            self.logger.info(f"Testing DNS server: {dns_server}")
            
            try:
                # Use retry manager for WAN tests
                def test_dns():
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(timeout)
                    result = sock.connect_ex((dns_server, 53))
                    sock.close()
                    if result != 0:
                        raise ConnectionError(f"Cannot connect to {dns_server}:53")
                    return True
                    
                self.retry_manager.retry_with_backoff(test_dns)
                self.logger.info(f"DNS server {dns_server}: OK")
                successful_tests += 1
                
            except Exception as e:
                self.logger.warning(f"DNS server {dns_server}: FAILED after retries - {e}")
                
        if successful_tests > 0:
            self.logger.info(f"WAN connectivity: OK ({successful_tests}/{len(dns_servers)} DNS servers reachable)")
            self.log_status("WAN Connectivity", "OK", f"{successful_tests}/{len(dns_servers)} DNS servers reachable")
            return True
        else:
            self.logger.error("WAN connectivity: FAILED - No DNS servers reachable after retries")
            self.log_status("WAN Connectivity", "CRITICAL_ERROR", "No DNS servers reachable")
            return False
            
    def verify_v4l2loopback_version_enhanced(self) -> bool:
        """Enhanced v4l2loopback version verification with proper checksums."""
        self.logger.info("Verifying v4l2loopback version with checksum validation...")
        
        # Look for the main module file
        kernel_version = subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip()
        
        possible_paths = [
            f"/lib/modules/{kernel_version}/extra/v4l2loopback.ko",
            f"/lib/modules/{kernel_version}/kernel/drivers/media/v4l2-core/v4l2loopback.ko",
            f"/lib/modules/{kernel_version}/updates/v4l2loopback.ko",
            "/usr/src/v4l2loopback/v4l2loopback.ko"
        ]
        
        module_path = None
        for path in possible_paths:
            if os.path.exists(path):
                module_path = path
                break
                
        if not module_path:
            self.logger.warning("Could not locate v4l2loopback module file for checksum verification")
            self.log_status("v4l2loopback Version", "WARNING", "Module file not found for verification")
            return True  # Proceed anyway
            
        # Calculate checksum
        checksum = self.calculate_file_checksum(module_path)
        if not checksum:
            self.log_status("v4l2loopback Version", "WARNING", "Checksum calculation failed")
            return True
            
        # Compare with known checksums
        custom_checksum = self.config['v4l2loopback']['custom_checksum']
        official_checksum = self.config['v4l2loopback']['official_checksum']
        preferred_version = self.config['v4l2loopback']['preferred_version']
        
        if custom_checksum and checksum == custom_checksum:
            self.logger.info("v4l2loopback: Custom modified version detected ✓")
            self.log_status("v4l2loopback Version", "OK", "Custom modified version confirmed")
            return True
        elif official_checksum and checksum == official_checksum:
            if preferred_version == "custom":
                self.logger.warning("v4l2loopback: Official version detected, but custom version preferred")
                self.log_status("v4l2loopback Version", "WARNING", "Official version (custom preferred)")
            else:
                self.logger.info("v4l2loopback: Official version detected")
                self.log_status("v4l2loopback Version", "OK", "Official version")
            return True
        else:
            self.logger.warning(f"v4l2loopback: Unknown version (checksum: {checksum[:16]}...)")
            self.log_status("v4l2loopback Version", "WARNING", f"Unknown version: {checksum[:16]}...")
            return True
            
    def calculate_file_checksum(self, filepath: str) -> Optional[str]:
        """Calculate SHA256 checksum of a file."""
        try:
            hash_sha256 = hashlib.sha256()
            with open(filepath, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            self.logger.error(f"Failed to calculate checksum for {filepath}: {e}")
            return None
            
    def validate_configuration(self) -> bool:
        """Validate configuration file structure and values."""
        self.logger.info("Validating configuration...")
        
        validation_errors = []
        
        # Required sections
        required_sections = ['system', 'network', 'v4l2loopback', 'ffmpeg', 'cameras', 'obs', 'scoreboard']
        for section in required_sections:
            if section not in self.config:
                validation_errors.append(f"Missing required section: {section}")
                
        # Validate field number
        field_num = self.config.get('system', {}).get('field_number')
        if not isinstance(field_num, int) or field_num < 1:
            validation_errors.append("Invalid field_number: must be positive integer")
            
        # Validate OBS settings
        obs_host = self.config.get('obs', {}).get('host')
        obs_port = self.config.get('obs', {}).get('port')
        if not obs_host or not isinstance(obs_port, int) or not (1 <= obs_port <= 65535):
            validation_errors.append("Invalid OBS host/port configuration")
            
        # Validate network timeouts
        timeouts = ['gateway_timeout', 'wan_timeout', 'connection_retry_delay']
        for timeout in timeouts:
            value = self.config.get('network', {}).get(timeout)
            if not isinstance(value, (int, float)) or value <= 0:
                validation_errors.append(f"Invalid network timeout: {timeout}")
                
        if validation_errors:
            for error in validation_errors:
                self.logger.error(f"Config validation: {error}")
            self.log_status("Config Validation", "CRITICAL_ERROR", f"{len(validation_errors)} validation errors")
            return False
        else:
            self.logger.info("Configuration validation: OK")
            self.log_status("Config Validation", "OK", "All validations passed")
            return True
            
    def enhanced_camera_discovery(self) -> List[Dict[str, Any]]:
        """Enhanced camera discovery with multiple methods."""
        discovery_method = self.config['cameras']['discovery_method']
        
        if discovery_method == "config_only":
            self.logger.info("Camera discovery: Config-only mode")
            return []
        elif discovery_method == "arp_scan":
            return self.camera_discovery.discover_cameras_arp()
        elif discovery_method == "brute_force":
            gateway = self.get_default_gateway()
            if gateway:
                network_base = '.'.join(gateway.split('.')[:-1])
                return self.camera_discovery.discover_cameras_brute_force(network_base)
            else:
                self.logger.error("Cannot determine network base for brute force scan")
                return []
        else:
            self.logger.warning(f"Unknown discovery method: {discovery_method}, using ARP scan")
            return self.camera_discovery.discover_cameras_arp()
            
    def get_default_gateway(self) -> Optional[str]:
        """Get the default gateway IP address."""
        try:
            result = subprocess.run(
                ["ip", "route", "show", "default"], 
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'default via' in line:
                        parts = line.split()
                        gateway_index = parts.index('via') + 1
                        if gateway_index < len(parts):
                            gateway = parts[gateway_index]
                            if self.validate_ip(gateway):
                                return gateway
            return None
        except Exception as e:
            self.logger.error(f"Failed to get default gateway: {e}")
            return None
            
    def validate_ip(self, ip: str) -> bool:
        """Validate IP address format."""
        try:
            socket.inet_aton(ip)
            return True
        except socket.error:
            return False
            
    def run_bootstrap(self) -> bool:
        """Execute enhanced bootstrap sequence."""
        self.logger.info("Starting Enhanced ROC Bootstrap sequence...")
        start_time = time.time()
        
        # Configuration validation
        if not self.validate_configuration():
            return False
            
        # System checks
        if not self.check_root_privileges():
            return False
            
        # Network connectivity with enhanced retry logic
        lan_ok = self.check_lan_connectivity()
        wan_ok = self.check_wan_connectivity_enhanced()
        
        if not lan_ok:
            return False
            
        # v4l2 system with enhanced verification
        v4l2_ok = self.check_v4l2_modules()
        devices_ok = self.check_v4l2_devices() if v4l2_ok else False
        
        # FFmpeg with format validation
        ffmpeg_ok = self.check_ffmpeg_enhanced()
        
        # Enhanced camera discovery
        cameras_found = self.enhanced_camera_discovery()
        
        # Save discovered cameras
        if cameras_found:
            self.save_camera_config(cameras_found)
            
        # Generate report
        bootstrap_success = self.generate_startup_report()
        
        # Prepare handoff
        if bootstrap_success:
            handoff_ok = self.prepare_phase2_handoff()
            bootstrap_success = bootstrap_success and handoff_ok
            
        elapsed_time = time.time() - start_time
        self.logger.info(f"Bootstrap completed in {elapsed_time:.2f} seconds")
        
        return bootstrap_success
        
    def check_root_privileges(self) -> bool:
        """Verify script is running with necessary privileges."""
        if os.geteuid() != 0:
            self.logger.error("ROC Bootstrap requires root privileges for system setup")
            self.log_status("System Privileges", "CRITICAL_ERROR", "Root access required")
            return False
            
        self.log_status("System Privileges", "OK", "Root access confirmed")
        return True
        
    def check_lan_connectivity(self) -> bool:
        """Check LAN connectivity to gateway."""
        self.logger.info("Checking LAN connectivity...")
        
        gateway = self.get_default_gateway()
        if not gateway:
            self.logger.error("Could not determine default gateway")
            self.log_status("LAN Connectivity", "CRITICAL_ERROR", "Gateway detection failed")
            return False
            
        self.logger.info(f"Testing connectivity to gateway: {gateway}")
        
        try:
            def test_gateway():
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(self.config['network']['gateway_timeout'])
                # Test common gateway ports (SSH, HTTP, HTTPS)
                test_ports = [22, 80, 443]
                for port in test_ports:
                    try:
                        result = sock.connect_ex((gateway, port))
                        sock.close()
                        if result == 0:
                            return True
                        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock.settimeout(self.config['network']['gateway_timeout'])
                    except:
                        continue
                sock.close()
                
                # If no ports are open, try ping
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "3", gateway],
                    capture_output=True
                )
                return result.returncode == 0
                
            self.retry_manager.retry_with_backoff(test_gateway)
            self.logger.info("LAN connectivity: OK")
            self.log_status("LAN Connectivity", "OK", f"Gateway {gateway} reachable")
            return True
            
        except Exception as e:
            self.logger.error(f"Cannot reach gateway {gateway}: {e}")
            self.log_status("LAN Connectivity", "CRITICAL_ERROR", f"Gateway {gateway} unreachable")
            return False
            
    def check_v4l2_modules(self) -> bool:
        """Check for v4l2 and v4l2loopback modules."""
        self.logger.info("Checking v4l2 modules...")
        
        # Check if v4l2 is available
        try:
            result = subprocess.run(["modinfo", "videodev"], capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.error("v4l2 (videodev) module not found")
                self.log_status("v4l2 Modules", "CRITICAL_ERROR", "videodev module missing")
                return False
                
            self.logger.info("v4l2 videodev module: OK")
            
        except Exception as e:
            self.logger.error(f"Error checking videodev module: {e}")
            self.log_status("v4l2 Modules", "CRITICAL_ERROR", f"videodev check failed: {e}")
            return False
            
        # Check v4l2loopback
        try:
            result = subprocess.run(["modinfo", "v4l2loopback"], capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.warning("v4l2loopback module not loaded, will attempt installation")
                self.log_status("v4l2loopback", "WARNING", "Module not loaded")
                return self.install_v4l2loopback()
            else:
                self.logger.info("v4l2loopback module: OK")
                return self.verify_v4l2loopback_version_enhanced()
                
        except Exception as e:
            self.logger.error(f"Error checking v4l2loopback: {e}")
            self.log_status("v4l2loopback", "CRITICAL_ERROR", f"Module check failed: {e}")
            return False
            
    def install_v4l2loopback(self) -> bool:
        """Install custom v4l2loopback from repository."""
        if not self.config['system']['auto_install']:
            self.logger.error("Auto-installation disabled, cannot install v4l2loopback")
            self.log_status("v4l2loopback Install", "CRITICAL_ERROR", "Auto-install disabled")
            return False
            
        self.logger.info("Installing custom v4l2loopback...")
        
        try:
            # Create temporary directory
            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            install_dir = TEMP_DIR / "v4l2loopback"
            
            # Remove existing directory
            if install_dir.exists():
                subprocess.run(["rm", "-rf", str(install_dir)])
            
            # Clone repository
            self.logger.info("Cloning v4l2loopback repository...")
            result = subprocess.run([
                "git", "clone", self.config['v4l2loopback']['repo_url'], str(install_dir)
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to clone repository: {result.stderr}")
                self.log_status("v4l2loopback Install", "CRITICAL_ERROR", "Repository clone failed")
                return False
                
            # Build and install
            self.logger.info("Building v4l2loopback module...")
            
            build_commands = [
                ["make", "clean"],
                ["make"],
                ["make", "install"],
                ["depmod", "-a"]
            ]
            
            for cmd in build_commands:
                self.logger.info(f"Running: {' '.join(cmd)}")
                result = subprocess.run(cmd, cwd=install_dir, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    self.logger.error(f"Build command failed: {' '.join(cmd)} - {result.stderr}")
                    self.log_status("v4l2loopback Install", "CRITICAL_ERROR", f"Build failed: {' '.join(cmd)}")
                    return False
                    
            # Load the module
            self.logger.info("Loading v4l2loopback module...")
            devices_needed = self.config['v4l2loopback']['devices_needed']
            
            result = subprocess.run([
                "modprobe", "v4l2loopback", f"devices={devices_needed}", 
                f"video_nr=0-{devices_needed-1}", "card_label=ROC_Camera"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                self.logger.error(f"Failed to load v4l2loopback: {result.stderr}")
                self.log_status("v4l2loopback Install", "CRITICAL_ERROR", "Module load failed")
                return False
                
            # Create module configuration for persistence
            modprobe_conf = f"""# ROC v4l2loopback configuration
options v4l2loopback devices={devices_needed} video_nr=0-{devices_needed-1} card_label=ROC_Camera
"""
            
            with open("/etc/modprobe.d/roc-v4l2loopback.conf", "w") as f:
                f.write(modprobe_conf)
                
            # Add to modules load list
            with open("/etc/modules-load.d/roc-v4l2loopback.conf", "w") as f:
                f.write("v4l2loopback\n")
                
            self.logger.info("v4l2loopback installation: SUCCESS")
            self.log_status("v4l2loopback Install", "OK", f"Installed with {devices_needed} devices")
            return True
            
        except Exception as e:
            self.logger.error(f"v4l2loopback installation error: {e}")
            self.log_status("v4l2loopback Install", "CRITICAL_ERROR", str(e))
            return False
            
    def check_v4l2_devices(self) -> bool:
        """Verify v4l2loopback devices are available."""
        self.logger.info("Checking v4l2loopback devices...")
        
        devices_needed = self.config['v4l2loopback']['devices_needed']
        found_devices = []
        
        for i in range(devices_needed):
            device_path = f"/dev/video{i}"
            if os.path.exists(device_path):
                # Verify it's actually a v4l2loopback device
                try:
                    result = subprocess.run([
                        "v4l2-ctl", "--device", device_path, "--info"
                    ], capture_output=True, text=True, timeout=5)
                    
                    if result.returncode == 0 and "v4l2 loopback" in result.stdout.lower():
                        found_devices.append(device_path)
                    
                except Exception as e:
                    self.logger.debug(f"Could not verify {device_path}: {e}")
                    
        if len(found_devices) >= devices_needed:
            self.logger.info(f"v4l2loopback devices: OK ({len(found_devices)} devices found)")
            self.log_status("v4l2loopback Devices", "OK", f"{len(found_devices)} devices available")
            return True
        else:
            self.logger.error(f"Insufficient v4l2loopback devices: {len(found_devices)}/{devices_needed}")
            self.log_status("v4l2loopback Devices", "CRITICAL_ERROR", 
                          f"Only {len(found_devices)}/{devices_needed} devices found")
            return False
            
    def check_ffmpeg_enhanced(self) -> bool:
        """Enhanced FFmpeg check with format validation."""
        self.logger.info("Checking FFmpeg installation with enhanced validation...")
        
        try:
            # Check if ffmpeg is installed
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self.logger.error("FFmpeg not found")
                self.log_status("FFmpeg", "CRITICAL_ERROR", "FFmpeg not installed")
                return self.install_ffmpeg()
                
            # Parse version
            version_line = result.stdout.split('\n')[0]
            self.logger.info(f"FFmpeg found: {version_line}")
            
            # Check required codecs
            codecs_result = subprocess.run(["ffmpeg", "-codecs"], capture_output=True, text=True, timeout=10)
            available_codecs = codecs_result.stdout
            
            missing_codecs = []
            for codec in self.config['ffmpeg']['required_codecs']:
                if codec not in available_codecs:
                    missing_codecs.append(codec)
                    
            # Check required formats
            formats_result = subprocess.run(["ffmpeg", "-formats"], capture_output=True, text=True, timeout=10)
            available_formats = formats_result.stdout
            
            missing_formats = []
            for format_name in self.config['ffmpeg']['required_formats']:
                if format_name not in available_formats:
                    missing_formats.append(format_name)
                    
            # Report results
            if missing_codecs or missing_formats:
                warning_msg = []
                if missing_codecs:
                    warning_msg.append(f"Missing codecs: {missing_codecs}")
                if missing_formats:
                    warning_msg.append(f"Missing formats: {missing_formats}")
                    
                self.logger.warning("; ".join(warning_msg))
                self.log_status("FFmpeg", "WARNING", "; ".join(warning_msg))
                return True  # Still functional
            else:
                self.logger.info("FFmpeg: OK (all required codecs and formats available)")
                self.log_status("FFmpeg", "OK", "All required codecs and formats available")
                return True
                
        except Exception as e:
            self.logger.error(f"FFmpeg check error: {e}")
            self.log_status("FFmpeg", "CRITICAL_ERROR", str(e))
            return False
            
    def install_ffmpeg(self) -> bool:
        """Install FFmpeg if auto-installation is enabled."""
        if not self.config['system']['auto_install']:
            self.logger.error("Auto-installation disabled, cannot install FFmpeg")
            self.log_status("FFmpeg Install", "CRITICAL_ERROR", "Auto-install disabled")
            return False
            
        self.logger.info("Installing FFmpeg...")
        
        try:
            # Detect package manager and install
            package_managers = [
                (["apt", "update"], ["apt", "install", "-y", "ffmpeg"]),
                (["dnf", "update"], ["dnf", "install", "-y", "ffmpeg"]),
                (["yum", "update"], ["yum", "install", "-y", "ffmpeg"]),
                (["pacman", "-Sy"], ["pacman", "-S", "--noconfirm", "ffmpeg"])
            ]
            
            for update_cmd, install_cmd in package_managers:
                # Check if package manager exists
                if subprocess.run(["which", update_cmd[0]], capture_output=True).returncode == 0:
                    self.logger.info(f"Using {update_cmd[0]} package manager")
                    
                    # Update package list
                    try:
                        result = subprocess.run(update_cmd, capture_output=True, text=True, timeout=300)
                        if result.returncode != 0:
                            self.logger.warning(f"Package update failed: {result.stderr}")
                    except subprocess.TimeoutExpired:
                        self.logger.warning("Package update timed out")
                        
                    # Install FFmpeg
                    try:
                        result = subprocess.run(install_cmd, capture_output=True, text=True, timeout=600)
                        if result.returncode == 0:
                            self.logger.info("FFmpeg installation: SUCCESS")
                            self.log_status("FFmpeg Install", "OK", "Installed successfully")
                            return True
                        else:
                            self.logger.error(f"FFmpeg installation failed: {result.stderr}")
                    except subprocess.TimeoutExpired:
                        self.logger.error("FFmpeg installation timed out")
                        
            self.log_status("FFmpeg Install", "CRITICAL_ERROR", "No compatible package manager found")
            return False
            
        except Exception as e:
            self.logger.error(f"FFmpeg installation error: {e}")
            self.log_status("FFmpeg Install", "CRITICAL_ERROR", str(e))
            return False
            
    def save_camera_config(self, cameras_found: List[Dict[str, Any]]):
        """Save discovered cameras to configuration file."""
        camera_config_file = Path(self.config['cameras']['config_file'])
        camera_config_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Create enhanced camera configuration
        camera_config = {
            "meta": {
                "discovery_timestamp": time.time(),
                "discovery_method": self.config['cameras']['discovery_method'],
                "cameras_found": len(cameras_found)
            },
            "cameras": []
        }
        
        for i, camera in enumerate(cameras_found):
            enhanced_camera = {
                "id": i,
                "name": f"Camera_{i+1}",
                "ip": camera["ip"],
                "mac": camera.get("mac", "unknown"),
                "interface": camera.get("interface", "unknown"),
                "open_ports": camera["open_ports"],
                "rtsp_available": camera.get("rtsp_available", False),
                "detected_at": camera["detected_at"],
                "discovery_method": camera["discovery_method"],
                "enabled": True,
                "device_index": i,
                "stream_config": {
                    "main_stream": f"rtsp://{camera['ip']}:554/main" if camera.get("rtsp_available") else None,
                    "sub_stream": f"rtsp://{camera['ip']}:554/sub" if camera.get("rtsp_available") else None,
                    "username": "",
                    "password": "",
                    "retry_attempts": 3,
                    "timeout": 10
                }
            }
            camera_config["cameras"].append(enhanced_camera)
            
        try:
            with open(camera_config_file, 'w') as f:
                json.dump(camera_config, f, indent=4)
                
            self.logger.info(f"Saved camera configuration to {camera_config_file}")
            self.log_status("Camera Config", "OK", f"Saved {len(cameras_found)} cameras")
            
        except Exception as e:
            self.logger.error(f"Failed to save camera configuration: {e}")
            self.log_status("Camera Config", "WARNING", f"Save failed: {e}")
            
    def generate_startup_report(self) -> bool:
        """Generate comprehensive startup report."""
        self.logger.info("="*60)
        self.logger.info("ROC ENHANCED BOOTSTRAP STARTUP REPORT")
        self.logger.info("="*60)
        
        # Component status summary
        for entry in self.startup_log:
            status_symbol = {
                "OK": "✅",
                "WARNING": "⚠️ ",
                "CRITICAL_ERROR": "❌"
            }.get(entry['status'], "❓")
            
            self.logger.info(f"{status_symbol} {entry['component']}: {entry['status']}")
            if entry['details']:
                self.logger.info(f"   Details: {entry['details']}")
                
        # Summary counts
        ok_count = len([e for e in self.startup_log if e['status'] == 'OK'])
        warning_count = len(self.warnings)
        error_count = len(self.critical_errors)
        
        self.logger.info("-" * 40)
        self.logger.info(f"Summary: {ok_count} OK, {warning_count} Warnings, {error_count} Critical Errors")
        
        if self.critical_errors:
            self.logger.error("CRITICAL ERRORS DETECTED:")
            for error in self.critical_errors:
                self.logger.error(f"  - {error['component']}: {error['details']}")
                
        if self.warnings:
            self.logger.warning("WARNINGS:")
            for warning in self.warnings:
                self.logger.warning(f"  - {warning['component']}: {warning['details']}")
                
        self.logger.info("="*60)
        
        return len(self.critical_errors) == 0
        
    def prepare_phase2_handoff(self) -> bool:
        """Prepare environment for Phase 2 execution."""
        self.logger.info("Preparing Phase 2 handoff...")
        
        # Ensure Phase 2 script exists
        phase2_script = Path(self.config['system']['phase2_script'])
        if not phase2_script.exists():
            self.logger.error(f"Phase 2 script not found: {phase2_script}")
            self.log_status("Phase 2 Prep", "CRITICAL_ERROR", "Phase 2 script missing")
            return False
            
        # Make Phase 2 script executable
        try:
            os.chmod(phase2_script, 0o755)
        except Exception as e:
            self.logger.warning(f"Could not make Phase 2 script executable: {e}")
        
        # Create status file for Phase 2
        status_file = TEMP_DIR / "phase1_status.json"
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        
        status_data = {
            "phase1_completed": True,
            "timestamp": time.time(),
            "critical_errors": len(self.critical_errors),
            "warnings": len(self.warnings),
            "startup_log": self.startup_log,
            "config": self.config,
            "system_info": {
                "hostname": socket.gethostname(),
                "kernel": subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip(),
                "python_version": sys.version,
                "bootstrap_version": "1.0.1"
            }
        }
        
        try:
            with open(status_file, 'w') as f:
                json.dump(status_data, f, indent=4)
                
            self.logger.info(f"Phase 1 status saved to {status_file}")
            self.log_status("Phase 2 Prep", "OK", "Handoff prepared")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to prepare Phase 2 handoff: {e}")
            self.log_status("Phase 2 Prep", "CRITICAL_ERROR", f"Handoff prep failed: {e}")
            return False

def main():
    """Main entry point for enhanced bootstrap."""
    try:
        bootstrap = ROCBootstrap()
        success = bootstrap.run_bootstrap()
        
        if success:
            bootstrap.logger.info("Phase 1 Bootstrap: SUCCESS - Ready for Phase 2")
            
            # Execute Phase 2
            phase2_script = bootstrap.config['system']['phase2_script']
            bootstrap.logger.info(f"Launching Phase 2: {phase2_script}")
            
            try:
                # Hand off execution to Phase 2
                os.execv(sys.executable, [sys.executable, phase2_script])
            except Exception as e:
                bootstrap.logger.error(f"Failed to launch Phase 2: {e}")
                return 1
        else:
            bootstrap.logger.error("Phase 1 Bootstrap: FAILED - Cannot proceed to Phase 2")
            bootstrap.logger.error("Please review the startup report above and resolve critical errors")
            return 1
            
    except KeyboardInterrupt:
        print("\nBootstrap interrupted by user")
        return 130
    except Exception as e:
        logging.error(f"Unhandled bootstrap error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())