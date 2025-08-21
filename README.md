# Outback Paintball Series Live Stream Controller (OPSLC/ROC)
## Introduction

The Remote OBS Controller (ROC) script represents a sophisticated automation system designed for managing Open Broadcaster Software (OBS) scenes in the context of live sports scoreboard monitoring. Developed for deployment in a Linux LXC container with systemd service management, the script integrates web scraping, real-time data parsing, and WebSocket communication to facilitate dynamic camera switching based on game states derived from a remote scoreboard. This version (v2.1.2) incorporates fixes for breakout sequence duration, pause detection, task cancellation, and OBS keep-alive mechanisms, ensuring robustness in high-latency or paused scenarios.

The script is implemented in Python 3, leveraging asynchronous programming via the `asyncio` library to handle non-blocking operations, which is crucial for ultra-fast polling and scene transitions. It employs a modular class-based architecture, with the `ROCController` class encapsulating all core functionality. Key libraries are chosen for their specialized capabilities: Selenium for persistent browser sessions and DOM parsing, BeautifulSoup for HTML extraction, WebSockets for OBS control, and Pandas for bracket file processing. These choices reflect a balance between performance, reliability, and ease of integration in a constrained environment.

## Imports and Dependencies

The script begins with a comprehensive set of imports, each selected for specific roles in the system's operation:

- **Standard Libraries**: Modules like `os`, `json`, `subprocess`, `logging`, `time`, `asyncio`, `hashlib`, `base64`, `socket`, `venv`, `signal`, and `sys` provide foundational utilities. For instance, `asyncio` is chosen for its native support of asynchronous I/O, enabling concurrent tasks without threading overhead. `logging` facilitates structured output for debugging and monitoring, configured to suppress verbose logs from third-party libraries to maintain focus on application-level events.
  
- **Third-Party Libraries**:
  - `pkg_resources`: Used indirectly for dependency management, though not explicitly in code; it supports virtual environment handling.
  - `pandas as pd`: Employed for reading ODS bracket files via `pd.read_excel(engine='odf')`. Pandas is selected for its powerful data manipulation capabilities, particularly with spreadsheet formats, allowing efficient parsing of tournament brackets into structured match data.
  - `selenium.webdriver` and related modules: Selenium is chosen for its robust browser automation, enabling headless Chrome sessions to load and parse dynamic scoreboard pages. Alternatives like Requests were insufficient due to the need for JavaScript execution and persistent sessions. Options such as `--headless` and `--no-sandbox` optimize for containerized environments.
  - `bs4.BeautifulSoup`: Complements Selenium by parsing HTML snapshots efficiently. It is preferred over lxml or html.parser for its leniency with malformed HTML and ease of selector-based extraction (e.g., finding elements by ID).
  - `websockets`: Handles OBS WebSocket connections asynchronously, chosen for its lightweight, pure-Python implementation that aligns with `asyncio`. It supports ping/pong for keep-alive, ensuring persistent connections.
  - `uuid`: Generates unique request IDs for OBS commands, preventing collisions in asynchronous requests.

These imports are managed within a virtual environment (`venv`), created and populated if absent, ensuring isolation and reproducibility without system-wide installations.

## Configuration and Defaults

A global `CONFIG_FILE` points to `/etc/roc/config.json`, with `DEFAULT_CONFIG` providing fallback values. This dictionary structure encapsulates OBS connection details, scoreboard URLs, scene names, and dependencies. The use of JSON for configuration allows easy external modification, merging defaults via a loop to handle missing keys. This design promotes flexibility in deployment, such as switching fields or scenes without code changes.

## ROCController Class Structure

The `ROCController` class serves as the central orchestrator, initialized with logging setup, configuration loading, and signal handlers for graceful shutdown (SIGINT/SIGTERM). Key attributes include state trackers like `game_state`, `breakout_triggered`, and `is_paused`, reflecting the system's reactive nature.

### Initialization and Setup Methods

- **`__init__`**: Initializes flags, states, and caches. Signal handlers set `exit_flag` for loop termination.
- **`setup_logging`**: Configures dual handlers (file and stream) at INFO level, suppressing noisy libraries to focus logs on critical events.
- **`load_config`**: Loads or defaults configuration, merging to ensure completeness.
- **`manage_venv` and `check_and_install_dependencies`**: Ensure a persistent virtual environment with required packages. `venv.create` is used for isolation, and `subprocess.run` installs dependencies via pip, marking completion to avoid redundancy.
- **`check_network`**: Verifies connectivity using `socket.create_connection`, essential for fault tolerance in networked setups.
- **`setup_webdriver` and `cleanup_webdriver`**: Initialize and tear down a headless Chrome instance. Options like `--disable-gpu` optimize resource usage in containers.

### Scoreboard Parsing and State Detection

- **`wait_for_valid_scoreboard_data`**: Returns a callable for WebDriverWait, checking for non-placeholder team names via JavaScript or DOM fallback. This dual approach handles dynamic content efficiently.
- **`parse_scoreboard`**: Loads the scoreboard once, then parses repeatedly using BeautifulSoup. It validates data quality, logging parsed values. Persistent sessions reduce overhead compared to per-poll reloads.
- **`time_to_seconds`**: Converts MM:SS strings to integers, handling errors gracefully.
- **`detect_game_state`**: Core logic for inferring states ('break', 'game', 'intermission') from timer changes. It detects new games via time jumps or specific values (e.g., 300s for 5-minute games), instant starts when break hits zero, and active timers based on decreasing values. The post-state calculation for `game_just_started` prevents false positives. Logging is throttled to avoid spam.

### Bracket Handling

- **`read_bracket`**: Parses ODS files into match lists using Pandas, chosen for its engine support ('odf') and DataFrame iteration efficiency.
- **`match_teams_to_bracket`**: Simple linear search for team matching, sufficient for small brackets.

### OBS Integration

- **`authenticate_obs`**: Handles WebSocket authentication via SHA256 hashing, as per OBS protocol.
- **`connect_obs`**: Establishes a connection with retries and exponential backoff, ensuring reliability.
- **`switch_scene`**: Sends SetCurrentProgramScene requests, caching to avoid redundancy. For breakout scenes, it skips response waits for speed; others use timeouts with assumptions on failure.
- **`handle_camera_switching`**: Manages state-based switches asynchronously. For new games, it triggers an instant breakout, scheduling a timed sequence task (cancellable to prevent overlaps). Rotations (40s) are paused during game pauses. This logic ensures professional transitions, with `asyncio.create_task` allowing non-blocking delays.
- **`keep_obs_alive`**: Periodic pings using `self.obs_ws.open` check, preventing disconnections.

### Main Execution Loop

- **`run`**: Orchestrates setup, connection, and polling. It detects pauses via unchanged timers (counter >=3), halting rotations. Polling adjusts dynamically: no sleep in critical phases for responsiveness.
- **`main` and Entry Point**: Async entry with error handling, exiting cleanly.

## Key Design Choices and Logic

The script's asynchronous paradigm (`asyncio`) is pivotal for real-time performance, allowing concurrent WebSocket handling, polling, and timed sequences without blocking. Pause detection mitigates unwanted switches during stalls, using a counter threshold for hysteresis. Task cancellation in sequences prevents overlapping timers from concurrent starts. Library selections prioritize headless, container-friendly tools: Selenium for dynamic web, WebSockets for protocol compliance, and Pandas for data handling. Error handling is graceful, with logs and fallbacks ensuring operational continuity.

This architecture exemplifies a reactive, state-driven system, optimized for low-latency automation in live environments.
