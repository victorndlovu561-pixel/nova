import json
import re
import sys
import threading
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Callable, List, Dict, Optional

from agent.planner       import create_plan, replan
from agent.error_handler import analyze_error, generate_fix, ErrorDecision


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    """Get Gemini API key from .env, environment, or config file."""
    import os
    from pathlib import Path
    
    # Get the directory where this file is located
    file_dir = Path(__file__).resolve().parent
    
    # Try loading from .env file (search relative to file location and CWD)
    env_paths = [
        # Relative to this file (backend/agent/ -> backend/ -> root)
        file_dir / ".." / ".env",
        file_dir / ".." / ".." / ".env",
        # Relative to current working directory
        Path(".env"),
        Path("../.env"),
        Path("../../.env"),
        # Home directory
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
    
    # Try environment variable
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        return env_key
    
    # Fall back to config file
    if API_CONFIG_PATH.exists():
        try:
            with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("gemini_api_key", "")
        except:
            pass
    
    # Final fallback
    return os.getenv("GOOGLE_API_KEY", "")


class NetworkScanner:
    """Scan network for ALL connected devices, not just Kasa."""
    
    async def scan_network(self) -> List[Dict]:
        """Full network scan using multiple methods."""
        devices = []
        
        # Method 1: ARP scan (local network)
        arp_devices = await self._arp_scan()
        devices.extend(arp_devices)
        
        # Method 2: mDNS/Bonjour discovery
        mdns_devices = await self._mdns_discover()
        devices.extend(mdns_devices)
        
        # Method 3: UPnP discovery
        upnp_devices = await self._upnp_discover()
        devices.extend(upnp_devices)
        
        # Method 4: Check known device MAC vendors
        for device in devices:
            device["vendor"] = await self._lookup_mac_vendor(device.get("mac"))
        
        # Deduplicate
        return self._deduplicate_devices(devices)
    
    async def _arp_scan(self) -> List[Dict]:
        """Scan local network using ARP table."""
        import subprocess
        import re
        
        try:
            result = subprocess.run(["arp", "-a"], capture_output=True, text=True)
            devices = []
            
            for line in result.stdout.split("\n"):
                # Parse: "192.168.1.5     xx-xx-xx-xx-xx-xx     dynamic"
                match = re.match(r'\s*(\d+\.\d+\.\d+\.\d+)\s+([\w-]+)\s+(\w+)', line)
                if match:
                    devices.append({
                        "ip": match.group(1),
                        "mac": match.group(2),
                        "type": match.group(3),
                        "source": "arp"
                    })
            
            return devices
        except Exception as e:
            print(f"[NetworkScanner] ARP scan failed: {e}")
            return []
    
    async def _mdns_discover(self) -> List[Dict]:
        """Discover devices via mDNS/Bonjour."""
        try:
            from zeroconf import ServiceBrowser, Zeroconf
            # Implementation placeholder - would need async listener
            pass
        except ImportError:
            pass
        return []
    
    async def _upnp_discover(self) -> List[Dict]:
        """Discover devices via UPnP."""
        try:
            import socket
            import struct
            
            # UPnP discovery message
            msg = (
                'M-SEARCH * HTTP/1.1\r\n'
                'HOST: 239.255.255.250:1900\r\n'
                'MAN: "ssdp:discover"\r\n'
                'MX: 3\r\n'
                'ST: ssdp:all\r\n'
                '\r\n'
            )
            
            devices = []
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.settimeout(3)
            sock.sendto(msg.encode(), ('239.255.255.250', 1900))
            
            try:
                while True:
                    data, addr = sock.recvfrom(1024)
                    devices.append({
                        "ip": addr[0],
                        "raw_response": data.decode(),
                        "source": "upnp"
                    })
            except socket.timeout:
                pass
            finally:
                sock.close()
            
            return devices
        except Exception as e:
            print(f"[NetworkScanner] UPnP scan failed: {e}")
            return []
    
    async def _lookup_mac_vendor(self, mac: str) -> Optional[str]:
        """Lookup MAC vendor from OUI database."""
        if not mac:
            return None
        
        # Common vendor OUI prefixes
        oui_db = {
            "b0-be-76": "Amazon",
            "ac-63-be": "Amazon",
            "50-f5-da": "Google",
            "30-8c-fb": "Philips Hue",
            "00-17-88": "Philips Hue",
            "18-b4-30": "Nest/Google",
            "64-16-66": "Sonos",
            "48-a6-b8": "Sonos",
            "00-0e-58": "Ring",
            "8c-85-90": "Samsung",
            "00-12-ee": "Samsung",
            "c0-49-ef": "Apple",
            "3c-5a-b4": "Google",
            "94-eb-2c": "Google",
            "6c-29-95": "Google",
        }
        
        # Normalize MAC
        mac_clean = mac.replace(":", "-").replace(".", "-").lower()
        oui = mac_clean[:8]
        
        return oui_db.get(oui, "Unknown")
    
    def _deduplicate_devices(self, devices: List[Dict]) -> List[Dict]:
        """Remove duplicate devices by IP."""
        seen = set()
        unique = []
        for device in devices:
            ip = device.get("ip")
            if ip and ip not in seen:
                seen.add(ip)
                unique.append(device)
        return unique


def _run_generated_code(description: str, speak: Callable | None = None) -> str:
    from google import genai
    from google.genai import types

    if speak:
        speak("Writing custom code for this task, sir.")

    home      = Path.home()
    desktop   = home / "Desktop"
    downloads = home / "Downloads"
    documents = home / "Documents"

    if not desktop.exists():
        try:
            import winreg
            key     = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])
        except Exception:
            pass

    client = genai.Client(api_key=_get_api_key())
    
    system_instruction = (
        "You are an expert Python developer. "
        "Write clean, complete, working Python code. "
        "Use standard library + common packages. "
        "Install missing packages with subprocess + pip if needed. "
        "Return ONLY the Python code. No explanation, no markdown, no backticks.\n\n"
        f"SYSTEM PATHS:\n"
        f"  Desktop   = r'{desktop}'\n"
        f"  Downloads = r'{downloads}'\n"
        f"  Documents = r'{documents}'\n"
        f"  Home      = r'{home}'\n"
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"Write Python code to accomplish this task:\n\n{description}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction
            )
        )
        code = response.text.strip()
        code = re.sub(r"```(?:python)?", "", code).strip().rstrip("`").strip()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        print(f"[Executor] 🐍 Running generated code: {tmp_path}")

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True, text=True,
            timeout=120, cwd=str(Path.home())
        )

        try:
            os.unlink(tmp_path)
        except Exception:
            pass

        output = result.stdout.strip()
        error  = result.stderr.strip()

        if result.returncode == 0 and output:
            return output
        elif result.returncode == 0:
            return "Task completed successfully."
        elif error:
            raise RuntimeError(f"Code error: {error[:400]}")
        return "Completed."

    except subprocess.TimeoutExpired:
        raise RuntimeError("Generated code timed out after 120 seconds.")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Generated code failed: {e}")

def _inject_context(params: dict, tool: str, step_results: dict, goal: str = "") -> dict:
    if not step_results:
        return params

    params = dict(params)

    if tool == "file_controller" and params.get("action") in ("write", "create_file"):
        content = params.get("content", "")
        if not content or len(content) < 50:
            all_results = [
                v for v in step_results.values()
                if v and len(v) > 100 and v not in ("Done.", "Completed.")
            ]
            if all_results:
                combined = "\n\n---\n\n".join(all_results)
                translated = _translate_to_goal_language(combined, goal)
                params["content"] = translated
                print(f"[Executor] 💉 Injected + translated content")

    return params
def _detect_language(text: str) -> str:
    from google import genai
    
    client = genai.Client(api_key=_get_api_key())
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=f"What language is this text written in? "
                     f"Reply with ONLY the language name in English (e.g. Turkish, English, French).\n\n"
                     f"Text: {text[:200]}"
        )
        return response.text.strip()
    except Exception:
        return "English"


def _translate_to_goal_language(content: str, goal: str) -> str:
    if not goal:
        return content
    try:
        from google import genai
        
        client = genai.Client(api_key=_get_api_key())
        
        target_lang = _detect_language(goal)
        print(f"[Executor] 🌐 Translating to: {target_lang}")

        prompt = (
            f"You are a professional translator. "
            f"Translate the following text into {target_lang}.\n"
            f"IMPORTANT:\n"
            f"- Translate EVERYTHING, leave nothing in English\n"
            f"- Keep all facts, numbers, and data intact\n"
            f"- Keep the structure and formatting\n"
            f"- Output ONLY the translated text, nothing else\n\n"
            f"Text to translate:\n{content[:4000]}"
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        translated = response.text.strip()
        print(f"[Executor] ✅ Translation done ({target_lang})")
        return translated
    except Exception as e:
        print(f"[Executor] ⚠️ Translation failed: {e}")
        return content

def _call_tool(tool: str, parameters: dict, speak: Callable | None) -> str:
    # Route misnamed tools before dispatching
    TOOL_ALIASES = {
        "check_installed_software": "computer_settings",
        "start_antivirus_scan": "computer_settings",
        "scan_network": "network_scan",
        "find_devices": "network_scan",
        "check_connected_devices": "network_scan",
        "web_search_tool": "web_search",
        "list_smart_devices": "network_scan",
        "control_light_device": "control_light",
    }
    
    # Remap tool name if it's an alias
    if tool in TOOL_ALIASES:
        mapped = TOOL_ALIASES[tool]
        print(f"[Executor] 🔄 Routing '{tool}' → '{mapped}'")
        tool = mapped

    if tool == "open_app":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from open_app import open_app
        return open_app(parameters=parameters, player=None) or "Done."

    elif tool == "web_search":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from web_search import web_search
        return web_search(parameters=parameters, player=None) or "Done."
    elif tool == "game_updater":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from game_updater import game_updater
        return game_updater(parameters=parameters, player=None, speak=speak) or "Done."
    elif tool == "browser_control":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from browser_control import browser_control
        return browser_control(parameters=parameters, player=None) or "Done."

    elif tool == "file_controller":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from file_controller import file_controller
        return file_controller(parameters=parameters, player=None) or "Done."

    elif tool == "code_helper":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from code_helper import code_helper
        return code_helper(parameters=parameters, player=None, speak=speak) or "Done."

    elif tool == "dev_agent":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from dev_agent import dev_agent
        return dev_agent(parameters=parameters, player=None, speak=speak) or "Done."

    elif tool == "screen_process":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from screen_processor import screen_process
        screen_process(parameters=parameters, player=None)
        return "Screen captured and analyzed."

    elif tool == "send_message":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from send_message import send_message
        return send_message(parameters=parameters, player=None) or "Done."

    elif tool == "reminder":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from reminder import reminder
        return reminder(parameters=parameters, player=None) or "Done."

    elif tool == "youtube_video":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from youtube_video import youtube_video
        return youtube_video(parameters=parameters, player=None) or "Done."

    elif tool == "weather_report":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from weather_report import weather_action
        return weather_action(parameters=parameters, player=None) or "Done."

    elif tool == "computer_settings":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from computer_settings import computer_settings
        return computer_settings(parameters=parameters, player=None) or "Done."

    elif tool == "desktop_control":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from desktop import desktop_control
        return desktop_control(parameters=parameters, player=None) or "Done."

    elif tool == "computer_control":
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from computer_control import computer_control
        return computer_control(parameters=parameters, player=None) or "Done."

    elif tool == "generated_code":
        description = parameters.get("description", "")
        if not description:
            raise ValueError("generated_code requires a 'description' parameter.")
        return _run_generated_code(description, speak=speak)

    elif tool == "flight_finder":
        # Import from backend root, not actions module
        import sys
        from pathlib import Path
        backend_root = Path(__file__).resolve().parent.parent
        if str(backend_root) not in sys.path:
            sys.path.insert(0, str(backend_root))
        from flight_finder import flight_finder
        return flight_finder(parameters=parameters, player=None, speak=speak) or "Done."

    else:
        print(f"[Executor] ⚠️ Unknown tool '{tool}' — falling back to generated_code")
        return _run_generated_code(f"Accomplish this task: {parameters}", speak=speak)

class AgentExecutor:

    MAX_REPLAN_ATTEMPTS = 2

    # Tool routing mapping for common agent actions
    TOOL_ROUTING = {
        "check_installed_software": "computer_settings",
        "start_antivirus_scan": "computer_settings", 
        "web_search": "web_search_tool",
        "scan_network": "network_scan",
        "check_connected_devices": "network_scan",
        "scan_local_network": "network_scan",
        "find_devices": "network_scan",
        "check_tv": "network_scan",
        "check_smart_tv": "network_scan",
        "tv_status": "network_scan",
        "check_device": "network_scan",
        "device_status": "network_scan",
        "list_devices": "network_scan",
        "what_devices": "network_scan",
        "show_devices": "network_scan",
    }

    def __init__(self):
        self.network_scanner = NetworkScanner()

    async def execute_step(self, step: Dict) -> Dict:
        """Execute a step with proper tool routing."""
        action = step.get("tool", "") or step.get("action", "")
        
        # Check for TV/device keywords in natural language queries
        action_lower = action.lower()
        device_keywords = ["tv", "smart tv", "television", "device", "phone", "speaker", "chromecast", "roku"]
        network_keywords = ["network", "connected", "devices on", "find my", "scan for", "what devices", "show devices"]
        
        # If action contains device keywords, route to network scan
        if any(kw in action_lower for kw in device_keywords + network_keywords):
            if not self.TOOL_ROUTING.get(action):  # Only if not explicitly routed
                return await self._execute_network_scan(step)
        
        # Route to correct tool
        routed_tool = self.TOOL_ROUTING.get(action, action)
        
        if routed_tool == "computer_settings":
            return await self._execute_computer_settings(step)
        elif routed_tool == "web_search_tool":
            return await self._execute_web_search(step)
        elif routed_tool == "network_scan":
            return await self._execute_network_scan(step)
        else:
            # Fall back to generic tool call
            params = step.get("parameters", {})
            result = _call_tool(action, params, None)
            return {"result": result, "tool": action}

    async def _execute_computer_settings(self, step: Dict) -> Dict:
        """Execute computer settings related actions."""
        from computer_settings import computer_settings
        
        action = step.get("tool", "") or step.get("action", "")
        params = step.get("parameters", {})
        
        # Map specific actions to computer_settings calls
        if "antivirus" in action.lower():
            params["action"] = "antivirus_scan"
        elif "installed" in action.lower():
            params["action"] = "list_software"
        else:
            params["action"] = params.get("action", "system_info")
        
        result = computer_settings(params)
        return {"result": result, "tool": "computer_settings"}

    async def _execute_web_search(self, step: Dict) -> Dict:
        """Execute web search."""
        from web_search import web_search
        
        params = step.get("parameters", {})
        query = params.get("query", "")
        
        result = web_search({"query": query})
        return {"result": result, "tool": "web_search"}

    async def _execute_network_scan(self, step: Dict) -> Dict:
        """Execute network scanning using KasaAgent for comprehensive discovery."""
        from kasa_agent import KasaAgent
        
        # Use KasaAgent for full network scan (ARP, UPnP, mDNS, port scanning)
        agent = KasaAgent()
        devices = await agent.scan_full_network()
        
        # Also discover Kasa-specific devices
        kasa_devices = await agent.discover_devices()
        
        # Format results
        device_count = len(devices)
        kasa_count = len(kasa_devices)
        vendors = list(set(d.get("vendor", "Unknown") for d in devices if d.get("vendor")))
        device_types = list(set(d.get("device_type", "unknown") for d in devices))
        
        # Find TVs specifically
        tvs = [d for d in devices if "tv" in d.get("device_type", "").lower() or 
                                    "samsung" in (d.get("vendor") or "").lower() or
                                    "lg" in (d.get("vendor") or "").lower() or
                                    "sony" in (d.get("vendor") or "").lower()]
        
        result = {
            "devices": devices,
            "count": device_count,
            "kasa_devices": kasa_count,
            "vendors": vendors,
            "device_types": device_types,
            "tvs_found": len(tvs),
            "tv_details": tvs,
            "summary": f"Found {device_count} total devices ({kasa_count} Kasa). TVs: {len(tvs)}. Vendors: {', '.join(vendors[:5])}"
        }
        
        return {"result": result, "tool": "network_scan"}

    def execute(
        self,
        goal:        str,
        speak:       Callable | None        = None,
        cancel_flag: threading.Event | None = None,
    ) -> str:
        print(f"\n[Executor] 🎯 Goal: {goal}")

        replan_attempts = 0
        completed_steps = []
        step_results    = {} 
        plan            = create_plan(goal)

        while True:
            steps = plan.get("steps", [])

            if not steps:
                msg = "I couldn't create a valid plan for this task, sir."
                if speak: speak(msg)
                return msg

            success      = True
            failed_step  = None
            failed_error = ""

            for step in steps:
                if cancel_flag and cancel_flag.is_set():
                    if speak: speak("Task cancelled, sir.")
                    return "Task cancelled."

                step_num = step.get("step", "?")
                tool     = step.get("tool", "generated_code")
                desc     = step.get("description", "")
                params   = step.get("parameters", {})

                params = _inject_context(params, tool, step_results, goal=goal)

                print(f"\n[Executor] ▶️ Step {step_num}: [{tool}] {desc}")

                attempt = 1
                step_ok = False

                while attempt <= 3:
                    if cancel_flag and cancel_flag.is_set():
                        break
                    try:
                        result = _call_tool(tool, params, speak)
                        step_results[step_num] = result 
                        completed_steps.append(step)
                        print(f"[Executor] ✅ Step {step_num} done: {str(result)[:100]}")
                        step_ok = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        print(f"[Executor] ❌ Step {step_num} attempt {attempt} failed: {error_msg}")

                        recovery = analyze_error(step, error_msg, attempt=attempt)
                        decision = recovery["decision"]
                        user_msg = recovery.get("user_message", "")

                        if speak and user_msg:
                            speak(user_msg)

                        if decision == ErrorDecision.RETRY:
                            attempt += 1
                            import time; time.sleep(2)
                            continue

                        elif decision == ErrorDecision.SKIP:
                            print(f"[Executor] ⏭️ Skipping step {step_num}")
                            completed_steps.append(step)
                            step_ok = True
                            break

                        elif decision == ErrorDecision.ABORT:
                            msg = f"Task aborted, sir. {recovery.get('reason', '')}"
                            if speak: speak(msg)
                            return msg

                        else: 
                            fix_suggestion = recovery.get("fix_suggestion", "")
                            if fix_suggestion and tool != "generated_code":
                                try:
                                    fixed_step = generate_fix(step, error_msg, fix_suggestion)
                                    if speak: speak("Trying an alternative approach, sir.")
                                    res = _call_tool(
                                        fixed_step["tool"],
                                        fixed_step["parameters"],
                                        speak
                                    )
                                    step_results[step_num] = res
                                    completed_steps.append(step)
                                    step_ok = True
                                    break
                                except Exception as fix_err:
                                    print(f"[Executor] ⚠️ Fix failed: {fix_err}")

                            failed_step  = step
                            failed_error = error_msg
                            success      = False
                            break

                if not step_ok and not failed_step:
                    failed_step  = step
                    failed_error = "Max retries exceeded"
                    success      = False

                if not success:
                    break

            if success:
                return self._summarize(goal, completed_steps, speak)

            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
                msg = f"Task failed after {replan_attempts} replan attempts, sir."
                if speak: speak(msg)
                return msg

            if speak: speak("Adjusting my approach, sir.")

            replan_attempts += 1
            plan = replan(goal, completed_steps, failed_step, failed_error)

    def _summarize(self, goal: str, completed_steps: list, speak: Callable | None) -> str:
        fallback = f"All done, sir. Completed {len(completed_steps)} steps for: {goal[:60]}."
        try:
            from google import genai
            
            client = genai.Client(api_key=_get_api_key())
            steps_str = "\n".join(f"- {s.get('description', '')}" for s in completed_steps)
            prompt = (
                f'User goal: "{goal}"\n'
                f"Completed steps:\n{steps_str}\n\n"
                "Write a single natural sentence summarizing what was accomplished. "
                "Address the user as 'sir'. Be direct and positive."
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=prompt
            )
            summary = response.text.strip()
            if speak: speak(summary)
            return summary
        except Exception:
            if speak: speak(fallback)
            return fallback