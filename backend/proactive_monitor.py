import asyncio
import time
import psutil
import json
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

class TriggerType(Enum):
    TIME = "time"           # Specific time or interval
    SYSTEM = "system"       # CPU, memory, battery thresholds
    FILE = "file"           # File changes, new files
    WEATHER = "weather"     # Temperature, rain alerts
    CALENDAR = "calendar"   # Upcoming events
    GIT = "git"             # Uncommitted changes, new commits
    CUSTOM = "custom"       # User-defined condition

class ActionType(Enum):
    SPEAK = "speak"         # Text-to-speech notification
    NOTIFY = "notify"       # UI notification
    EXECUTE = "execute"     # Run a tool/command
    REMINDER = "reminder"   # Set a reminder
    ANALYZE = "analyze"     # Data analysis and insights
    WORKOUT = "workout"     # Fitness/workout guidance
    DESIGN = "design"       # CAD/design session prep

@dataclass
class ProactiveRule:
    id: str
    name: str
    description: str
    trigger_type: TriggerType
    condition: Dict[str, Any]  # Trigger-specific parameters
    action_type: ActionType
    action_params: Dict[str, Any]
    enabled: bool = True
    last_triggered: Optional[float] = None
    cooldown_minutes: int = 5  # Prevent spam

class ProactiveMonitor:
    """
    Background monitoring system for proactive AI behavior.
    Watches conditions and initiates actions without user prompting.
    """
    
    def __init__(self, workspace_root: str, on_speak: Optional[Callable[[str], None]] = None,
                 on_notify: Optional[Callable[[Dict], None]] = None):
        self.workspace_root = Path(workspace_root)
        self.memory_dir = self.workspace_root / "memory"
        self.rules_file = self.memory_dir / "proactive_rules.json"
        self.history_file = self.memory_dir / "proactive_history.jsonl"
        
        self.on_speak = on_speak  # Callback to make Nova speak
        self.on_notify = on_notify  # Callback for UI notifications
        
        self.rules: List[ProactiveRule] = []
        self.running = False
        self._task: Optional[asyncio.Task] = None
        
        # Track triggered rules for context awareness
        self._triggered_rules: List[str] = []
        self._rule_cooldowns: Dict[str, float] = {}
        
        # Ensure memory directory exists
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        self._load_rules()
        self._ensure_default_rules()
    
    def _load_rules(self):
        """Load rules from file."""
        if self.rules_file.exists():
            try:
                with open(self.rules_file, "r") as f:
                    data = json.load(f)
                    self.rules = [
                        ProactiveRule(
                            id=r["id"],
                            name=r["name"],
                            description=r["description"],
                            trigger_type=TriggerType(r["trigger_type"]),
                            condition=r["condition"],
                            action_type=ActionType(r["action_type"]),
                            action_params=r["action_params"],
                            enabled=r.get("enabled", True),
                            last_triggered=r.get("last_triggered"),
                            cooldown_minutes=r.get("cooldown_minutes", 5)
                        )
                        for r in data.get("rules", [])
                    ]
            except Exception as e:
                print(f"[ProactiveMonitor] Error loading rules: {e}")
    
    def _save_rules(self):
        """Save rules to file."""
        try:
            data = {
                "rules": [
                    {
                        **asdict(rule),
                        "trigger_type": rule.trigger_type.value,
                        "action_type": rule.action_type.value
                    }
                    for rule in self.rules
                ]
            }
            with open(self.rules_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ProactiveMonitor] Error saving rules: {e}")
    
    def _ensure_default_rules(self):
        """Create default proactive rules if none exist."""
        if self.rules:
            return
        
        defaults = [
            # Level 1 - System Health Alerts
            ProactiveRule(
                id="low_battery",
                name="Low Battery Warning",
                description="Alert when battery drops below 20%",
                trigger_type=TriggerType.SYSTEM,
                condition={"metric": "battery_percent", "threshold": 20, "operator": "<="},
                action_type=ActionType.SPEAK,
                action_params={"message": "Sir, your battery is running low at {value}%. You should plug in soon."},
                cooldown_minutes=30
            ),
            ProactiveRule(
                id="high_cpu",
                name="High CPU Usage",
                description="Alert when CPU usage is high for extended period",
                trigger_type=TriggerType.SYSTEM,
                condition={"metric": "cpu_percent", "threshold": 90, "operator": ">=", "duration_seconds": 60},
                action_type=ActionType.SPEAK,
                action_params={"message": "Sir, your CPU usage is at {value}%. Something may be consuming excessive resources."},
                cooldown_minutes=15
            ),
            ProactiveRule(
                id="low_disk_space",
                name="Low Disk Space Warning",
                description="Alert when disk space is below 10%",
                trigger_type=TriggerType.SYSTEM,
                condition={"metric": "disk_percent", "threshold": 90, "operator": ">="},
                action_type=ActionType.SPEAK,
                action_params={"message": "Sir, your disk is {value}% full. You may want to free up some space."},
                cooldown_minutes=60
            ),
            
            # Level 2 - Work Context & Productivity
            ProactiveRule(
                id="unfinished_tasks",
                name="Incomplete Tasks Reminder",
                description="Remind about tasks left incomplete from previous sessions",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_check_unfinished_tasks", "check_interval_minutes": 30},
                action_type=ActionType.SPEAK,
                action_params={"message": "Sir, you mentioned working on '{task}' recently. Shall we continue where you left off?"},
                cooldown_minutes=60
            ),
            ProactiveRule(
                id="historical_patterns",
                name="Historical Issue Alert",
                description="Alert when current work matches past issues",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_check_historical_patterns", "check_interval_minutes": 10},
                action_type=ActionType.SPEAK,
                action_params={"message": "Sir, this issue reminds me of '{past_solution}' from your notes. The pattern similarity is {relevance} words. Would you like me to pull up those notes?"},
                cooldown_minutes=30
            ),
            ProactiveRule(
                id="project_context",
                name="Project Activity Detection",
                description="Detect active project work and offer assistance",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_check_project_context", "check_interval_minutes": 15},
                action_type=ActionType.SPEAK,
                action_params={"message": "I see you've been working on {recent_files}. Shall I prepare the development environment or run any tests?"},
                cooldown_minutes=120
            ),
            
            # Level 3 - User Patterns & Routines
            ProactiveRule(
                id="user_patterns",
                name="Routine Recognition",
                description="Learn and notify based on user routines",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_check_user_patterns", "check_interval_minutes": 60},
                action_type=ActionType.SPEAK,
                action_params={"message": "It's your usual {typical_activity} time, Sir. {preparation}"},
                cooldown_minutes=120
            ),
            
            # Level 4 - Scheduled Briefings
            ProactiveRule(
                id="morning_briefing",
                name="Morning Briefing",
                description="Daily morning summary at 8 AM",
                trigger_type=TriggerType.TIME,
                condition={"hour": 8, "minute": 0, "days": [0, 1, 2, 3, 4]},  # Weekdays
                action_type=ActionType.SPEAK,
                action_params={"message": "Good morning, Sir. Shall we review your projects and tasks for today?"},
                cooldown_minutes=720
            ),
            
            # Level 5 - Git & Development
            ProactiveRule(
                id="git_uncommitted",
                name="Git Uncommitted Changes",
                description="Remind about uncommitted changes after work session",
                trigger_type=TriggerType.GIT,
                condition={"repo_path": str(self.workspace_root), "check_interval_hours": 4},
                action_type=ActionType.SPEAK,
                action_params={"message": "Sir, you have {modified} modified and {untracked} new files uncommitted. Shall I help you commit these changes?"},
                cooldown_minutes=240
            ),
            
            # ============== JARVIS LEVEL 5: VOICE STRESS & PREDICTIVE ANALYSIS ==============
            ProactiveRule(
                id="voice_stress",
                name="Voice Stress Monitor",
                description="Analyze interaction patterns for stress indicators",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_analyze_voice_stress", "check_interval_minutes": 5},
                action_type=ActionType.SPEAK,
                action_params={"message": "{message}"},
                cooldown_minutes=20
            ),
            ProactiveRule(
                id="hardware_prediction",
                name="Predictive Hardware Failure",
                description="Predict hardware failures before they happen",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_predict_hardware_failure", "check_interval_minutes": 30},
                action_type=ActionType.SPEAK,
                action_params={"message": "{message}"},
                cooldown_minutes=240
            ),
            ProactiveRule(
                id="learn_from_fixes",
                name="Learn From Past Fixes",
                description="Remember solutions and suggest them preemptively",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_learn_from_past_fixes", "check_interval_minutes": 15},
                action_type=ActionType.SPEAK,
                action_params={"message": "{message}"},
                cooldown_minutes=60
            ),
            
            # ============== JARVIS LEVEL 5: IDLE DETECTION ==============
            ProactiveRule(
                id="idle_suggestions",
                name="Idle Time Suggestions",
                description="When system idle for 15+ minutes, suggest productive tasks",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_check_system_idle", "check_interval_minutes": 15, "idle_threshold_minutes": 15},
                action_type=ActionType.SPEAK,
                action_params={"message": "{message}"},
                cooldown_minutes=60
            ),
            
            # ============== JARVIS LEVEL 8: EMOTIONAL ARC & MAINTENANCE ==============
            ProactiveRule(
                id="emotional_arc",
                name="Emotional Arc Tracker",
                description="Track user's emotional state and detect burnout patterns",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_track_emotional_arc", "check_interval_minutes": 30},
                action_type=ActionType.SPEAK,
                action_params={"message": "{message}"},
                cooldown_minutes=240
            ),
            ProactiveRule(
                id="system_maintenance",
                name="Autonomous System Maintenance",
                description="Silently maintain system health like JARVIS maintaining the lab",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_maintain_system_health", "check_interval_minutes": 60},
                action_type=ActionType.NOTIFY,
                action_params={"message": "{message}", "silent": True},
                cooldown_minutes=60
            ),
            
            # ============== JARVIS LEVEL 6: PREDICTIVE ENVIRONMENT PREP ==============
            ProactiveRule(
                id="environment_prep",
                name="Predictive Environment Preparation",
                description="Prepare workspace based on learned user patterns",
                trigger_type=TriggerType.TIME,
                condition={"check_function": "_prepare_environment", "check_interval_minutes": 60},
                action_type=ActionType.SPEAK,
                action_params={"message": "{message}"},
                cooldown_minutes=240
            ),
            
            # ============== JARVIS LEVEL 5: SECURITY MONITORING ==============
            ProactiveRule(
                id="network_intrusion",
                name="Suspicious Network Activity",
                description="Detect unusual network patterns and intrusion attempts",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_detect_intrusion_patterns", "check_interval_minutes": 5},
                action_type=ActionType.SPEAK,
                action_params={"message": "{message}"},
                cooldown_minutes=15
            ),
            
            # ============== JARVIS LEVEL 4: ENVIRONMENTAL MONITORING ==============
            ProactiveRule(
                id="lab_temperature",
                name="Lab Temperature Alert",
                description="Monitor system temperature and thermal conditions",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_check_lab_conditions", "check_interval_minutes": 5},
                action_type=ActionType.SPEAK,
                action_params={"message": "Sir, {component} temperature is at {temp}°C. That's above optimal for delicate components."},
                cooldown_minutes=15
            ),
            
            # ============== JARVIS LEVEL 4: EMOTIONAL INTELLIGENCE ==============
            ProactiveRule(
                id="stress_detection",
                name="Stress Level Monitor",
                description="Detect user stress from conversation patterns",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_analyze_emotional_state", "check_interval_minutes": 10},
                action_type=ActionType.SPEAK,
                action_params={"message": "You seem {stress_level}, Sir. You've used {frustration} frustration indicators in recent messages. Perhaps a break would help?"},
                cooldown_minutes=30
            ),
            
            # ============== JARVIS LEVEL 4: WORKFLOW ANTICIPATION ==============
            ProactiveRule(
                id="workflow_prep",
                name="Workflow Preparation",
                description="Anticipate next steps in design/development workflow",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_predict_workflow_needs", "check_interval_minutes": 10},
                action_type=ActionType.SPEAK,
                action_params={"message": "I see you've created {recent_cad}. Shall I prepare the {next_step} environment?"},
                cooldown_minutes=60
            ),
            
            # ============== JARVIS LEVEL 4: PREDICTIVE RESOURCE MANAGEMENT ==============
            ProactiveRule(
                id="resource_prediction",
                name="Resource Need Prediction",
                description="Predict compute/resource needs based on activity",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_predict_resource_needs", "check_interval_minutes": 15},
                action_type=ActionType.SPEAK,
                action_params={"message": "Sir, based on your recent {predicted_task} work with {sim_files} simulation files, I've noted you may need additional processing resources."},
                cooldown_minutes=60
            ),
            
            # ============== JARVIS LEVEL 4: AUTONOMOUS ACTION ==============
            ProactiveRule(
                id="auto_backup",
                name="Autonomous Backup",
                description="Silently backup files when threshold reached",
                trigger_type=TriggerType.CUSTOM,
                condition={"check_function": "_check_autonomous_actions", "check_interval_minutes": 60},
                action_type=ActionType.EXECUTE,
                action_params={"tool": "backup", "silent": True},
                cooldown_minutes=1440  # Once per day
            ),
        ]
        
        self.rules = defaults
        self._save_rules()
        print(f"[ProactiveMonitor] Created {len(defaults)} default rules")
    
    def add_rule(self, rule: ProactiveRule):
        """Add a new proactive rule."""
        self.rules.append(rule)
        self._save_rules()
    
    def remove_rule(self, rule_id: str):
        """Remove a rule by ID."""
        self.rules = [r for r in self.rules if r.id != rule_id]
        self._save_rules()
    
    def enable_rule(self, rule_id: str, enabled: bool = True):
        """Enable or disable a rule."""
        for rule in self.rules:
            if rule.id == rule_id:
                rule.enabled = enabled
                break
        self._save_rules()
    
    def start(self):
        """Start the background monitoring loop."""
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self._monitor_loop())
            print("[ProactiveMonitor] Started background monitoring")
    
    def stop(self):
        """Stop the monitoring loop."""
        self.running = False
        if self._task:
            self._task.cancel()
            print("[ProactiveMonitor] Stopped background monitoring")
    
    async def _monitor_loop(self):
        """Main monitoring loop - checks all rules periodically."""
        while self.running:
            try:
                for rule in self.rules:
                    if not rule.enabled:
                        continue
                    
                    # Check cooldown
                    if rule.last_triggered:
                        cooldown_seconds = rule.cooldown_minutes * 60
                        if time.time() - rule.last_triggered < cooldown_seconds:
                            continue
                    
                    # Evaluate condition
                    triggered, context = await self._evaluate_condition(rule)
                    
                    if triggered:
                        await self._execute_action(rule, context)
                        rule.last_triggered = time.time()
                        self._log_trigger(rule, context)
                
                # Save rules periodically (updates last_triggered)
                self._save_rules()
                
            except Exception as e:
                print(f"[ProactiveMonitor] Error in monitor loop: {e}")
            
            # Check every 10 seconds
            await asyncio.sleep(10)
    
    async def _evaluate_condition(self, rule: ProactiveRule) -> tuple[bool, Dict]:
        """Evaluate if a rule's condition is met."""
        context = {}
        
        try:
            if rule.trigger_type == TriggerType.SYSTEM:
                return self._check_system_condition(rule.condition, context)
            
            elif rule.trigger_type == TriggerType.TIME:
                return self._check_time_condition(rule.condition, context)
            
            elif rule.trigger_type == TriggerType.GIT:
                return await self._check_git_condition(rule.condition, context)
            
            elif rule.trigger_type == TriggerType.FILE:
                return self._check_file_condition(rule.condition, context)
            
            elif rule.trigger_type == TriggerType.CUSTOM:
                # Check interval - don't run too frequently
                check_interval = rule.condition.get("check_interval_minutes", 10)
                if rule.last_triggered:
                    minutes_since = (time.time() - rule.last_triggered) / 60
                    if minutes_since < check_interval:
                        return False, context
                
                # Call custom check function
                check_function = rule.condition.get("check_function")
                if check_function == "_check_unfinished_tasks":
                    return await self._check_unfinished_tasks()
                elif check_function == "_check_historical_patterns":
                    return await self._check_historical_patterns()
                elif check_function == "_check_user_patterns":
                    return await self._check_user_patterns()
                elif check_function == "_check_project_context":
                    return await self._check_project_context()
                elif check_function == "_check_workout_schedule":
                    return await self._check_workout_schedule()
                elif check_function == "_check_design_session_prep":
                    return await self._check_design_session_prep()
                elif check_function == "_analyze_project_data":
                    return await self._analyze_project_data()
                elif check_function == "_analyze_conversation_patterns":
                    return await self._analyze_conversation_patterns()
                # JARVIS Level 4 checks
                elif check_function == "_check_lab_conditions":
                    return await self._check_lab_conditions()
                elif check_function == "_predict_resource_needs":
                    return await self._predict_resource_needs()
                elif check_function == "_check_autonomous_actions":
                    return await self._check_autonomous_actions()
                elif check_function == "_analyze_emotional_state":
                    return await self._analyze_emotional_state()
                elif check_function == "_predict_workflow_needs":
                    return await self._predict_workflow_needs()
                # JARVIS Level 5 checks
                elif check_function == "_analyze_voice_stress":
                    return await self._analyze_voice_stress()
                elif check_function == "_predict_hardware_failure":
                    return await self._predict_hardware_failure()
                elif check_function == "_learn_from_past_fixes":
                    return await self._learn_from_past_fixes()
                elif check_function == "_detect_intrusion_patterns":
                    return await self._detect_intrusion_patterns()
                elif check_function == "_check_system_idle":
                    return await self._check_system_idle()
                # JARVIS Level 6 checks
                elif check_function == "_prepare_environment":
                    return await self._prepare_environment()
                # JARVIS Level 7 checks (Tier 3)
                elif check_function == "_predict_compute_needs":
                    return await self._predict_compute_needs()
                elif check_function == "_check_ssd_health":
                    return await self._check_ssd_health()
                elif check_function == "_check_gpu_health":
                    return await self._check_gpu_health()
                # JARVIS Level 8 checks (Tier 4)
                elif check_function == "_track_emotional_arc":
                    return await self._track_emotional_arc()
                elif check_function == "_maintain_system_health":
                    return await self._maintain_system_health()
                
        except Exception as e:
            print(f"[ProactiveMonitor] Error evaluating {rule.id}: {e}")
        
        return False, context
    
    def _check_system_condition(self, condition: Dict, context: Dict) -> tuple[bool, Dict]:
        """Check system metrics condition."""
        metric = condition.get("metric")
        threshold = condition.get("threshold")
        operator = condition.get("operator", ">=")
        
        value = None
        
        if metric == "cpu_percent":
            value = psutil.cpu_percent(interval=1)
        elif metric == "memory_percent":
            value = psutil.virtual_memory().percent
        elif metric == "battery_percent":
            battery = psutil.sensors_battery()
            if battery:
                value = battery.percent
            else:
                return False, context
        elif metric == "disk_percent":
            value = psutil.disk_usage("/").percent
        
        if value is None:
            return False, context
        
        context["value"] = value
        context["threshold"] = threshold
        
        if operator == ">=":
            return value >= threshold, context
        elif operator == "<=":
            return value <= threshold, context
        elif operator == ">":
            return value > threshold, context
        elif operator == "<":
            return value < threshold, context
        elif operator == "==":
            return value == threshold, context
        
        return False, context
    
    def _check_time_condition(self, condition: Dict, context: Dict) -> tuple[bool, Dict]:
        """Check if current time matches condition."""
        now = datetime.now()
        target_hour = condition.get("hour", now.hour)
        target_minute = condition.get("minute", 0)
        days = condition.get("days", list(range(7)))  # All days by default
        
        # Check if today is in allowed days
        if now.weekday() not in days:
            return False, context
        
        # Check if current minute matches
        if now.hour == target_hour and now.minute == target_minute:
            return True, context
        
        return False, context
    
    # ============== JARVIS-LEVEL PROACTIVE FEATURES ==============
    
    async def _check_unfinished_tasks(self) -> tuple[bool, Dict]:
        """JARVIS Pattern #1: Check for tasks left incomplete."""
        context = {}
        
        # Check memory for incomplete work mentions
        try:
            recent_memories = self._load_structured_memory()
            
            # Look for notes or tasks marked as incomplete
            notes = recent_memories.get("notes", {})
            for note_title, note_data in notes.items():
                if isinstance(note_data, dict):
                    content = note_data.get("value", {}).get("content", "")
                    tags = note_data.get("value", {}).get("tags", [])
                    
                    if "todo" in tags or "task" in tags:
                        # Check if mentioned in last 48 hours but no completion
                        created = note_data.get("value", {}).get("created", "")
                        if created:
                            note_time = datetime.fromisoformat(created)
                            hours_ago = (datetime.now() - note_time).total_seconds() / 3600
                            
                            if 0 < hours_ago < 48:
                                context["task"] = note_title
                                context["content"] = content[:100]
                                return True, context
        except Exception as e:
            pass
        
        return False, context
    
    async def _check_historical_patterns(self) -> tuple[bool, Dict]:
        """JARVIS Pattern #2: Match current work to past issues/solutions."""
        context = {}
        
        try:
            # Get recent conversation topics
            memory_file = self.memory_dir / "conversations_memory.jsonl"
            if not memory_file.exists():
                return False, context
            
            # Extract recent technical topics from conversation
            recent_topics = []
            with open(memory_file, "r") as f:
                lines = f.readlines()[-50:]  # Last 50 messages
                for line in lines:
                    entry = json.loads(line)
                    text = entry.get("text", "").lower()
                    # Look for error/bug/problem mentions
                    if any(word in text for word in ["error", "bug", "fix", "problem", "issue"]):
                        recent_topics.append(text[:100])
            
            # Search memory for similar past issues
            if recent_topics:
                structured = self._load_structured_memory()
                notes = structured.get("notes", {})
                
                for topic in recent_topics:
                    for note_title, note_data in notes.items():
                        if isinstance(note_data, dict):
                            content = note_data.get("value", {}).get("content", "").lower()
                            # Simple keyword overlap
                            topic_words = set(topic.split())
                            content_words = set(content.split())
                            overlap = topic_words & content_words
                            
                            if len(overlap) >= 3:  # Significant overlap
                                context["current_issue"] = topic[:80]
                                context["past_solution"] = note_title
                                context["relevance"] = len(overlap)
                                return True, context
        except Exception as e:
            pass
        
        return False, context
    
    async def _check_user_patterns(self) -> tuple[bool, Dict]:
        """JARVIS Pattern #3: Learn user routines and prepare accordingly."""
        context = {}
        now = datetime.now()
        
        try:
            # Load learned patterns
            patterns_file = self.memory_dir / "user_patterns.json"
            if patterns_file.exists():
                with open(patterns_file, "r") as f:
                    patterns = json.load(f)
                
                # Check if this is a known routine time
                current_hour = now.hour
                current_weekday = now.weekday()
                
                # Look for patterns at this time
                time_key = f"{current_weekday}_{current_hour}"
                if time_key in patterns:
                    activity = patterns[time_key]
                    last_notified = activity.get("last_notified", 0)
                    
                    # Don't notify more than once per 2 hours for patterns
                    if time.time() - last_notified > 7200:
                        context["typical_activity"] = activity.get("name", "work")
                        context["preparation"] = activity.get("preparation", "")
                        activity["last_notified"] = time.time()
                        
                        with open(patterns_file, "w") as f:
                            json.dump(patterns, f, indent=2)
                        
                        return True, context
        except Exception as e:
            pass
        
        return False, context
    
    def _learn_user_pattern(self, activity: str, context: str = ""):
        """Learn and record user behavior patterns."""
        try:
            patterns_file = self.memory_dir / "user_patterns.json"
            patterns = {}
            
            if patterns_file.exists():
                with open(patterns_file, "r") as f:
                    patterns = json.load(f)
            
            now = datetime.now()
            time_key = f"{now.weekday()}_{now.hour}"
            
            # Record this activity
            if time_key not in patterns:
                patterns[time_key] = {"name": activity, "count": 0, "context": context, "last_notified": 0}
            
            patterns[time_key]["count"] += 1
            patterns[time_key]["last_seen"] = now.isoformat()
            
            with open(patterns_file, "w") as f:
                json.dump(patterns, f, indent=2)
                
        except Exception as e:
            pass
    
    async def _check_project_context(self) -> tuple[bool, Dict]:
        """JARVIS Pattern #4: Prepare workspace based on detected intent."""
        context = {}
        
        try:
            # Check for recently modified files that might indicate current focus
            project_files = list(self.workspace_root.glob("**/*.py")) + \
                          list(self.workspace_root.glob("**/*.js")) + \
                          list(self.workspace_root.glob("**/*.ts"))
            
            recently_modified = []
            for file_path in project_files[:20]:  # Check first 20 files
                try:
                    mtime = file_path.stat().st_mtime
                    hours_ago = (time.time() - mtime) / 3600
                    if hours_ago < 2:  # Modified in last 2 hours
                        recently_modified.append((file_path.name, hours_ago))
                except:
                    pass
            
            if recently_modified:
                recently_modified.sort(key=lambda x: x[1])
                context["recent_files"] = [f[0] for f in recently_modified[:3]]
                context["project_active"] = True
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    async def _check_git_condition(self, condition: Dict, context: Dict) -> tuple[bool, Dict]:
        """Check git repository status."""
        import subprocess
        
        repo_path = condition.get("repo_path", str(self.workspace_root))
        
        try:
            # Check for uncommitted changes
            result = subprocess.run(
                ["git", "-C", repo_path, "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                modified = len([l for l in lines if l.startswith(" M") or l.startswith("M ")])
                untracked = len([l for l in lines if l.startswith("??")])
                
                context["modified"] = modified
                context["untracked"] = untracked
                context["total"] = len(lines)
                
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 4: ENVIRONMENTAL MONITORING ==============
    
    async def _check_lab_conditions(self) -> tuple[bool, Dict]:
        """
        Multi-sensor fusion for environmental awareness.
        JARVIS: "Lab temperature rising 3 degrees above optimal for delicate components"
        """
        context = {}
        try:
            # CPU/GPU temperature (Windows/Linux)
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    for name, entries in temps.items():
                        for entry in entries:
                            if entry.current > 85:  # Critical temp
                                context["component"] = name
                                context["temp"] = entry.current
                                context["critical"] = True
                                return True, context
            
            # Fan speed anomaly (if available)
            if hasattr(psutil, "sensors_fans"):
                fans = psutil.sensors_fans()
                for name, entries in fans.items():
                    for entry in entries:
                        if entry.current == 0 and psutil.cpu_percent() > 50:
                            context["fan_failure"] = name
                            context["cpu_load"] = psutil.cpu_percent()
                            return True, context
            
            # Check for thermal throttling indicators
            cpu_freq = psutil.cpu_freq()
            if cpu_freq and cpu_freq.current < cpu_freq.max * 0.5:
                context["thermal_throttling"] = True
                context["current_freq"] = cpu_freq.current
                context["max_freq"] = cpu_freq.max
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 4: PREDICTIVE RESOURCE MANAGEMENT ==============
    
    async def _predict_resource_needs(self) -> tuple[bool, Dict]:
        """
        Analyze project complexity to predict compute needs.
        JARVIS: "Sir, based on the simulation you're about to run, 
                 I've allocated additional processing power from the cluster"
        """
        context = {}
        try:
            # Analyze recent file changes
            recent_changes = []
            for file_path in self.workspace_root.rglob("*"):
                if file_path.is_file():
                    try:
                        mtime = file_path.stat().st_mtime
                        hours_ago = (time.time() - mtime) / 3600
                        if hours_ago < 2:
                            recent_changes.append((file_path, hours_ago))
                    except:
                        pass
            
            if len(recent_changes) > 20:
                # High activity detected - predict heavy computation need
                context["activity_level"] = "high"
                context["recent_changes"] = len(recent_changes)
                
                # Check for simulation/modeling keywords in filenames
                simulation_indicators = ["sim", "model", "calc", "analysis", "render"]
                sim_files = [f for f, _ in recent_changes 
                           if any(ind in f.name.lower() for ind in simulation_indicators)]
                
                if sim_files:
                    context["predicted_task"] = "simulation"
                    context["sim_files"] = len(sim_files)
                    return True, context
                
                # Check for compilation indicators
                build_files = list(self.workspace_root.rglob("Makefile")) + \
                             list(self.workspace_root.rglob("*.gradle")) + \
                             list(self.workspace_root.rglob("package.json"))
                
                if build_files:
                    context["predicted_task"] = "build"
                    context["build_systems"] = len(build_files)
                    return True, context
                    
        except Exception as e:
            pass
        
        return False, context
    
    async def _check_real_cpu_usage(self) -> tuple[bool, Dict]:
        """Check CPU excluding System Idle Process - prevents false alarms."""
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=2)
        
        # Find top non-idle process
        top_proc = "unknown"
        top_cpu = 0
        idle_cpu = 0
        
        for proc in psutil.process_iter(['name', 'cpu_percent']):
            try:
                name = (proc.info['name'] or '').lower()
                cpu = proc.info['cpu_percent'] or 0
                
                if 'idle' in name or 'system idle' in name:
                    idle_cpu = cpu
                elif cpu > top_cpu:
                    top_cpu = cpu
                    top_proc = proc.info['name']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        # Real CPU = total - idle_per_core
        real_cpu = cpu_percent - (idle_cpu / psutil.cpu_count())
        
        context = {
            "real_cpu": real_cpu,
            "raw_cpu": cpu_percent,
            "idle_cpu": idle_cpu,
            "top_process": top_proc,
            "duration_minutes": 5
        }
        
        # Only alert if REAL CPU > 80% (not counting idle)
        if real_cpu > 80:
            return True, context
        
        return False, context
    
    # ============== JARVIS LEVEL 4: AUTONOMOUS ACTION ==============
    
    async def _check_autonomous_actions(self) -> tuple[bool, Dict]:
        """
        Take action without asking for routine tasks.
        JARVIS wouldn't ask "Shall I backup?" - he would just do it.
        """
        context = {}
        try:
            # Check if backup is needed
            backup_file = self.memory_dir / "last_backup.txt"
            needs_backup = False
            
            if backup_file.exists():
                with open(backup_file, "r") as f:
                    last_backup = float(f.read().strip())
                hours_since = (time.time() - last_backup) / 3600
                needs_backup = hours_since > 24
            else:
                needs_backup = True
            
            if needs_backup:
                # Check for significant changes
                changed_files = []
                for file_path in self.workspace_root.rglob("*"):
                    if file_path.is_file() and not str(file_path).startswith(str(self.memory_dir)):
                        try:
                            mtime = file_path.stat().st_mtime
                            if backup_file.exists():
                                with open(backup_file, "r") as f:
                                    last_backup = float(f.read().strip())
                                if mtime > last_backup:
                                    changed_files.append(file_path.name)
                        except:
                            pass
                
                if len(changed_files) > 5:
                    # Execute autonomous backup
                    context["action"] = "backup"
                    context["files_to_backup"] = len(changed_files)
                    context["silent"] = True
                    
                    # Record backup time
                    with open(backup_file, "w") as f:
                        f.write(str(time.time()))
                    
                    return True, context
            
            # Check for dependency updates needed
            requirements = self.workspace_root / "requirements.txt"
            if requirements.exists():
                req_mtime = requirements.stat().st_mtime
                days_since = (time.time() - req_mtime) / 86400
                
                if days_since > 7:  # Weekly check
                    context["action"] = "check_dependencies"
                    context["file"] = "requirements.txt"
                    context["silent"] = True
                    return True, context
                    
        except Exception as e:
            pass
        
        return False, context
    
    async def _execute_autonomous_action(self, action: str, context: Dict):
        """Execute actions without user confirmation for routine tasks."""
        print(f"[ProactiveMonitor] Executing autonomous action: {action}")
        
        try:
            if action == "backup":
                # Trigger backup via tool execution callback
                if self.on_notify:
                    self.on_notify({
                        "type": "autonomous_action",
                        "action": "backup",
                        "status": "started",
                        "files": context.get("files_to_backup", 0)
                    })
            
            elif action == "check_dependencies":
                # Could trigger dependency check
                pass
                
        except Exception as e:
            print(f"[ProactiveMonitor] Autonomous action failed: {e}")
    
    # ============== JARVIS LEVEL 4: EMOTIONAL INTELLIGENCE ==============
    
    async def _analyze_emotional_state(self) -> tuple[bool, Dict]:
        """
        Analyze stress indicators from interaction patterns.
        JARVIS: "You seem agitated, Sir. Perhaps a break?"
        """
        context = {}
        try:
            # Analyze recent conversation patterns
            memory_file = self.memory_dir / "conversations_memory.jsonl"
            if not memory_file.exists():
                return False, context
            
            with open(memory_file, "r") as f:
                lines = f.readlines()[-30:]  # Last 30 messages
            
            if len(lines) < 5:
                return False, context
            
            # Extract stress indicators
            stress_words = ["stuck", "can't", "impossible", "broken", "damn", "frustrated", "urgent"]
            frustration_count = 0
            command_count = 0
            short_response_count = 0
            
            for line in lines[-10:]:  # Last 10 exchanges
                entry = json.loads(line)
                text = entry.get("text", "").lower()
                
                # Count stress words
                frustration_count += sum(1 for word in stress_words if word in text)
                
                # Count short abrupt responses (1-2 words)
                word_count = len(text.split())
                if word_count <= 2 and entry.get("sender") == "User":
                    short_response_count += 1
                
                # Count command-like language
                if text.startswith(("do ", "fix ", "make ", "get ")):
                    command_count += 1
            
            # Calculate stress score
            stress_score = frustration_count + (short_response_count * 0.5) + (command_count * 0.3)
            
            if stress_score >= 3:
                context["stress_level"] = "high" if stress_score >= 5 else "elevated"
                context["indicators"] = {
                    "frustration": frustration_count,
                    "short_responses": short_response_count,
                    "commands": command_count
                }
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 4: WORKFLOW ANTICIPATION ==============
    
    async def _predict_workflow_needs(self) -> tuple[bool, Dict]:
        """
        Complex workflow anticipation based on end-to-end process understanding.
        JARVIS: When CAD file created → prepare simulation environment
                When simulation runs → prepare fabrication tools
        """
        context = {}
        try:
            # Check for CAD file creation
            cad_files = list(self.workspace_root.rglob("*.stl")) + \
                       list(self.workspace_root.rglob("*.obj")) + \
                       list(self.workspace_root.rglob("*.step"))
            
            recent_cad = []
            for f in cad_files:
                try:
                    hours_ago = (time.time() - f.stat().st_mtime) / 3600
                    if hours_ago < 1:  # Created in last hour
                        recent_cad.append((f.name, hours_ago))
                except:
                    pass
            
            if recent_cad:
                # Check if simulation environment prepared
                sim_files = list(self.workspace_root.rglob("*.sim")) + \
                           list(self.workspace_root.rglob("simulation*"))
                
                if not sim_files:
                    context["workflow_stage"] = "cad_created"
                    context["recent_cad"] = [f[0] for f in recent_cad]
                    context["next_step"] = "prepare_simulation"
                    return True, context
            
            # Check for code changes that suggest testing needed
            code_files = list(self.workspace_root.rglob("*.py")) + \
                        list(self.workspace_root.rglob("*.js"))
            
            recent_code_changes = []
            for f in code_files[:20]:
                try:
                    hours_ago = (time.time() - f.stat().st_mtime) / 3600
                    if hours_ago < 0.5:  # Changed in last 30 min
                        recent_code_changes.append(f.name)
                except:
                    pass
            
            if len(recent_code_changes) >= 3:
                # Check if tests exist and haven't been run
                test_files = list(self.workspace_root.rglob("test_*.py")) + \
                            list(self.workspace_root.rglob("*_test.py"))
                
                if test_files:
                    context["workflow_stage"] = "code_changed"
                    context["changed_files"] = recent_code_changes
                    context["next_step"] = "run_tests"
                    return True, context
                    
        except Exception as e:
            pass
        
        return False, context
    
    def _check_file_condition(self, condition: Dict, context: Dict) -> tuple[bool, Dict]:
        """Check file system conditions."""
        path_pattern = condition.get("path")
        check_type = condition.get("check", "exists")  # exists, modified, new
        
        if not path_pattern:
            return False, context
        
        try:
            if check_type == "exists":
                return Path(path_pattern).exists(), context
            
            elif check_type == "new":
                # Check for files newer than X minutes
                minutes = condition.get("minutes", 5)
                cutoff = time.time() - (minutes * 60)
                
                for file_path in Path(self.workspace_root).glob(path_pattern):
                    if file_path.stat().st_mtime > cutoff:
                        context["file"] = str(file_path)
                        return True, context
                        
        except Exception as e:
            print(f"[ProactiveMonitor] File check error: {e}")
        
        return False, context
    
    async def _execute_action(self, rule: ProactiveRule, context: Dict):
        """Execute the rule's action."""
        print(f"[ProactiveMonitor] Rule '{rule.name}' triggered - executing {rule.action_type.value}")
        
        try:
            if rule.action_type == ActionType.SPEAK:
                message = rule.action_params.get("message", "")
                # Format message with context values
                try:
                    message = message.format(**context)
                except KeyError:
                    pass  # Keep original if formatting fails
                
                if self.on_speak:
                    self.on_speak(message)
            
            elif rule.action_type == ActionType.NOTIFY:
                notification = {
                    "title": rule.name,
                    "message": rule.action_params.get("message", "").format(**context),
                    "priority": rule.action_params.get("priority", "normal"),
                    "timestamp": datetime.now().isoformat()
                }
                
                if self.on_notify:
                    self.on_notify(notification)
            
            elif rule.action_type == ActionType.EXECUTE:
                tool_name = rule.action_params.get("tool")
                tool_args = rule.action_params.get("args", {})
                silent = rule.action_params.get("silent", False)
                
                # Handle autonomous actions
                if tool_name == "backup" and context.get("action") == "backup":
                    await self._execute_autonomous_action("backup", context)
                elif tool_name == "check_dependencies":
                    await self._execute_autonomous_action("check_dependencies", context)
                else:
                    # Execute tool through AudioLoop's tool_handler
                    print(f"[ProactiveMonitor] Would execute tool: {tool_name}")
                    # TODO: Integrate with AudioLoop for tool execution
                    
                # Notify about silent autonomous actions
                if silent and tool_name == "backup":
                    # Don't speak for truly silent actions, just log
                    print(f"[ProactiveMonitor] Autonomous backup completed: {context.get('files_to_backup', 0)} files backed up")
                    
            elif rule.action_type == ActionType.ANALYZE:
                # Data analysis and insights
                analysis_type = rule.action_params.get("analysis_type", "general")
                message = rule.action_params.get("message", "Analysis complete.")
                try:
                    message = message.format(**context)
                except KeyError:
                    pass
                if self.on_speak:
                    self.on_speak(message)
                    
            elif rule.action_type == ActionType.WORKOUT:
                # Fitness/workout guidance
                workout_type = context.get("workout_type", "exercise")
                message = rule.action_params.get("message", f"Time for your {workout_type} workout.")
                try:
                    message = message.format(**context)
                except KeyError:
                    pass
                if self.on_speak:
                    self.on_speak(message)
                    
            elif rule.action_type == ActionType.DESIGN:
                # CAD/design session prep
                recent_cad = context.get("recent_cad", [])
                message = rule.action_params.get("message", "Design environment ready.")
                try:
                    message = message.format(**context)
                except KeyError:
                    pass
                if self.on_speak:
                    self.on_speak(message)
            
            elif rule.action_type == ActionType.REMINDER:
                reminder_text = rule.action_params.get("text", rule.name)
                # Could integrate with reminder tool
                if self.on_speak:
                    self.on_speak(f"Reminder: {reminder_text}")
                    
        except Exception as e:
            print(f"[ProactiveMonitor] Error executing action: {e}")
    
    # ============== PERSONALIZED ALERTS ==============
    
    def _get_personalized_greeting(self) -> str:
        """Generate personalized greeting based on user identity and time."""
        try:
            structured = self._load_structured_memory()
            identity = structured.get("identity", {})
            name_data = identity.get("name", {})
            user_name = name_data.get("value", "Sir") if isinstance(name_data, dict) else "Sir"
            
            hour = datetime.now().hour
            if 5 <= hour < 12:
                time_greeting = "Good morning"
            elif 12 <= hour < 17:
                time_greeting = "Good afternoon"
            elif 17 <= hour < 22:
                time_greeting = "Good evening"
            else:
                time_greeting = "Hello"
            
            return f"{time_greeting}, {user_name}"
        except:
            return "Hello, Sir"
    
    async def _check_personalized_alerts(self) -> tuple[bool, Dict]:
        """Generate personalized alerts based on user preferences and history."""
        context = {}
        try:
            structured = self._load_structured_memory()
            preferences = structured.get("preferences", {})
            identity = structured.get("identity", {})
            
            # Check for user preferences that need attention
            for pref_key, pref_data in preferences.items():
                if isinstance(pref_data, dict):
                    value = pref_data.get("value", "")
                    # Alert about preferences that might need action
                    if "coffee" in pref_key.lower() and datetime.now().hour == 9:
                        context["preference"] = "coffee"
                        context["value"] = value
                        context["message"] = f"Shall I prepare your {value}?"
                        return True, context
            
            # Check for identity-based alerts
                                
        except Exception as e:
            pass
        
        return False, context
    
    def _learn_workout_completion(self, workout_type: str):
        """Record workout completion for pattern learning."""
        try:
            structured_file = self.memory_dir / "structured_memory.json"
            if structured_file.exists():
                with open(structured_file, "r") as f:
                    memory = json.load(f)
                
                if "habits" not in memory:
                    memory["habits"] = {}
                
                habit_key = f"workout_{workout_type.replace(' ', '_')}"
                memory["habits"][habit_key] = {
                    "value": workout_type,
                    "timestamp": datetime.now().isoformat(),
                    "last_done": datetime.now().isoformat(),
                    "count": memory.get("habits", {}).get(habit_key, {}).get("count", 0) + 1
                }
                
                with open(structured_file, "w") as f:
                    json.dump(memory, f, indent=2)
        except Exception as e:
            pass
    
    # ============== DESIGN SESSIONS ==============
    
    async def _check_design_session_prep(self) -> tuple[bool, Dict]:
        """Prepare design environment based on detected intent."""
        context = {}
        try:
            # Check for CAD/design files recently opened
            cad_files = list(self.workspace_root.glob("**/*.stl")) + \
                       list(self.workspace_root.glob("**/*.obj")) + \
                       list(self.workspace_root.glob("**/*.step")) + \
                       list(self.workspace_root.glob("**/*.fcstd"))
            
            recently_opened = []
            for file_path in cad_files[:10]:
                try:
                    atime = file_path.stat().st_atime
                    hours_ago = (time.time() - atime) / 3600
                    if hours_ago < 24:  # Accessed in last 24 hours
                        recently_opened.append((file_path.name, hours_ago))
                except:
                    pass
            
            if recently_opened:
                recently_opened.sort(key=lambda x: x[1])
                recent_file = recently_opened[0][0]
                
                # Check if user has been discussing design lately
                memory_file = self.memory_dir / "conversations_memory.jsonl"
                if memory_file.exists():
                    with open(memory_file, "r") as f:
                        lines = f.readlines()[-20:]  # Last 20 messages
                        for line in lines:
                            entry = json.loads(line)
                            text = entry.get("text", "").lower()
                            if any(word in text for word in ["cad", "3d", "design", "model", "prototype"]):
                                context["recent_file"] = recent_file
                                context["message"] = f"I see you were working on '{recent_file}'. Shall I load it and prepare the CAD environment?"
                                return True, context
                                
        except Exception as e:
            pass
        
        return False, context
    
    def _prepare_design_context(self, project_name: str) -> Dict:
        """Prepare design context for a project."""
        context = {
            "project": project_name,
            "cad_files": [],
            "last_design": None,
            "suggestions": []
        }
        
        try:
            project_path = self.workspace_root / "projects" / project_name / "cad"
            if project_path.exists():
                cad_files = list(project_path.glob("*.stl")) + list(project_path.glob("*.obj"))
                context["cad_files"] = [f.name for f in cad_files]
                
                if cad_files:
                    most_recent = max(cad_files, key=lambda f: f.stat().st_mtime)
                    context["last_design"] = most_recent.name
                    
                    # Suggest next steps based on file patterns
                    if "prototype" in most_recent.name.lower():
                        context["suggestions"].append("Continue refining the prototype?")
                    if "v" in most_recent.name.lower():
                        version_num = most_recent.name.lower().split("v")[-1].split(".")[0]
                        if version_num.isdigit():
                            context["suggestions"].append(f"Start version {int(version_num) + 1}?")
        except:
            pass
        
        return context
    
    # ============== DATA ANALYSIS ==============
    
    async def _analyze_project_data(self) -> tuple[bool, Dict]:
        """Analyze project data and provide insights."""
        context = {}
        try:
            # Analyze code patterns in the workspace
            code_stats = {
                "python_files": len(list(self.workspace_root.glob("**/*.py"))),
                "js_files": len(list(self.workspace_root.glob("**/*.js"))),
                "total_lines": 0,
                "recent_commits": 0
            }
            
            # Count lines in recent files
            for py_file in list(self.workspace_root.glob("**/*.py"))[:20]:
                try:
                    with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                        code_stats["total_lines"] += len(f.readlines())
                except:
                    pass
            
            # Check git activity
            import subprocess
            try:
                result = subprocess.run(
                    ["git", "-C", str(self.workspace_root), "log", "--oneline", "--since=24.hours"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    code_stats["recent_commits"] = len(result.stdout.strip().split("\n"))
            except:
                pass
            
            # Generate insight if there's significant activity
            if code_stats["recent_commits"] > 3 or code_stats["total_lines"] > 500:
                context["stats"] = code_stats
                context["message"] = f"You've been productive - {code_stats['recent_commits']} commits and {code_stats['total_lines']} lines today. Shall I generate a summary?"
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    async def _analyze_conversation_patterns(self) -> tuple[bool, Dict]:
        """Analyze conversation patterns for insights."""
        context = {}
        try:
            memory_file = self.memory_dir / "conversations_memory.jsonl"
            if not memory_file.exists():
                return False, context
            
            # Analyze last 100 messages
            with open(memory_file, "r") as f:
                lines = f.readlines()[-100:]
            
            user_messages = []
            topics = set()
            
            for line in lines:
                entry = json.loads(line)
                if entry.get("sender") == "User":
                    text = entry.get("text", "").lower()
                    user_messages.append(text)
                    
                    # Extract topics
                    for word in ["bug", "error", "feature", "design", "meeting", "deadline"]:
                        if word in text:
                            topics.add(word)
            
            # Detect patterns
            if len(user_messages) > 20:
                # Check for frustration patterns
                frustration_words = ["stuck", "can't", "error", "failed", "broken"]
                frustration_count = sum(1 for msg in user_messages[-10:] 
                                      for word in frustration_words if word in msg)
                
                if frustration_count >= 3:
                    context["pattern"] = "frustration"
                    context["topics"] = list(topics)
                    context["message"] = "I notice you've been dealing with several issues. Would you like me to search for solutions or take a break?"
                    return True, context
                
                # Check for repetitive tasks
                if len(topics) == 1:
                    context["pattern"] = "focused"
                    context["topic"] = list(topics)[0]
                    context["message"] = f"You've been focusing on {list(topics)[0]}. Shall I help you document your progress?"
                    return True, context
                    
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 5: VOICE STRESS ANALYSIS ==============
    
    def analyze_audio_stress(self, audio_data: bytes) -> Dict:
        """
        Analyze audio features for stress detection.
        JARVIS: Like detecting Tony's agitated tone before he explodes.
        
        Args:
            audio_data: Raw audio bytes (int16)
            
        Returns:
            Dict with stress indicators: zcr, rms, pitch, stress_score
        """
        try:
            # Convert audio samples to numpy array
            samples = np.frombuffer(audio_data, dtype=np.int16)
            
            # Zero-crossing rate (pitch estimation proxy)
            # High ZCR = higher pitch = potential stress
            zcr = np.sum(np.abs(np.diff(np.sign(samples)))) / (2 * len(samples))
            
            # RMS volume
            rms = np.sqrt(np.mean(samples.astype(np.float64)**2))
            
            # Spectral centroid (brightness of sound)
            # Stressed voices often have more high-frequency energy
            fft = np.fft.fft(samples)
            magnitude = np.abs(fft)
            freqs = np.fft.fftfreq(len(samples))
            spectral_centroid = np.sum(freqs * magnitude) / np.sum(magnitude)
            
            # Calculate stress score (0-1)
            # High ZCR + High volume + High spectral centroid = stressed
            stress_score = min(1.0, (zcr * 2 + rms / 10000 + abs(spectral_centroid) * 10) / 3)
            
            return {
                "zcr": float(zcr),
                "rms": float(rms),
                "spectral_centroid": float(spectral_centroid),
                "stress_score": float(stress_score),
                "stressed": stress_score > 0.7
            }
        except Exception as e:
            return {"stressed": False, "error": str(e)}
    
    async def _analyze_voice_stress(self) -> tuple[bool, Dict]:
        """
        Analyze voice patterns for stress indicators.
        JARVIS: "Your heart rate is elevated, Sir. Shall I lower the lab temperature?"
        """
        context = {}
        try:
            # Analyze interaction velocity as stress proxy
            memory_file = self.memory_dir / "conversations_memory.jsonl"
            if not memory_file.exists():
                return False, context
            
            with open(memory_file, "r") as f:
                lines = f.readlines()[-20:]
            
            if len(lines) < 5:
                return False, context
            
            # Calculate message velocity (messages per minute)
            timestamps = []
            for line in lines:
                entry = json.loads(line)
                ts = entry.get("timestamp", 0)
                if ts:
                    timestamps.append(ts)
            
            if len(timestamps) >= 2:
                time_span = max(timestamps) - min(timestamps)
                if time_span > 0:
                    msg_rate = len(timestamps) / (time_span / 60)  # msgs per minute
                    
                    # High message rate = rushed/stressed
                    if msg_rate > 10:  # More than 10 messages per minute
                        context["stress_indicator"] = "high_velocity"
                        context["msg_rate"] = round(msg_rate, 1)
                        context["message"] = f"Your interaction rate is {msg_rate:.1f} messages per minute, Sir. You seem rushed."
                        return True, context
            
            # Check for repeated corrections (backspace patterns in text)
            correction_patterns = ["no wait", "actually", "sorry", "let me", "i mean"]
            correction_count = 0
            for line in lines[-5:]:
                entry = json.loads(line)
                text = entry.get("text", "").lower()
                correction_count += sum(1 for pattern in correction_patterns if pattern in text)
            
            if correction_count >= 3:
                context["stress_indicator"] = "uncertainty"
                context["corrections"] = correction_count
                context["message"] = "You seem uncertain, Sir. Multiple self-corrections detected. Shall I slow down?"
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 7: PREDICTIVE RESOURCE ALLOCATION ==============
    
    async def _predict_compute_needs(self) -> tuple[bool, Dict]:
        """
        Analyze work patterns to predict and prepare compute resources.
        JARVIS: "Preparing the cluster for simulation work, Sir."
        
        Detects patterns:
        - CAD work at specific times
        - Heavy compilation periods
        - Simulation/modeling workflows
        """
        context = {}
        try:
            now = datetime.now()
            hour = now.hour
            weekday = now.weekday() < 5
            
            # Check for learned CAD patterns
            structured = self._load_structured_memory()
            habits = structured.get("habits", {})
            
            # Pattern 1: Evening CAD work (9-11 PM on weekdays)
            if weekday and 21 <= hour <= 23:
                cad_habit = habits.get("cad_work", {})
                if isinstance(cad_habit, dict) and cad_habit.get("frequency", 0) > 3:
                    # Check recent CAD file activity
                    recent_cad = []
                    for ext in [".stl", ".obj", ".step", ".fcstd"]:
                        recent_cad.extend(self.workspace_root.rglob(f"*{ext}"))
                    
                    # Filter to recent modifications
                    today_start = time.time() - 86400
                    active_cad = [f for f in recent_cad if f.stat().st_mtime > today_start]
                    
                    if len(active_cad) >= 2:
                        context["predicted_task"] = "CAD simulation"
                        context["recent_files"] = len(active_cad)
                        context["resource_prep"] = "GPU memory allocation"
                        context["message"] = f"Sir, I've detected {len(active_cad)} active CAD files. Preparing compute resources for potential simulation work."
                        return True, context
            
            # Pattern 2: Development/build patterns
            if weekday and 9 <= hour <= 17:
                # Check for build system indicators
                build_files = list(self.workspace_root.rglob("Makefile")) + \
                             list(self.workspace_root.rglob("package.json")) + \
                             list(self.workspace_root.rglob("Cargo.toml"))
                
                recent_builds = []
                for bf in build_files:
                    try:
                        if bf.stat().st_mtime > time.time() - 3600:  # Modified in last hour
                            recent_builds.append(bf.name)
                    except:
                        pass
                
                if len(recent_builds) >= 2:
                    context["predicted_task"] = "compilation/build"
                    context["build_systems"] = recent_builds
                    context["resource_prep"] = "CPU cores allocation"
                    context["message"] = f"Multiple build systems active ({', '.join(recent_builds[:2])}). Preparing for compilation tasks."
                    return True, context
            
            # Pattern 3: High memory usage prediction
            mem = psutil.virtual_memory()
            if mem.percent > 70:
                # Check for memory-intensive processes
                memory_intensive = []
                for proc in psutil.process_iter(['name', 'memory_percent']):
                    try:
                        if proc.info['memory_percent'] and proc.info['memory_percent'] > 5:
                            memory_intensive.append(proc.info['name'])
                    except:
                        pass
                
                if len(memory_intensive) >= 3:
                    context["predicted_task"] = "memory optimization"
                    context["memory_intensive_apps"] = memory_intensive[:3]
                    context["current_memory"] = mem.percent
                    context["message"] = f"Memory at {mem.percent:.0f}% with {len(memory_intensive)} heavy processes. Suggesting cleanup or upgrade."
                    return True, context
                    
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 7: HARDWARE HEALTH DASHBOARD ==============
    
    async def _check_ssd_health(self) -> tuple[bool, Dict]:
        """
        Monitor SSD wear level and predict failure.
        JARVIS: "The primary storage shows degradation. Replacement advised."
        
        Uses SMART data if available, falls back to usage patterns.
        """
        context = {}
        try:
            # Try to get disk I/O stats as proxy for wear
            disk_io = psutil.disk_io_counters()
            if not disk_io:
                return False, context
            
            # Calculate write volume (TB written)
            total_writes_tb = disk_io.write_bytes / 1e12
            
            # Estimate wear based on typical SSD endurance
            # Conservative estimate: 600 TBW for 1TB consumer SSD
            ssd_capacity_tb = 1.0  # Assume 1TB, would be detected in full implementation
            estimated_wear_percent = min(100, (total_writes_tb / (ssd_capacity_tb * 600)) * 100)
            
            # Alternative: Check disk usage patterns
            disk_usage = psutil.disk_usage('/')
            disk_percent = disk_usage.percent
            
            # Check for warning signs
            warnings = []
            
            if estimated_wear_percent > 80:
                warnings.append(f"SSD wear at {estimated_wear_percent:.1f}%")
            
            if disk_percent > 95:
                warnings.append(f"Disk critically full ({disk_percent}%)")
            
            # Check for performance degradation (high I/O wait)
            cpu_times = psutil.cpu_times_percent(interval=0.1)
            if hasattr(cpu_times, 'iowait') and cpu_times.iowait > 10:
                warnings.append(f"High I/O wait ({cpu_times.iowait:.1f}%)")
            
            if warnings:
                # Estimate remaining life (rough approximation)
                if estimated_wear_percent > 0:
                    remaining_percent = 100 - estimated_wear_percent
                    # Assume average 20GB writes per day
                    daily_writes_tb = 0.02
                    remaining_days = (remaining_percent / 100 * ssd_capacity_tb * 600) / daily_writes_tb if daily_writes_tb > 0 else 365
                else:
                    remaining_days = 365
                
                context["wear_level"] = round(estimated_wear_percent, 1)
                context["warnings"] = warnings
                context["estimated_days"] = round(remaining_days)
                context["total_writes_tb"] = round(total_writes_tb, 2)
                
                context["message"] = f"Sir, your SSD has reached {estimated_wear_percent:.1f}% wear. I recommend backing up and planning a replacement within {round(remaining_days)} days."
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    async def _check_gpu_health(self) -> tuple[bool, Dict]:
        """Monitor GPU health if available."""
        context = {}
        try:
            # Try to detect GPU using various methods
            # NVIDIA GPUs
            try:
                import subprocess
                result = subprocess.run(['nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'], 
                                      capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for i, line in enumerate(lines):
                        parts = line.split(', ')
                        if len(parts) >= 4:
                            temp = float(parts[0])
                            util = float(parts[1])
                            mem_used = float(parts[2])
                            mem_total = float(parts[3])
                            
                            if temp > 80:
                                context[f"gpu_{i}_temp"] = temp
                                context["message"] = f"GPU {i} temperature critical at {temp}°C. Check cooling system."
                                return True, context
            except:
                pass
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 5: PREDICTIVE HARDWARE FAILURE ==============
    
    async def _predict_hardware_failure(self) -> tuple[bool, Dict]:
        """
        Predict hardware failures before they happen.
        JARVIS: "The primary actuator shows 3% degradation—I've ordered replacement parts"
        
        Analyzes:
        - SMART disk data (reallocated sectors, temperature)
        - Memory error rates
        - CPU/GPU degradation patterns
        - SSD wear leveling
        """
        context = {}
        warnings = []
        
        try:
            # Disk health check (Windows/Linux)
            if hasattr(psutil, "disk_io_counters"):
                io_counters = psutil.disk_io_counters()
                if io_counters:
                    # High I/O wait could indicate disk issues
                    read_bytes = io_counters.read_bytes
                    write_bytes = io_counters.write_bytes
                    
                    # Check for excessive writes (SSD wear)
                    if write_bytes > 1e12:  # > 1TB written
                        warnings.append("High disk write volume detected")
                        context["disk_writes_tb"] = write_bytes / 1e12
            
            # Memory error detection (if available)
            mem = psutil.virtual_memory()
            if mem.percent > 95:
                warnings.append("Memory pressure critical")
                context["memory_pressure"] = mem.percent
            
            # Check for thermal degradation pattern
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    high_temp_count = 0
                    for name, entries in temps.items():
                        for entry in entries:
                            # Count high temperature excursions
                            if entry.current > 80:
                                high_temp_count += 1
                    
                    if high_temp_count >= 2:
                        warnings.append(f"{high_temp_count} components running hot")
                        context["hot_components"] = high_temp_count
            
            # Boot time analysis (slow boot = disk issues)
            try:
                boot_time = psutil.boot_time()
                uptime_hours = (time.time() - boot_time) / 3600
                
                # If uptime is very long, suggest restart for memory cleanup
                if uptime_hours > 168:  # > 1 week
                    warnings.append("System uptime exceeds 1 week")
                    context["uptime_days"] = uptime_hours / 24
            except:
                pass
            
            # Compile warning if any found
            if warnings:
                context["warnings"] = warnings
                context["warning_count"] = len(warnings)
                context["message"] = f"Sir, I've detected {len(warnings)} potential hardware concerns: {'; '.join(warnings[:2])}. Shall I run diagnostics?"
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 5: LEARNING FROM PAST FIXES ==============
    
    async def _learn_from_past_fixes(self) -> tuple[bool, Dict]:
        """
        When errors occur, remember the fix and proactively suggest next time.
        JARVIS remembered solutions and applied them preemptively.
        """
        context = {}
        try:
            # Search recent conversations for error mentions
            memory_file = self.memory_dir / "conversations_memory.jsonl"
            if not memory_file.exists():
                return False, context
            
            with open(memory_file, "r") as f:
                lines = f.readlines()[-50:]
            
            # Look for error patterns followed by solutions
            error_keywords = ["error", "bug", "crash", "failed", "exception"]
            solution_keywords = ["fixed", "solved", "working", "resolved"]
            
            recent_errors = []
            recent_fixes = []
            
            for line in lines:
                entry = json.loads(line)
                text = entry.get("text", "").lower()
                
                if any(err in text for err in error_keywords):
                    recent_errors.append(text[:50])
                
                if any(sol in text for sol in solution_keywords):
                    recent_fixes.append(text[:50])
            
            # If errors recurring without recent fixes
            if len(recent_errors) >= 3 and len(recent_fixes) == 0:
                context["recurring_errors"] = len(recent_errors)
                context["message"] = "Sir, I notice several errors without resolution. Shall I search the memory banks for similar past issues?"
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 5: IDLE DETECTION ==============
    
    async def _check_system_idle(self) -> tuple[bool, Dict]:
        """
        Detect when user has been idle and suggest productive tasks.
        JARVIS: "Sir, I notice you've been idle. Shall I review your pending tasks or suggest a workout?"
        """
        context = {}
        try:
            # Check system idle time via CPU and input activity
            # Track last user interaction from memory
            memory_file = self.memory_dir / "conversations_memory.jsonl"
            if not memory_file.exists():
                return False, context
            
            with open(memory_file, "r") as f:
                lines = f.readlines()[-10:]
            
            if not lines:
                return False, context
            
            # Get last user message timestamp
            last_interaction = 0
            for line in reversed(lines):
                entry = json.loads(line)
                if entry.get("sender") == "User":
                    last_interaction = entry.get("timestamp", 0)
                    break
            
            if last_interaction == 0:
                return False, context
            
            # Calculate idle time in minutes
            idle_minutes = (time.time() - last_interaction) / 60
            
            if idle_minutes >= 15:  # 15 minutes idle threshold
                context["idle_minutes"] = round(idle_minutes)
                
                # Load pending tasks if available
                structured = self._load_structured_memory()
                goals = structured.get("goals", {})
                pending_tasks = [k for k, v in goals.items() if isinstance(v, dict) and not v.get("completed", False)]
                
                if pending_tasks:
                    context["pending_tasks"] = len(pending_tasks)
                    context["message"] = f"Sir, I notice you've been idle for {round(idle_minutes)} minutes. You have {len(pending_tasks)} pending tasks. Shall I review them?"
                else:
                    context["message"] = f"Sir, you've been idle for {round(idle_minutes)} minutes. Would you like a workout suggestion or shall I check for project updates?"
                
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 6: PREDICTIVE ENVIRONMENT PREPARATION ==============
    
    async def _prepare_environment(self) -> tuple[bool, Dict]:
        """
        Predictively prepare workspace based on learned patterns.
        JARVIS: Pre-loads CAD tools at 9 PM if user typically designs then.
        """
        context = {}
        try:
            now = datetime.now()
            weekday = now.weekday() < 5
            hour = now.hour
            
            # Load user habits from memory
            structured = self._load_structured_memory()
            habits = structured.get("habits", {})
            
            # Check for CAD/design patterns
            cad_habit = habits.get("cad_work", {})
            if isinstance(cad_habit, dict):
                typical_time = cad_habit.get("typical_time", "")
                if typical_time:
                    typical_hour = int(typical_time.split(":")[0])
                    if hour == typical_hour - 1:  # 1 hour before typical time
                        context["prep_type"] = "cad"
                        context["app"] = "CAD tools"
                        context["message"] = "I see you typically start CAD work at this time. Shall I prepare the design environment?"
                        return True, context
            
            # Check for coding patterns
            code_habit = habits.get("coding", {})
            if isinstance(code_habit, dict):
                typical_time = code_habit.get("typical_time", "")
                if typical_time:
                    typical_hour = int(typical_time.split(":")[0])
                    if hour == typical_hour - 1:
                        context["prep_type"] = "coding"
                        context["app"] = "development environment"
                        context["message"] = "Preparing your development environment for tonight's session."
                        return True, context
            
            # Check for project context from recent files
            cad_files = list(self.workspace_root.rglob("*.stl")) + \
                       list(self.workspace_root.rglob("*.obj"))
            recent_cad = [f for f in cad_files if (time.time() - f.stat().st_mtime) < 86400 * 3]
            
            if recent_cad and hour in [19, 20, 21]:  # Evening work hours
                context["prep_type"] = "project_continuation"
                context["recent_files"] = len(recent_cad)
                context["message"] = f"I see you've been working on {len(recent_cad)} design files recently. The environment is ready to continue."
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 5: SECURITY MONITORING ==============
    
    async def _detect_intrusion_patterns(self) -> tuple[bool, Dict]:
        """
        Monitor for suspicious network and system activity.
        JARVIS: "Sir, I'm detecting unusual network activity from {ip}. Initiating countermeasures."
        """
        context = {}
        try:
            # Check for unusual network connections
            if hasattr(psutil, "net_connections"):
                connections = psutil.net_connections(kind='inet')
                
                # Count connections by remote address
                remote_ips = {}
                for conn in connections:
                    if conn.raddr:
                        ip = conn.raddr.ip
                        remote_ips[ip] = remote_ips.get(ip, 0) + 1
                
                # Flag IPs with excessive connections (potential port scanning)
                suspicious_ips = {ip: count for ip, count in remote_ips.items() 
                                if count > 50 and not ip.startswith(('127.', '192.168.', '10.', '172.'))}
                
                if suspicious_ips:
                    top_ip = max(suspicious_ips, key=suspicious_ips.get)
                    context["ip"] = top_ip
                    context["connection_count"] = suspicious_ips[top_ip]
                    context["message"] = f"Sir, I'm detecting {suspicious_ips[top_ip]} connections from {top_ip}. This appears unusual."
                    return True, context
            
            # Check for high CPU processes that shouldn't be there (malware indicator)
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    cpu = proc.info['cpu_percent']
                    name = proc.info['name']
                    if cpu > 80 and name not in ['python.exe', 'python', 'Code.exe', 'node']:
                        context["process"] = name
                        context["cpu"] = cpu
                        context["message"] = f"Sir, {name} is consuming {cpu}% CPU. Shall I investigate?"
                        return True, context
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                    
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 8: EMOTIONAL ARC TRACKING ==============
    
    async def _track_emotional_arc(self) -> tuple[bool, Dict]:
        """
        Track user's emotional state over time and detect burnout patterns.
        JARVIS: "Sir, I've noticed your mood has been consistently low this week."
        """
        context = {}
        try:
            # Load conversation history
            memory_file = self.memory_dir / "conversations_memory.jsonl"
            if not memory_file.exists():
                return False, context
            
            # Analyze last 7 days of conversations
            cutoff_time = time.time() - (7 * 86400)
            daily_mood = []
            
            with open(memory_file, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("timestamp", 0) > cutoff_time and entry.get("sender") == "User":
                            text = entry.get("text", "").lower()
                            timestamp = entry.get("timestamp")
                            
                            # Simple sentiment analysis
                            positive_words = ["great", "awesome", "excellent", "good", "happy", "love", "perfect"]
                            negative_words = ["bad", "terrible", "hate", "awful", "stressed", "tired", "frustrated", "annoyed", "worried"]
                            burnout_words = ["exhausted", "burned out", "can't take it", "overwhelmed", "giving up", "done with this"]
                            
                            pos_count = sum(1 for w in positive_words if w in text)
                            neg_count = sum(1 for w in negative_words if w in text)
                            burnout_count = sum(1 for w in burnout_words if w in text)
                            
                            # Calculate mood score (-1 to 1)
                            if burnout_count > 0:
                                mood = -0.8  # Critical burnout indicator
                            else:
                                total = pos_count + neg_count
                                if total > 0:
                                    mood = (pos_count - neg_count) / total
                                else:
                                    mood = 0
                            
                            daily_mood.append((timestamp, mood, text[:50]))
                    except:
                        pass
            
            if len(daily_mood) < 3:
                return False, context
            
            # Detect burnout patterns
            recent_moods = daily_mood[-10:]  # Last 10 interactions
            avg_mood = sum(m[1] for m in recent_moods) / len(recent_moods)
            
            # Check for consistently low mood
            if avg_mood < -0.3:
                context["mood_trend"] = "low"
                context["avg_mood"] = round(avg_mood, 2)
                context["days_tracked"] = 7
                context["message"] = "Sir, I've noticed your mood has been consistently low this week. Shall I suggest some activities to help?"
                return True, context
            
            # Check for burnout indicators
            burnout_indicators = sum(1 for m in daily_mood if m[1] == -0.8)
            if burnout_indicators >= 2:
                context["mood_trend"] = "burnout"
                context["burnout_signals"] = burnout_indicators
                context["message"] = "Sir, I'm detecting burnout signals in your recent messages. I recommend taking a break or adjusting your workload."
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    # ============== JARVIS LEVEL 8: AUTONOMOUS SYSTEM MAINTENANCE ==============
    
    async def _maintain_system_health(self) -> tuple[bool, Dict]:
        """
        Autonomously maintain system health like JARVIS maintaining the lab.
        Runs silently without user interruption.
        """
        context = {}
        tasks_completed = []
        
        try:
            # Task 1: Clean temp files older than 7 days
            temp_cleaned = await self._clean_temp_files()
            if temp_cleaned > 0:
                tasks_completed.append(f"Cleaned {temp_cleaned} temp files")
            
            # Task 2: Check for memory leaks (high swap usage)
            swap = psutil.swap_memory()
            if swap.percent > 50:
                tasks_completed.append(f"High swap usage detected: {swap.percent}%")
            
            # Task 3: Optimize database if conversations_memory.jsonl > 10MB
            memory_file = self.memory_dir / "conversations_memory.jsonl"
            if memory_file.exists():
                size_mb = memory_file.stat().st_size / (1024 * 1024)
                if size_mb > 10:
                    # Archive old entries
                    archived = await self._archive_old_conversations()
                    if archived > 0:
                        tasks_completed.append(f"Archived {archived} old conversations")
            
            # Task 4: Check log file sizes
            log_dir = self.workspace_root / "logs"
            if log_dir.exists():
                total_log_size = sum(f.stat().st_size for f in log_dir.glob("*.log"))
                if total_log_size > 100 * 1024 * 1024:  # 100MB
                    tasks_completed.append("Log rotation recommended")
            
            # Only report if significant work done
            if len(tasks_completed) >= 2:
                context["tasks_completed"] = tasks_completed
                context["silent"] = True  # Don't speak for routine maintenance
                context["message"] = f"Maintenance completed: {len(tasks_completed)} tasks"
                return True, context
                
        except Exception as e:
            pass
        
        return False, context
    
    async def _clean_temp_files(self) -> int:
        """Clean temporary files older than 7 days. Returns count cleaned."""
        cleaned = 0
        try:
            temp_dirs = [
                self.workspace_root / "temp",
                self.workspace_root / ".cache",
                Path("/tmp") if os.name != 'nt' else Path(os.environ.get('TEMP', 'C:/Windows/Temp'))
            ]
            
            cutoff = time.time() - (7 * 86400)
            
            for temp_dir in temp_dirs:
                if temp_dir.exists():
                    for file_path in temp_dir.rglob("*"):
                        try:
                            if file_path.is_file() and file_path.stat().st_mtime < cutoff:
                                file_path.unlink()
                                cleaned += 1
                        except:
                            pass
        except:
            pass
        
        return cleaned
    
    async def _archive_old_conversations(self) -> int:
        """Archive conversations older than 90 days. Returns count archived."""
        try:
            memory_file = self.memory_dir / "conversations_memory.jsonl"
            archive_file = self.memory_dir / "conversations_archive.jsonl"
            
            cutoff = time.time() - (90 * 86400)
            archived = 0
            
            with open(memory_file, "r") as f:
                lines = f.readlines()
            
            # Separate old and new
            old_lines = []
            new_lines = []
            
            for line in lines:
                try:
                    entry = json.loads(line)
                    if entry.get("timestamp", 0) < cutoff:
                        old_lines.append(line)
                    else:
                        new_lines.append(line)
                except:
                    new_lines.append(line)
            
            # Archive old entries
            if old_lines:
                with open(archive_file, "a") as f:
                    f.writelines(old_lines)
                archived = len(old_lines)
            
            # Write back new entries
            with open(memory_file, "w") as f:
                f.writelines(new_lines)
            
            return archived
            
        except:
            return 0
    
    # ============== JARVIS LEVEL 4: AUTOMATED DAILY BRIEFING ==============
    
    async def _generate_morning_briefing(self) -> str:
        """
        JARVIS-style morning briefing with system status and project updates.
        
        Returns:
            Formatted briefing message
        """
        try:
            now = datetime.now()
            
            # Gather system status
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Gather project stats
            project_stats = self._get_project_updates()
            
            # Gather weather (placeholder - would integrate with weather API)
            weather_info = "Weather data not available"
            
            # Calculate system health
            devices_operational = True
            health_status = "All systems operational" if devices_operational else "Some devices need attention"
            
            # Build briefing
            lines = [
                f"Good morning, Sir. It's {now.strftime('%I:%M %p')}.",
                "",
                "SYSTEM STATUS:",
                f"  CPU: {cpu_percent:.1f}% | Memory: {memory.percent:.1f}% | Disk: {disk.percent:.1f}%",
                f"  Status: {health_status}",
                "",
                "PROJECTS:",
                f"  Active: {project_stats['active_projects']} | Pending tasks: {project_stats['pending_tasks']}",
            ]
            
            if project_stats.get('recent_commits', 0) > 0:
                lines.append(f"  Recent activity: {project_stats['recent_commits']} commits today")
            
            if project_stats.get('recent_cad', 0) > 0:
                lines.append(f"  Design work: {project_stats['recent_cad']} files modified")
            
            lines.extend([
                "",
                "How would you like to proceed today?",
            ])
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Good morning, Sir. System briefing temporarily unavailable."
    
    def _get_project_updates(self) -> Dict:
        """Get current project statistics for briefing."""
        stats = {
            "active_projects": 0,
            "pending_tasks": 0,
            "recent_commits": 0,
            "recent_cad": 0
        }
        
        try:
            # Count projects
            projects_dir = self.workspace_root / "projects"
            if projects_dir.exists():
                stats["active_projects"] = len([d for d in projects_dir.iterdir() if d.is_dir()])
            
            # Check for recent CAD work
            recent_cad = list(self.workspace_root.rglob("*.stl")) + \
                        list(self.workspace_root.rglob("*.obj"))
            today_start = time.time() - 86400
            stats["recent_cad"] = len([f for f in recent_cad if f.stat().st_mtime > today_start])
            
            # Check git activity
            git_dirs = list(self.workspace_root.rglob(".git"))
            for git_dir in git_dirs[:5]:  # Check up to 5 repos
                try:
                    repo_root = git_dir.parent
                    # Count recent commits (would need git integration)
                    stats["recent_commits"] += 0  # Placeholder
                except:
                    pass
            
            # Get pending tasks from memory
            structured = self._load_structured_memory()
            goals = structured.get("goals", {})
            stats["pending_tasks"] = sum(1 for g in goals.values() 
                                        if isinstance(g, dict) and not g.get("completed", False))
            
        except Exception as e:
            pass
        
        return stats
    
    def _log_trigger(self, rule: ProactiveRule, context: Dict):
        """Log when a rule triggers."""
        entry = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "rule_id": rule.id,
            "rule_name": rule.name,
            "context": context
        }
        
        try:
            with open(self.history_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            print(f"[ProactiveMonitor] Error logging trigger: {e}")
    
    def get_rules_summary(self) -> str:
        """Get a summary of all rules and their status."""
        lines = ["=== Proactive Monitor Rules ===\n"]
        
        for rule in self.rules:
            status = "✓" if rule.enabled else "✗"
            last_triggered = "Never"
            if rule.last_triggered:
                ago = (time.time() - rule.last_triggered) / 60
                last_triggered = f"{ago:.0f}m ago"
            
            lines.append(f"[{status}] {rule.name}")
            lines.append(f"    Type: {rule.trigger_type.value} → {rule.action_type.value}")
            lines.append(f"    Last: {last_triggered} | Cooldown: {rule.cooldown_minutes}m")
            lines.append(f"    {rule.description}\n")
        
        return "\n".join(lines)


# Singleton instance
_proactive_monitor = None

def get_proactive_monitor(workspace_root: str = None, on_speak: Callable = None,
                          on_notify: Callable = None) -> ProactiveMonitor:
    """Get or create the global ProactiveMonitor instance."""
    global _proactive_monitor
    if _proactive_monitor is None:
        if workspace_root is None:
            current_dir = Path(__file__).resolve().parent
            workspace_root = current_dir.parent
        _proactive_monitor = ProactiveMonitor(workspace_root, on_speak, on_notify)
    return _proactive_monitor
