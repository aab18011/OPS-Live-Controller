# ROC - Remote OBS Controller

![Python Version](https://img.shields.io/badge/python-3.8%20%7C%203.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-blue)
![Software Version](https://img.shields.io/badge/version-v3.0.0b-blue)
![Alpha Version](https://img.shields.io/badge/alpha-v3.0.1a-green)

**Author:** Aidan A. Bradley  
**GitHub:** [github.com/aab18011](https://github.com/aab18011)  
**Website:** [https://aab18011.github.io/](https://aab18011.github.io/)  
**Date:** August 24, 2025  
**Company/League:** Outback Paintball Series (OPS) - Matt's Outback Paintball (League Owner)  
**Sponsor:** Tom Brierton  
**Location:** Riley Mountain Rd., Coventry, CT  

## Overview
ROC (Remote OBS Controller) is an open-source, Python-based suite for automated scene switching in OBS Studio, designed for livestreaming multi-camera setups. Initially developed for the Outback Paintball Series to broadcast paintball tournaments, ROC integrates scene switching, a custom v4l2loopback installer, and FFmpeg-based camera streaming into a unified system.

Key principles:
- **Unified Architecture:** Combines previously separate repositories (scene switcher, v4l2loopback installer, FFmpeg connector) into one cohesive codebase.
- **PEP 8 Compliance:** Ensures readable, maintainable code.
- **Semantic Versioning:** Follows MAJOR.MINOR.PATCH (e.g., v3.0.0b for beta, v3.0.1a for alpha).
- **Open-Source Ethos:** Licensed under MIT, with academic-level documentation to support users in education, research, or hobbyist contexts.

ROC operates in two phases:
1. **Bootstrap (Phase 1):** Initializes system, checks dependencies, discovers cameras, and configures settings.
2. **Main Application (Phase 2):** Manages runtime operations, camera streaming, and scene switching via a rule-based engine.

## Features
- **Automated Scene Switching:** JSON-defined rules trigger scene changes based on real-time data (e.g., game state, timers).
- **Camera Management:** Auto-discovers cameras (ARP/brute-force), streams via FFmpeg to v4l2loopback devices.
- **Resilience:** Exponential backoff for network retries, health monitoring for OBS, cameras, and scoreboards.
- **Extensible Actions:** Supports delays, sequences, parallel actions, and custom scripts.
- **Metrics & Logging:** Tracks rule executions, scene history, and system health.
- **Hot-Reload:** Dynamically updates rules without restarting.
- **Versatile:** Adaptable for any multi-camera livestream with event-driven switching.

## System Requirements
- **OS**: Ubuntu 20.04+, Debian 11+, CentOS 8+, or Arch Linux
- **Hardware**: 2GB RAM (4GB recommended), 2-core CPU, 10GB free disk space
- **Network**: Stable LAN for cameras/scoreboards; internet for dependency installation
- **Software**: Python 3.8+, OBS Studio with WebSocket plugin v5.0+

## Installation
Requires Python 3.8+ and Linux (tested on Ubuntu/Debian). Installs FFmpeg, v4l2loopback, and Python dependencies.

### Quick Start
```bash
git clone https://github.com/aab18011/roc.git
cd roc
sudo bash install_roc.sh
roc start
```
See [Installation](#installation) for detailed setup and [Usage](#usage) for commands.

### Detailed Installation
1. **Clone Repository:**
   ```bash
   git clone https://github.com/aab18011/roc.git
   cd roc
   ```
2. **Run Installer:**
   ```bash
   sudo bash install_roc.sh
   ```
   - Creates `roc` user, directories, virtual environment, installs dependencies, compiles v4l2loopback, sets up systemd service, and runs interactive config.
   - Prompts for OBS details, field number, scoreboard URL, and camera discovery method.
3. **Post-Install:**
   - Edit `/etc/roc/config.json` and `/etc/roc/cameras.json`.
   - Start service: `roc start`

## Usage
Runs as a systemd service under the `roc` user. Manage via `/usr/local/bin/roc`.

### Commands
- `roc start`: Start service.
- `roc stop`: Stop service.
- `roc restart`: Restart service.
- `roc status`: Check status.
- `roc logs [-f]`: View logs (live with `-f`).
- `roc health`: Show system resources, service status.
- `roc metrics`: Display runtime metrics (JSON).
- `roc cameras`: List camera status (JSON).
- `roc rules`: Show scene rules status (JSON).
- `roc config`: Run configuration manager (if implemented).

### Configuration
- **Main Config (`/etc/roc/config.json`):** Defines system, network, OBS, camera, scoreboard, and scene settings.
- **Cameras (`/etc/roc/cameras.json`):** Lists camera IPs, credentials, streams.
- **Scene Rules (`/etc/roc/scene_rules.json`):** Specifies conditions and actions.
  #### Example Configurations
  **Cameras (`/etc/roc/cameras.json`):**
  ```json
  {
    "cameras": [
      {
        "id": "cam1",
        "ip": "192.168.1.100",
        "port": 554,
        "protocol": "rtsp",
        "path": "/main",
        "username": "admin",
        "password": "pass123",
        "stream_type": "main"
      }
    ]
  }
  ```

  **Complex Scene Rule (`/etc/roc/scene_rules.json`):**
  ```json
  {
    "name": "game_with_timeout",
    "priority": 80,
    "conditions": [
      {"field": "game_time", "operator": ">", "value": 0},
      {"field": "timeout_active", "operator": "=", "value": true}
    ],
    "actions": [
      {"type": "switch_scene", "scene": "timeout"},
      {"type": "delay", "value": 5},
      {"type": "switch_scene", "scene": "game"}
    ]
  }
  ```
- Hot-reload rules by editing `scene_rules.json`.

### Interaction
- **Runtime:** Monitors scoreboards, evaluates rules, controls OBS scenes asynchronously.
- **Customization:** Add custom actions in rules (e.g., Python snippets).
- **Debugging:** Set `"debug_mode": true` in config for verbose logs.

## Code Explanation
Adheres to PEP 8, structured modularly:
- **roc_bootstrap_enhanced.py:** Initializes system, checks dependencies, discovers cameras. Uses `NetworkRetryManager`, `EnhancedCameraDiscovery`, `ROCBootstrap`.
- **roc_main_enhanced.py:** Manages runtime, cameras, scene engine. Includes `ConnectionManager`, `CameraManager`, `SceneEngine`.
- **roc_scene_engine.py:** Rule-based engine for scene switching. Uses `SceneEngineAdvanced` for JSON rule evaluation.

Uses `asyncio` for concurrency, `dataclasses` for structures, `logging` for traceability.

## Plans for Future
ROC aims to enhance flexibility and control for livestreaming. Planned features include:
- **RTSP/RTMP Support**: Add `"protocol": "rtsp"` or `"rtmp"` in `cameras.json` to support varied camera types. *Challenge*: Ensuring compatibility with diverse camera firmware.
- **Headless OBS**: Enable OBS control without a GUI via WebSocket, ideal for lightweight servers. *Challenge*: Testing on minimal Linux distros.
- **Remote Control**: Develop a mobile app or Raspberry Pi interface for on-the-field scene toggling, with override priority. *Challenge*: Secure key-based authentication for remote commands.
- **Automated Ads**: Import video ads from a folder, resize via FFmpeg, and schedule in OBS. *Challenge*: Optimizing resize performance for real-time playback.

## Uninstallation
1. Stop service: `roc stop`
2. Disable service: `systemctl disable roc.service`
3. Remove files:
   ```bash
   sudo rm -rf /opt/roc /etc/roc /var/log/roc /tmp/roc
   sudo rm -f /usr/local/bin/roc /etc/systemd/system/roc.service
   sudo rm -f /etc/modprobe.d/roc-v4l2loopback.conf /etc/modules-load.d/roc-v4l2loopback.conf
   ```
4. Remove user: `sudo userdel -r roc`
5. Remove dependencies (optional): `sudo apt remove ffmpeg v4l-utils`
6. Reload systemd: `systemctl daemon-reload`
7. Remove v4l2loopback: `sudo rmmod v4l2loopback`

## Troubleshooting
### Common Issues
| Issue | Possible Cause | Solution |
|-------|----------------|----------|
| FFmpeg stream fails | Incorrect RTSP URL | Verify URL with `ffprobe rtsp://<ip>:554/main` |
| OBS WebSocket error | Wrong port/password | Check `/etc/roc/config.json` for correct `obs` settings |
| High CPU usage | Too many cameras | Reduce cameras or set FFmpeg `-threads 2` in `cameras.json` |
| Rules not triggering | Invalid JSON syntax | Validate `scene_rules.json`; enable `"debug_mode": true` |
| Service fails to start | v4l2loopback not loaded | Check `lsmod | grep v4l2loopback`; reload with `modprobe v4l2loopback` |

### Support
Open a [GitHub Issue](https://github.com/aab18011/roc/issues) with logs and system details.

## Contributing
We welcome contributions to ROC! To contribute:
1. Fork the repository and create a feature branch (`git checkout -b feature/xyz`).
2. Follow PEP 8.
3. Update the [Changelog](#changelog) with your changes.
4. Submit a pull request with a clear description.
5. For bugs or features, open an issue with logs and steps to reproduce.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## Disclaimer
ROC is provided "as is" without warranty of any kind. Use at your own risk, and ensure proper configuration for production environments.

## License
ROC is licensed under the MIT License. See [LICENSE](LICENSE) or the [MIT License text](https://opensource.org/licenses/MIT).

## Changelog
Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and Semantic Versioning.

### [Unreleased]
- Planned: RTSP/RTMP protocol selection in config.
- Planned: Headless OBS control.
- Planned: Remote control via smartphone/Raspberry Pi.
- Planned: Automated advertisement playback.

### [3.0.1a] - 2025-08-24 (Alpha)
#### Added
- Hot-reload for scene rules.
#### Fixed
- Network retry backoff bugs.

### [3.0.0b] - 2025-08-01 (Beta)
#### Added
- Unified codebase, merging scene switcher, custom v4l2loopback installer, and FFmpeg-v4l2loopback connector from separate v2.x repositories into a single, modular system.
- Phase-based architecture (bootstrap, main runtime, scene engine).
- Enhanced installer with rollback, progress tracking, and interactive config.
- Systemd service for robust deployment.
- Camera auto-discovery (ARP/brute-force).
- Advanced scene engine with JSON rules, supporting complex conditions and actions.
#### Changed
- Replaced v2.x series’ fragmented codebase with a cohesive, Python-driven system, improving maintainability and performance.
- Optimized asynchronous processing and polling for lower latency.
#### Removed
- SQLite database (unused, added complexity).
- Separate bash orchestrator (now integrated into Python).

### [2.5.0b] - 2025-08-21
#### Added
- Dynamic polling (0.1s for critical moments).
- Pause detection via three consecutive identical timer values.
- Scene switch caching to avoid redundant switches.
- Optimized breakout sequence (7s Breakout, 30s Default, Game Scene).
- Robust OBS WebSocket keep-alive.
- Suppressed verbose third-party logs.
#### Changed
- Refactored into `ROCController` class.
- Enhanced config handling with fallbacks.
- Optimized game start detection and scoreboard parsing.
- Improved mid-match startup robustness.
#### Fixed
- Mid-match startup issues.
- Excessive Selenium log output.

### [2.4.0] - 2025-08-20
#### Added
- SQLite database for logs (removed in v2.2.8).
- `setup.py` for dependency automation.
- Systemd service (`roc-controller.service`).
- Network checks for WAN/LAN.
- Persistent browser session for polling.
#### Changed
- Updated scoreboard IPs.
- Removed stability check for faster data acceptance.
- Optional `bracket.ods` handling.
- Refined camera switching logic.
#### Fixed
- `FileNotFoundError` for `bracket.ods`.
- Placeholder team name parsing.
- Persistent `Interview Scene` issues.

### [2.2.8] - 2025-07-15
#### Removed
- SQLite database and related functionality.
#### Changed
- Streamlined logging to file-based output.
- Improved virtual environment checks.

### [2.2.5] - 2025-06-20
#### Added
- Robust virtual environment checks with `.roc-venv` marker.
#### Fixed
- Dependency installation issues.

### [2.1.12] - 2025-05-10
#### Added
- Detailed logging with timestamps and state changes.
- Modernized systemd service configuration.
#### Changed
- Standardized log format.

### [2.1.9] - 2025-04-25
#### Fixed
- OBS WebSocket stability with better reconnection logic.

### [2.1.5] - 2025-04-10
#### Changed
- Improved OBS WebSocket session persistence.
#### Fixed
- Excessive WebSocket traffic.

### [2.1.0] - 2025-03-15
#### Added
- Single-file structure (`main.py`).
#### Changed
- Consolidated functionality into one script.
#### Removed
- Multiple Python files and bash orchestrator.

### [2.0.0] - 2025-02-01
#### Added
- Initial release with scoreboard monitoring, OBS control, bracket parsing, network checks, pause functionality, camera switching, virtual environment, systemd integration, and bash orchestration.
#### Known Issues
- Issues with bracket file, team names, stability checks, logging verbosity, scene persistence, and dependency management.
