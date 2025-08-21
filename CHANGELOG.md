- [ ] Changelog

All notable changes to the **Remote OBS Controller (ROC)** project are documented in this file. The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## \[2.5.0b\] - 2025-08-21

### Added

- **Ultra-Fast Polling**: Implemented dynamic polling interval (`0.1s`) for critical moments (e.g., break timer nearing zero, game start) to ensure instant scene transitions, with configurable normal polling.
- **Pause Detection**: Added game pause detection by tracking three consecutive identical timer values (\~0.3s), preventing unwanted scene changes during pauses.
- **Task Cancellation**: Introduced cancellation of breakout sequence tasks to avoid overlaps during rapid game state changes.
- **Scene Switch Caching**: Added `scene_switch_cache` to prevent redundant OBS scene switches, optimizing performance.
- **Enhanced Breakout Sequence**: Optimized timing for breakout sequence (`7s Breakout Scene`, `30s Default Scene`, then `Game Scene`), with asynchronous task handling for non-blocking transitions.
- **OBS Keep-Alive Improvements**: Strengthened WebSocket keep-alive with robust ping handling and reconnection logic for reliable OBS connectivity.
- **Verbose Logging Suppression**: Further reduced verbosity of third-party logs (`selenium`, `urllib3`) to focus on critical ROC logs, redirecting ChromeDriver logs to `/dev/null`.

### Changed

- **Class-Based Structure**: Refactored into a `ROCController` class for improved organization, maintainability, and state encapsulation.
- **Configuration Handling**: Enhanced config loading with default fallback and key merging to handle missing fields gracefully.
- **Game Start Detection**: Improved logic to detect game starts via:
  - Significant game time jumps (&gt;60s).
  - Common game start times (5min, 10min, 12min).
  - Break timer reaching zero with an active game timer.
- **Scoreboard Parsing**: Optimized to prioritize JavaScript `scoreboardState` access, with DOM fallback only when necessary, reducing overhead.
- **Polling Optimization**: Removed sleep during critical transitions (e.g., break-to-game) for ultra-fast response to state changes.
- **Startup Robustness**: Added support for starting mid-match (e.g., after power surges), ensuring correct scene selection based on current game state.

### Fixed

- **Mid-Match Startup**: Ensured proper scene switching when the script starts during an ongoing match, addressing test cases for power surge recovery.
- **Verbose Log Output**: Eliminated excessive Selenium HTML dumps by setting appropriate logging levels and suppressing ChromeDriver logs.

## \[2.4.0\] - 2025-08-20

### Added

- **Database Integration**: Introduced SQLite database (`/var/roc/roc.db`) for logging errors (`error_logs`), match data (`match_logs`), and team images (`teams`) as BLOBs (later removed in v2.2.8).
- **Setup Script**: Created `setup.py` to automate dependency installation, virtual environment creation, configuration file setup, and systemd service configuration.
- **Systemd Service**: Added `roc-controller.service` for easy startup with `systemctl start roc-controller`, supporting automatic restarts.
- **Network Checks**: Implemented robust checks for WAN (8.8.8.8) and LAN (scoreboard IPs: `192.168.1.222:5000` for Field 1, `192.168.1.251:5000` for Field 2) connectivity, with errors logged to file and database.
- **Persistent Page Loading**: Modified Selenium to maintain a single browser session, polling for updates to key DOM elements (`main-game-team1-name`, `main-game-team2-name`, `break-timer`, `game-timer`) without reloading.
- **Team Image Support**: Added placeholder functionality for storing team images in the database (not fully utilized, removed in v2.2.8).

### Changed

- **Scoreboard IPs**: Updated Field 1 to `192.168.1.222:5000` from `192.168.1.200:5000`, keeping Field 2 at `192.168.1.251:5000`.
- **Stability Check Removal**: Eliminated one-second stability check for data validation, accepting first valid data (non-placeholder teams, valid timers) to prevent premature exits.
- **Bracket File Handling**: Made `bracket.ods` optional, logging a warning instead of an error if missing, allowing continued operation without bracket data.
- **Camera Logic**: Refined camera switching to follow sequence: `Breakout Scene` (7s), `Default Scene` (30s), `Game Scene` for new games, with 40s alternation between `Game Scene` and `Default Scene` during games.
- **Logging**: Enhanced with detailed state transitions and error reporting to `/var/log/roc-controller.log` and database.

### Fixed

- **Missing Bracket File**: Addressed `FileNotFoundError` for `/root/orss/bracket.ods` by using an empty match list as fallback.
- **Missing Team Names**: Fixed premature parsing of placeholder names (`abcd`, `efghi`) by waiting for valid `scoreboardState` or DOM data with `WebDriverWait`.
- **Persistent Interview Scene**: Corrected issue where script remained on `Interview Scene` due to invalid scoreboard data or incorrect state detection.

## \[2.2.8\] - 2025-07-15

### Removed

- **Database Integration**: Removed SQLite database (`/var/roc/roc.db`) and related functionality (error logging, match logging, team image storage) as it was unused and added unnecessary complexity.

### Changed

- **Dependency Management**: Refined checks for virtual environment existence, ensuring robust handling of pre-existing `venv` at `/opt/roc-venv`.
- **Logging**: Streamlined logging to focus on file-based output (`/var/log/roc-controller.log`), removing database logging dependencies.

## \[2.2.5\] - 2025-06-20

### Added

- **Virtual Environment Checks**: Introduced robust checks for existing virtual environment using `.roc-venv` marker file, ensuring persistence across reboots.
- **Dependency Management**: Implemented reliable Python-based dependency installation within the virtual environment, replacing earlier failed attempts.

### Fixed

- **Dependency Installation**: Resolved issues with Python handling its own dependencies, ensuring `pip` installs required packages (`pandas`, `obs-websocket-py`, `selenium`, etc.) correctly.

## \[2.1.12\] - 2025-05-10

### Added

- **Serious Logging**: Enhanced logging with detailed debugging information, including timestamps, state changes, and error details, improving traceability in `/var/log/roc-controller.log`.
- **Systemd Service Modernization**: Updated systemd service configuration to use modern practices, including proper `WorkingDirectory`, `User`, and `Restart` settings for reliability.

### Changed

- **Logging Format**: Standardized log format for better readability and consistency, aiding in debugging and monitoring.

## \[2.1.9\] - 2025-04-25

### Fixed

- **OBS WebSocket Stability**: Further refined OBS WebSocket connection handling with improved reconnection logic and error recovery, reducing communication "busyness".

## \[2.1.5\] - 2025-04-10

### Changed

- **OBS WebSocket Handling**: Improved session persistence for OBS WebSocket connections, reducing connection drops and optimizing communication efficiency.

### Fixed

- **Busy Communication**: Addressed excessive WebSocket traffic by streamlining authentication and request handling, ensuring a more stable connection.

## \[2.1.0\] - 2025-03-15

### Added

- **Single File Structure**: Merged multiple Python files into a single `main.py` script, simplifying maintenance and deployment.

### Changed

- **Code Organization**: Consolidated all functionality (scoreboard parsing, OBS control, dependency management) into a single file, eliminating the need for a bash script orchestrator.
- **Dependency Management**: Attempted to shift dependency management to Python (partially successful, fully resolved in v2.2.5).

### Removed

- **Multiple Files**: Eliminated separate Python modules and bash script orchestration used in v2.0.0, reducing complexity.

## \[2.0.0\] - 2025-02-01

### Added

- **Initial Release**: First version of the Remote OBS Controller, designed for paintball tournament livestreaming.
- **Scoreboard Monitoring**: Implemented Selenium-based parsing of scoreboard data from `http://192.168.1.200:5000` (Field 1) and `192.168.1.251:5000` (Field 2).
- **OBS WebSocket Integration**: Added control of OBS scenes via WebSocket (`obs-websocket-py`), with authentication and scene switching.
- **Bracket Parsing**: Supported reading tournament brackets from `bracket.ods` using `pandas` and `odfpy`.
- **Network Checks**: Included checks for LAN and WAN connectivity.
- **Pause Functionality**: Added manual pause/resume via `/tmp/roc-pause` file.
- **Camera Switching Logic**: Implemented initial logic for switching between `Interview Scene`, `Break Scene`, `Game Scene`, `Breakout Scene`, and `Default Scene`.
- **Virtual Environment**: Set up persistent virtual environment at `/opt/roc-venv` with dependency management via bash script.
- **Systemd Integration**: Configured as a systemd service for deployment in a Linux LXC container.
- **Bash Script Orchestration**: Used a bash script to manage multiple Python files and dependencies.

### Known Issues

- **Missing Bracket File**: Script fails with `FileNotFoundError` if `bracket.ods` is missing.
- **Placeholder Team Names**: Premature parsing captures placeholder names (`abcd`, `efghi`) due to incomplete scoreboard loading.
- **Stability Check**: One-second stability check causes exits on large timer changes.
- **Verbose Logging**: Excessive HTML output from Selenium clogs logs.
- **Persistent Interview Scene**: Script often stuck on `Interview Scene` due to invalid data or state detection errors.
- **Dependency Management**: Bash script-based dependency handling is less reliable than desired.
