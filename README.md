# Remote OBS Controller (ROC)

![License](https://img.shields.io/badge/license-AGPLv3-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Version](https://img.shields.io/badge/version-2.5.0b-green.svg)

## Overview

The **Remote OBS Controller (ROC)**, also known as the Outback Paintball Series Live Stream Controller (OPSLC/ROC), is a sophisticated automation system designed to manage scene transitions in Open Broadcaster Software (OBS) for live sports events, specifically optimized for paintball tournament livestreaming. Deployed as a systemd service within a Linux LXC container, ROC enables autonomous camera switching based on real-time scoreboard data, allowing operators to focus on commentary and field camera operations.

The system integrates web scraping, real-time data parsing, and WebSocket communication to facilitate dynamic scene transitions aligned with game states (intermission, break, game). Built with Python 3 and leveraging `asyncio` for non-blocking operations, ROC ensures ultra-fast, low-latency performance critical for live environments. Version 2.5.0b includes robust features like persistent browser sessions, intelligent game state detection, and enhanced OBS connectivity, with support for mid-match startup scenarios (e.g., post-power surge).

## Key Features

- **Persistent Virtual Environment**: Manages dependency isolation with automatic creation and verification using a `.roc-venv` marker file.
- **Robust Network Checks**: Verifies connectivity to scoreboards (e.g., `192.168.1.222:5000`, `192.168.1.251:5000`) and internet (8.8.8.8).
- **Dynamic Scoreboard Parsing**: Uses Selenium for persistent browser sessions and BeautifulSoup for HTML extraction, ensuring reliable team and timer data retrieval.
- **Intelligent Game State Detection**: Infers game states (intermission, break, game) using timer-based heuristics, with pause detection to prevent unwanted scene changes.
- **Ultra-Fast Scene Switching**: Implements instant breakout sequences (`7s Breakout Scene`, `30s Default Scene`, then `Game Scene`) and 40-second rotations during games, optimized with task cancellation and caching.
- **Graceful Error Handling**: Handles missing bracket files, invalid team names, and network issues with fallbacks and detailed logging.
- **OBS WebSocket Integration**: Maintains persistent connections with keep-alive pings, robust reconnection logic, and optimized communication.
- **Manual Pause Control**: Supports manual intervention via `/tmp/roc-pause` file for operator control.
- **Systemd Service**: Runs as a reliable systemd service for easy deployment and automatic restarts.

## Installation

### Prerequisites

- **System Requirements**:
  - Debian-based Linux LXC container (e.g., on Proxmox)
  - Python 3.8 or higher
  - Chromium and ChromeDriver
  - Internet and LAN connectivity to OBS host and scoreboards

- **Dependencies**:
  - Python packages: `pandas>=2.2.2`, `obs-websocket-py>=1.0`, `selenium>=4.23.1`, `beautifulsoup4>=4.12.3`, `websockets>=12.0`, `odfpy>=1.4.1`
  - System packages: `chromium`, `chromedriver`

### Setup Steps

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/aab18011/OPS-Live-Controller.git
   cd roc
   ```

2. **Install System Dependencies**:
   ```bash
   sudo apt update
   sudo apt install -y python3-venv python3-pip chromium chromedriver
   ```

3. **Set Up the Virtual Environment**:
   The script automatically creates a virtual environment at `/opt/roc-venv` and installs dependencies. To manually set it up:
   ```bash
   python3 -m venv /opt/roc-venv
   source /opt/roc-venv/bin/activate
   pip install --upgrade pandas==2.2.2 obs-websocket-py==1.0 selenium==4.23.1 beautifulsoup4==4.12.3 websockets==12.0 odfpy==1.4.1
   ```

4. **Configure the Application**:
   Create the configuration file at `/etc/roc/config.json`:
   ```json
   {
       "obs": {
           "host": "192.168.1.****",
           "port": 4455,
           "password": "your_obs_password"
       },
       "scoreboards": {
           "field1": "192.168.1.****:****",
           "field2": "192.168.1.****:****"
       },
       "bracket_file": "/path/to/bracket.ods",
       "chrome_binary": "/path/to/chromium",
       "chrome_driver": "/path/to/chromedriver",
       "default_scene": "Default Scene",
       "break_scene": "Break Scene",
       "game_scene": "Game Scene",
       "breakout_scene": "Breakout Scene",
       "interview_scene": "Interview Scene",
       "venv_path": "/path/to/venv",
       "field_number": 1,
       "polling_interval": 0.1,
       "dependencies": {
           "pandas": "2.2.2",
           "obs-websocket-py": "1.0",
           "selenium": "4.23.1",
           "beautifulsoup4": "4.12.3",
           "websockets": "12.0",
           "odfpy": "1.4.1"
       }
   }
   ```
   Update the `host`, `password`, `scoreboards`, and `bracket_file` fields as needed.

5. **Set Up the Systemd Service**:
   Create `/etc/systemd/system/roc-controller.service`:
   ```ini
   [Unit]
   Description=Remote OBS Controller
   After=network.target

   [Service]
   ExecStart=/path/to/venv/bin/python3 /path/to/main.py
   Restart=always
   User=root
   WorkingDirectory=/path/to/wd

   [Install]
   WantedBy=multi-user.target
   ```
   Then enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable roc-controller
   sudo systemctl start roc-controller
   ```

6. **Verify Installation**:
   Check logs to ensure the service is running:
   ```bash
   tail -f /var/log/roc-controller.log
   ```

## Configuration

The configuration file (`/etc/roc/config.json`) defines critical settings:
- **OBS Settings**: Host, port, and password for OBS WebSocket connection.
- **Scoreboards**: URLs for field scoreboards (e.g., `192.168.1.****:****` for Field 1).
- **Bracket File**: Path to the optional `bracket.ods` file for tournament schedules.
- **Scene Names**: Names of OBS scenes (`Default Scene`, `Break Scene`, etc.).
- **Virtual Environment**: Path to the persistent `venv` (`/opt/roc-venv`).
- **Polling Interval**: Set to `0.1s` for ultra-fast polling during critical moments.

If the configuration file is missing, the script uses defaults but logs a warning. Ensure the `bracket.ods` file is placed at `/root/orss/bracket.ods` if used, or the script will proceed without it.

## Usage

1. **Start the Service**:
   ```bash
   sudo systemctl start roc-controller
   ```

2. **Monitor Logs**:
   View real-time logs for debugging:
   ```bash
   tail -f /var/log/roc-controller.log
   ```

3. **Pause/Resume Automation**:
   - Pause: Create a pause file to enter manual mode:
     ```bash
     touch /tmp/roc-pause
     ```
   - Resume: Remove the pause file to resume automation:
     ```bash
     rm /tmp/roc-pause
     ```

4. **Stop the Service**:
   ```bash
   sudo systemctl stop roc-controller
   ```

The script monitors the specified scoreboard URL, parsing team names and timers to trigger scene switches:
- **Intermission**: Switches to `Interview Scene`.
- **Break**: Switches to `Break Scene`.
- **Game Start**: Triggers `Breakout Scene` (7s), `Default Scene` (30s), then `Game Scene`.
- **During Game**: Alternates between `Game Scene` and `Default Scene` every 40s, pausing during game stalls.

## Technical Details

### Architecture

The ROC is implemented as a single Python script (`main.py`) using a class-based architecture (`ROCController`). It leverages `asyncio` for asynchronous, non-blocking operations, ensuring real-time performance. Key components include:

- **Scoreboard Parsing**: Uses Selenium for persistent browser sessions and BeautifulSoup for DOM parsing, prioritizing JavaScript `scoreboardState` access with DOM fallback to handle dynamic content.
- **Game State Detection**: Infers states based on timer changes, detecting new games via time jumps (>60s), common start times (5min, 10min, 12min), or break timer reaching zero. Pause detection prevents unwanted switches during stalls.
- **OBS Integration**: Communicates with OBS via WebSocket, with authentication, keep-alive pings, and scene switch caching for efficiency.
- **Bracket Parsing**: Optionally reads `bracket.ods` files using Pandas with the `odf` engine for tournament schedules.
- **Error Handling**: Gracefully handles missing files, invalid data, and network issues with fallbacks and detailed logging.

### Design Choices

- **Asynchronous Programming**: `asyncio` ensures non-blocking operations, critical for ultra-fast polling (0.1s) during game starts and breaks.
- **Persistent Sessions**: Single browser session reduces overhead, with `WebDriverWait` ensuring valid data before parsing.
- **Scene Switch Optimization**: Caching and task cancellation prevent redundant switches and overlapping sequences.
- **Container Optimization**: Headless Chrome with options like `--no-sandbox` and `--disable-gpu` ensures compatibility with LXC containers.
- **Logging**: Comprehensive logging to `/var/log/roc-controller.log` with suppressed third-party verbosity for clarity.

### Version History

See [CHANGELOG.md](CHANGELOG.md) for a detailed version history. Key milestones include:
- **v2.0.0**: Initial release with bash script orchestration and multiple Python files.
- **v2.1.0**: Merged into a single `main.py`, improved OBS WebSocket handling.
- **v2.2.5**: Robust virtual environment checks and dependency management.
- **v2.2.8**: Removed unused SQLite database for simplicity.
- **v2.4.0**: Fixed missing bracket file, placeholder team names, and persistent `Interview Scene` issues; added persistent page loading and refined camera logic.
- **v2.5.0**: Optimized breakout sequence timing for precise game start transitions.
- **v2.5.0b**: Added mid-match startup support, pause detection, and task cancellation, passing all test cases.

## Development

### Project Structure

```
roc/
├── main.py             # Main ROC script
├── CHANGELOG.md        # Version history
├── README.md           # This file
____________external_directory_______________
└── /etc/roc/
    └── config.json     # Configuration file
```

### Contributing

Contributions are welcome! To contribute:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Com changes (`git commit -m 'Add your feature'`).
4. Push to the branch (`git push origin feature/your-feature`).
5. Open a pull request.

Please ensure code follows PEP 8 style guidelines and includes tests for new features.

### Testing

The script has been tested for:
- **Mid-Match Startup**: Correct scene selection when starting during an ongoing match (e.g., post-power surge).
- **Game State Transitions**: Accurate detection of intermission, break, game, and pause states.
- **Network Reliability**: Robust handling of network latency (50ms–750ms) and failures.
- **Scene Switching**: Precise timing for breakout sequences and 40-second rotations.

To run tests locally, set up a test scoreboard server and OBS instance, then start the service and verify logs.

## License

This project is licensed under the Affero-Gnu Public License v3.0 (AGPLv3). See the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Author: Aidan A. Bradley
- Thomas Brierton (support and feedback)
- Built for the Outback Paintball Series to enhance live streaming automation.
