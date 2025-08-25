#!/usr/bin/env python3
"""
ROC Scene Logic Engine - Phase 3
Author: Aidan A. Bradley
Version: 3.0.0b

Advanced configuration-driven scene switching system with:
- JSON-based rule definitions
- Complex condition evaluation
- Scene choreography sequences  
- Custom action scripting
- Performance analytics
- Hot-reload of rules
"""

import json
import time
import asyncio
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, asdict
from enum import Enum

class ActionType(Enum):
    """Types of scene actions."""
    SWITCH_SCENE = "switch_scene"
    BREAKOUT_SEQUENCE = "breakout_sequence"
    CAMERA_ROTATION = "camera_rotation"
    CUSTOM_SCRIPT = "custom_script"
    DELAY = "delay"
    PARALLEL = "parallel"
    SEQUENCE = "sequence"

class ConditionOperator(Enum):
    """Condition evaluation operators."""
    EQUALS = "=="
    NOT_EQUALS = "!="
    GREATER_THAN = ">"
    GREATER_EQUAL = ">="
    LESS_THAN = "<"
    LESS_EQUAL = "<="
    CONTAINS = "contains"
    REGEX = "regex"
    IN_LIST = "in"
    CHANGED = "changed"
    STABLE_FOR = "stable_for"

@dataclass
class SceneRule:
    """Scene switching rule definition."""
    name: str
    priority: int
    conditions: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    min_duration: float = 0
    max_duration: float = 0
    cooldown: float = 0
    enabled: bool = True
    description: str = ""

@dataclass 
class RuleExecutionMetrics:
    """Metrics for rule execution tracking."""
    rule_name: str
    execution_count: int = 0
    last_executed: float = 0
    total_execution_time: float = 0
    success_count: int = 0
    failure_count: int = 0
    average_execution_time: float = 0

class SceneEngineAdvanced:
    """Advanced scene switching engine with comprehensive rule support."""
    
    def __init__(self, config: Dict[str, Any], obs_client, logger: logging.Logger):
        self.config = config
        self.obs_client = obs_client
        self.logger = logger
        
        # State tracking
        self.current_scene = None
        self.last_scene_change = 0
        self.scene_history = []
        self.data_history = {}
        self.rule_metrics = {}
        
        # Rule management
        self.rules = []
        self.rules_file = Path(config.get('scene_rules_file', '/etc/roc/scene_rules.json'))
        self.last_rules_reload = 0
        
        # Action handlers
        self.action_handlers = {
            ActionType.SWITCH_SCENE: self._handle_switch_scene,
            ActionType.BREAKOUT_SEQUENCE: self._handle_breakout_sequence,
            ActionType.CAMERA_ROTATION: self._handle_camera_rotation,
            ActionType.CUSTOM_SCRIPT: self._handle_custom_script,
            ActionType.DELAY: self._handle_delay,
            ActionType.PARALLEL: self._handle_parallel,
            ActionType.SEQUENCE: self._handle_sequence
        }
        
        # Load initial rules
        self.load_scene_rules()
        
    def load_scene_rules(self) -> bool:
        """Load scene rules from JSON configuration file."""
        try:
            if not self.rules_file.exists():
                self.logger.info(f"Rules file not found, creating default: {self.rules_file}")
                self._create_default_rules()
                
            with open(self.rules_file, 'r') as f:
                rules_config = json.load(f)
                
            # Parse rules into SceneRule objects
            self.rules = []
            for rule_data in rules_config.get('rules', []):
                rule = SceneRule(
                    name=rule_data['name'],
                    priority=rule_data.get('priority', 50),
                    conditions=rule_data.get('conditions', []),
                    actions=rule_data.get('actions', []),
                    min_duration=rule_data.get('min_duration', 0),
                    max_duration=rule_data.get('max_duration', 0),
                    cooldown=rule_data.get('cooldown', 0),
                    enabled=rule_data.get('enabled', True),
                    description=rule_data.get('description', '')
                )
                self.rules.append(rule)
                
                # Initialize metrics
                if rule.name not in self.rule_metrics:
                    self.rule_metrics[rule.name] = RuleExecutionMetrics(rule.name)
                    
            # Sort by priority (higher first)
            self.rules.sort(key=lambda r: r.priority, reverse=True)
            
            self.last_rules_reload = time.time()
            self.logger.info(f"Loaded {len(self.rules)} scene rules")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load scene rules: {e}")
            return False
            
    def _create_default_rules(self):
        """Create default scene rules configuration."""
        default_config = {
            "meta": {
                "description": "ROC Advanced Scene Switching Rules",
                "version": "1.0.1",
                "created": time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())
            },
            "global_settings": {
                "min_scene_duration": 2.0,
                "max_scene_duration": 300.0,
                "default_transition": "fade",
                "transition_duration": 0.5
            },
            "rules": [
                {
                    "name": "game_start_breakout",
                    "description": "Ultra-fast breakout sequence when game starts",
                    "priority": 200,
                    "conditions": [
                        {
                            "field": "game_time",
                            "operator": ">",
                            "value": 0
                        },
                        {
                            "field": "game_time",
                            "operator": "changed",
                            "from_value": 0
                        }
                    ],
                    "actions": [
                        {
                            "type": "breakout_sequence",
                            "duration": 2.0,
                            "cameras": ["dorito_left", "dorito_right", "center_field"]
                        }
                    ],
                    "min_duration": 1.0,
                    "cooldown": 10.0,
                    "enabled": True
                },
                {
                    "name": "active_game",
                    "description": "Switch to game scene during active play",
                    "priority": 100,
                    "conditions": [
                        {
                            "field": "game_time",
                            "operator": ">",
                            "value": 0
                        },
                        {
                            "field": "break_time",
                            "operator": "==",
                            "value": 0
                        }
                    ],
                    "actions": [
                        {
                            "type": "switch_scene",
                            "scene": "game"
                        }
                    ],
                    "min_duration": 5.0,
                    "enabled": True
                },
                {
                    "name": "break_period",
                    "description": "Switch to break scene during breaks",
                    "priority": 90,
                    "conditions": [
                        {
                            "field": "break_time",
                            "operator": ">",
                            "value": 0
                        }
                    ],
                    "actions": [
                        {
                            "type": "switch_scene",
                            "scene": "break"
                        }
                    ],
                    "min_duration": 3.0,
                    "enabled": True
                },
                {
                    "name": "interview_mode",
                    "description": "Default interview scene when no game activity",
                    "priority": 10,
                    "conditions": [
                        {
                            "field": "game_time",
                            "operator": "==",
                            "value": 0
                        },
                        {
                            "field": "break_time",
                            "operator": "==",
                            "value": 0
                        }
                    ],
                    "actions": [
                        {
                            "type": "switch_scene",
                            "scene": "interview"
                        }
                    ],
                    "min_duration": 10.0,
                    "enabled": True
                },
                {
                    "name": "camera_rotation_long_game",
                    "description": "Rotate cameras during long games",
                    "priority": 80,
                    "conditions": [
                        {
                            "field": "game_time",
                            "operator": ">",
                            "value": 60
                        },
                        {
                            "field": "current_scene",
                            "operator": "stable_for",
                            "value": 15
                        }
                    ],
                    "actions": [
                        {
                            "type": "camera_rotation",
                            "cameras": ["camera_1", "camera_2", "camera_3"],
                            "duration_per_camera": 8,
                            "return_to_scene": "game"
                        }
                    ],
                    "min_duration": 24.0,
                    "cooldown": 30.0,
                    "enabled": False
                }
            ]
        }
        
        # Ensure directory exists
        self.rules_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.rules_file, 'w') as f:
            json.dump(default_config, f, indent=4)
            
    def check_rules_reload(self):
        """Check if rules file has been modified and reload if necessary."""
        try:
            if self.rules_file.exists():
                file_mtime = self.rules_file.stat().st_mtime
                if file_mtime > self.last_rules_reload:
                    self.logger.info("Rules file modified, reloading...")
                    self.load_scene_rules()
        except Exception as e:
            self.logger.error(f"Error checking rules file: {e}")
            
    def evaluate_condition(self, condition: Dict[str, Any], current_data: Dict[str, Any]) -> bool:
        """Evaluate a single condition with enhanced operators."""
        field = condition.get('field')
        operator = condition.get('operator')
        expected_value = condition.get('value')
        
        if field not in current_data:
            return False
            
        actual_value = current_data[field]
        
        try:
            if operator == "==":
                return self._compare_values(actual_value, expected_value, "==")
            elif operator == "!=":
                return self._compare_values(actual_value, expected_value, "!=")
            elif operator == ">":
                return float(actual_value) > float(expected_value)
            elif operator == ">=":
                return float(actual_value) >= float(expected_value)
            elif operator == "<":
                return float(actual_value) < float(expected_value)
            elif operator == "<=":
                return float(actual_value) <= float(expected_value)
            elif operator == "contains":
                return str(expected_value).lower() in str(actual_value).lower()
            elif operator == "regex":
                return bool(re.search(str(expected_value), str(actual_value)))
            elif operator == "in":
                return actual_value in expected_value
            elif operator == "changed":
                return self._check_value_changed(field, condition.get('from_value'))
            elif operator == "stable_for":
                return self._check_value_stable(field, expected_value)
            else:
                self.logger.warning(f"Unknown operator: {operator}")
                return False
                
        except Exception as e:
            self.logger.debug(f"Condition evaluation error: {e}")
            return False
            
    def _compare_values(self, actual: Any, expected: Any, operator: str) -> bool:
        """Smart value comparison handling different types."""
        # Try numeric comparison first
        try:
            actual_num = float(actual)
            expected_num = float(expected)
            if operator == "==":
                return abs(actual_num - expected_num) < 0.001  # Float tolerance
            elif operator == "!=":
                return abs(actual_num - expected_num) >= 0.001
        except (ValueError, TypeError):
            pass
            
        # Fall back to string comparison
        if operator == "==":
            return str(actual).lower() == str(expected).lower()
        elif operator == "!=":
            return str(actual).lower() != str(expected).lower()
            
        return False
        
    def _check_value_changed(self, field: str, from_value: Any = None) -> bool:
        """Check if a field value has changed from a specific value."""
        if field not in self.data_history:
            return False
            
        history = self.data_history[field]
        if len(history) < 2:
            return False
            
        previous_value = history[-2]['value']
        current_value = history[-1]['value']
        
        if from_value is not None:
            # Check if changed from specific value
            return previous_value == from_value and current_value != from_value
        else:
            # Check if value changed at all
            return previous_value != current_value
            
    def _check_value_stable(self, field: str, duration: float) -> bool:
        """Check if a field has been stable for a given duration."""
        if field not in self.data_history:
            return False
            
        history = self.data_history[field]
        if not history:
            return False
            
        current_time = time.time()
        current_value = history[-1]['value']
        
        # Check if value has been the same for the required duration
        for entry in reversed(history):
            if entry['value'] != current_value:
                return False
            if current_time - entry['timestamp'] >= duration:
                return True
                
        return False
        
    def update_data_history(self, data: Dict[str, Any]):
        """Update historical data for change detection."""
        current_time = time.time()
        
        for field, value in data.items():
            if field not in self.data_history:
                self.data_history[field] = []
                
            history = self.data_history[field]
            
            # Add new entry
            history.append({
                'value': value,
                'timestamp': current_time
            })
            
            # Keep only last 100 entries per field
            if len(history) > 100:
                history.pop(0)
                
    def evaluate_rule(self, rule: SceneRule, current_data: Dict[str, Any]) -> bool:
        """Evaluate if a rule should trigger."""
        if not rule.enabled:
            return False
            
        # Check cooldown
        metrics = self.rule_metrics.get(rule.name)
        if metrics and metrics.last_executed > 0:
            time_since_last = time.time() - metrics.last_executed
            if time_since_last < rule.cooldown:
                return False
                
        # Check minimum duration since last scene change
        time_since_scene_change = time.time() - self.last_scene_change
        if time_since_scene_change < rule.min_duration:
            return False
            
        # Check maximum duration (force change if exceeded)
        if rule.max_duration > 0 and time_since_scene_change > rule.max_duration:
            return True  # Force trigger
            
        # Evaluate all conditions (AND logic)
        for condition in rule.conditions:
            if not self.evaluate_condition(condition, current_data):
                return False
                
        return True
        
    async def process_scoreboard_data(self, data: Dict[str, Any]):
        """Process new scoreboard data and execute matching rules."""
        # Hot-reload rules if changed
        self.check_rules_reload()
        
        # Add derived fields
        enhanced_data = self._enhance_data(data)
        
        # Update history for change detection
        self.update_data_history(enhanced_data)
        
        # Find matching rules
        matching_rules = []
        for rule in self.rules:
            if self.evaluate_rule(rule, enhanced_data):
                matching_rules.append(rule)
                
        if not matching_rules:
            return
            
        # Execute highest priority rule
        selected_rule = matching_rules[0]
        
        self.logger.info(f"Executing scene rule: {selected_rule.name} (priority: {selected_rule.priority})")
        
        # Track metrics
        metrics = self.rule_metrics[selected_rule.name]
        execution_start = time.time()
        
        try:
            # Execute all actions in the rule
            await self._execute_rule_actions(selected_rule, enhanced_data)
            
            # Update success metrics
            execution_time = time.time() - execution_start
            metrics.execution_count += 1
            metrics.success_count += 1
            metrics.last_executed = time.time()
            metrics.total_execution_time += execution_time
            metrics.average_execution_time = metrics.total_execution_time / metrics.execution_count
            
        except Exception as e:
            self.logger.error(f"Rule execution failed for {selected_rule.name}: {e}")
            metrics.failure_count += 1
            
    def _enhance_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add derived fields to scoreboard data."""
        enhanced = data.copy()
        
        # Add current scene info
        enhanced['current_scene'] = self.current_scene
        enhanced['time_in_current_scene'] = time.time() - self.last_scene_change
        
        # Add historical context
        enhanced['scene_history'] = self.scene_history[-5:]  # Last 5 scenes
        
        # Detect game state changes
        game_time = data.get('game_time', 0)
        if hasattr(self, '_last_game_time'):
            enhanced['game_time_changed'] = game_time != self._last_game_time
            enhanced['game_started'] = self._last_game_time == 0 and game_time > 0
            enhanced['game_ended'] = self._last_game_time > 0 and game_time == 0
        else:
            enhanced['game_time_changed'] = False
            enhanced['game_started'] = False
            enhanced['game_ended'] = False
            
        self._last_game_time = game_time
        
        return enhanced
        
    async def _execute_rule_actions(self, rule: SceneRule, data: Dict[str, Any]):
        """Execute all actions for a rule."""
        for action in rule.actions:
            action_type = ActionType(action.get('type'))
            
            if action_type in self.action_handlers:
                await self.action_handlers[action_type](action, data)
            else:
                self.logger.warning(f"Unknown action type: {action_type}")
                
    async def _handle_switch_scene(self, action: Dict[str, Any], data: Dict[str, Any]):
        """Handle scene switch action."""
        scene_name = action.get('scene')
        if not scene_name:
            return
            
        obs_scene_name = self.config.get('obs', {}).get('scenes', {}).get(scene_name, scene_name)
        
        try:
            if self.obs_client:
                await self.obs_client.set_current_scene(obs_scene_name)
                
            self._update_scene_state(scene_name)
            self.logger.info(f"Switched to scene: {obs_scene_name}")
            
        except Exception as e:
            self.logger.error(f"Failed to switch to scene {obs_scene_name}: {e}")
            
    async def _handle_breakout_sequence(self, action: Dict[str, Any], data: Dict[str, Any]):
        """Handle breakout sequence for game starts."""
        duration = action.get('duration', 2.0)
        cameras = action.get('cameras', [])
        
        self.logger.info(f"Starting breakout sequence (duration: {duration}s)")
        
        # Quick breakout scene
        await self._handle_switch_scene({'scene': 'breakout'}, data)
        
        # Optional camera cuts during breakout
        if cameras:
            camera_duration = duration / len(cameras)
            for camera in cameras:
                await self._handle_switch_scene({'scene': f'camera_{camera}'}, data)
                await asyncio.sleep(camera_duration)
        else:
            await asyncio.sleep(duration)
            
        # Return to game scene
        await self._handle_switch_scene({'scene': 'game'}, data)
        
    async def _handle_camera_rotation(self, action: Dict[str, Any], data: Dict[str, Any]):
        """Handle camera rotation sequence."""
        cameras = action.get('cameras', [])
        duration_per_camera = action.get('duration_per_camera', 5.0)
        return_scene = action.get('return_to_scene', 'game')
        
        self.logger.info(f"Starting camera rotation: {cameras}")
        
        for camera in cameras:
            await self._handle_switch_scene({'scene': f'camera_{camera}'}, data)
            await asyncio.sleep(duration_per_camera)
            
        # Return to specified scene
        await self._handle_switch_scene({'scene': return_scene}, data)
        
    async def _handle_custom_script(self, action: Dict[str, Any], data: Dict[str, Any]):
        """Handle custom script execution."""
        script = action.get('script', '')
        if not script:
            return
            
        self.logger.info("Executing custom scene script")
        
        try:
            # Safe execution environment
            safe_globals = {
                'scene_engine': self,
                'data': data,
                'logger': self.logger,
                'asyncio': asyncio,
                'time': time,
                'switch_scene': lambda scene: self._handle_switch_scene({'scene': scene}, data)
            }
            
            # Execute script
            exec(script, safe_globals)
            
        except Exception as e:
            self.logger.error(f"Custom script execution failed: {e}")
            
    async def _handle_delay(self, action: Dict[str, Any], data: Dict[str, Any]):
        """Handle delay action."""
        duration = action.get('duration', 1.0)
        await asyncio.sleep(duration)
        
    async def _handle_parallel(self, action: Dict[str, Any], data: Dict[str, Any]):
        """Handle parallel action execution."""
        sub_actions = action.get('actions', [])
        
        tasks = []
        for sub_action in sub_actions:
            action_type = ActionType(sub_action.get('type'))
            if action_type in self.action_handlers:
                task = asyncio.create_task(self.action_handlers[action_type](sub_action, data))
                tasks.append(task)
                
        await asyncio.gather(*tasks, return_exceptions=True)
        
    async def _handle_sequence(self, action: Dict[str, Any], data: Dict[str, Any]):
        """Handle sequential action execution."""
        sub_actions = action.get('actions', [])
        
        for sub_action in sub_actions:
            action_type = ActionType(sub_action.get('type'))
            if action_type in self.action_handlers:
                await self.action_handlers[action_type](sub_action, data)
                
    def _update_scene_state(self, scene_name: str):
        """Update internal scene state tracking."""
        if scene_name != self.current_scene:
            # Add to history
            self.scene_history.append({
                'scene': self.current_scene,
                'duration': time.time() - self.last_scene_change,
                'timestamp': self.last_scene_change
            })
            
            # Keep only last 20 scenes in history
            if len(self.scene_history) > 20:
                self.scene_history.pop(0)
                
            self.current_scene = scene_name
            self.last_scene_change = time.time()
            
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive scene engine metrics."""
        return {
            'current_scene': self.current_scene,
            'time_in_scene': time.time() - self.last_scene_change,
            'total_rules': len(self.rules),
            'enabled_rules': len([r for r in self.rules if r.enabled]),
            'scene_changes': len(self.scene_history),
            'rule_metrics': {name: asdict(metrics) for name, metrics in self.rule_metrics.items()},
            'recent_scene_history': self.scene_history[-10:]
        }
        
    def get_rule_status(self) -> List[Dict[str, Any]]:
        """Get status of all rules for debugging."""
        status = []
        for rule in self.rules:
            metrics = self.rule_metrics.get(rule.name)
            status.append({
                'name': rule.name,
                'priority': rule.priority,
                'enabled': rule.enabled,
                'executions': metrics.execution_count if metrics else 0,
                'last_executed': metrics.last_executed if metrics else 0,
                'success_rate': (metrics.success_count / max(1, metrics.execution_count) * 100) if metrics else 0,
                'description': rule.description
            })
        return status

# Example usage and testing functions
def create_example_rules_config():
    """Create an example rules configuration file."""
    example_config = {
        "meta": {
            "description": "ROC Paintball Tournament Scene Rules",
            "version": "1.0.1",
            "field": "Field 1",
            "tournament": "PSP World Cup 2024"
        },
        "global_settings": {
            "min_scene_duration": 2.0,
            "default_breakout_duration": 3.0,
            "camera_rotation_enabled": True,
            "custom_scripts_enabled": False
        },
        "rules": [
            {
                "name": "ultra_fast_breakout",
                "description": "Instant breakout sequence on game start",
                "priority": 250,
                "conditions": [
                    {"field": "game_started", "operator": "==", "value": True}
                ],
                "actions": [
                    {
                        "type": "sequence",
                        "actions": [
                            {"type": "switch_scene", "scene": "breakout"},
                            {"type": "delay", "duration": 1.5},
                            {"type": "switch_scene", "scene": "game"}
                        ]
                    }
                ],
                "cooldown": 15.0,
                "enabled": True
            },
            {
                "name": "dynamic_game_coverage", 
                "description": "Switch between game angles based on activity",
                "priority": 120,
                "conditions": [
                    {"field": "game_time", "operator": ">", "value": 10},
                    {"field": "current_scene", "operator": "stable_for", "value": 12}
                ],
                "actions": [
                    {
                        "type": "camera_rotation",
                        "cameras": ["dorito_side", "snake_side", "center_field"],
                        "duration_per_camera": 6,
                        "return_to_scene": "game"
                    }
                ],
                "min_duration": 18.0,
                "cooldown": 25.0,
                "enabled": True
            }
        ]
    }
    
    with open('/tmp/example_scene_rules.json', 'w') as f:
        json.dump(example_config, f, indent=4)
        
    print("Example rules created at /tmp/example_scene_rules.json")

if __name__ == "__main__":
    # Create example configuration
    create_example_rules_config()
    
    # Basic testing
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("SceneEngineTest")
    
    config = {
        'scene_rules_file': '/tmp/example_scene_rules.json',
        'obs': {
            'scenes': {
                'game': 'Game Scene',
                'break': 'Break Scene',
                'breakout': 'Breakout Scene'
            }
        }
    }
    
    # Mock OBS client
    class MockOBSClient:
        async def set_current_scene(self, scene_name):
            print(f"Mock: Switching to scene {scene_name}")
    
    engine = SceneEngineAdvanced(config, MockOBSClient(), logger)
    
    # Test with sample data
    async def test_engine():
        # Simulate game start
        await engine.process_scoreboard_data({
            'game_time': 120,
            'break_time': 0,
            'team_a_score': 0,
            'team_b_score': 0
        })
        
        # Show metrics
        print("\nEngine Metrics:")
        print(json.dumps(engine.get_metrics(), indent=2))
    
    asyncio.run(test_engine())
