import json
import re
import sys
from pathlib import Path
from enum import Enum


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


class ErrorDecision(Enum):
    RETRY       = "retry"      
    SKIP        = "skip"       
    REPLAN      = "replan"     
    ABORT       = "abort"    


ERROR_ANALYST_PROMPT = """You are the error recovery module of NOVA AI assistant.

A task step has failed. Analyze the error and decide what to do.

DECISIONS:
- retry   : Transient error (network timeout, temporary file lock, race condition).
             The same step can succeed if tried again.
- skip    : This step is not critical and the task can succeed without it.
- replan  : The approach was wrong. A different tool or method should be tried.
- abort   : The task is fundamentally impossible or unsafe to continue.

Also provide:
- A brief explanation of WHY it failed (1 sentence)
- A fix suggestion if decision is replan (what to try instead)
- Max retries: how many times to retry if decision is retry (1 or 2)

Return ONLY valid JSON:
{
  "decision": "retry|skip|replan|abort",
  "reason": "why it failed",
  "fix_suggestion": "what to try instead (for replan)",
  "max_retries": 1,
  "user_message": "Short message to tell the user (max 15 words)"
}
"""


# Known error patterns that we can handle without LLM call
ERROR_PATTERNS = [
    # Network/temporary errors → retry
    (r"(timeout|timed.?out|connection.*refused|temporarily unavailable|try again later|rate.?limit)", 
     ErrorDecision.RETRY, "Network or rate limit error", 2),
    
    # File not found → skip if not critical, else replan
    (r"(no such file|file not found|cannot find.*file|does not exist)", 
     ErrorDecision.SKIP, "File not found", 0),
    
    # Permission denied → replan
    (r"(permission denied|access.*denied|not allowed|unauthorized)", 
     ErrorDecision.REPLAN, "Permission denied", 0),
    
    # Tool not found / unknown action → replan with different approach
    (r"(unknown action|unknown tool|not recognized|not implemented|no.*handler)", 
     ErrorDecision.REPLAN, "Action not supported by this tool", 0),
    
    # Invalid parameter → replan
    (r"(invalid.*(parameter|argument|input)|missing.*(parameter|argument|required))", 
     ErrorDecision.REPLAN, "Invalid or missing parameters", 0),
    
    # Memory/disk full → abort
    (r"(out of memory|disk full|no space left|insufficient.*memory)", 
     ErrorDecision.ABORT, "System resource exhausted", 0),
]

# Error patterns that should ALWAYS trigger replan (tool not capable)
FORCE_REPLAN_PATTERNS = [
    r"Unknown action:",
    r"not found",
    r"cannot be found",
    r"is not recognized",
    r"no module named",
]


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


def _match_error_pattern(error: str) -> dict | None:
    """
    Check if the error matches any known pattern.
    Returns a decision dict if matched, None otherwise.
    """
    error_lower = error.lower()
    
    # Check force replan patterns first (these always win)
    for pattern in FORCE_REPLAN_PATTERNS:
        if re.search(pattern, error_lower):
            print(f"[ErrorHandler] 🎯 Force replan pattern matched: {pattern}")
            return {
                "decision": ErrorDecision.REPLAN,
                "reason": "The tool does not support this action",
                "fix_suggestion": "Use a different tool or approach",
                "max_retries": 0,
                "user_message": "This tool can't do that. Trying another approach, sir."
            }
    
    # Check general error patterns
    for pattern, decision, reason, max_retries in ERROR_PATTERNS:
        if re.search(pattern, error_lower):
            print(f"[ErrorHandler] 🎯 Pattern matched: {reason} → {decision.value}")
            
            user_messages = {
                ErrorDecision.RETRY: "That didn't work. Trying again, sir.",
                ErrorDecision.SKIP: "Skipping this step, sir.",
                ErrorDecision.REPLAN: "That approach failed. Adapting, sir.",
                ErrorDecision.ABORT: "This task cannot be completed, sir.",
            }
            
            return {
                "decision": decision,
                "reason": reason,
                "fix_suggestion": f"Error matched pattern: {reason}. Consider alternative approach.",
                "max_retries": max_retries,
                "user_message": user_messages.get(decision, "")
            }
    
    return None


def analyze_error(
    step: dict,
    error: str,
    attempt: int = 1,
    max_attempts: int = 2
) -> dict:
    """
    Analyzes a failed step and returns a recovery decision.

    Args:
        step         : The step dict that failed
        error        : Error message/traceback
        attempt      : Current attempt number
        max_attempts : How many times we've already tried

    Returns:
        {
            "decision": ErrorDecision,
            "reason": str,
            "fix_suggestion": str,
            "max_retries": int,
            "user_message": str
        }
    """
    # Step 1: Check if max attempts reached
    if attempt >= max_attempts:
        print(f"[ErrorHandler] ⚠️ Max attempts ({attempt}/{max_attempts}) reached — forcing replan")
        return {
            "decision":      ErrorDecision.REPLAN,
            "reason":        f"Failed {attempt} times: {error[:100]}",
            "fix_suggestion": "Try a completely different approach or tool",
            "max_retries":   0,
            "user_message":  "Trying a different approach, sir."
        }
    
    # Step 2: Check known error patterns (fast, no API call)
    pattern_result = _match_error_pattern(error)
    if pattern_result:
        # If step is critical and decision is SKIP, force REPLAN instead
        if step.get("critical") and pattern_result["decision"] == ErrorDecision.SKIP:
            pattern_result["decision"] = ErrorDecision.REPLAN
            pattern_result["user_message"] = "This step is critical — finding alternative approach, sir."
        
        return pattern_result
    
    # Step 3: Use LLM for unknown errors
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_get_api_key())

    prompt = f"""Failed step:
Tool: {step.get('tool', 'unknown')}
Description: {step.get('description', 'No description')}
Parameters: {json.dumps(step.get('parameters', {}), indent=2)}
Critical: {step.get('critical', False)}

Error:
{error[:500]}

Attempt number: {attempt}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=ERROR_ANALYST_PROMPT
            )
        )
        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        result = json.loads(text)
        decision_str = result.get("decision", "replan").lower()
        decision_map = {
            "retry":  ErrorDecision.RETRY,
            "skip":   ErrorDecision.SKIP,
            "replan": ErrorDecision.REPLAN,
            "abort":  ErrorDecision.ABORT,
        }
        result["decision"] = decision_map.get(decision_str, ErrorDecision.REPLAN)

        # Critical steps should not be skipped
        if step.get("critical") and result["decision"] == ErrorDecision.SKIP:
            result["decision"] = ErrorDecision.REPLAN
            result["user_message"] = "This step is critical — finding alternative approach, sir."

        print(f"[ErrorHandler] 🤖 LLM Decision: {result['decision'].value} — {result.get('reason', '')[:80]}")
        return result

    except Exception as e:
        print(f"[ErrorHandler] ⚠️ LLM analysis failed: {e} — defaulting to replan")
        return {
            "decision":       ErrorDecision.REPLAN,
            "reason":         f"Analysis failed: {str(e)[:100]}",
            "fix_suggestion": "Try alternative approach with different tool",
            "max_retries":    0,
            "user_message":   "Encountered an issue, adjusting approach, sir."
        }


def generate_fix(step: dict, error: str, fix_suggestion: str) -> dict:
    """
    When decision is REPLAN and a fix suggestion exists,
    generates a replacement step.

    Returns a modified step dict.
    """
    from google import genai
    from google.genai import types
    
    # Quick fix: If the error was "Unknown action", try to map to a different tool
    if "unknown action" in error.lower() or "not recognized" in error.lower():
        tool = step.get("tool", "")
        description = step.get("description", "")
        
        # Common remappings
        if tool == "computer_settings":
            # Try web_search as fallback
            print(f"[ErrorHandler] 🔄 Remapping failed computer_settings → web_search")
            return {
                "step":        step.get("step"),
                "tool":        "web_search",
                "description": f"Search for: {description}",
                "parameters":  {"query": description[:200]},
                "depends_on":  step.get("depends_on", []),
                "critical":    False  # Downgrade criticality for fallback
            }

    # LLM-based fix generation for complex cases
    client = genai.Client(api_key=_get_api_key())

    prompt = f"""A task step failed. Generate a replacement step using one of these tools:
- web_search (for finding information)
- file_controller (for file operations)
- computer_settings (for system operations)
- open_app (for opening applications)

Original step:
Tool: {step.get('tool')}
Description: {step.get('description')}
Parameters: {json.dumps(step.get('parameters', {}), indent=2)}

Error: {error[:300]}
Fix suggestion: {fix_suggestion}

Output ONLY a JSON object with the replacement step:
{{
  "tool": "tool_name",
  "parameters": {{}}
}}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are an expert at mapping failed tasks to working tools. Return ONLY valid JSON."
            )
        )
        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        
        fix_data = json.loads(text)
        
        return {
            "step":        step.get("step"),
            "tool":        fix_data.get("tool", "web_search"),
            "description": f"Auto-fix for: {step.get('description')}",
            "parameters":  fix_data.get("parameters", {"query": fix_suggestion}),
            "depends_on":  step.get("depends_on", []),
            "critical":    step.get("critical", False)
        }

    except Exception as e:
        print(f"[ErrorHandler] ⚠️ Fix generation failed: {e}")
        # Ultimate fallback: web search
        return {
            "step":        step.get("step"),
            "tool":        "web_search",
            "description": f"Fallback search for: {step.get('description')}",
            "parameters":  {"query": step.get("description", fix_suggestion)[:200]},
            "depends_on":  step.get("depends_on", []),
            "critical":    False
        }