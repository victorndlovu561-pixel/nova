import json
import re
import sys
from pathlib import Path
from datetime import datetime


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


PLANNER_PROMPT = """You are the planning module of NOVA (Necessary Operational & Versatile Assistant).
Your job: break any user goal into a sequence of steps using ONLY the tools listed below.

ABSOLUTE RULES:
- NEVER use generated_code or write Python scripts. It does not exist.
- NEVER reference previous step results in parameters. Every step is independent.
- Use web_search for ANY information retrieval, research, or current data.
- Use file_controller to save content to disk.
- Use computer_settings for system commands: antivirus scans, software checks, volume, brightness.
- Use network_scan to discover devices on the local network.
- Max 5 steps. Use the minimum steps needed.

AVAILABLE TOOLS AND THEIR PARAMETERS:

open_app
  app_name: string (required)

web_search
  query: string (required) — write a clear, focused search query
  mode: "search" | "compare" (optional, default: search)
  items: list of strings (optional, for compare mode)
  aspect: string (optional, for compare mode)

game_updater
  action: "update" | "install" | "list" | "download_status" | "schedule" (required)
  platform: "steam" | "epic" | "both" (optional, default: both)
  game_name: string (optional)
  app_id: string (optional)
  shutdown_when_done: boolean (optional)

browser_control
  action: "go_to" | "search" | "click" | "type" | "scroll" | "get_text" | "press" | "close" (required)
  url: string (for go_to)
  query: string (for search)
  text: string (for click/type)
  direction: "up" | "down" (for scroll)

file_controller
  action: "write" | "create_file" | "read" | "list" | "delete" | "move" | "copy" | "find" | "disk_usage" (required)
  path: string — use "desktop" for Desktop folder
  name: string — filename
  content: string — file content (for write/create_file)

computer_settings
  action: string (required)
  description: string — natural language description of what to do
  value: string (optional)

network_scan
  action: "scan" | "devices" | "ports" (required)
  target: string (optional - IP or IP range, defaults to local network)

computer_control
  action: "type" | "click" | "hotkey" | "press" | "scroll" | "screenshot" | "screen_find" | "screen_click" (required)
  text: string (for type)
  x, y: int (for click)
  keys: string (for hotkey, e.g. "ctrl+c")
  key: string (for press)
  direction: "up" | "down" (for scroll)
  description: string (for screen_find/screen_click)

screen_process
  text: string (required) — what to analyze or ask about the screen
  angle: "screen" | "camera" (optional)

send_message
  receiver: string (required)
  message_text: string (required)
  platform: string (required)

reminder
  date: string YYYY-MM-DD (required)
  time: string HH:MM (required)
  message: string (required)

desktop_control
  action: "wallpaper" | "organize" | "clean" | "list" | "task" (required)
  path: string (optional)
  task: string (optional)

youtube_video
  action: "play" | "summarize" | "trending" (required)
  query: string (for play)

weather_report
  city: string (required)

flight_finder
  origin: string (required)
  destination: string (required)
  date: string (required)

code_helper
  action: "write" | "edit" | "run" | "explain" (required)
  description: string (required)
  language: string (optional)
  output_path: string (optional)
  file_path: string (optional)

dev_agent
  description: string (required)
  language: string (optional)

MAPPING RULES:
- "check for viruses" or "virus scan" or "antivirus" → computer_settings with action: check_installed_software, then action: start_antivirus_scan
- "check network" or "scan network" or "what's on my network" → network_scan with action: scan
- "check connected devices" or "find my phone" or "list devices" → network_scan with action: devices
- "save to file" or "write to notepad" → file_controller with action: write
- "search for" or "look up" or "find information" → web_search

EXAMPLES:

Goal: "check for viruses on my computer"
Steps:
- computer_settings | action: check_installed_software, description: "Check if antivirus software is installed"
- computer_settings | action: start_antivirus_scan, description: "Run full system virus scan"

Goal: "scan my network and tell me what devices are connected"
Steps:
- network_scan | action: scan, target: "local"

Goal: "research mechanical engineering and save it to a notepad file"
Steps:
- web_search | query: "mechanical engineering overview definition history"
- web_search | query: "mechanical engineering applications and future trends"
- file_controller | action: write, path: desktop, name: mechanical_engineering.txt, content: "MECHANICAL ENGINEERING RESEARCH\\n\\nResults from web search will be saved here."

Goal: "what devices are on my wifi"
Steps:
- network_scan | action: devices

Goal: "check my computer for malware and viruses"
Steps:
- computer_settings | action: check_installed_software, description: "List installed security software"
- computer_settings | action: start_antivirus_scan, description: "Run a full malware and virus scan"

OUTPUT — return ONLY valid JSON, no markdown, no explanation, no code blocks:
{
  "goal": "...",
  "steps": [
    {
      "step": 1,
      "tool": "tool_name",
      "description": "what this step does",
      "parameters": {},
      "critical": true
    }
  ]
}
"""


def _get_api_key() -> str:
    """Get Gemini API key from .env, environment, or config file."""
    import os
    from pathlib import Path
    
    file_dir = Path(__file__).resolve().parent
    
    env_paths = [
        file_dir / ".." / ".env",
        file_dir / ".." / ".." / ".env",
        Path(".env"),
        Path("../.env"),
        Path("../../.env"),
        Path.home() / ".env"
    ]
    
    for env_path in env_paths:
        resolved_path = env_path.resolve()
        if resolved_path.exists():
            try:
                with open(resolved_path, "r") as f:
                    for line in f:
                        if line.strip().startswith("GEMINI_API_KEY="):
                            return line.strip().split("=", 1)[1].strip('"\'')
            except:
                pass
    
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key
    
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("gemini_api_key", "")
        except:
            pass
    
    return os.getenv("GOOGLE_API_KEY", "")


# Local keyword-based plan generator for common patterns
# This catches requests that the LLM might mishandle
KEYWORD_PLANS = {
    "virus": {
        "goal": "Check computer for viruses and malware",
        "steps": [
            {
                "step": 1,
                "tool": "computer_settings",
                "description": "Check if antivirus software is installed",
                "parameters": {"action": "check_installed_software"},
                "critical": True
            },
            {
                "step": 2,
                "tool": "computer_settings",
                "description": "Run a full system virus scan",
                "parameters": {"action": "start_antivirus_scan"},
                "critical": True
            }
        ]
    },
    "network": {
        "goal": "Scan local network for connected devices",
        "steps": [
            {
                "step": 1,
                "tool": "network_scan",
                "description": "Scan the local network for all connected devices",
                "parameters": {"action": "scan"},
                "critical": True
            }
        ]
    },
    "malware": {
        "goal": "Check for malware",
        "steps": [
            {
                "step": 1,
                "tool": "computer_settings",
                "description": "Check for installed security software",
                "parameters": {"action": "check_installed_software"},
                "critical": True
            },
            {
                "step": 2,
                "tool": "computer_settings",
                "description": "Run malware scan",
                "parameters": {"action": "start_antivirus_scan"},
                "critical": True
            }
        ]
    },
    "cpu": {
        "goal": "Investigate CPU usage",
        "steps": [
            {
                "step": 1,
                "tool": "computer_settings",
                "description": "Get detailed CPU usage by process",
                "parameters": {"action": "cpu_usage"},
                "critical": True
            }
        ]
    },
    "system idle": {
        "goal": "Explain System Idle Process",
        "steps": [
            {
                "step": 1,
                "tool": "computer_settings",
                "description": "Check actual CPU usage excluding idle",
                "parameters": {"action": "cpu_usage"},
                "critical": True
            }
        ]
    },
    "high cpu": {
        "goal": "Investigate high CPU usage",
        "steps": [
            {
                "step": 1,
                "tool": "computer_settings",
                "description": "Get detailed CPU usage by process",
                "parameters": {"action": "cpu_usage"},
                "critical": True
            }
        ]
    },
}


def _match_keyword_plan(goal: str) -> dict | None:
    """Check if the goal matches any known keyword patterns."""
    goal_lower = goal.lower()
    
    for keyword, plan in KEYWORD_PLANS.items():
        if keyword in goal_lower:
            # Deep copy to avoid mutation
            import copy
            matched_plan = copy.deepcopy(plan)
            matched_plan["goal"] = goal  # Use original goal
            print(f"[Planner] 🎯 Keyword match: '{keyword}' → pre-built plan")
            return matched_plan
    
    return None


def _validate_and_fix_steps(steps: list, goal: str) -> list:
    """Fix common tool routing errors in generated steps."""
    fixed = []
    
    for step in steps:
        tool = step.get("tool", "")
        description = step.get("description", "").lower()
        
        # Fix: "check_installed_software" and "start_antivirus_scan" should use computer_settings
        if tool in ("check_installed_software", "start_antivirus_scan", "antivirus_scan"):
            step["tool"] = "computer_settings"
            if not step.get("parameters"):
                step["parameters"] = {}
            step["parameters"]["action"] = tool
            print(f"[Planner] 🔧 Fixed tool routing: {tool} → computer_settings")
        
        # Fix: "scan_network" or "network" tool → use network_scan
        if tool in ("scan_network", "scan_local_network", "find_devices", "check_connected_devices"):
            step["tool"] = "network_scan"
            if not step.get("parameters"):
                step["parameters"] = {}
            step["parameters"]["action"] = "scan"
            print(f"[Planner] 🔧 Fixed tool routing: {tool} → network_scan")
        
        # Fix: "inform_user" is not a tool - skip it
        if tool in ("inform_user", "notify_user", "tell_user", "speak"):
            print(f"[Planner] ⏭️ Skipping non-executable step: {tool}")
            continue
        
        # Fix: "web_search_tool" → web_search
        if tool == "web_search_tool":
            step["tool"] = "web_search"
        
        # Fix: empty parameters
        if not step.get("parameters"):
            step["parameters"] = {}
        
        fixed.append(step)
    
    return fixed


def create_plan(goal: str, context: str = "") -> dict:
    """Create an execution plan for a user goal."""
    
    # Step 1: Check keyword patterns first (fast, reliable)
    keyword_plan = _match_keyword_plan(goal)
    if keyword_plan:
        return keyword_plan
    
    # Step 2: Use LLM for complex/unfamiliar goals
    from google import genai
    from google.genai import types

    try:
        client = genai.Client(api_key=_get_api_key())
        
        prompt = f"Goal: {goal}\nContext: {context}\n\nCreate a plan as JSON with 'steps' array."
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=PLANNER_PROMPT)
        )
        
        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        plan = json.loads(text)
        
        # Validate and fix tool routing
        if "steps" in plan:
            plan["steps"] = _validate_and_fix_steps(plan["steps"], goal)
        
        if not plan.get("steps"):
            raise ValueError("No valid steps generated")
        
        print(f"[Planner] ✅ Plan created: {len(plan['steps'])} steps")
        return plan
        
    except Exception as e:
        print(f"[Planner] ⚠️ LLM planning failed: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    """Generate a fallback plan when LLM fails."""
    print("[Planner] 🔄 Using fallback plan")
    
    # Try keyword matching one more time
    keyword_plan = _match_keyword_plan(goal)
    if keyword_plan:
        return keyword_plan
    
    # Default: web search
    return {
        "goal": goal,
        "steps": [
            {
                "step": 1,
                "tool": "web_search",
                "description": f"Search for information about: {goal}",
                "parameters": {"query": goal},
                "critical": True
            }
        ]
    }


def replan(goal: str, completed_steps: list, failed_step: dict, error: str) -> dict:
    """Generate a revised plan after a step fails."""
    from google import genai
    from google.genai import types

    try:
        client = genai.Client(api_key=_get_api_key())
        
        # Build context from completed steps
        completed_desc = "\n".join(
            f"Step {s.get('step', '?')}: {s.get('description', '')}" 
            for s in completed_steps
        )
        
        prompt = (
            f"Original goal: {goal}\n\n"
            f"Completed steps:\n{completed_desc}\n\n"
            f"FAILED step: {failed_step.get('description', '')}\n"
            f"Error: {error}\n\n"
            "Create a revised plan that avoids this error. "
            "Return ONLY valid JSON with a 'steps' array."
        )
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=PLANNER_PROMPT)
        )
        
        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        plan = json.loads(text)

        # Fix any generated_code references
        for step in plan.get("steps", []):
            if step.get("tool") == "generated_code":
                step["tool"] = "web_search"
                step["parameters"] = {"query": step.get("description", goal)[:200]}
        
        # Validate tool routing
        if "steps" in plan:
            plan["steps"] = _validate_and_fix_steps(plan["steps"], goal)

        print(f"[Planner] 🔄 Revised plan: {len(plan.get('steps', []))} steps")
        return plan
        
    except Exception as e:
        print(f"[Planner] ⚠️ Replan failed: {e}")
        return _fallback_plan(goal)