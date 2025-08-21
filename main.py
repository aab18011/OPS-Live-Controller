"""
# REMOTE OBS CONTROLLER
# VERSION: v2.5.0b
# AUTHOR: Aidan A. Bradley
# DATE: August 21, 2025
#
# Overview:
# The Remote OBS Controller (ROC) is a sophisticated automation system designed to manage scene transitions 
# in Open Broadcaster Software (OBS) for live sports events, specifically optimized for paintball tournament 
# livestreaming. Deployed within a Linux LXC container under systemd service management, ROC facilitates 
# autonomous camera switching to follow game action, allowing operators to focus on commentary and field 
# camera operations. By integrating real-time scoreboard data parsing, persistent browser sessions, and WebSocket 
# communication, the system ensures seamless and responsive scene changes aligned with game states (intermission,
# break, game).
#
# Key Features:
# - Persistent virtual environment management for dependency isolation
# - Robust network connectivity verification for scoreboards and internet
# - Persistent Selenium-based browser sessions with dynamic page loading detection
# - Intelligent game state detection using timer-based heuristics
# - Configurable scene-switching logic with ultra-fast breakout sequences
# - Graceful error handling and recovery mechanisms
# - WebSocket keep-alive for reliable OBS connectivity
#
# Technical Details:
# The system leverages Python 3 with asyncio for asynchronous operations, ensuring 
# non-blocking execution critical for real-time performance. Selenium and BeautifulSoup 
# handle dynamic scoreboard parsing, while the websockets library manages OBS 
# communication. Pandas processes tournament bracket ODS files. Configuration is stored 
# in a JSON file, with defaults for OBS settings, scoreboard URLs, and scene names. The 
# script employs logging for debugging and monitoring, with suppression of verbose 
# third-party logs to maintain clarity.
#
# Usage:
# Deploy as a systemd service in a Linux LXC container. Ensure dependencies (Chromium, 
# ChromeDriver, specified Python packages) are installed, and configure /etc/roc/config.json 
# with appropriate network and OBS settings. The script monitors a specified scoreboard URL, 
# parsing team names and timers to trigger scene switches (e.g., Breakout Scene for game 
# starts, Game Scene for ongoing play). Manual pause is supported via /tmp/roc-pause file.
#
# Notes:
# - Optimized for low-latency transitions using ultra-fast polling (0.1s) during critical moments.
# - Handles paused game states to prevent unwanted scene changes.
# - Supports graceful shutdown via SIGINT/SIGTERM signals.
# - Requires network connectivity to scoreboards and OBS host.
#
# Dependencies:
# - Python packages: pandas>=2.2.2, obs-websocket-py>=1.0, selenium>=4.23.1, beautifulsoup4>=4.12.3, websockets>=12.0, odfpy>=1.4.1
# - System: Chromium, ChromeDriver
#
# Changelog:
# v2.5.0b: Enhanced breakout sequence timing, improved pause detection, added task cancellation for sequence overlaps, and strengthened OBS keep-alive checks.
"""

import os
import json
import subprocess
import logging
import time
import asyncio
import websockets
import hashlib
import base64
import socket
import venv
import pkg_resources
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import uuid
import signal
import sys

# Configuration
CONFIG_FILE = '/path/to/config.json'
DEFAULT_CONFIG = {
    "obs": {
        "host": "192.168.xxx.yyy",
        "port": 4455,
        "password": "your_obs_password"
    },
    "scoreboards": {
        "field1": "192.168.xxx.yyy:zzzz",
        "field2": "192.168.xxx.yyy:zzzz"
    },
    "bracket_file": "/path/to/bracket-file.ods",
    "chrome_binary": "/path/to/chromium",
    "chrome_driver": "/path/to/chromedriver",
    "default_scene": "Default Scene",
    "break_scene": "Break Scene", 
    "game_scene": "Game Scene",
    "breakout_scene": "Breakout Scene",
    "interview_scene": "Interview Scene",
    "venv_path": "/path/to/venv",
    "field_number": 1,
    "polling_interval": 0.1,  # Ultra-fast polling for instant scene changes
    "dependencies": {
        "pandas": "2.2.2",
        "obs-websocket-py": "1.0", 
        "selenium": "4.23.1",
        "beautifulsoup4": "4.12.3",
        "websockets": "12.0",
        "odfpy": "1.4.1"
    }
}

class ROCController:
    """Main Remote OBS Controller class."""
    
    def __init__(self):
        self.setup_logging()
        self.config = self.load_config()
        self.driver = None
        self.obs_ws = None
        self.page_loaded = False
        self.exit_flag = False
        self.pause_flag = False
        self.game_state = 'intermission'
        self.previous_game_state = 'intermission'
        self.last_switch_time = 0
        self.current_scene_type = None
        self.breakout_triggered = False
        self.old_break_time = None
        self.old_game_time = None
        self.game_just_started = False
        self.last_poll_time = 0
        self.scene_switch_cache = {}  # Cache last switched scene to avoid redundant switches
        self.sequence_task = None
        self.pause_counter = 0
        self.is_paused = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def setup_logging(self):
        """Configure logging with appropriate levels."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("/var/log/roc-controller.log"),
                logging.StreamHandler()
            ]
        )
        
        # Suppress even more verbose logging for ultra-fast polling
        logging.getLogger('selenium.webdriver.remote.remote_connection').setLevel(logging.ERROR)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.ERROR)
        logging.getLogger('selenium.webdriver.common.service').setLevel(logging.ERROR)
        
        self.logger = logging.getLogger(__name__)
    
    def load_config(self):
        """Load configuration from file or create default."""
        if not os.path.exists(CONFIG_FILE):
            self.logger.warning(f"Config file {CONFIG_FILE} not found. Using defaults.")
            return DEFAULT_CONFIG
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Merge with defaults for missing keys
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                return config
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}. Using defaults.")
            return DEFAULT_CONFIG
    
    def _signal_handler(self, sig, frame):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received signal {sig}. Initiating shutdown...")
        self.exit_flag = True
    
    def manage_venv(self):
        """Create and manage persistent virtual environment."""
        venv_path = self.config['venv_path']
        venv_marker = os.path.join(venv_path, '.roc-venv')
        
        if not os.path.exists(venv_marker):
            self.logger.info(f"Creating persistent venv at {venv_path}")
            try:
                if os.path.exists(venv_path):
                    import shutil
                    shutil.rmtree(venv_path)
                
                venv.create(venv_path, with_pip=True)
                with open(venv_marker, 'w') as f:
                    f.write(f"ROC Virtual Environment\nCreated: {time.ctime()}\n")
                
                self.logger.info("Virtual environment created successfully")
            except Exception as e:
                self.logger.error(f"Failed to create venv: {e}")
                raise
        else:
            self.logger.info(f"Using existing venv at {venv_path}")
    
    def check_and_install_dependencies(self):
        """Install required Python packages in venv."""
        pip_path = os.path.join(self.config['venv_path'], 'bin', 'pip')
        deps_marker = os.path.join(self.config['venv_path'], '.deps-installed')
        
        if os.path.exists(deps_marker):
            self.logger.info("Dependencies previously installed")
            return
        
        self.logger.info("Installing Python dependencies...")
        try:
            for package, version in self.config['dependencies'].items():
                self.logger.info(f"Installing {package}>={version}")
                subprocess.run([
                    pip_path, 'install', '--upgrade', f"{package}>={version}"
                ], check=True, capture_output=True, text=True)
            
            with open(deps_marker, 'w') as f:
                f.write(f"Dependencies installed: {time.ctime()}\n")
            
            self.logger.info("All dependencies installed successfully")
        except Exception as e:
            self.logger.error(f"Failed to install dependencies: {e}")
            raise
    
    def check_network(self):
        """Verify network connectivity to scoreboards and internet."""
        self.logger.info("Checking network connectivity...")
        
        # Check internet connectivity
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            self.logger.info("Internet connection: OK")
        except OSError as e:
            self.logger.error(f"Internet connection failed: {e}")
            return False
        
        # Check scoreboard connectivity
        for field, url in self.config['scoreboards'].items():
            host = url.split(':')[0]
            port = int(url.split(':')[1])
            try:
                socket.create_connection((host, port), timeout=3)
                self.logger.info(f"{field} scoreboard ({host}:{port}): OK")
            except OSError as e:
                self.logger.error(f"{field} scoreboard connection failed: {e}")
                return False
        
        return True
    
    def setup_webdriver(self):
        """Initialize Chrome WebDriver with optimal settings."""
        self.logger.info("Initializing WebDriver...")
        
        options = Options()
        options.binary_location = self.config['chrome_binary']
        options.add_argument("--headless")
        options.add_argument("--no-sandbox") 
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-logging")
        options.add_argument("--log-level=3")  # Suppress INFO messages
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(self.config['chrome_driver'])
        service.log_path = "/dev/null"  # Suppress ChromeDriver logs
        
        try:
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(15)
            self.logger.info("WebDriver initialized successfully")
            return driver
        except Exception as e:
            self.logger.error(f"WebDriver initialization failed: {e}")
            return None
    
    def cleanup_webdriver(self):
        """Clean shutdown of WebDriver."""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("WebDriver closed successfully")
            except Exception as e:
                self.logger.warning(f"WebDriver cleanup warning: {e}")
            finally:
                self.driver = None
    
    def wait_for_valid_scoreboard_data(self):
        """Wait for scoreboard to load valid team data."""
        placeholder_teams = {'abcd', 'efghi', '', 'team1', 'team2', 'null', 'nan'}
        
        def check_valid_data(driver):
            try:
                # Try JavaScript approach first
                state = driver.execute_script("""
                    return typeof scoreboardState !== 'undefined' && 
                           scoreboardState && 
                           scoreboardState.mainGame && 
                           scoreboardState.mainGame.length >= 2 ? scoreboardState : null;
                """)
                
                if state and 'mainGame' in state:
                    team1 = state['mainGame'][0].get('name', '').strip().lower()
                    team2 = state['mainGame'][1].get('name', '').strip().lower()
                else:
                    # Fallback to DOM parsing
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    team1_elem = soup.find('span', id='main-game-team1-name')
                    team2_elem = soup.find('span', id='main-game-team2-name')
                    
                    if not team1_elem or not team2_elem:
                        return False
                    
                    team1 = team1_elem.get_text(strip=True).lower()
                    team2 = team2_elem.get_text(strip=True).lower()
                
                # Check if teams are valid (not placeholders and have reasonable length)
                return (team1 not in placeholder_teams and 
                        team2 not in placeholder_teams and
                        len(team1) >= 2 and len(team2) >= 2)
                
            except Exception as e:
                self.logger.debug(f"Data validation check failed: {e}")
                return False
        
        return check_valid_data
    
    def parse_scoreboard(self, url):
        """Parse scoreboard data with persistent connection and proper loading detection."""
        try:
            # Load page only once per session
            if not self.page_loaded:
                full_url = f"http://{url}"
                self.logger.info(f"Loading scoreboard page: {full_url}")
                
                self.driver.get(full_url)
                
                # Wait for page to be completely loaded
                WebDriverWait(self.driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                
                # Wait for valid scoreboard data (with network latency tolerance)
                WebDriverWait(self.driver, 15).until(
                    self.wait_for_valid_scoreboard_data()
                )
                
                self.page_loaded = True
                self.logger.info("Scoreboard page loaded with valid data")
            
            # Parse current data
            placeholder_teams = {'abcd', 'efghi', '', 'team1', 'team2', 'null', 'nan'}
            
            # Get fresh page source for parsing
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Extract team names
            team1_elem = soup.find('span', id='main-game-team1-name')
            team2_elem = soup.find('span', id='main-game-team2-name')
            break_elem = soup.find('div', id='break-timer')
            game_elem = soup.find('div', id='game-timer')
            
            if not all([team1_elem, team2_elem, break_elem, game_elem]):
                self.logger.warning("Required scoreboard elements not found")
                return None, None, None, None
            
            team1 = team1_elem.get_text(strip=True).lower()
            team2 = team2_elem.get_text(strip=True).lower()
            break_time = break_elem.get_text(strip=True)
            game_time = game_elem.get_text(strip=True)
            
            # Validate data quality - accept first valid data without stability check
            if (team1 in placeholder_teams or team2 in placeholder_teams or
                len(team1) < 2 or len(team2) < 2):
                self.logger.debug(f"Invalid team data: {team1} vs {team2}")
                return None, None, None, None
            
            self.logger.info(f"Scoreboard data: {team1} vs {team2} | Break: {break_time} | Game: {game_time}")
            return team1, team2, break_time, game_time
            
        except Exception as e:
            self.logger.error(f"Scoreboard parsing error: {e}")
            return None, None, None, None
    
    def time_to_seconds(self, time_str):
        """Convert MM:SS time string to seconds."""
        try:
            if not time_str or ':' not in time_str:
                return 0
            minutes, seconds = map(int, time_str.split(':'))
            return minutes * 60 + seconds
        except (ValueError, AttributeError) as e:
            self.logger.debug(f"Time conversion error for '{time_str}': {e}")
            return 0
    
    def detect_game_state(self, new_break_seconds, new_game_seconds):
        """Detect game state based on timer changes with ultra-fast transition detection."""
        current_time = time.time()
        
        # Check for new game start (significant increase in game time OR typical game start times)
        new_game_start = False
        
        if self.old_game_time is not None:
            time_diff = new_game_seconds - self.old_game_time
            
            # Detect new game: big jump in time (>60s) OR common game start times
            if (time_diff > 60 or  # Big time jump 
                (new_game_seconds in [300, 720, 600] and self.old_game_time < new_game_seconds) or  # 5min, 10min, or 12min starts
                (time_diff > 10 and new_game_seconds > 200)):  # Any significant increase for longer games
                
                new_game_start = True
                self.logger.info(f"🎮 NEW GAME DETECTED: time jumped from {self.old_game_time}s to {new_game_seconds}s (diff: +{time_diff}s)")
        
        # CRITICAL: Instant game start detection - break hits 0 and game timer is active
        instant_game_start = (
            self.old_break_time is not None and 
            self.old_break_time > 0 and 
            new_break_seconds == 0 and 
            new_game_seconds > 0
        )
        
        if instant_game_start:
            self.logger.info(f"⚡ INSTANT GAME START: Break reached 0, game timer active at {new_game_seconds}s")
        
        # Determine timer activity
        break_active = (new_break_seconds > 0 and 
                       (self.old_break_time is None or new_break_seconds <= self.old_break_time))
        
        game_active = (new_game_seconds > 0 and 
                      (self.old_game_time is None or new_game_seconds <= self.old_game_time))
        
        # Determine current state
        if break_active:
            state = 'break'
        elif game_active:
            state = 'game' 
        else:
            state = 'intermission'
        
        # Check if we just transitioned from break/intermission to game (after state calc to avoid false positives)
        game_just_started = False
        if state == 'game' and self.previous_game_state in ['break', 'intermission']:
            game_just_started = True
            self.logger.info(f"🚀 GAME JUST STARTED: Transition from {self.previous_game_state} to game")
        
        # Log only if state changed or polling interval is slow
        if state != self.previous_game_state or current_time - self.last_poll_time > 2:
            self.logger.info(f"Game state: {state} | Break: {new_break_seconds}s (was {self.old_break_time}) | Game: {new_game_seconds}s (was {self.old_game_time}) | Break active: {break_active} | Game active: {game_active}")
            self.last_poll_time = current_time
        
        # Return combined start detection
        return state, new_game_start or game_just_started or instant_game_start
    
    def read_bracket(self):
        """Load tournament bracket from ODS file."""
        bracket_file = self.config['bracket_file']
        
        if not os.path.exists(bracket_file):
            self.logger.warning(f"Bracket file not found: {bracket_file}")
            return []
        
        try:
            df = pd.read_excel(bracket_file, engine='odf')
            matches = []
            
            for _, row in df.iterrows():
                match = {
                    'team_a': str(row.iloc[0]).strip().lower(),
                    'team_b': str(row.iloc[1]).strip().lower(), 
                    'time': row.iloc[2] if len(row) > 2 else None,
                    'field_no': row.iloc[3] if len(row) > 3 else None
                }
                matches.append(match)
            
            self.logger.info(f"Loaded {len(matches)} bracket matches")
            return matches
            
        except Exception as e:
            self.logger.error(f"Failed to read bracket file: {e}")
            return []
    
    def match_teams_to_bracket(self, matches, team1, team2):
        """Find bracket match for current teams."""
        for match in matches:
            if ((match['team_a'] == team1 and match['team_b'] == team2) or
                (match['team_a'] == team2 and match['team_b'] == team1)):
                return match
        return None
    
    async def authenticate_obs(self, websocket):
        """Handle OBS WebSocket authentication."""
        try:
            hello_msg = await websocket.recv()
            hello = json.loads(hello_msg)
            
            if 'authentication' in hello.get('d', {}):
                auth_data = hello['d']['authentication']
                challenge = auth_data['challenge']
                salt = auth_data['salt']
                
                # Generate authentication response
                secret = base64.b64encode(
                    hashlib.sha256((self.config['obs']['password'] + salt).encode()).digest()
                ).decode()
                
                auth_response = base64.b64encode(
                    hashlib.sha256((secret + challenge).encode()).digest()
                ).decode()
                
                # Send authentication
                auth_msg = {
                    "op": 1,
                    "d": {
                        "rpcVersion": 1, 
                        "authentication": auth_response,
                        "eventSubscriptions": 33
                    }
                }
                
                await websocket.send(json.dumps(auth_msg))
                
                # Wait for identification response
                response = await websocket.recv()
                self.logger.info("OBS WebSocket authenticated successfully")
            else:
                self.logger.info("OBS WebSocket connected (no auth required)")
                
        except Exception as e:
            self.logger.error(f"OBS authentication failed: {e}")
            raise
    
    async def connect_obs(self):
        """Establish connection to OBS WebSocket."""
        url = f"ws://{self.config['obs']['host']}:{self.config['obs']['port']}"
        max_retries = 5
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"Connecting to OBS at {url} (attempt {attempt + 1})")
                
                websocket = await websockets.connect(
                    url, 
                    ping_interval=10, 
                    ping_timeout=5,
                    close_timeout=10
                )
                
                await self.authenticate_obs(websocket)
                self.logger.info("OBS connection established")
                return websocket
                
            except Exception as e:
                self.logger.error(f"OBS connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 30)  # Exponential backoff
        
        raise ConnectionError("Failed to connect to OBS after all retry attempts")
    
    async def switch_scene(self, scene_name):
        """Switch OBS scene with ultra-fast execution and caching."""
        # Skip if we're already on this scene
        if self.scene_switch_cache.get('current_scene') == scene_name:
            return
            
        request_id = str(uuid.uuid4())
        
        try:
            request = {
                "op": 6,
                "d": {
                    "requestType": "SetCurrentProgramScene",
                    "requestId": request_id,
                    "requestData": {"sceneName": scene_name}
                }
            }
            
            # Send request immediately without waiting for response in critical moments
            await self.obs_ws.send(json.dumps(request))
            
            # For breakout scene, don't wait for confirmation - speed is critical
            if scene_name == self.config['breakout_scene']:
                self.scene_switch_cache['current_scene'] = scene_name
                self.logger.info(f"⚡ INSTANT switch to scene: {scene_name}")
                return
            
            # For other scenes, wait for confirmation with short timeout
            try:
                response_msg = await asyncio.wait_for(self.obs_ws.recv(), timeout=2.0)
                response = json.loads(response_msg)
                
                if response.get('d', {}).get('requestStatus', {}).get('result', False):
                    self.scene_switch_cache['current_scene'] = scene_name
                    self.logger.info(f"Switched to scene: {scene_name}")
                else:
                    error_msg = response.get('d', {}).get('requestStatus', {}).get('comment', 'Unknown error')
                    self.logger.error(f"Scene switch failed for {scene_name}: {error_msg}")
                    
            except asyncio.TimeoutError:
                # Assume success for timeout to avoid blocking
                self.scene_switch_cache['current_scene'] = scene_name
                self.logger.warning(f"Scene switch timeout for {scene_name} - assuming success")
                
        except Exception as e:
            self.logger.error(f"Scene switch error for {scene_name}: {e}")
    
    async def handle_camera_switching(self, current_state, new_game_start):
        """Manage camera switching logic with ultra-fast breakout sequence."""
        current_time = time.time()
        
        # Handle different game states
        if current_state == 'intermission':
            await self.switch_scene(self.config['interview_scene'])
            # Only reset breakout if we were previously in a game
            if self.previous_game_state == 'game':
                self.logger.info("🔄 Game ended - resetting breakout trigger")
                if self.sequence_task is not None:
                    self.sequence_task.cancel()
                    self.sequence_task = None
                self.breakout_triggered = False
                self.last_switch_time = 0
                self.current_scene_type = None
            
        elif current_state == 'break':
            await self.switch_scene(self.config['break_scene'])
            # Don't reset breakout during break - game might resume
            
        elif current_state == 'game':
            # Handle new game start sequence - ULTRA FAST execution
            if new_game_start and not self.breakout_triggered:
                self.logger.info("⚡ ULTRA-FAST BREAKOUT SEQUENCE STARTING...")
                
                # INSTANT breakout scene switch - no delays
                self.logger.info("📹 INSTANT Breakout Scene")
                await self.switch_scene(self.config['breakout_scene'])
                
                # Create async task for timed sequence to avoid blocking main loop
                async def timed_sequence():
                    try:
                        # Wait 7 seconds for breakout
                        await asyncio.sleep(7)
                        
                        self.logger.info("📹 Default Scene (30 seconds)")
                        await self.switch_scene(self.config['default_scene'])
                        self.current_scene_type = 'default'
                        
                        # Wait 30 seconds for default
                        await asyncio.sleep(30)
                        
                        # Switch to game scene and start rotation
                        self.logger.info("📹 Starting Game Scene rotation")
                        await self.switch_scene(self.config['game_scene'])
                        self.current_scene_type = 'game'
                        self.last_switch_time = time.time()
                    except asyncio.CancelledError:
                        self.logger.info("Breakout sequence task cancelled")
                
                # Cancel any existing sequence task
                if self.sequence_task is not None:
                    self.sequence_task.cancel()
                
                # Start the timed sequence without blocking
                self.sequence_task = asyncio.create_task(timed_sequence())
                
                # Mark breakout as triggered immediately
                self.breakout_triggered = True
                
            elif self.breakout_triggered and not self.is_paused and current_time - self.last_switch_time >= 40:
                # Regular 40-second rotation (only after breakout sequence completes)
                if self.current_scene_type == 'game':
                    self.logger.info("📹 Switching to Default Scene (40s rotation)")
                    await self.switch_scene(self.config['default_scene'])
                    self.current_scene_type = 'default'
                elif self.current_scene_type == 'default':
                    self.logger.info("📹 Switching to Game Scene (40s rotation)")
                    await self.switch_scene(self.config['game_scene'])
                    self.current_scene_type = 'game'
                
                self.last_switch_time = current_time
                
            elif not self.breakout_triggered and self.previous_game_state != 'game':
                # If we're in game state but haven't done breakout, just use game scene
                self.logger.info("📹 Game active but no breakout - using Game Scene")
                await self.switch_scene(self.config['game_scene'])
                self.current_scene_type = 'game'
    
    def check_pause_status(self):
        """Check if manual pause is requested."""
        pause_file = '/tmp/roc-pause'
        
        if os.path.exists(pause_file):
            if not self.pause_flag:
                self.pause_flag = True
                self.logger.info("Manual pause activated")
        else:
            if self.pause_flag:
                self.pause_flag = False
                self.logger.info("Manual pause deactivated - resuming automation")
    
    async def keep_obs_alive(self):
        """Send periodic pings to keep OBS connection alive."""
        while not self.exit_flag:
            try:
                if self.obs_ws and self.obs_ws.open:
                    await self.obs_ws.ping()
                await asyncio.sleep(10)
            except Exception as e:
                self.logger.warning(f"Keep-alive ping failed: {e}")
                break
    
    async def run(self):
        """Main execution loop."""
        self.logger.info("Starting Remote OBS Controller")
        
        # Initialize environment
        self.manage_venv()
        self.check_and_install_dependencies()
        
        if not self.check_network():
            self.logger.error("Network connectivity check failed")
            return False
        
        # Setup WebDriver
        self.driver = self.setup_webdriver()
        if not self.driver:
            self.logger.error("Failed to initialize WebDriver")
            return False
        
        # Connect to OBS
        try:
            self.obs_ws = await self.connect_obs()
        except Exception as e:
            self.logger.error(f"Failed to connect to OBS: {e}")
            return False
        
        # Get scoreboard URL for configured field
        field_key = f"field{self.config['field_number']}"
        if field_key not in self.config['scoreboards']:
            self.logger.error(f"Field {self.config['field_number']} not found in scoreboard config")
            return False
        
        scoreboard_url = self.config['scoreboards'][field_key]
        self.logger.info(f"Monitoring {field_key} scoreboard at {scoreboard_url}")
        
        # Start keep-alive task
        keep_alive_task = asyncio.create_task(self.keep_obs_alive())
        
        try:
            # Main monitoring loop
            while not self.exit_flag:
                # Check for manual pause
                self.check_pause_status()
                if self.pause_flag:
                    await asyncio.sleep(1)
                    continue
                
                # Parse scoreboard data with minimal processing overhead
                team1, team2, break_time, game_time = self.parse_scoreboard(scoreboard_url)
                
                if not team1 or not team2:
                    # Only switch to interview if we're not already there
                    if self.scene_switch_cache.get('current_scene') != self.config['interview_scene']:
                        self.logger.warning("Invalid team data - switching to interview scene")
                        await self.switch_scene(self.config['interview_scene'])
                    await asyncio.sleep(0.5)  # Shorter wait for invalid data
                    continue
                
                # Convert times to seconds (optimized)
                break_seconds = self.time_to_seconds(break_time) if break_time else 0
                game_seconds = self.time_to_seconds(game_time) if game_time else 0
                
                # Store previous state before detecting new state
                self.previous_game_state = self.game_state
                
                # Detect game state and check for new game (critical path)
                current_state, new_game_start = self.detect_game_state(break_seconds, game_seconds)
                
                # Detect paused state
                if self.old_break_time is not None and self.old_game_time is not None:
                    if break_seconds == self.old_break_time and game_seconds == self.old_game_time:
                        self.pause_counter += 1
                    else:
                        self.pause_counter = 0
                else:
                    self.pause_counter = 0
                self.is_paused = self.pause_counter >= 3  # ~0.3 seconds of no change
                
                if self.is_paused and self.pause_counter == 3:
                    self.logger.info("Game paused detected")
                elif not self.is_paused and self.pause_counter == 0:
                    if self.old_break_time is not None:
                        self.logger.info("Game resumed")
                
                # Handle camera switching (optimized for speed)
                await self.handle_camera_switching(current_state, new_game_start)
                
                # Update state tracking
                self.game_state = current_state
                self.old_break_time = break_seconds
                self.old_game_time = game_seconds
                
                # Ultra-short polling interval - no sleep for critical transitions
                if current_state == 'break' and break_seconds <= 5:
                    # Critical moment - poll as fast as possible
                    continue
                elif new_game_start:
                    # Just started a game - keep polling fast
                    continue
                else:
                    # Normal polling
                    await asyncio.sleep(self.config['polling_interval'])
                
        except Exception as e:
            self.logger.error(f"Main loop error: {e}")
            return False
        
        finally:
            # Cleanup
            self.logger.info("Shutting down...")
            
            keep_alive_task.cancel()
            if self.sequence_task is not None:
                self.sequence_task.cancel()
            
            if self.obs_ws:
                try:
                    await self.obs_ws.close()
                    self.logger.info("OBS WebSocket connection closed")
                except Exception as e:
                    self.logger.warning(f"Error closing OBS connection: {e}")
            
            self.cleanup_webdriver()
            
        return True

# Entry point for systemd service
async def main():
    """Main entry point."""
    controller = ROCController()
    success = await controller.run()
    return 0 if success else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt")
        sys.exit(0)
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        sys.exit(1)
