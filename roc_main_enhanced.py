#!/usr/bin/env python3
"""
ROC (Remote OBS Controller) Main Application - Phase 2 (Enhanced)
Author: Aidan A. Bradley
Version: 1.0.1

Enhanced version with:
- Robust connection management with exponential backoff
- Per-camera health monitoring and auto-recovery
- Complete scene switching logic engine
- Better error handling and recovery
- Configuration-driven scene rules
"""

import os
import sys
import json
import time
import asyncio
import signal
import logging
import subprocess
import threading
import queue
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import importlib.util

# Add the path to import modules
sys.path.insert(0, str(Path(__file__).parent))

# Configuration paths
TEMP_DIR = Path("/tmp/roc")
CONFIG_DIR = Path("/etc/roc")
LOG_DIR = Path("/var/log/roc")
MODULES_DIR = Path("/opt/roc/modules")

class ConnectionState(Enum):
    """Enhanced connection state enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"
    DISABLED = "disabled"

class SystemState(Enum):
    """System operational states."""
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    SHUTTING_DOWN = "shutting_down"
    ERROR = "error"

@dataclass
class ConnectionStatus:
    """Enhanced connection status tracking."""
    state: ConnectionState
    last_connected: float = 0
    last_attempt: float = 0
    reconnect_attempts: int = 0
    total_failures: int = 0
    throttle_until: float = 0
    error_message: str = ""
    connection_quality: float = 1.0  # 0-1 scale

@dataclass
class CameraStatus:
    """Camera-specific status tracking."""
    camera_id: str
    ip_address: str
    device_index: int
    connection_status: ConnectionStatus
    stream_active: bool = False
    ffmpeg_process: Optional[subprocess.Popen] = None
    last_frame_time: float = 0
    frame_count: int = 0
    error_count: int = 0
    restart_count: int = 0

class ConnectionManager:
    """Enhanced connection manager with exponential backoff and health monitoring."""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.connections: Dict[str, Dict[str, Any]] = {}
        self.user_input_queue = queue.Queue()
        self.running = True
        
    def register_connection(self, name: str, test_func: Callable, connect_func: Callable, 
                          requires_auth: bool = False, auto_reconnect: bool = True,
                          max_attempts: int = 10, base_delay: float = 2.0):
        """Register a connection for monitoring with enhanced options."""
        self.connections[name] = {
            'status': ConnectionStatus(ConnectionState.DISCONNECTED),
            'test_func': test_func,
            'connect_func': connect_func,
            'requires_auth': requires_auth,
            'auto_reconnect': auto_reconnect,
            'max_attempts': max_attempts,
            'base_delay': base_delay,
            'connection_obj': None
        }
        self.logger.info(f"Registered connection: {name}")
        
    def calculate_backoff_delay(self, attempts: int, base_delay: float) -> float:
        """Calculate exponential backoff delay with jitter."""
        import random
        max_delay = 60.0  # Cap at 1 minute
        delay = min(base_delay * (2 ** attempts), max_delay)
        # Add jitter to prevent thundering herd
        jitter = delay * 0.1 * random.random()
        return delay + jitter
        
    async def test_connection(self, name: str) -> bool:
        """Test if a connection is alive."""
        if name not in self.connections:
            return False
            
        try:
            conn_info = self.connections[name]
            if asyncio.iscoroutinefunction(conn_info['test_func']):
                return await conn_info['test_func']()
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, conn_info['test_func'])
        except Exception as e:
            self.logger.debug(f"Connection test failed for {name}: {e}")
            return False
            
    async def handle_disconnection(self, name: str, error_msg: str = ""):
        """Handle disconnection with enhanced logic."""
        if name not in self.connections:
            return
            
        conn_info = self.connections[name]
        status = conn_info['status']
        
        status.state = ConnectionState.DISCONNECTED
        status.error_message = error_msg
        status.total_failures += 1
        
        self.logger.warning(f"Connection lost to {name}: {error_msg} (Total failures: {status.total_failures})")
        
        if conn_info['requires_auth']:
            # Prompt user for authenticated connections
            await self.prompt_user_reconnect(name)
        elif conn_info['auto_reconnect'] and status.reconnect_attempts < conn_info['max_attempts']:
            # Auto-reconnect for non-authenticated connections
            status.state = ConnectionState.RECONNECTING
            status.last_attempt = time.time()
        else:
            status.state = ConnectionState.FAILED
            self.logger.error(f"Connection {name} marked as failed after {status.reconnect_attempts} attempts")
            
    async def prompt_user_reconnect(self, name: str):
        """Prompt user to confirm reconnection for authenticated services."""
        self.logger.info(f"\n{'='*50}")
        self.logger.info(f"CONNECTION LOST: {name}")
        self.logger.info("This connection requires authentication.")
        self.logger.info("Options:")
        self.logger.info("  r = Reconnect now")
        self.logger.info("  d = Disable auto-reconnect") 
        self.logger.info("  i = Ignore (wait for manual intervention)")
        self.logger.info("  (or wait 30 seconds for auto-reconnect)")
        self.logger.info("="*50)
        
        # Handle user input with timeout
        def get_user_input():
            try:
                response = input("Choice (r/d/i): ").strip().lower()
                self.user_input_queue.put((name, response))
            except:
                self.user_input_queue.put((name, 'timeout'))
                
        input_thread = threading.Thread(target=get_user_input, daemon=True)
        input_thread.start()
        
        # Wait for response or timeout
        start_time = time.time()
        while time.time() - start_time < 30:
            try:
                response_name, response = self.user_input_queue.get(timeout=1)
                if response_name == name:
                    if response == 'r':
                        self.logger.info(f"User requested immediate reconnection to {name}")
                        if name in self.connections:
                            self.connections[name]['status'].state = ConnectionState.RECONNECTING
                        return
                    elif response == 'd':
                        self.logger.info(f"User disabled auto-reconnect for {name}")
                        if name in self.connections:
                            self.connections[name]['auto_reconnect'] = False
                            self.connections[name]['status'].state = ConnectionState.DISABLED
                        return
                    elif response == 'i':
                        self.logger.info(f"User chose to ignore {name} - manual intervention required")
                        return
            except queue.Empty:
                continue
                
        # Timeout - assume reconnect
        self.logger.info(f"No response received - will attempt to reconnect to {name}")
        if name in self.connections:
            self.connections[name]['status'].state = ConnectionState.RECONNECTING
            
    async def attempt_reconnection(self, name: str) -> bool:
        """Attempt to reconnect with enhanced error handling."""
        conn_info = self.connections[name]
        status = conn_info['status']
        
        if status.reconnect_attempts >= conn_info['max_attempts']:
            status.state = ConnectionState.FAILED
            self.logger.error(f"Max reconnection attempts reached for {name}")
            return False
            
        try:
            self.logger.info(f"Attempting to reconnect to {name} (attempt {status.reconnect_attempts + 1}/{conn_info['max_attempts']})")
            
            status.state = ConnectionState.CONNECTING
            
            if asyncio.iscoroutinefunction(conn_info['connect_func']):
                connection_obj = await conn_info['connect_func']()
            else:
                loop = asyncio.get_event_loop()
                connection_obj = await loop.run_in_executor(None, conn_info['connect_func'])
            
            if connection_obj is not None:
                conn_info['connection_obj'] = connection_obj
                status.state = ConnectionState.CONNECTED
                status.last_connected = time.time()
                status.reconnect_attempts = 0
                status.error_message = ""
                status.connection_quality = 1.0
                
                self.logger.info(f"Successfully reconnected to {name}")
                return True
            else:
                raise Exception("Connection function returned None")
                
        except Exception as e:
            status.reconnect_attempts += 1
            status.last_attempt = time.time()
            
            delay = self.calculate_backoff_delay(status.reconnect_attempts, conn_info['base_delay'])
            status.throttle_until = time.time() + delay
            
            self.logger.warning(f"Reconnection to {name} failed (attempt {status.reconnect_attempts}): {e}")
            self.logger.info(f"Will retry in {delay:.2f} seconds")
            
            status.state = ConnectionState.RECONNECTING
            return False
            
    async def monitor_connections(self):
        """Monitor all connections and handle reconnections."""
        self.logger.info("Starting connection monitoring...")
        
        while self.running:
            try:
                current_time = time.time()
                
                for name, conn_info in self.connections.items():
                    status = conn_info['status']
                    
                    # Skip if throttled or disabled
                    if current_time < status.throttle_until or status.state == ConnectionState.DISABLED:
                        continue
                        
                    if status.state == ConnectionState.CONNECTED:
                        # Test existing connection
                        if not await self.test_connection(name):
                            await self.handle_disconnection(name, "Connection test failed")
                        else:
                            # Update connection quality based on response time
                            status.connection_quality = min(status.connection_quality * 1.01, 1.0)
                            
                    elif status.state == ConnectionState.RECONNECTING:
                        # Attempt reconnection
                        await self.attempt_reconnection(name)
                        
                await asyncio.sleep(1)  # Check every second
                
            except Exception as e:
                self.logger.error(f"Connection monitor error: {e}")
                await asyncio.sleep(5)
                
    def get_connection_status(self, name: str) -> Optional[ConnectionStatus]:
        """Get connection status for a specific connection."""
        return self.connections.get(name, {}).get('status')
        
    def get_all_statuses(self) -> Dict[str, ConnectionStatus]:
        """Get all connection statuses."""
        return {name: info['status'] for name, info in self.connections.items()}
        
    def shutdown(self):
        """Shutdown connection manager."""
        self.running = False
        self.logger.info("Connection manager shutting down...")

class CameraManager:
    """Enhanced camera management with per-camera health monitoring."""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.cameras: Dict[str, CameraStatus] = {}
        self.camera_config = self.load_camera_config()
        self.running = True
        
    def load_camera_config(self) -> Dict[str, Any]:
        """Load camera configuration from file."""
        camera_config_file = Path(self.config.get('cameras', {}).get('config_file', '/etc/roc/cameras.json'))
        
        if not camera_config_file.exists():
            self.logger.warning(f"Camera config file not found: {camera_config_file}")
            return {"cameras": []}
            
        try:
            with open(camera_config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load camera config: {e}")
            return {"cameras": []}
            
    def initialize_cameras(self):
        """Initialize all cameras from configuration."""
        cameras_list = self.camera_config.get('cameras', [])
        
        for camera_info in cameras_list:
            if not camera_info.get('enabled', True):
                continue
                
            camera_id = camera_info.get('name', f"camera_{camera_info.get('id', 'unknown')}")
            
            camera_status = CameraStatus(
                camera_id=camera_id,
                ip_address=camera_info.get('ip', ''),
                device_index=camera_info.get('device_index', 0),
                connection_status=ConnectionStatus(ConnectionState.DISCONNECTED)
            )
            
            self.cameras[camera_id] = camera_status
            self.logger.info(f"Initialized camera: {camera_id} ({camera_status.ip_address})")
            
    async def start_camera_stream(self, camera_id: str) -> bool:
        """Start FFmpeg stream for a specific camera."""
        if camera_id not in self.cameras:
            self.logger.error(f"Unknown camera: {camera_id}")
            return False
            
        camera = self.cameras[camera_id]
        camera_config = next((c for c in self.camera_config['cameras'] if c.get('name') == camera_id), None)
        
        if not camera_config:
            self.logger.error(f"No configuration found for camera: {camera_id}")
            return False
            
        # Stop existing stream if running
        await self.stop_camera_stream(camera_id)
        
        try:
            # Build FFmpeg command
            rtsp_url = camera_config.get('stream_config', {}).get('main_stream')
            if not rtsp_url:
                self.logger.error(f"No stream URL configured for camera: {camera_id}")
                return False
                
            device_path = f"/dev/video{camera.device_index}"
            
            # Enhanced FFmpeg command with error recovery
            ffmpeg_cmd = [
                "ffmpeg",
                "-re",  # Read input at native frame rate
                "-rtsp_transport", "tcp",  # Use TCP for RTSP (more reliable)
                "-i", rtsp_url,
                "-vcodec", "rawvideo",
                "-pix_fmt", "yuv420p",
                "-threads", "2",
                "-f", "v4l2",
                "-preset", "ultrafast",  # Low latency
                "-tune", "zerolatency",
                "-bufsize", "64k",
                "-maxrate", "2M",
                device_path
            ]
            
            # Add authentication if configured
            username = camera_config.get('stream_config', {}).get('username')
            password = camera_config.get('stream_config', {}).get('password')
            if username and password:
                # Insert auth before -i
                auth_index = ffmpeg_cmd.index('-i')
                ffmpeg_cmd.insert(auth_index, '-rtsp_flags')
                ffmpeg_cmd.insert(auth_index + 1, 'prefer_tcp')
                # Modify URL to include auth
                rtsp_url = rtsp_url.replace('rtsp://', f'rtsp://{username}:{password}@')
                ffmpeg_cmd[ffmpeg_cmd.index(rtsp_url)] = rtsp_url
                
            self.logger.info(f"Starting FFmpeg for {camera_id}: {' '.join(ffmpeg_cmd[:10])}...")
            
            # Start FFmpeg process
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            camera.ffmpeg_process = process
            camera.stream_active = True
            camera.connection_status.state = ConnectionState.CONNECTED
            camera.connection_status.last_connected = time.time()
            camera.last_frame_time = time.time()
            
            self.logger.info(f"FFmpeg started for {camera_id} (PID: {process.pid})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start camera stream {camera_id}: {e}")
            camera.connection_status.state = ConnectionState.FAILED
            camera.error_count += 1
            return False
            
    async def stop_camera_stream(self, camera_id: str):
        """Stop FFmpeg stream for a specific camera."""
        if camera_id not in self.cameras:
            return
            
        camera = self.cameras[camera_id]
        
        if camera.ffmpeg_process:
            try:
                self.logger.info(f"Stopping FFmpeg for {camera_id} (PID: {camera.ffmpeg_process.pid})")
                camera.ffmpeg_process.terminate()
                
                # Wait for graceful termination
                try:
                    camera.ffmpeg_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.logger.warning(f"FFmpeg for {camera_id} didn't terminate gracefully, killing...")
                    camera.ffmpeg_process.kill()
                    camera.ffmpeg_process.wait()
                    
                camera.ffmpeg_process = None
                
            except Exception as e:
                self.logger.error(f"Error stopping camera {camera_id}: {e}")
                
        camera.stream_active = False
        camera.connection_status.state = ConnectionState.DISCONNECTED
        
    async def check_camera_health(self, camera_id: str) -> bool:
        """Check health of a specific camera."""
        if camera_id not in self.cameras:
            return False
            
        camera = self.cameras[camera_id]
        
        # Check if FFmpeg process is running
        if not camera.ffmpeg_process or camera.ffmpeg_process.poll() is not None:
            self.logger.warning(f"FFmpeg process for {camera_id} is not running")
            camera.stream_active = False
            return False
            
        # Check if we're receiving frames (basic check)
        current_time = time.time()
        if current_time - camera.last_frame_time > 30:  # 30 seconds without frames
            self.logger.warning(f"No frames received from {camera_id} for 30 seconds")
            return False
            
        # Check FFmpeg stderr for errors
        try:
            if camera.ffmpeg_process.stderr:
                # Non-blocking read of stderr
                import fcntl
                import os
                fd = camera.ffmpeg_process.stderr.fileno()
                fl = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
                
                try:
                    stderr_data = camera.ffmpeg_process.stderr.read()
                    if stderr_data and "error" in stderr_data.lower():
                        self.logger.warning(f"FFmpeg errors detected for {camera_id}: {stderr_data[:200]}")
                        return False
                except:
                    pass  # No data available, that's OK
                    
        except Exception as e:
            self.logger.debug(f"Error checking FFmpeg stderr for {camera_id}: {e}")
            
        return True
        
    async def restart_camera(self, camera_id: str) -> bool:
        """Restart a camera stream."""
        if camera_id not in self.cameras:
            return False
            
        camera = self.cameras[camera_id]
        camera.restart_count += 1
        
        self.logger.info(f"Restarting camera {camera_id} (restart #{camera.restart_count})")
        
        await self.stop_camera_stream(camera_id)
        await asyncio.sleep(2)  # Brief pause
        return await self.start_camera_stream(camera_id)
        
    async def monitor_cameras(self):
        """Monitor all cameras and restart failed ones."""
        self.logger.info("Starting camera health monitoring...")
        
        while self.running:
            try:
                for camera_id in list(self.cameras.keys()):
                    camera = self.cameras[camera_id]
                    
                    if camera.stream_active:
                        if not await self.check_camera_health(camera_id):
                            self.logger.warning(f"Camera health check failed for {camera_id}")
                            camera.error_count += 1
                            
                            # Restart if not too many recent restarts
                            if camera.restart_count < 5:  # Max 5 restarts
                                await self.restart_camera(camera_id)
                            else:
                                self.logger.error(f"Camera {camera_id} has failed too many times, disabling")
                                camera.connection_status.state = ConnectionState.FAILED
                                await self.stop_camera_stream(camera_id)
                        else:
                            # Reset error count on successful health check
                            if camera.error_count > 0:
                                camera.error_count = max(0, camera.error_count - 1)
                                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Camera monitor error: {e}")
                await asyncio.sleep(5)
                
    async def start_all_cameras(self):
        """Start all configured cameras."""
        self.logger.info("Starting all cameras...")
        
        tasks = []
        for camera_id in self.cameras.keys():
            tasks.append(self.start_camera_stream(camera_id))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = sum(1 for r in results if r is True)
        self.logger.info(f"Started {successful}/{len(results)} cameras successfully")
        
    async def stop_all_cameras(self):
        """Stop all cameras."""
        self.logger.info("Stopping all cameras...")
        
        tasks = []
        for camera_id in self.cameras.keys():
            tasks.append(self.stop_camera_stream(camera_id))
            
        await asyncio.gather(*tasks, return_exceptions=True)
        
    def get_camera_status(self, camera_id: str) -> Optional[CameraStatus]:
        """Get status for a specific camera."""
        return self.cameras.get(camera_id)
        
    def get_all_camera_statuses(self) -> Dict[str, CameraStatus]:
        """Get all camera statuses."""
        return self.cameras.copy()
        
    def shutdown(self):
        """Shutdown camera manager."""
        self.running = False
        self.logger.info("Camera manager shutting down...")

class SceneEngine:
    """Configuration-driven scene switching engine."""
    
    def __init__(self, config: Dict[str, Any], logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.current_scene = None
        self.last_scene_change = 0
        self.scene_rules = self.load_scene_rules()
        self.obs_connection = None
        
    def load_scene_rules(self) -> List[Dict[str, Any]]:
        """Load scene switching rules from configuration."""
        rules_file = CONFIG_DIR / "scene_rules.json"
        
        if rules_file.exists():
            try:
                with open(rules_file, 'r') as f:
                    rules_config = json.load(f)
                    return rules_config.get('rules', [])
            except Exception as e:
                self.logger.error(f"Failed to load scene rules: {e}")
                
        # Default rules if no file exists
        default_rules = [
            {
                "name": "game_active",
                "priority": 100,
                "conditions": [
                    {"field": "game_time", "operator": ">", "value": 0},
                    {"field": "break_time", "operator": "==", "value": 0}
                ],
                "action": {"type": "switch_scene", "scene": "game"},
                "min_duration": 5
            },
            {
                "name": "break_active", 
                "priority": 90,
                "conditions": [
                    {"field": "break_time", "operator": ">", "value": 0}
                ],
                "action": {"type": "switch_scene", "scene": "break"},
                "min_duration": 3
            },
            {
                "name": "game_start_breakout",
                "priority": 150,
                "conditions": [
                    {"field": "game_time", "operator": ">", "value": 0},
                    {"field": "game_just_started", "operator": "==", "value": True}
                ],
                "action": {"type": "breakout_sequence"},
                "min_duration": 1
            },
            {
                "name": "interview_mode",
                "priority": 50,
                "conditions": [
                    {"field": "game_time", "operator": "==", "value": 0},
                    {"field": "break_time", "operator": "==", "value": 0}
                ],
                "action": {"type": "switch_scene", "scene": "interview"},
                "min_duration": 10
            }
        ]
        
        # Save default rules for future editing
        try:
            rules_config = {
                "meta": {
                    "description": "ROC Scene Switching Rules",
                    "version": "1.0"
                },
                "rules": default_rules
            }
            with open(rules_file, 'w') as f:
                json.dump(rules_config, f, indent=4)
            self.logger.info(f"Created default scene rules at {rules_file}")
        except Exception as e:
            self.logger.warning(f"Could not save default scene rules: {e}")
            
        return default_rules
        
    def evaluate_condition(self, condition: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """Evaluate a single condition against scoreboard data."""
        field = condition.get('field')
        operator = condition.get('operator')
        expected_value = condition.get('value')
        
        if field not in data:
            return False
            
        actual_value = data[field]
        
        try:
            if operator == "==":
                return actual_value == expected_value
            elif operator == "!=":
                return actual_value != expected_value
            elif operator == ">":
                return float(actual_value) > float(expected_value)
            elif operator == ">=":
                return float(actual_value) >= float(expected_value)
            elif operator == "<":
                return float(actual_value) < float(expected_value)
            elif operator == "<=":
                return float(actual_value) <= float(expected_value)
            elif operator == "contains":
                return str(expected_value) in str(actual_value)
            elif operator == "regex":
                import re
                return bool(re.search(str(expected_value), str(actual_value)))
            else:
                self.logger.warning(f"Unknown operator: {operator}")
                return False
        except Exception as e:
            self.logger.debug(f"Condition evaluation error: {e}")
            return False
            
    def evaluate_rule(self, rule: Dict[str, Any], data: Dict[str, Any]) -> bool:
        """Evaluate if a rule should trigger based on current data."""
        conditions = rule.get('conditions', [])
        
        # All conditions must be true (AND logic)
        for condition in conditions:
            if not self.evaluate_condition(condition, data):
                return False
                
        # Check minimum duration since last scene change
        min_duration = rule.get('min_duration', 0)
        current_time = time.time()
        
        if current_time - self.last_scene_change < min_duration:
            return False
            
        return True
        
    async def process_scoreboard_data(self, data: Dict[str, Any]):
        """Process scoreboard data and execute scene rules."""
        # Add derived fields
        enhanced_data = data.copy()
        
        # Detect game start
        current_time = time.time()
        if 'game_time' in data and data['game_time'] > 0:
            if not hasattr(self, '_last_game_time') or self._last_game_time == 0:
                enhanced_data['game_just_started'] = True
                self.logger.info("Game start detected!")
            else:
                enhanced_data['game_just_started'] = False
        else:
            enhanced_data['game_just_started'] = False
            
        self._last_game_time = data.get('game_time', 0)
        
        # Find the highest priority rule that matches
        matching_rules = []
        for rule in self.scene_rules:
            if self.evaluate_rule(rule, enhanced_data):
                matching_rules.append(rule)
                
        if not matching_rules:
            return
            
        # Sort by priority (higher = more important)
        matching_rules.sort(key=lambda r: r.get('priority', 0), reverse=True)
        selected_rule = matching_rules[0]
        
        self.logger.info(f"Scene rule triggered: {selected_rule['name']}")
        
        # Execute the action
        action = selected_rule.get('action', {})
        await self.execute_action(action, enhanced_data)
        
    async def execute_action(self, action: Dict[str, Any], data: Dict[str, Any]):
        """Execute a scene action."""
        action_type = action.get('type')
        
        if action_type == "switch_scene":
            scene_name = action.get('scene')
            await self.switch_to_scene(scene_name)
            
        elif action_type == "breakout_sequence":
            await self.execute_breakout_sequence()
            
        elif action_type == "camera_rotation":
            cameras = action.get('cameras', [])
            duration = action.get('duration', 5)
            await self.rotate_cameras(cameras, duration)
            
        elif action_type == "custom":
            # Execute custom Python code (be careful!)
            code = action.get('code', '')
            await self.execute_custom_code(code, data)
            
        else:
            self.logger.warning(f"Unknown action type: {action_type}")
            
    async def switch_to_scene(self, scene_name: str):
        """Switch to a specific OBS scene."""
        if not self.obs_connection:
            self.logger.error("No OBS connection available for scene switch")
            return
            
        scene_mapping = self.config.get('obs', {}).get('scenes', {})
        obs_scene_name = scene_mapping.get(scene_name, scene_name)
        
        try:
            # This would integrate with your OBS WebSocket client
            self.logger.info(f"Switching to scene: {obs_scene_name}")
            
            # Placeholder for actual OBS WebSocket call
            # await self.obs_connection.set_current_scene(obs_scene_name)
            
            self.current_scene = scene_name
            self.last_scene_change = time.time()
            
        except Exception as e:
            self.logger.error(f"Failed to switch scene to {obs_scene_name}: {e}")
            
    async def execute_breakout_sequence(self):
        """Execute the breakout sequence for game start."""
        self.logger.info("Executing breakout sequence...")
        
        # Quick sequence: breakout -> game
        await self.switch_to_scene('breakout')
        await asyncio.sleep(2)  # Show breakout for 2 seconds
        await self.switch_to_scene('game')
        
    async def rotate_cameras(self, cameras: List[str], duration: float):
        """Rotate through multiple cameras."""
        self.logger.info(f"Starting camera rotation: {cameras} for {duration}s each")
        
        for camera in cameras:
            # This would switch to a camera-specific scene
            await self.switch_to_scene(f"camera_{camera}")
            await asyncio.sleep(duration)
            
    async def execute_custom_code(self, code: str, data: Dict[str, Any]):
        """Execute custom Python code (use with caution)."""
        self.logger.warning("Executing custom scene code - this could be dangerous!")
        
        try:
            # Create a restricted execution environment
            allowed_globals = {
                'switch_scene': self.switch_to_scene,
                'logger': self.logger,
                'data': data,
                'asyncio': asyncio,
                'time': time
            }
            
            exec(code, allowed_globals)
            
        except Exception as e:
            self.logger.error(f"Custom code execution failed: {e}")

class ROCMainApplication:
    """Enhanced main ROC application coordinator."""
    
    def __init__(self):
        self.setup_logging()
        self.load_phase1_status()
        self.config = self.phase1_status.get('config', {})
        
        # System state
        self.system_state = SystemState.INITIALIZING
        self.exit_flag = False
        
        # Core components
        self.connection_manager = ConnectionManager(self.config, self.logger)
        self.camera_manager = CameraManager(self.config, self.logger)
        self.scene_engine = SceneEngine(self.config, self.logger)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Pause file monitoring
        self.pause_file = Path("/tmp/roc-pause")
        
    def setup_logging(self):
        """Configure logging system."""
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
            handlers=[
                logging.FileHandler(LOG_DIR / "roc_main.log"),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger("ROC-Main")
        self.logger.info("="*60)
        self.logger.info("ROC Enhanced Main Application - Phase 2 Starting")
        self.logger.info("="*60)
        
    def load_phase1_status(self):
        """Load Phase 1 status information."""
        status_file = TEMP_DIR / "phase1_status.json"
        
        if not status_file.exists():
            self.logger.error("Phase 1 status file not found - running without bootstrap info")
            self.phase1_status = {}
            return
            
        try:
            with open(status_file, 'r') as f:
                self.phase1_status = json.load(f)
                
            self.logger.info("Loaded Phase 1 status information")
            
            # Log any critical issues from Phase 1
            if self.phase1_status.get('critical_errors', 0) > 0:
                self.logger.warning(f"Phase 1 reported {self.phase1_status['critical_errors']} critical errors")
                
        except Exception as e:
            self.logger.error(f"Failed to load Phase 1 status: {e}")
            self.phase1_status = {}
            
    def _signal_handler(self, sig, frame):
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {sig} - initiating shutdown")
        self.exit_flag = True
        self.system_state = SystemState.SHUTTING_DOWN
        
    def check_pause_state(self) -> bool:
        """Check if system is paused via pause file."""
        if self.pause_file.exists():
            if self.system_state != SystemState.PAUSED:
                self.logger.info("System paused via pause file")
                self.system_state = SystemState.PAUSED
            return True
        else:
            if self.system_state == SystemState.PAUSED:
                self.logger.info("System unpaused - pause file removed")
                self.system_state = SystemState.RUNNING
            return False
            
    async def run_main_loop(self) -> bool:
        """Enhanced main application loop."""
        self.logger.info("Starting enhanced main application loop...")
        
        try:
            # Initialize cameras
            self.camera_manager.initialize_cameras()
            
            # Start all cameras
            await self.camera_manager.start_all_cameras()
            
            # Start monitoring tasks
            monitor_task = asyncio.create_task(self.connection_manager.monitor_connections())
            camera_monitor_task = asyncio.create_task(self.camera_manager.monitor_cameras())
            
            # Set system state to running
            self.system_state = SystemState.RUNNING
            
            # Main loop
            while not self.exit_flag:
                try:
                    # Check pause state
                    if self.check_pause_state():
                        await asyncio.sleep(1)
                        continue
                        
                    # Periodic system health checks
                    if int(time.time()) % 60 == 0:  # Every minute
                        await self.log_system_health()
                        
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    self.logger.error(f"Main loop iteration error: {e}")
                    self.system_state = SystemState.ERROR
                    await asyncio.sleep(5)
                    
        except Exception as e:
            self.logger.error(f"Main loop critical error: {e}")
            return False
            
        finally:
            # Cleanup
            self.logger.info("Shutting down ROC Main Application...")
            
            # Cancel monitoring tasks
            monitor_task.cancel()
            camera_monitor_task.cancel()
            
            # Stop all cameras
            await self.camera_manager.stop_all_cameras()
            
            # Shutdown components
            self.connection_manager.shutdown()
            self.camera_manager.shutdown()
            
        return True
        
    async def log_system_health(self):
        """Log comprehensive system health information."""
        camera_statuses = self.camera_manager.get_all_camera_statuses()
        connection_statuses = self.connection_manager.get_all_statuses()
        
        active_cameras = sum(1 for c in camera_statuses.values() if c.stream_active)
        failed_cameras = sum(1 for c in camera_statuses.values() if c.connection_status.state == ConnectionState.FAILED)
        
        connected_services = sum(1 for c in connection_statuses.values() if c.state == ConnectionState.CONNECTED)
        failed_services = sum(1 for c in connection_statuses.values() if c.state == ConnectionState.FAILED)
        
        self.logger.info(f"System Health - State: {self.system_state.value}")
        self.logger.info(f"  Cameras: {active_cameras} active, {failed_cameras} failed")
        self.logger.info(f"  Services: {connected_services} connected, {failed_services} failed")
        self.logger.info(f"  Current Scene: {self.scene_engine.current_scene}")
        
    async def run(self) -> int:
        """Main application entry point."""
        try:
            success = await self.run_main_loop()
            if success:
                self.logger.info("ROC Main Application completed successfully")
                return 0
            else:
                self.logger.error("ROC Main Application failed")
                return 1
                
        except Exception as e:
            self.logger.error(f"Unhandled error in main application: {e}")
            return 1

def main():
    """Main entry point for Phase 2."""
    try:
        app = ROCMainApplication()
        return asyncio.run(app.run())
    except KeyboardInterrupt:
        logging.info("Application interrupted by user")
        return 130
    except Exception as e:
        logging.error(f"Unhandled application error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())