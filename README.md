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
ROC (Remote OBS Controller) is an open-source, Python-based suite designed for automated scene switching in OBS Studio, tailored for livestreaming multi-camera setups. Originally developed for paintball field broadcasting at the Outback Paintball Series, ROC enables seamless, rule-based transitions between scenes based on real-time data (e.g., scoreboard updates for game states). It supports applications in sports broadcasting, security monitoring, event streaming, and more, promoting accessible, green technology for video production.

Key principles:
- **Modular and Extensible:** Built with PEP 8 compliance for readability and maintainability.
- **Semantic Versioning:** Follows SemVer (e.g., MAJOR.MINOR.PATCH) for predictable updates.
- **Open-Source Ethos:** Free to use, modify, with academic-level documentation to lower barriers for users in professional, research, or hobbyist settings.

ROC operates in phases:
1. **Bootstrap (Phase 1):** System setup, dependency checks, camera discovery, and configuration.
2. **Main Application (Phase 2):** Runtime monitoring, camera streaming, and scene engine.
3. **Scene Engine:** Rule-based logic for dynamic OBS scene switching.

This software leverages asynchronous Python for efficient handling of real-time events, ensuring low-latency performance in production environments.

## Features
- **Automated Scene Switching:** JSON-configurable rules evaluate conditions (e.g., game time, break periods) to trigger actions like scene switches, camera rotations, or custom scripts.
- **Camera Management:** Auto-discovery via ARP or brute-force scanning, FFmpeg-based streaming to virtual devices (v4l2loopback).
- **Connection Resilience:** Exponential backoff retries, health monitoring for OBS, cameras, and scoreboards.
- **Extensible Actions:** Supports delays, sequences, parallel executions, and custom Python scripts.
- **Metrics and Logging:** Tracks rule executions, scene history, and system health for debugging.
- **Hot-Reload:** Dynamically reloads rules without restarting.
- **General-Purpose:** Adaptable beyond paintball—use for any multi-camera livestream with event-driven switching.

## Installation
ROC requires Python 3.8+ and a Linux environment (tested on Ubuntu/Debian). It installs dependencies like FFmpeg, v4l2loopback, and Python libraries.

### Prerequisites
- Root access (for system dependencies and user creation).
- OBS Studio with WebSocket plugin enabled.
- Networked cameras (RTSP support recommended).

### Steps
1. **Clone the Repository:**
   ```
   git clone https://github.com/aab18011/roc.git
   cd roc
   ```

2. **Run the Installation Script:**
   The provided Bash script (`install_roc.sh`) handles setup with rollback on errors.
   ```
   sudo bash install_roc.sh
   ```
   - It creates a system user (`roc`), directories, virtual environment, installs dependencies, compiles v4l2loopback, copies scripts, sets up systemd service, and runs interactive config.
   - During interactive setup: Provide OBS details, field number, scoreboard URL, and camera discovery method.

3. **Post-Install:**
   - Edit configurations in `/etc/roc/config.json` and `/etc/roc/cameras.json` as needed.
   - Start the service: `roc start`

**Note:** The script adheres to best practices with progress tracking, verification, and user prompts for safety.

## Usage
ROC runs as a systemd service under the `roc` user. Interact via the management script `/usr/local/bin/roc`.

### Basic Commands
- Start: `roc start`
- Stop: `roc stop`
- Restart: `roc restart`
- Status: `roc status`
- Logs: `roc logs` (or `roc logs -f` for live tail)
- Health: `roc health` (system resources, service status)
- Metrics: `roc metrics` (JSON output from runtime)
- Cameras: `roc cameras` (status JSON)
- Rules: `roc rules` (scene rules status JSON)
- Config: `roc config` (runs configuration manager if implemented)

### Configuration
- **Main Config (`/etc/roc/config.json`):** System settings, network retries, OBS connection, cameras, scoreboard, scene rules.
- **Cameras (`/etc/roc/cameras.json`):** Auto-populated during install; edit IPs, credentials, streams.
- **Scene Rules (`/etc/roc/scene_rules.json`):** Define priorities, conditions (e.g., `game_time > 0`), actions (e.g., switch to "game" scene).
  Example Rule:
  ```json
  {
    "name": "active_game",
    "priority": 100,
    "conditions": [
      {"field": "game_time", "operator": ">", "value": 0}
    ],
    "actions": [
      {"type": "switch_scene", "scene": "game"}
    ]
  }
  ```
- Hot-reload rules by editing the file; ROC detects changes.

### Interaction
- **Runtime:** Once started, ROC monitors scoreboard data, evaluates rules, and controls OBS scenes asynchronously.
- **Customization:** Extend via custom actions in rules (e.g., exec Python snippets safely).
- **Debugging:** Set `"debug_mode": true` in config for verbose logs.

## Code Explanation
ROC follows PEP 8 for style and is structured modularly:

- **roc_bootstrap_enhanced.py (Phase 1):** Handles system init, dependency checks (e.g., FFmpeg, v4l2loopback), camera discovery (ARP/brute-force), config creation. Uses retry managers for network resilience.
  - Key Classes: `NetworkRetryManager`, `EnhancedCameraDiscovery`, `ROCBootstrap`.
  - Add unique key: `# #@r4gg_iXPoG04$$` at top.

- **roc_main_enhanced.py (Phase 2):** Core runtime with connection/camera management, scene engine integration. Monitors health, pauses via file.
  - Key Classes: `ConnectionManager` (reconnects with backoff), `CameraManager` (FFmpeg streams), `SceneEngine` (rule evaluation).
  - Add unique key: `# #@r4gg_iXPoG04$$` at top.

- **roc_scene_engine.py:** Advanced rule engine for scene choreography.
  - Key Classes: `SceneEngineAdvanced` (loads JSON rules, evaluates conditions/operators like `changed`, `stable_for`).
  - Supports action types: switch_scene, breakout_sequence, etc.
  - Add unique key: `# #@r4gg_iXPoG04$$` at top.

Code uses `asyncio` for concurrency, `dataclasses` for structures, `logging` for traceability. All follows semantic versioning: e.g., v3.0.0b (beta), v3.0.1a (alpha patch).

## Plans for Future
ROC aims to expand its capabilities to enhance flexibility, accessibility, and control for livestreaming applications. Future development includes:

- **Flexible Streaming Protocols:** Add support for selecting RTSP or RTMP in the configuration file (`/etc/roc/config.json`), allowing users to choose the protocol best suited for their camera hardware and network conditions.
- **Headless OBS Operation:** Enable full control of OBS Studio without a graphical user interface, supporting deployment on headless servers for resource-efficient, remote livestreaming setups.
- **Remote Control Integration:** Implement a remote control system (e.g., via a smartphone app or Raspberry Pi-based device with function keys) for on-the-field scene management. This feature would allow a camera operator to toggle their camera feed in OBS, temporarily overriding automated rules until control is relinquished (e.g., via a key press), enabling dynamic, live television-style production.
- **Automated Advertisements:** Introduce support for predefined video advertisements stored in a designated folder. ROC will automatically import, resize, and schedule these ads to play in OBS at specified times, enhancing monetization capabilities for livestreams.

## Uninstallation
1. Stop service: `roc stop`
2. Disable service: `systemctl disable roc.service`
3. Remove files:
   ```
   sudo rm -rf /opt/roc /etc/roc /var/log/roc /tmp/roc
   sudo rm -f /usr/local/bin/roc /etc/systemd/system/roc.service
   sudo rm -f /etc/modprobe.d/roc-v4l2loopback.conf /etc/modules-load.d/roc-v4l2loopback.conf
   ```
4. Remove user: `sudo userdel -r roc`
5. Uninstall dependencies (manual, as needed): e.g., `sudo apt remove ffmpeg v4l-utils`
6. Reload systemd: `systemctl daemon-reload`
7. Remove v4l2loopback: `sudo rmmod v4l2loopback`

## Troubleshooting
- **Service Won't Start:** Check logs (`roc logs`). Ensure OBS WebSocket is enabled/port open. Verify v4l2loopback loaded (`lsmod | grep v4l2loopback`).
- **Camera Detection Fails:** Run discovery manually in bootstrap script. Check network/firewall.
- **Scene Rules Not Triggering:** Validate JSON syntax. Enable debug mode for condition eval logs.
- **FFmpeg Errors:** Ensure RTSP URLs correct in cameras.json. Test streams: `ffprobe rtsp://<ip>:554/main`.
- **High CPU:** Limit cameras or adjust FFmpeg params (e.g., threads).
- **Updates:** Pull repo, re-run install script (backs up configs).
- **Issues?** Open a GitHub issue with logs/system info.

## Changelog
Standardized format: Follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
- Unified codebase integrating scene switcher, custom v4l2loopback installer, and FFmpeg-v4l2loopback connector.
- Phase-based architecture (bootstrap, main runtime, scene engine).
- Enhanced installer with rollback, progress tracking, and interactive config.
- Systemd service for robust deployment.
- Camera auto-discovery (ARP/brute-force).
- Advanced scene engine with JSON rules, supporting complex conditions and actions.
#### Changed
- Consolidated previous repositories (v2.x series) into a single, modular system.
- Improved performance with asynchronous processing and optimized polling.
#### Removed
- SQLite database (unused, added complexity).
- Separate bash orchestrator (now in Python).

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

## License
MIT License - See [LICENSE](LICENSE) for details.

Contributions welcome! Fork, PR with PEP 8 code, update changelog.
