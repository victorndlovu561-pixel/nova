import asyncio
import base64
import io
import os
import sys
import traceback
from dotenv import load_dotenv
from typing import Dict, List, Optional, Any
import cv2
import pyaudio
import PIL.Image
import mss
import argparse
import math
import struct
import time

from google import genai
from google.genai import types

# Suppress Gemini API library warnings about non-data parts
import logging
import warnings
logging.getLogger('google.genai').setLevel(logging.ERROR)
logging.getLogger('google.api_core').setLevel(logging.ERROR)

# Suppress Python warnings about non-data parts
warnings.filterwarnings('ignore', message='.*non-data parts.*')
warnings.filterwarnings('ignore', message='.*concatenated data.*')

# Also suppress warnings from underlying HTTP libraries
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)

if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup
    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

from tools import tools_list
from agent.task_queue import TaskQueue, TaskPriority, get_queue
from agent.executor import AgentExecutor
from tool_handler import ToolHandler
from cad_agent import CadAgent
from web_agent import WebAgent
from printer_agent import PrinterAgent
from kasa_agent import KasaAgent
from flight_finder import flight_finder
from open_app import open_app
from weather_report import weather_action
from send_message import send_message
from reminder import reminder
from computer_settings import computer_settings
from screen_processor import screen_process
from youtube_video import youtube_video
from desktop import desktop_control
from browser_control import browser_control
from file_controller import file_controller
from code_helper import code_helper
from dev_agent import dev_agent
from web_search import web_search as web_search_action
from computer_control import computer_control
from game_updater import game_updater
from proactive_monitor import ProactiveMonitor, get_proactive_monitor

FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
DEFAULT_MODE = "camera"

load_dotenv()
client = genai.Client(http_options={"api_version": "v1beta"}, api_key=os.getenv("GEMINI_API_KEY"))

tools = [{"function_declarations": [] + tools_list[0]['function_declarations'][0:]}]

# --- CONFIG UPDATE: Enabled Transcription ---
config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    # We switch these from [] to {} to enable them with default settings
    output_audio_transcription={}, 
    input_audio_transcription={},
    system_instruction="""
You are NOVA (Necessary Operational & Versatile Assistant).
Creator: Victor Ndlovu (address as 'Sir')

PERSONALITY:
- Professional and efficient, but warm when appropriate
- Use "Sir" consistently, never the user's name unless told
- Be proactive: anticipate needs before being asked
- Brief responses for simple queries, detailed for complex ones
- Humor: subtle and situational, not forced
- When uncertain, ask clarifying questions rather than guessing

CAPABILITIES TO EMPHASIZE:
- 3D design and fabrication (3D printing)
- Smart home control (lights, devices)
- File management and project organization
- Web research and automation
- System monitoring and maintenance
- Memory of past conversations and preferences

CONTEXT AWARENESS:
- You have access to conversation history - reference it naturally
- You track projects and their files
- You know the current time and can reference routines
- System health metrics are monitored in background
""",
    tools=tools,
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Charon"
            )
        )
    )
)

pya = pyaudio.PyAudio()

class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE, on_audio_data=None, on_video_frame=None, on_cad_data=None, on_web_data=None, on_transcription=None, on_tool_confirmation=None, on_cad_status=None, on_cad_thought=None, on_project_update=None, on_device_update=None, on_error=None, input_device_index=None, input_device_name=None, output_device_index=None, kasa_agent=None):
        self.video_mode = video_mode
        self.on_audio_data = on_audio_data
        self.on_video_frame = on_video_frame
        self.on_cad_data = on_cad_data
        self.on_web_data = on_web_data
        self.on_transcription = on_transcription
        self.on_tool_confirmation = on_tool_confirmation 
        self.on_cad_status = on_cad_status
        self.on_cad_thought = on_cad_thought
        self.on_project_update = on_project_update
        self.on_device_update = on_device_update
        self.on_error = on_error
        self.input_device_index = input_device_index
        self.input_device_name = input_device_name
        self.output_device_index = output_device_index

        self.audio_in_queue = None
        self.out_queue = None
        self.paused = False

        self.chat_buffer = {"sender": None, "text": ""} # For aggregating chunks
        
        # Track last transcription text to calculate deltas (Gemini sends cumulative text)
        self._last_input_transcription = ""
        self._last_output_transcription = ""

        self.session = None
        
        # Create CadAgent with thought callback
        def handle_cad_thought(thought_text):
            if self.on_cad_thought:
                self.on_cad_thought(thought_text)
        
        def handle_cad_status(status_info):
            if self.on_cad_status:
                self.on_cad_status(status_info)
        
        self.cad_agent = CadAgent(on_thought=handle_cad_thought, on_status=handle_cad_status)
        self.web_agent = WebAgent()
        self.kasa_agent = kasa_agent if kasa_agent else KasaAgent()
        self.printer_agent = PrinterAgent()

        # Initialize Agent Task Queue for complex task execution
        self.task_queue = get_queue()
        self.agent_executor = AgentExecutor()

        # Initialize ToolHandler for centralized tool handling
        self.tool_handler = ToolHandler(self)

        self.send_text_task = None
        self.stop_event = asyncio.Event()
        
        self.permissions = {} # Default Empty (Will treat unset as True)
        self._pending_confirmations = {}

        # Video buffering state
        self._latest_image_payload = None
        # VAD State
        self._is_speaking = False
        self._silence_start_time = None
        
        # Initialize ProjectManager
        from project_manager import ProjectManager
        # Assuming we are running from backend/ or root? 
        # Using abspath of current file to find root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # If ada.py is in backend/, project root is one up
        project_root = os.path.dirname(current_dir)
        self.project_manager = ProjectManager(project_root)
        
        # Initialize MemoryManager (JARVIS-style persistent memory)
        from memory_manager import MemoryManager
        self.memory_manager = MemoryManager(project_root)
        
        # Initialize ProactiveMonitor (background monitoring)
        def proactive_speak(message: str):
            """Callback for proactive monitor to make Nova speak."""
            if self.session:
                asyncio.create_task(
                    self.session.send(
                        input=f"System Notification: {message}",
                        end_of_turn=True
                    )
                )
        
        def _handle_proactive_notification(notification: Dict):
            """Forward proactive notifications to frontend."""
            if self.on_device_update:
                self.on_device_update({
                    "type": "proactive_notification",
                    "data": notification
                })
        
        self.proactive_monitor = get_proactive_monitor(
            workspace_root=project_root,
            on_speak=proactive_speak,
            on_notify=_handle_proactive_notification
        )
        
        # Sync Initial Project State
        if self.on_project_update:
            # We need to defer this slightly or just call it. 
            # Since this is init, loop might not be running, but on_project_update in server.py uses asyncio.create_task which needs a loop.
            # We will handle this by calling it in run() or just print for now.
            pass

    def flush_chat(self):
        """Forces the current chat buffer to be written to log."""
        if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
            # Save to ProjectManager (project-specific chat)
            self.project_manager.log_chat(self.chat_buffer["sender"], self.chat_buffer["text"])
            # Save to MemoryManager (JARVIS-style persistent memory - free, not project-dependent)
            self.memory_manager.save_interaction(
                sender=self.chat_buffer["sender"],
                text=self.chat_buffer["text"],
                context="conversations",
                metadata={"project": self.project_manager.current_project}
            )
            # Extract and store facts from user messages
            if self.chat_buffer["sender"] == "User":
                self._extract_and_remember_facts(self.chat_buffer["text"])
            self.chat_buffer = {"sender": None, "text": ""}
        # Reset transcription tracking for new turn
        self._last_input_transcription = ""
        self._last_output_transcription = ""

    def _extract_and_remember_facts(self, text: str):
        """Extract facts from user message and store in structured memory."""
        import re
        text_lower = text.lower().strip()
        
        # Pattern: "My name is X" or "I am X" or "Call me X"
        name_patterns = [
            r"my name is (\w+)",
            r"i am (\w+) (?:and|but|so|if|from|in|at|on)",
            r"i am (\w+)$",
            r"call me (\w+)",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text_lower)
            if match:
                name = match.group(1).capitalize()
                if len(name) > 2 and name not in ["The", "This", "That"]:
                    self.memory_manager.remember("identity", "name", name)
                    return
        
        # Pattern: "I like/love/enjoy/hate X"
        preference_patterns = [
            r"i (?:like|love|enjoy|prefer) (\w+(?:\s+\w+){0,3})",
            r"i (?:hate|dislike|can't stand) (\w+(?:\s+\w+){0,3})",
        ]
        for pattern in preference_patterns:
            match = re.search(pattern, text_lower)
            if match:
                thing = match.group(1).strip()
                if len(thing) > 2:
                    pref_key = f"likes_{thing.replace(' ', '_')}"
                    self.memory_manager.remember("preferences", pref_key, thing)
                    return
        
        # Pattern: "I work as/in/at X" or "My job is X"
        job_patterns = [
            r"i work (?:as|in|at) (\w+(?:\s+\w+){0,2})",
            r"my job is (\w+(?:\s+\w+){0,2})",
            r"i am a[n]? (\w+(?:\s+\w+){0,2})",
        ]
        for pattern in job_patterns:
            match = re.search(pattern, text_lower)
            if match:
                job = match.group(1).strip()
                if len(job) > 2:
                    self.memory_manager.remember("identity", "occupation", job)
                    return
        
        # Pattern: "I live in/at X" or "I'm from X"
        location_patterns = [
            r"i live (?:in|at) (\w+(?:\s+\w+){0,2})",
            r"i am from (\w+(?:\s+\w+){0,2})",
            r"i'm from (\w+(?:\s+\w+){0,2})",
        ]
        for pattern in location_patterns:
            match = re.search(pattern, text_lower)
            if match:
                location = match.group(1).strip()
                if len(location) > 2:
                    self.memory_manager.remember("identity", "location", location)
                    return

    def update_permissions(self, new_perms):
        print(f"[NOVA DEBUG] [CONFIG] Updating tool permissions...")
        print(f"[NOVA DEBUG] [CONFIG] Current permissions: {dict(self.permissions)}")
        print(f"[NOVA DEBUG] [CONFIG] New permissions to merge: {new_perms}")
        self.permissions.update(new_perms)
        print(f"[NOVA DEBUG] [CONFIG] Updated permissions: {dict(self.permissions)}")
        # Check if any are auto-allowed
        auto_allowed = [k for k, v in self.permissions.items() if v == False]
        if auto_allowed:
            print(f"[NOVA DEBUG] [CONFIG] Auto-allowed tools: {auto_allowed}")

    def set_paused(self, paused):
        self.paused = paused

    def stop(self):
        self.stop_event.set()
        
    def resolve_tool_confirmation(self, request_id, confirmed):
        print(f"[NOVA DEBUG] [RESOLVE] resolve_tool_confirmation called. ID: {request_id}, Confirmed: {confirmed}")
        if request_id in self._pending_confirmations:
            future = self._pending_confirmations[request_id]
            if not future.done():
                print(f"[NOVA DEBUG] [RESOLVE] Future found and pending. Setting result to: {confirmed}")
                future.set_result(confirmed)
            else:
                 print(f"[NOVA DEBUG] [WARN] Request {request_id} future already done. Result: {future.result()}")
        else:
            print(f"[NOVA DEBUG] [WARN] Confirmation Request {request_id} not found in pending dict. Keys: {list(self._pending_confirmations.keys())}")

    def clear_audio_queue(self):
        """Clears the queue of pending audio chunks to stop playback immediately."""
        try:
            count = 0
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()
                count += 1
            if count > 0:
                print(f"[NOVA DEBUG] [AUDIO] Cleared {count} chunks from playback queue due to interruption.")
        except Exception as e:
            print(f"[NOVA DEBUG] [ERR] Failed to clear audio queue: {e}")

    async def _inject_context_on_wake(self):
        """
        Proactive Context Injection - JARVIS-like awareness.
        When user starts speaking, inject relevant context based on time and patterns.
        """
        try:
            from datetime import datetime
            now = datetime.now()
            hour = now.hour
            
            context = ""
            
            # Time-based context
            if 5 <= hour < 9:
                context = "Morning context: User typically checks emails and plans the day."
            elif 9 <= hour < 12:
                context = "Work mode: Peak productivity hours."
            elif 12 <= hour < 14:
                context = "Lunch time context: User may be returning from break."
            elif 14 <= hour < 17:
                context = "Afternoon context: Focus on execution and tasks."
            elif 17 <= hour < 20:
                context = "Evening transition: Wrapping up work or shifting to personal projects."
            elif 20 <= hour < 23:
                context = f"Evening context: User often works on personal projects in '{self.project_manager.current_project}'."
            else:
                context = "Late night context: User may be troubleshooting or ideating."
            
            # Add project context
            recent_cad = list(self.project_manager.get_current_project_path().rglob("*.stl"))
            if recent_cad:
                context += f" Recent CAD work detected: {len(recent_cad)} files."
            
            # Add proactive suggestions
            if self.proactive_monitor:
                triggered = len(self.proactive_monitor._triggered_rules)
                if triggered > 0:
                    context += f" {triggered} proactive notifications pending."
            
            if context:
                await self.session.send(input=f"System Context: {context}", end_of_turn=False)
                
                # Trigger anticipatory tool preparation based on context
                if hasattr(self, 'tool_handler') and self.tool_handler:
                    await self.tool_handler.anticipate_tools(context)
                
        except Exception as e:
            print(f"[NOVA DEBUG] [CONTEXT] Error injecting context: {e}")

    async def send_frame(self, frame_data):
        # Update the latest frame payload
        if isinstance(frame_data, bytes):
            b64_data = base64.b64encode(frame_data).decode('utf-8')
        else:
            b64_data = frame_data 

        # Store as the designated "next frame to send"
        self._latest_image_payload = {"mime_type": "image/jpeg", "data": b64_data}
        # No event signal needed - listen_audio pulls it

    async def send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send(input=msg, end_of_turn=False)

    async def listen_audio(self):
        mic_info = pya.get_default_input_device_info()

        # Resolve Input Device by Name if provided
        resolved_input_device_index = None
        
        if self.input_device_name:
            print(f"[NOVA] Attempting to find input device matching: '{self.input_device_name}'")
            count = pya.get_device_count()
            best_match = None
            
            for i in range(count):
                try:
                    info = pya.get_device_info_by_index(i)
                    if info['maxInputChannels'] > 0:
                        name = info.get('name', '')
                        # Simple case-insensitive check
                        if self.input_device_name.lower() in name.lower() or name.lower() in self.input_device_name.lower():
                             print(f"   Candidate {i}: {name}")
                             # Prioritize exact match or very close match if possible, but first match is okay for now
                             resolved_input_device_index = i
                             best_match = name
                             break
                except Exception:
                    continue
            
            if resolved_input_device_index is not None:
                print(f"[NOVA] Resolved input device '{self.input_device_name}' to index {resolved_input_device_index} ({best_match})")
            else:
                print(f"[NOVA] Could not find device matching '{self.input_device_name}'. Checking index...")

        # Fallback to index if Name lookup failed or wasn't provided
        if resolved_input_device_index is None and self.input_device_index is not None:
             try:
                 resolved_input_device_index = int(self.input_device_index)
                 print(f"[NOVA] Requesting Input Device Index: {resolved_input_device_index}")
             except ValueError:
                 print(f"[NOVA] Invalid device index '{self.input_device_index}', reverting to default.")
                 resolved_input_device_index = None

        if resolved_input_device_index is None:
             print("[NOVA] Using Default Input Device")

        try:
            self.audio_stream = await asyncio.to_thread(
                pya.open,
                format=FORMAT,
                channels=CHANNELS,
                rate=SEND_SAMPLE_RATE,
                input=True,
                input_device_index=resolved_input_device_index if resolved_input_device_index is not None else mic_info["index"],
                frames_per_buffer=CHUNK_SIZE,
            )
        except OSError as e:
            print(f"[NOVA] [ERR] Failed to open audio input stream: {e}")
            print("[NOVA] [WARN] Audio features will be disabled. Please check microphone permissions.")
            return

        if __debug__:
            kwargs = {"exception_on_overflow": False}
        else:
            kwargs = {}
        
        # VAD Constants
        VAD_THRESHOLD = 800 # Adj based on mic sensitivity (800 is conservative for 16-bit)
        SILENCE_DURATION = 0.5 # Seconds of silence to consider "done speaking"
        
        while True:
            if self.paused:
                await asyncio.sleep(0.1)
                continue

            try:
                data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
                
                # 1. Send Audio
                if self.out_queue:
                    await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
                
                # 2. VAD Logic for Video
                # rms = audioop.rms(data, 2)
                # Replacement for audioop.rms(data, 2)
                count = len(data) // 2
                if count > 0:
                    shorts = struct.unpack(f"<{count}h", data)
                    sum_squares = sum(s**2 for s in shorts)
                    rms = int(math.sqrt(sum_squares / count))
                else:
                    rms = 0
                
                if rms > VAD_THRESHOLD:
                    # Speech Detected
                    self._silence_start_time = None
                    
                    if not self._is_speaking:
                        # NEW Speech Utterance Started
                        self._is_speaking = True
                        print(f"[NOVA DEBUG] [VAD] Speech Detected (RMS: {rms}). Sending Video Frame.")
                        
                        # Proactive Context Injection - JARVIS-like awareness
                        # Inject context when user starts speaking
                        await self._inject_context_on_wake()
                        
                        # Send ONE frame
                        if self._latest_image_payload and self.out_queue:
                            await self.out_queue.put(self._latest_image_payload)
                        else:
                            print(f"[NOVA DEBUG] [VAD] No video frame available to send.")
                            
                else:
                    # Silence
                    if self._is_speaking:
                        if self._silence_start_time is None:
                            self._silence_start_time = time.time()
                        
                        elif time.time() - self._silence_start_time > SILENCE_DURATION:
                            # Silence confirmed, reset state
                            print(f"[NOVA DEBUG] [VAD] Silence detected. Resetting speech state.")
                            self._is_speaking = False
                            self._silence_start_time = None

            except Exception as e:
                print(f"Error reading audio: {e}")
                await asyncio.sleep(0.1)

    async def handle_cad_request(self, prompt):
        print(f"[NOVA DEBUG] [CAD] Background Task Started: handle_cad_request('{prompt}')")
        if self.on_cad_status:
            self.on_cad_status("generating")
            
        # Auto-create project if stuck in temp
        if self.project_manager.current_project == "temp":
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_project_name = f"Project_{timestamp}"
            print(f"[NOVA DEBUG] [CAD] Auto-creating project: {new_project_name}")
            
            success, msg = self.project_manager.create_project(new_project_name)
            if success:
                self.project_manager.switch_project(new_project_name)
                # Notify User (Optional, or rely on update)
                try:
                    await self.session.send(input=f"System Notification: Automatic Project Creation. Switched to new project '{new_project_name}'.", end_of_turn=False)
                    if self.on_project_update:
                         self.on_project_update(new_project_name)
                except Exception as e:
                    print(f"[NOVA DEBUG] [ERR] Failed to notify auto-project: {e}")

        # Get project cad folder path
        cad_output_dir = str(self.project_manager.get_current_project_path() / "cad")
        
        # Call the secondary agent with project path
        cad_data = await self.cad_agent.generate_prototype(prompt, output_dir=cad_output_dir)
        
        if cad_data:
            print(f"[NOVA DEBUG] [OK] CadAgent returned data successfully.")
            print(f"[NOVA DEBUG] [INFO] Data Check: {len(cad_data.get('vertices', []))} vertices, {len(cad_data.get('edges', []))} edges.")
            
            if self.on_cad_data:
                print(f"[NOVA DEBUG] [SEND] Dispatching data to frontend callback...")
                self.on_cad_data(cad_data)
                print(f"[NOVA DEBUG] [SENT] Dispatch complete.")
            
            # Save to Project
            if 'file_path' in cad_data:
                self.project_manager.save_cad_artifact(cad_data['file_path'], prompt)
            else:
                 # Fallback (legacy support)
                 self.project_manager.save_cad_artifact("output.stl", prompt)

            # Notify the model that the task is done - this triggers speech about completion
            completion_msg = "System Notification: CAD generation is complete! The 3D model is now displayed for the user. Let them know it's ready."
            try:
                await self.session.send(input=completion_msg, end_of_turn=True)
                print(f"[NOVA DEBUG] [NOTE] Sent completion notification to model.")
            except Exception as e:
                 print(f"[NOVA DEBUG] [ERR] Failed to send completion notification: {e}")

        else:
            print(f"[NOVA DEBUG] [ERR] CadAgent returned None.")
            # Optionally notify failure
            try:
                await self.session.send(input="System Notification: CAD generation failed.", end_of_turn=True)
            except Exception:
                pass



    async def handle_write_file(self, path, content):
        print(f"[NOVA DEBUG] [FS] Writing file: '{path}'")
        
        # Auto-create project if stuck in temp
        if self.project_manager.current_project == "temp":
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_project_name = f"Project_{timestamp}"
            print(f"[NOVA DEBUG] [FS] Auto-creating project: {new_project_name}")
            
            success, msg = self.project_manager.create_project(new_project_name)
            if success:
                self.project_manager.switch_project(new_project_name)
                # Notify User
                try:
                    await self.session.send(input=f"System Notification: Automatic Project Creation. Switched to new project '{new_project_name}'.", end_of_turn=False)
                    if self.on_project_update:
                         self.on_project_update(new_project_name)
                except Exception as e:
                    print(f"[NOVA DEBUG] [ERR] Failed to notify auto-project: {e}")
        
        # Force path to be relative to current project
        # If absolute path is provided, we try to strip it or just ignore it and use basename
        filename = os.path.basename(path)
        
        # If path contained subdirectories (e.g. "backend/server.py"), preserving that structure might be desired IF it's within the project.
        # But for safety, and per user request to "always create the file in the project", 
        # we will root it in the current project path.
        
        current_project_path = self.project_manager.get_current_project_path()
        final_path = current_project_path / filename # Simple flat structure for now, or allow relative?
        
        # If the user specifically wanted a subfolder, they might have provided "sub/file.txt".
        # Let's support relative paths if they don't start with /
        if not os.path.isabs(path):
             final_path = current_project_path / path
        
        print(f"[NOVA DEBUG] [FS] Resolved path: '{final_path}'")

        try:
            # Ensure parent exists
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            with open(final_path, 'w', encoding='utf-8') as f:
                f.write(content)
            result = f"File '{final_path.name}' written successfully to project '{self.project_manager.current_project}'."
        except Exception as e:
            result = f"Failed to write file '{path}': {str(e)}"

        print(f"[NOVA DEBUG] [FS] Result: {result}")
        try:
             await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
             print(f"[NOVA DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_read_directory(self, path):
        print(f"[NOVA DEBUG] [FS] Reading directory: '{path}'")
        try:
            if not os.path.exists(path):
                result = f"Directory '{path}' does not exist."
            else:
                items = os.listdir(path)
                result = f"Contents of '{path}': {', '.join(items)}"
        except Exception as e:
            result = f"Failed to read directory '{path}': {str(e)}"

        print(f"[NOVA DEBUG] [FS] Result: {result}")
        try:
             await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
             print(f"[NOVA DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_read_file(self, path):
        print(f"[NOVA DEBUG] [FS] Reading file: '{path}'")
        try:
            if not os.path.exists(path):
                result = f"File '{path}' does not exist."
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                result = f"Content of '{path}':\n{content}"
        except Exception as e:
            result = f"Failed to read file '{path}': {str(e)}"

        print(f"[NOVA DEBUG] [FS] Result: {result}")
        try:
             await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
             print(f"[NOVA DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_web_agent_request(self, prompt):
        print(f"[NOVA DEBUG] [WEB] Web Agent Task: '{prompt}'")
        
        async def update_frontend(image_b64, log_text):
            if self.on_web_data:
                 self.on_web_data({"image": image_b64, "log": log_text})
                 
        # Run the web agent and wait for it to return
        result = await self.web_agent.run_task(prompt, update_callback=update_frontend)
        print(f"[NOVA DEBUG] [WEB] Web Agent Task Returned: {result}")
        
        # Send the final result back to the main model
        try:
             await self.session.send(input=f"System Notification: Web Agent has finished.\nResult: {result}", end_of_turn=True)
        except Exception as e:
             print(f"[NOVA DEBUG] [ERR] Failed to send web agent result to model: {e}")

    def _create_speak_callback(self) -> callable:
        """Create a thread-safe speak callback for background task execution."""
        def speak_callback(message: str):
            try:
                # Use thread-safe scheduling for background thread compatibility
                main_loop = getattr(self, '_event_loop', None)
                if main_loop:
                    asyncio.run_coroutine_threadsafe(
                        self.session.send(input=f"System Notification: Agent update - {message}", end_of_turn=False),
                        main_loop
                    )
                else:
                    # Fallback - try to get running loop
                    try:
                        loop = asyncio.get_running_loop()
                        asyncio.run_coroutine_threadsafe(
                            self.session.send(input=f"System Notification: Agent update - {message}", end_of_turn=False),
                            loop
                        )
                    except RuntimeError:
                        print(f"[NOVA DEBUG] [AGENT] Cannot send speak: no event loop available")
            except Exception as e:
                print(f"[NOVA DEBUG] [AGENT] Failed to send speak message: {e}")
        return speak_callback

    async def handle_execute_task(self, goal: str, priority: str = "normal"):
        """Submit a task to the agent task queue for background execution (fire-and-forget)."""
        print(f"[NOVA DEBUG] [AGENT] Task submission: '{goal[:60]}...' (priority: {priority})")

        # Map priority string to TaskPriority enum
        priority_map = {
            "high": TaskPriority.HIGH,
            "normal": TaskPriority.NORMAL,
            "low": TaskPriority.LOW
        }
        task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)

        speak_callback = self._create_speak_callback()

        # Submit to task queue
        task_id = self.task_queue.submit(
            goal=goal,
            priority=task_priority,
            speak=speak_callback,
            on_complete=self._on_task_complete
        )

        print(f"[NOVA DEBUG] [AGENT] Task queued with ID: {task_id}")

        # Notify the model that the task has been submitted
        try:
            await self.session.send(
                input=f"System Notification: Task submitted (ID: {task_id}). The agent will work on: {goal}. You'll be notified when it's complete.",
                end_of_turn=True
            )
        except Exception as e:
            print(f"[NOVA DEBUG] [ERR] Failed to send task submission notification: {e}")

    async def handle_execute_task_async(self, goal: str, priority: str = "normal", timeout: float = 120) -> str:
        """
        Submit a task and await its completion (async/await pattern).
        
        Args:
            goal: Natural language goal for the agent
            priority: "high", "normal", or "low"
            timeout: Maximum seconds to wait for completion
            
        Returns:
            Task result string
            
        Raises:
            asyncio.TimeoutError: If task exceeds timeout
            RuntimeError: If task fails
        """
        print(f"[NOVA DEBUG] [AGENT] Async task submission: '{goal[:60]}...' (priority: {priority})")

        from agent.task_queue import TaskPriority
        
        priority_map = {
            "high": TaskPriority.HIGH,
            "normal": TaskPriority.NORMAL,
            "low": TaskPriority.LOW
        }
        task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)
        speak_callback = self._create_speak_callback()

        # Submit async and await result
        task_id = await self.task_queue.submit_async(
            goal=goal,
            priority=task_priority,
            speak=speak_callback
        )
        
        print(f"[NOVA DEBUG] [AGENT] Async task queued: {task_id}, awaiting result...")

        try:
            result = await self.task_queue.get_result_async(task_id, timeout=timeout)
            print(f"[NOVA DEBUG] [AGENT] Async task completed: {task_id}")
            return result
        except asyncio.TimeoutError:
            print(f"[NOVA DEBUG] [AGENT] Async task timed out: {task_id}")
            raise
        except Exception as e:
            print(f"[NOVA DEBUG] [AGENT] Async task failed: {task_id} - {e}")
            raise

    def _on_task_complete(self, task_id: str, result: str):
        """Callback when an agent task completes."""
        print(f"[NOVA DEBUG] [AGENT] Task {task_id} completed: {result[:100]}")
        try:
            # Use thread-safe scheduling for background thread compatibility
            main_loop = getattr(self, '_event_loop', None)
            if main_loop:
                asyncio.run_coroutine_threadsafe(
                    self.session.send(
                        input=f"System Notification: Task {task_id} completed. Result: {result}",
                        end_of_turn=True
                    ),
                    main_loop
                )
            else:
                print(f"[NOVA DEBUG] [AGENT] Cannot notify task completion: no event loop available")
        except Exception as e:
            print(f"[NOVA DEBUG] [ERR] Failed to send task completion: {e}")

    async def receive_audio(self):
        "Background task to reads from the websocket and write pcm chunks to the output queue"
        try:
            while True:
                turn = self.session.receive()
                async for response in turn:
                    # 1. Handle Audio Data
                    if data := response.data:
                        self.audio_in_queue.put_nowait(data)
                        # NOTE: 'continue' removed here to allow processing transcription/tools in same packet

                    # 2. Handle Transcription (User & Model)
                    if response.server_content:
                        if response.server_content.input_transcription:
                            transcript = response.server_content.input_transcription.text
                            if transcript:
                                # Skip if this is an exact duplicate event
                                if transcript != self._last_input_transcription:
                                    # Calculate delta (Gemini may send cumulative or chunk-based text)
                                    delta = transcript
                                    if transcript.startswith(self._last_input_transcription):
                                        delta = transcript[len(self._last_input_transcription):]
                                    self._last_input_transcription = transcript
                                    
                                    # Only send if there's new text
                                    if delta:
                                        # User is speaking, so interrupt model playback!
                                        self.clear_audio_queue()

                                        # Send to frontend (Streaming)
                                        if self.on_transcription:
                                             self.on_transcription({"sender": "User", "text": delta})
                                        
                                        # Buffer for Logging
                                        if self.chat_buffer["sender"] != "User":
                                            # Flush previous if exists
                                            if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
                                                self.flush_chat()
                                            # Start new
                                            self.chat_buffer = {"sender": "User", "text": delta}
                                        else:
                                            # Append
                                            self.chat_buffer["text"] += delta
                        
                        if response.server_content.output_transcription:
                            transcript = response.server_content.output_transcription.text
                            if transcript:
                                # Skip if this is an exact duplicate event
                                if transcript != self._last_output_transcription:
                                    # Calculate delta (Gemini may send cumulative or chunk-based text)
                                    delta = transcript
                                    if transcript.startswith(self._last_output_transcription):
                                        delta = transcript[len(self._last_output_transcription):]
                                    self._last_output_transcription = transcript
                                    
                                    # Only send if there's new text
                                    if delta:
                                        # Send to frontend (Streaming)
                                        if self.on_transcription:
                                             self.on_transcription({"sender": "ADA", "text": delta})
                                        
                                        # Buffer for Logging
                                        if self.chat_buffer["sender"] != "ADA":
                                            # Flush previous
                                            if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
                                                self.flush_chat()
                                            # Start new
                                            self.chat_buffer = {"sender": "ADA", "text": delta}
                                        else:
                                            # Append
                                            self.chat_buffer["text"] += delta
                        
                        # Flush buffer on turn completion if needed, 
                        # but usually better to wait for sender switch or explicit end.
                        # We can also check turn_complete signal if available in response.server_content.model_turn etc

                    # 3. Handle Tool Calls
                    if response.tool_call:
                        print("The tool was called")
                        function_responses = []
                        for fc in response.tool_call.function_calls:
                            # Check Permissions (Default to True if not set)
                            permission_value = self.permissions.get(fc.name)
                            confirmation_required = permission_value if permission_value is not None else True
                            
                            print(f"[NOVA DEBUG] [PERM] Tool '{fc.name}': permission_value={permission_value}, confirmation_required={confirmation_required}")
                            
                            if not confirmation_required:
                                print(f"[NOVA DEBUG] [TOOL] Permission check: '{fc.name}' -> AUTO-ALLOW")
                            else:
                                # Confirmation Logic
                                if self.on_tool_confirmation:
                                    import uuid
                                    request_id = str(uuid.uuid4())
                                    print(f"[NOVA DEBUG] [STOP] Requesting confirmation for '{fc.name}' (ID: {request_id})")
                                    
                                    future = asyncio.Future()
                                    self._pending_confirmations[request_id] = future
                                    
                                    self.on_tool_confirmation({
                                        "id": request_id, 
                                        "tool": fc.name, 
                                        "args": fc.args
                                    })
                                    
                                    try:
                                        confirmed = await future
                                    finally:
                                        self._pending_confirmations.pop(request_id, None)

                                    print(f"[NOVA DEBUG] [CONFIRM] Request {request_id} resolved. Confirmed: {confirmed}")

                                    if not confirmed:
                                        print(f"[NOVA DEBUG] [DENY] Tool call '{fc.name}' denied by user.")
                                        function_response = types.FunctionResponse(
                                            id=fc.id,
                                            name=fc.name,
                                            response={"result": "User denied the request to use this tool."}
                                        )
                                        function_responses.append(function_response)
                                        continue

                            # Delegate to ToolHandler
                            function_response = await self.tool_handler.handle_tool(fc)
                            function_responses.append(function_response)
                            
                        if function_responses:
                            await self.session.send_tool_response(function_responses=function_responses)
                
                # Turn/Response Loop Finished
                self.flush_chat()

                while not self.audio_in_queue.empty():
                    self.audio_in_queue.get_nowait()
        except Exception as e:
            error_msg = str(e)
            print(f"Error in receive_audio: {error_msg}")
            
            # Handle specific API/WebSocket errors
            if "1011" in error_msg or "CANCELLED" in error_msg or "ConnectionClosedError" in error_msg:
                print("[NOVA DEBUG] [RECV] Gemini API session error - will reconnect")
                # Don't print full traceback for known transient errors
                # Re-raise to trigger outer reconnect loop
                raise e
            elif "timeout" in error_msg.lower() or "temporarily unavailable" in error_msg.lower():
                print("[NOVA DEBUG] [RECV] Transient error - retrying...")
                # Brief pause before reconnection attempt
                await asyncio.sleep(1)
                raise e
            else:
                # Unknown error - print full traceback
                traceback.print_exc()
                raise e

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
            output_device_index=self.output_device_index,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            if self.on_audio_data:
                self.on_audio_data(bytestream)
            await asyncio.to_thread(stream.write, bytestream)

    async def switch_video_source(self, camera_id: int = 0, camera_url: str = None):
        """
        Switch between multiple camera feeds.
        Supports: webcam (0, 1, 2...), IP cameras (rtsp://...), phone cameras
        
        Args:
            camera_id: Webcam index (0 for default)
            camera_url: Optional IP camera URL (rtsp://, http://)
        """
        try:
            # Release current capture if exists
            if hasattr(self, '_cap') and self._cap is not None:
                self._cap.release()
            
            if camera_url:
                # IP camera or phone camera via URL
                self._cap = await asyncio.to_thread(cv2.VideoCapture, camera_url)
                self.current_camera = f"IP:{camera_url}"
            else:
                # Standard webcam
                self._cap = await asyncio.to_thread(cv2.VideoCapture, camera_id, cv2.CAP_AVFOUNDATION)
                self.current_camera = f"WEBCAM:{camera_id}"
            
            # Test capture
            ret, frame = self._cap.read()
            if not ret:
                print(f"[NOVA DEBUG] Failed to switch to camera {camera_id}")
                return False
            
            print(f"[NOVA DEBUG] Switched to camera: {self.current_camera}")
            return True
            
        except Exception as e:
            print(f"[NOVA DEBUG] Error switching camera: {e}")
            return False
    
    async def get_frames(self):
        # Initialize capture if not exists
        if not hasattr(self, '_cap') or self._cap is None:
            self._cap = await asyncio.to_thread(cv2.VideoCapture, 0, cv2.CAP_AVFOUNDATION)
            self.current_camera = "WEBCAM:0"
        
        try:
            while True:
                if self.paused:
                    await asyncio.sleep(0.1)
                    continue
                frame = await asyncio.to_thread(self._get_frame, self._cap)
                if frame is None:
                    break
                await asyncio.sleep(1.0)
                if self.out_queue:
                    await self.out_queue.put(frame)
        finally:
            if hasattr(self, '_cap') and self._cap is not None:
                self._cap.release()

    def _get_frame(self, cap):
        ret, frame = cap.read()
        if not ret:
            return None
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(frame_rgb)
        img.thumbnail([1024, 1024])
        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)
        image_bytes = image_io.read()
        return {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()}

    async def _get_screen(self):
        pass 
    async def get_screen(self):
         pass

    async def run(self, start_message=None):
        # Store reference to the main event loop for thread-safe callbacks
        self._event_loop = asyncio.get_event_loop()
        
        retry_delay = 1
        is_reconnect = False
        
        while not self.stop_event.is_set():
            try:
                print(f"[NOVA DEBUG] [CONNECT] Connecting to Gemini Live API...")
                async with (
                    client.aio.live.connect(model=MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session

                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue = asyncio.Queue(maxsize=10)

                    tg.create_task(self.send_realtime())
                    tg.create_task(self.listen_audio())
                    # tg.create_task(self._process_video_queue()) # Removed in favor of VAD

                    if self.video_mode == "camera":
                        tg.create_task(self.get_frames())
                    elif self.video_mode == "screen":
                        tg.create_task(self.get_screen())

                    tg.create_task(self.receive_audio())
                    tg.create_task(self.play_audio())

                    # Handle Startup vs Reconnect Logic
                    if not is_reconnect:
                        if start_message:
                            print(f"[NOVA DEBUG] [INFO] Sending start message: {start_message}")
                            await self.session.send(input=start_message, end_of_turn=True)
                        
                        # Send full conversation memory history to Gemini
                        print(f"[NOVA DEBUG] [STARTUP] Loading conversation memory...")
                        all_conversations = self.memory_manager.recall_recent(context="conversations", limit=None)
                        if all_conversations:
                            memory_msg = "Previous conversation history:\n\n"
                            for entry in all_conversations:
                                sender = entry.get('sender', 'Unknown')
                                text = entry.get('text', '')
                                dt = entry.get('datetime', '')
                                memory_msg += f"[{dt}] {sender}: {text}\n"
                            memory_msg += "\nUse this context to maintain continuity with the user."
                            print(f"[NOVA DEBUG] [STARTUP] Sending {len(all_conversations)} conversation entries to Gemini...")
                            await self.session.send(input=memory_msg, end_of_turn=True)
                        
                        # Start Proactive Monitor
                        print(f"[NOVA DEBUG] [STARTUP] Starting proactive monitoring...")
                        self.proactive_monitor.start()
                        
                        # Sync Project State
                        if self.on_project_update and self.project_manager:
                            self.on_project_update(self.project_manager.current_project)
                    
                    else:
                        print(f"[NOVA DEBUG] [RECONNECT] Connection restored.")
                        # Restore Context
                        print(f"[NOVA DEBUG] [RECONNECT] Fetching recent chat history to restore context...")
                        history = self.project_manager.get_recent_chat_history(limit=10)
                        
                        context_msg = "System Notification: Connection was lost and just re-established. Here is the recent chat history to help you resume seamlessly:\n\n"
                        for entry in history:
                            sender = entry.get('sender', 'Unknown')
                            text = entry.get('text', '')
                            context_msg += f"[{sender}]: {text}\n"
                        
                        context_msg += "\nPlease acknowledge the reconnection to the user (e.g. 'I lost connection for a moment, but I'm back...') and resume what you were doing."
                        
                        print(f"[NOVA DEBUG] [RECONNECT] Sending restoration context to model...")
                        await self.session.send(input=context_msg, end_of_turn=True)

                    # Reset retry delay on successful connection
                    retry_delay = 1
                    
                    # Wait until stop event, or until the session task group exits (which happens on error)
                    # Actually, the TaskGroup context manager will exit if any tasks fail/cancel.
                    # We need to keep this block alive.
                    # The original code just waited on stop_event, but that doesn't account for session death.
                    # We should rely on the TaskGroup raising an exception when subtasks fail (like receive_audio).
                    
                    # However, since receive_audio is a task in the group, if it crashes (connection closed), 
                    # the group will cancel others and exit. We catch that exit below.
                    
                    # We can await stop_event, but if the connection dies, receive_audio crashes -> group closes -> we exit `async with` -> restart loop.
                    # To ensure we don't block indefinitely if connection dies silently (unlikely with receive_audio), we just wait.
                    await self.stop_event.wait()

            except asyncio.CancelledError:
                print(f"[NOVA DEBUG] [STOP] Main loop cancelled.")
                break
                
            except Exception as e:
                # This catches the ExceptionGroup from TaskGroup or direct exceptions
                print(f"[NOVA DEBUG] [ERR] Connection Error: {e}")
                
                if self.stop_event.is_set():
                    break
                
                print(f"[NOVA DEBUG] [RETRY] Reconnecting in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 10) # Exponential backoff capped at 10s
                is_reconnect = True # Next loop will be a reconnect
                
            finally:
                # Cleanup before retry
                if hasattr(self, 'audio_stream') and self.audio_stream:
                    try:
                        self.audio_stream.close()
                    except: 
                        pass

def get_input_devices():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    devices = []
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            devices.append((i, p.get_device_info_by_host_api_device_index(0, i).get('name')))
    p.terminate()
    return devices

def get_output_devices():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    devices = []
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxOutputChannels')) > 0:
            devices.append((i, p.get_device_info_by_host_api_device_index(0, i).get('name')))
    p.terminate()
    return devices

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        help="pixels to stream from",
        choices=["camera", "screen", "none"],
    )
    args = parser.parse_args()
    main = AudioLoop(video_mode=args.mode)
    asyncio.run(main.run())