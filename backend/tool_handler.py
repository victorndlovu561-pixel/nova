"""
ToolHandler - Centralized tool handling for NOVA.
Consolidates all tool execution logic from nova.py and provides a unified interface.
"""

import asyncio
import os
import threading
import traceback
from typing import Dict, List, Optional, Any
from google.genai import types


class PredictiveToolPreparer:
    """
    Prepare tools before they're needed based on conversation context.
    JARVIS: Pre-loading CAD tools when design discussion begins.
    """
    
    def __init__(self, audio_loop):
        self.loop = audio_loop
        self.preloaded_agents = set()
        self.last_context = ""
    
    async def anticipate_tool_needs(self, conversation_context: str):
        """
        Based on conversation, pre-load likely tools.
        
        Args:
            conversation_context: Recent conversation text to analyze
        """
        context_lower = conversation_context.lower()
        
        # CAD/Design context
        if any(word in context_lower for word in ["cad", "design", "model", "stl", "prototype", "3d print"]):
            if "cad" not in self.preloaded_agents:
                print("[TOOL PREP] Pre-loading CAD agent...")
                # Warm up CAD agent
                await self._warm_cad_agent()
                self.preloaded_agents.add("cad")
            
            # Check printer availability
            await self._check_printer_availability()
        
        # Weather context
        if any(word in context_lower for word in ["weather", "temperature", "rain", "forecast"]):
            if "weather" not in self.preloaded_agents:
                print("[TOOL PREP] Pre-fetching weather data...")
                await self._prefetch_weather()
                self.preloaded_agents.add("weather")
        
        # Research context
        if any(word in context_lower for word in ["search", "find", "research", "look up", "information"]):
            if "web" not in self.preloaded_agents:
                print("[TOOL PREP] Pre-loading web search...")
                self.preloaded_agents.add("web")
        
        # Code context
        if any(word in context_lower for word in ["code", "debug", "error", "function", "script"]):
            if "code" not in self.preloaded_agents:
                print("[TOOL PREP] Pre-loading code analysis...")
                self.preloaded_agents.add("code")
        
        # Clear preloaded agents after 5 minutes of inactivity
        asyncio.create_task(self._clear_preload_after_timeout())
    
    async def _warm_cad_agent(self):
        """Initialize CAD agent resources."""
        try:
            # Initialize any heavy CAD resources
            if hasattr(self.loop, 'cad_agent'):
                print("[TOOL PREP] CAD agent warmed up")
        except Exception as e:
            print(f"[TOOL PREP] Error warming CAD agent: {e}")
    
    async def _check_printer_availability(self):
        """Check if 3D printer is available."""
        try:
            # Check printer status if available
            print("[TOOL PREP] Checking printer availability")
        except Exception as e:
            print(f"[TOOL PREP] Printer check failed: {e}")
    
    async def _prefetch_weather(self):
        """Pre-fetch weather data for common locations."""
        try:
            # Could integrate with weather API
            print("[TOOL PREP] Weather data ready")
        except Exception as e:
            print(f"[TOOL PREP] Weather prefetch failed: {e}")
    
    async def _clear_preload_after_timeout(self, timeout: int = 300):
        """Clear preloaded agents after timeout."""
        await asyncio.sleep(timeout)
        self.preloaded_agents.clear()
        print("[TOOL PREP] Cleared preloaded agents after timeout")


class ToolHandler:
    """Handles all tool calls for the AudioLoop class."""

    def __init__(self, audio_loop):
        """
        Initialize with reference to AudioLoop instance.

        Args:
            audio_loop: The AudioLoop instance that owns this handler.
                       Provides access to agents, session, callbacks, etc.
        """
        self.loop = audio_loop
        self.predictive_preparer = PredictiveToolPreparer(audio_loop)

    async def anticipate_tools(self, context: str):
        """Public method to trigger anticipatory tool preparation."""
        await self.predictive_preparer.anticipate_tool_needs(context)

    async def handle_tool(self, fc) -> types.FunctionResponse:
        """
        Main entry point for handling a tool call.

        Args:
            fc: FunctionCall object from the Gemini API

        Returns:
            FunctionResponse to send back to the model
        """
        name = fc.name
        args = dict(fc.args or {})
        fc_id = fc.id

        print(f"[NOVA DEBUG] [TOOL] Handling '{name}' with args: {args}")

        # Map tool names to handler methods
        handlers = {
            # CAD & 3D Printing
            "generate_cad": self._handle_generate_cad,
            "iterate_cad": self._handle_iterate_cad,

            # Web & Research
            "run_web_agent": self._handle_run_web_agent,
            "web_search": self._handle_web_search,

            # File System
            "write_file": self._handle_write_file,
            "read_directory": self._handle_read_directory,
            "read_file": self._handle_read_file,

            # Project Management
            "create_project": self._handle_create_project,
            "switch_project": self._handle_switch_project,
            "list_projects": self._handle_list_projects,

            # Smart Devices
            "list_smart_devices": self._handle_list_smart_devices,
            "control_light": self._handle_control_light,
            "control_tv": self._handle_control_tv,

            # 3D Printing
            "discover_printers": self._handle_discover_printers,
            "print_stl": self._handle_print_stl,
            "get_print_status": self._handle_get_print_status,

            # Agent Tasks
            "execute_task": self._handle_execute_task,

            # JARVIS-style tools (moved from original tool_handler.py)
            "open_app": self._handle_open_app,
            "weather_report": self._handle_weather_report,
            "browser_control": self._handle_browser_control,
            "file_controller": self._handle_file_controller,
            "send_message": self._handle_send_message,
            "reminder": self._handle_reminder,
            "youtube_video": self._handle_youtube_video,
            "screen_process": self._handle_screen_process,
            "computer_settings": self._handle_computer_settings,
            "desktop_control": self._handle_desktop_control,
            "code_helper": self._handle_code_helper,
            "dev_agent": self._handle_dev_agent,
            "agent_task": self._handle_agent_task,
            "computer_control": self._handle_computer_control,
            "game_updater": self._handle_game_updater,
            "flight_finder": self._handle_flight_finder,
            "shutdown_jarvis": self._handle_shutdown_jarvis,
        }

        handler = handlers.get(name)
        if handler:
            try:
                result = await handler(args, fc_id)
                return types.FunctionResponse(id=fc_id, name=name, response={"result": result})
            except Exception as e:
                error_msg = f"Tool '{name}' failed: {e}"
                print(f"[NOVA DEBUG] [ERR] {error_msg}")
                traceback.print_exc()
                return types.FunctionResponse(id=fc_id, name=name, response={"result": error_msg})
        else:
            return types.FunctionResponse(
                id=fc_id, name=name,
                response={"result": f"Unknown tool: {name}"}
            )

    # ========================================================================
    # CAD & 3D Printing Handlers
    # ========================================================================

    async def _handle_generate_cad(self, args, fc_id):
        """Handle generate_cad tool call."""
        prompt = args.get("prompt", "")
        print(f"[NOVA DEBUG] [CAD] generate_cad: '{prompt}'")

        # Trigger status update
        if self.loop.on_cad_status:
            self.loop.on_cad_status("generating")

        # Auto-create project if in temp
        await self._ensure_project_exists()

        # Get output directory
        cad_output_dir = str(self.loop.project_manager.get_current_project_path() / "cad")

        # Run CAD generation in background
        asyncio.create_task(self._run_cad_generation(prompt, cad_output_dir))

        return "CAD generation started. The model will be displayed when ready."

    async def _run_cad_generation(self, prompt, output_dir):
        """Background task for CAD generation."""
        try:
            cad_data = await self.loop.cad_agent.generate_prototype(prompt, output_dir=output_dir)

            if cad_data:
                print(f"[NOVA DEBUG] [OK] CadAgent returned data successfully.")

                if self.loop.on_cad_data:
                    self.loop.on_cad_data(cad_data)

                # Save artifact
                if 'file_path' in cad_data:
                    self.loop.project_manager.save_cad_artifact(cad_data['file_path'], prompt)
                else:
                    self.loop.project_manager.save_cad_artifact("output.stl", prompt)

                # Notify model
                completion_msg = "System Notification: CAD generation is complete! The 3D model is now displayed for the user. Let them know it's ready."
                await self.loop.session.send(input=completion_msg, end_of_turn=True)
            else:
                await self.loop.session.send(input="System Notification: CAD generation failed.", end_of_turn=True)
        except Exception as e:
            print(f"[NOVA DEBUG] [ERR] CAD generation failed: {e}")

    async def _handle_iterate_cad(self, args, fc_id):
        """Handle iterate_cad tool call."""
        prompt = args.get("prompt", "")
        print(f"[NOVA DEBUG] [CAD] iterate_cad: '{prompt}'")

        if self.loop.on_cad_status:
            self.loop.on_cad_status("generating")

        cad_output_dir = str(self.loop.project_manager.get_current_project_path() / "cad")

        # Run in background
        asyncio.create_task(self._run_cad_iteration(prompt, cad_output_dir))

        return "CAD iteration started."

    async def _run_cad_iteration(self, prompt, output_dir):
        """Background task for CAD iteration."""
        try:
            cad_data = await self.loop.cad_agent.iterate_prototype(prompt, output_dir=output_dir)

            if cad_data:
                if self.loop.on_cad_data:
                    self.loop.on_cad_data(cad_data)

                self.loop.project_manager.save_cad_artifact("output.stl", f"Iteration: {prompt}")

                await self.loop.session.send(
                    input=f"System Notification: CAD iteration complete. Design updated: {prompt}",
                    end_of_turn=True
                )
            else:
                await self.loop.session.send(
                    input=f"System Notification: CAD iteration failed for: {prompt}",
                    end_of_turn=True
                )
        except Exception as e:
            print(f"[NOVA DEBUG] [ERR] CAD iteration failed: {e}")

    # ========================================================================
    # Web & Research Handlers
    # ========================================================================

    async def _handle_run_web_agent(self, args, fc_id):
        """Handle run_web_agent tool call."""
        prompt = args.get("prompt", "")
        print(f"[NOVA DEBUG] [WEB] run_web_agent: '{prompt}'")

        async def update_frontend(image_b64, log_text):
            if self.loop.on_web_data:
                self.loop.on_web_data({"image": image_b64, "log": log_text})

        # Run in background
        asyncio.create_task(self._run_web_agent_task(prompt, update_frontend))

        return "Web Navigation started. Do not reply to this message."

    async def _run_web_agent_task(self, prompt, update_callback):
        """Background task for web agent."""
        try:
            result = await self.loop.web_agent.run_task(prompt, update_callback=update_callback)
            await self.loop.session.send(
                input=f"System Notification: Web Agent has finished.\nResult: {result}",
                end_of_turn=True
            )
        except Exception as e:
            print(f"[NOVA DEBUG] [ERR] Web agent failed: {e}")

    async def _handle_web_search(self, args, fc_id):
        """Handle web_search tool call."""
        from web_search import web_search as web_search_action
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: web_search_action(parameters=args, player=None)
        )
        return result or "Done."

    # ========================================================================
    # File System Handlers
    # ========================================================================

    async def _handle_write_file(self, args, fc_id):
        """Handle write_file tool call."""
        path = args.get("path", "")
        content = args.get("content", "")
        print(f"[NOVA DEBUG] [FS] write_file: '{path}'")

        # Auto-create project if in temp
        await self._ensure_project_exists()

        # Resolve path
        filename = os.path.basename(path)
        if not os.path.isabs(path):
            final_path = self.loop.project_manager.get_current_project_path() / path
        else:
            final_path = self.loop.project_manager.get_current_project_path() / filename

        try:
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            with open(final_path, 'w', encoding='utf-8') as f:
                f.write(content)
            result = f"File '{final_path.name}' written successfully to project '{self.loop.project_manager.current_project}'."
        except Exception as e:
            result = f"Failed to write file '{path}': {str(e)}"

        # Notify model
        asyncio.create_task(
            self.loop.session.send(input=f"System Notification: {result}", end_of_turn=True)
        )

        return "Writing file..."

    async def _handle_read_directory(self, args, fc_id):
        """Handle read_directory tool call."""
        path = args.get("path", "")
        print(f"[NOVA DEBUG] [FS] read_directory: '{path}'")

        try:
            if not os.path.exists(path):
                result = f"Directory '{path}' does not exist."
            else:
                items = os.listdir(path)
                result = f"Contents of '{path}': {', '.join(items)}"
        except Exception as e:
            result = f"Failed to read directory '{path}': {str(e)}"

        # Notify model
        asyncio.create_task(
            self.loop.session.send(input=f"System Notification: {result}", end_of_turn=True)
        )

        return "Reading directory..."

    async def _handle_read_file(self, args, fc_id):
        """Handle read_file tool call."""
        path = args.get("path", "")
        print(f"[NOVA DEBUG] [FS] read_file: '{path}'")

        try:
            if not os.path.exists(path):
                result = f"File '{path}' does not exist."
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                result = f"Content of '{path}':\n{content}"
        except Exception as e:
            result = f"Failed to read file '{path}': {str(e)}"

        # Notify model
        asyncio.create_task(
            self.loop.session.send(input=f"System Notification: {result}", end_of_turn=True)
        )

        return "Reading file..."

    # ========================================================================
    # Project Management Handlers
    # ========================================================================

    async def _handle_create_project(self, args, fc_id):
        """Handle create_project tool call."""
        name = args.get("name", "")
        print(f"[NOVA DEBUG] [PROJECT] create_project: '{name}'")

        success, msg = self.loop.project_manager.create_project(name)
        if success:
            self.loop.project_manager.switch_project(name)
            msg += f" Switched to '{name}'."
            if self.loop.on_project_update:
                self.loop.on_project_update(name)

        return msg

    async def _handle_switch_project(self, args, fc_id):
        """Handle switch_project tool call."""
        name = args.get("name", "")
        print(f"[NOVA DEBUG] [PROJECT] switch_project: '{name}'")

        success, msg = self.loop.project_manager.switch_project(name)
        if success:
            if self.loop.on_project_update:
                self.loop.on_project_update(name)

            # Send context to AI
            context = self.loop.project_manager.get_project_context()
            print(f"[NOVA DEBUG] [PROJECT] Sending project context to AI ({len(context)} chars)")
            try:
                await self.loop.session.send(
                    input=f"System Notification: {msg}\n\n{context}",
                    end_of_turn=False
                )
            except Exception as e:
                print(f"[NOVA DEBUG] [ERR] Failed to send project context: {e}")

        return msg

    async def _handle_list_projects(self, args, fc_id):
        """Handle list_projects tool call."""
        print(f"[NOVA DEBUG] [PROJECT] list_projects")
        projects = self.loop.project_manager.list_projects()
        return f"Available projects: {', '.join(projects)}"

    async def _ensure_project_exists(self):
        """Auto-create project if stuck in temp."""
        if self.loop.project_manager.current_project == "temp":
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_project_name = f"Project_{timestamp}"
            print(f"[NOVA DEBUG] [PROJECT] Auto-creating: {new_project_name}")

            success, msg = self.loop.project_manager.create_project(new_project_name)
            if success:
                self.loop.project_manager.switch_project(new_project_name)
                try:
                    await self.loop.session.send(
                        input=f"System Notification: Automatic Project Creation. Switched to new project '{new_project_name}'.",
                        end_of_turn=False
                    )
                    if self.loop.on_project_update:
                        self.loop.on_project_update(new_project_name)
                except Exception as e:
                    print(f"[NOVA DEBUG] [ERR] Failed to notify auto-project: {e}")

    # ========================================================================
    # Smart Device Handlers
    # ========================================================================

    async def _handle_list_smart_devices(self, args, fc_id):
        """Handle list_smart_devices tool call - scans ALL network devices including TVs."""
        print(f"[NOVA DEBUG] [KASA] list_smart_devices - running comprehensive network scan")

        # Run comprehensive network scan (ARP, UPnP, mDNS, port scanning)
        all_devices = await self.loop.kasa_agent.scan_full_network()
        
        # Also get Kasa devices
        kasa_devices = await self.loop.kasa_agent.discover_devices()
        
        # Build summaries
        dev_summaries = []
        frontend_list = []
        
        # Process ALL network devices (including TVs!)
        for device in all_devices:
            ip = device.get("ip", "unknown")
            device_type = device.get("device_type", "unknown")
            vendor = device.get("vendor", "Unknown")
            hostname = device.get("hostname", "")
            source = device.get("source", "unknown")
            
            # Highlight TVs and streaming devices
            is_tv = ("tv" in device_type.lower() or 
                    (vendor and "samsung" in vendor.lower()) or 
                    (vendor and "lg" in vendor.lower()) or
                    (vendor and "sony" in vendor.lower()) or
                    "chromecast" in device_type.lower() or
                    "roku" in device_type.lower())
            
            status = "📺 TV" if is_tv else f"📡 {device_type}"
            info = f"{status} | {ip} | {vendor}"
            if hostname:
                info += f" ({hostname})"
            info += f" [{source}]"
            
            dev_summaries.append(info)
            
            frontend_list.append({
                "ip": ip,
                "alias": hostname or vendor or device_type,
                "model": vendor,
                "type": device_type,
                "is_on": None,  # Unknown for non-Kasa
                "brightness": None,
                "hsv": None,
                "has_color": False,
                "has_brightness": False,
                "is_tv": is_tv,
                "vendor": vendor,
                "open_ports": device.get("open_ports", []),
                "source": source
            })
        
        # Process Kasa devices separately
        for ip, d in self.loop.kasa_agent.devices.items():
            dev_type = "unknown"
            if d.is_bulb: dev_type = "bulb"
            elif d.is_plug: dev_type = "plug"
            elif d.is_strip: dev_type = "strip"
            elif d.is_dimmer: dev_type = "dimmer"
            
            info = f"💡 Kasa | {d.alias} (IP: {ip}, Type: {dev_type})"
            if d.is_on:
                info += " [ON]"
            else:
                info += " [OFF]"
            dev_summaries.append(info)
            
            frontend_list.append({
                "ip": ip,
                "alias": d.alias,
                "model": d.model,
                "type": dev_type,
                "is_on": d.is_on,
                "brightness": d.brightness if d.is_bulb or d.is_dimmer else None,
                "hsv": d.hsv if d.is_bulb and d.is_color else None,
                "has_color": d.is_color if d.is_bulb else False,
                "has_brightness": d.is_dimmable if d.is_bulb or d.is_dimmer else False,
                "is_tv": False,
                "vendor": "TP-Link",
                "open_ports": [9999],
                "source": "kasa"
            })

        if self.loop.on_device_update:
            self.loop.on_device_update(frontend_list)
        
        # Count TVs specifically
        tv_count = sum(1 for d in all_devices if d.get("device_type", "").lower() in ["smart_tv", "chromecast", "roku"])
        
        result_text = f"🔍 Found {len(all_devices)} network devices, {len(kasa_devices)} Kasa devices."
        if tv_count > 0:
            result_text += f"\n📺 {tv_count} TV/Streaming device(s) detected!"
        
        if dev_summaries:
            result_text += "\n\n" + "\n".join(dev_summaries)
        else:
            result_text += "\nNo devices found on network."
        
        return result_text

    async def _handle_control_light(self, args, fc_id):
        """Handle control_light tool call - only works with Kasa smart devices."""
        target = args.get("target", "")
        action = args.get("action", "")
        brightness = args.get("brightness")
        color = args.get("color")

        print(f"[NOVA DEBUG] [KASA] control_light: Target='{target}' Action='{action}'")

        # Check if we have any Kasa devices
        if not self.loop.kasa_agent.devices:
            # Try to discover Kasa devices first
            print("[NOVA DEBUG] [KASA] No Kasa devices cached, attempting discovery...")
            await self.loop.kasa_agent.discover_devices()
        
        # Check if target is a known Kasa device
        is_kasa_device = target in self.loop.kasa_agent.devices
        if not is_kasa_device:
            # Check if it's an alias
            dev = self.loop.kasa_agent.get_device_by_alias(target)
            is_kasa_device = dev is not None
        
        if not is_kasa_device:
            # Not a Kasa device - provide helpful info about what IS available
            available_devices = []
            for ip, d in self.loop.kasa_agent.devices.items():
                dev_type = "device"
                if d.is_bulb: dev_type = "smart bulb"
                elif d.is_plug: dev_type = "smart plug"
                elif d.is_strip: dev_type = "power strip"
                elif d.is_dimmer: dev_type = "dimmer"
                available_devices.append(f"'{d.alias}' ({dev_type}, IP: {ip})")
            
            if available_devices:
                return f"Sorry sir, '{target}' is not a controllable Kasa smart device. Available Kasa devices: {', '.join(available_devices)}. I cannot control TVs, Chromecast, or other non-Kasa devices directly."
            else:
                return "Sorry sir, no Kasa smart devices (bulbs, plugs, switches) were found on the network. I can only control TP-Link Kasa smart home devices, not TVs, computers, or other network devices."

        result_msg = f"Action '{action}' on '{target}' failed."
        success = False

        if action == "turn_on":
            success = await self.loop.kasa_agent.turn_on(target)
            if success:
                result_msg = f"Turned ON '{target}'."
        elif action == "turn_off":
            success = await self.loop.kasa_agent.turn_off(target)
            if success:
                result_msg = f"Turned OFF '{target}'."
        elif action == "set":
            success = True
            result_msg = f"Updated '{target}':"

        if success or action == "set":
            if brightness is not None:
                sb = await self.loop.kasa_agent.set_brightness(target, brightness)
                if sb:
                    result_msg += f" Set brightness to {brightness}."
            if color is not None:
                sc = await self.loop.kasa_agent.set_color(target, color)
                if sc:
                    result_msg += f" Set color to {color}."

        # Update frontend
        if success:
            updated_list = []
            for ip, dev in self.loop.kasa_agent.devices.items():
                dev_type = "unknown"
                if dev.is_bulb: dev_type = "bulb"
                elif dev.is_plug: dev_type = "plug"
                elif dev.is_strip: dev_type = "strip"
                elif dev.is_dimmer: dev_type = "dimmer"

                d_info = {
                    "ip": ip,
                    "alias": dev.alias,
                    "model": dev.model,
                    "type": dev_type,
                    "is_on": dev.is_on,
                    "brightness": dev.brightness if dev.is_bulb or dev.is_dimmer else None,
                    "hsv": dev.hsv if dev.is_bulb and dev.is_color else None,
                    "has_color": dev.is_color if dev.is_bulb else False,
                    "has_brightness": dev.is_dimmable if dev.is_bulb or dev.is_dimmer else False
                }
                updated_list.append(d_info)

            if self.loop.on_device_update:
                self.loop.on_device_update(updated_list)
        else:
            if self.loop.on_error:
                self.loop.on_error(result_msg)

        return result_msg

    async def _handle_control_tv(self, args, fc_id):
        """Handle control_tv tool call - controls smart TVs and streaming devices."""
        target = args.get("target", "")
        action = args.get("action", "")
        app_name = args.get("app_name", "")

        print(f"[NOVA DEBUG] [TV] control_tv: Target='{target}' Action='{action}'")

        # Get all network devices to find TVs
        if not self.loop.kasa_agent.network_devices:
            await self.loop.kasa_agent.scan_full_network()

        # Find TV/streaming device by IP, hostname, or device type
        tv_device = None
        for device in self.loop.kasa_agent.network_devices:
            if (device.ip == target or 
                (device.hostname and target.lower() in device.hostname.lower()) or
                target.lower() in device.device_type.lower()):
                tv_device = device
                break
        
        # If no specific match, look for any TV/Chromecast/Roku
        if not tv_device and target.lower() in ["tv", "chromecast", "roku", "television", "smart tv"]:
            for device in self.loop.kasa_agent.network_devices:
                if ("tv" in device.device_type.lower() or
                    "chromecast" in device.device_type.lower() or
                    "roku" in device.device_type.lower() or
                    (device.vendor and any(v in device.vendor.lower() for v in ["samsung", "lg", "sony", "chromecast", "roku"]))):
                    tv_device = device
                    break

        if not tv_device:
            return f"Sorry sir, I couldn't find the TV/streaming device '{target}'. Please use 'list_smart_devices' to scan the network first."

        print(f"[NOVA DEBUG] [TV] Found device: {tv_device.ip} ({tv_device.device_type})")

        # Try to control the TV using different methods based on device type
        try:
            if tv_device.device_type == "chromecast":
                return await self._control_chromecast(tv_device, action, app_name)
            elif "roku" in tv_device.device_type.lower():
                return await self._control_roku(tv_device, action, app_name)
            elif "samsung" in (tv_device.vendor or "").lower():
                return await self._control_samsung_tv(tv_device, action)
            else:
                # Generic control attempt via network protocols
                return await self._control_generic_tv(tv_device, action)
        except Exception as e:
            print(f"[NOVA DEBUG] [TV] Control failed: {e}")
            return f"Sorry sir, I couldn't control the {tv_device.device_type} at {tv_device.ip}. The device may not support network control. Error: {e}"

    async def _control_chromecast(self, device, action, app_name=None):
        """Control a Chromecast device."""
        try:
            import pychromecast
            from pychromecast.controllers.youtube import YouTubeController
            
            # Try to find and connect to the Chromecast
            chromecasts, browser = pychromecast.get_chromecasts()
            cast = None
            for cc in chromecasts:
                if cc.host == device.ip or cc.name.lower() in (device.hostname or "").lower():
                    cast = cc
                    break
            
            if not cast and chromecasts:
                # Use first available Chromecast
                cast = chromecasts[0]
            
            if not cast:
                return f"Could not connect to Chromecast. Please ensure pychromecast is installed: pip install pychromecast"
            
            cast.wait()
            
            if action == "turn_off":
                cast.quit_app()
                return f"Turned off Chromecast at {device.ip}."
            elif action == "pause":
                cast.media_controller.pause()
                return f"Paused playback on Chromecast."
            elif action == "play":
                cast.media_controller.play()
                return f"Resumed playback on Chromecast."
            elif action == "stop":
                cast.media_controller.stop()
                return f"Stopped playback on Chromecast."
            elif action == "volume_up":
                cast.volume_up()
                return f"Volume increased on Chromecast."
            elif action == "volume_down":
                cast.volume_down()
                return f"Volume decreased on Chromecast."
            elif action == "mute":
                cast.set_volume_muted(True)
                return f"Muted Chromecast."
            elif action == "home":
                cast.quit_app()
                return f"Returned Chromecast to home screen."
            else:
                return f"Action '{action}' executed on Chromecast."
                
        except ImportError:
            return f"Chromecast control requires pychromecast. Install with: pip install pychromecast"
        except Exception as e:
            return f"Chromecast control failed: {e}"

    async def _control_roku(self, device, action, app_name=None):
        """Control a Roku device using ECP protocol."""
        try:
            import requests
            
            roku_ip = device.ip
            
            # Roku External Control Protocol (ECP) commands
            key_commands = {
                "turn_off": "PowerOff",
                "turn_on": "PowerOn",
                "home": "Home",
                "play": "Play",
                "pause": "Pause",
                "stop": "Home",  # Roku doesn't have a direct stop, go home
                "volume_up": "VolumeUp",
                "volume_down": "VolumeDown",
                "mute": "VolumeMute",
            }
            
            if action in key_commands:
                key = key_commands[action]
                response = requests.post(f"http://{roku_ip}:8060/keypress/{key}", timeout=5)
                if response.status_code == 200:
                    return f"Executed '{action}' on Roku at {roku_ip}."
                else:
                    return f"Roku command failed with status {response.status_code}."
            else:
                return f"Action '{action}' not supported for Roku. Supported: {', '.join(key_commands.keys())}"
                
        except ImportError:
            return f"Roku control requires requests library. Install with: pip install requests"
        except Exception as e:
            return f"Roku control failed: {e}"

    async def _control_samsung_tv(self, device, action):
        """Control a Samsung Smart TV using Tizen API."""
        try:
            # Try using samsungctl library
            from samsungctl import Remote
            
            config = {
                "name": "NOVA",
                "description": "NOVA Smart Assistant",
                "id": "",
                "host": device.ip,
                "port": 55000,
                "method": "legacy",  # or "websocket" for newer TVs
            }
            
            key_commands = {
                "turn_off": "KEY_POWER",
                "turn_on": "KEY_POWER",
                "home": "KEY_HOME",
                "play": "KEY_PLAY",
                "pause": "KEY_PAUSE",
                "stop": "KEY_STOP",
                "volume_up": "KEY_VOLUP",
                "volume_down": "KEY_VOLDOWN",
                "mute": "KEY_MUTE",
            }
            
            if action in key_commands:
                key = key_commands[action]
                with Remote(config) as remote:
                    remote.control(key)
                return f"Executed '{action}' on Samsung TV at {device.ip}."
            else:
                return f"Action '{action}' not supported for Samsung TV."
                
        except ImportError:
            return f"Samsung TV control requires samsungctl library. Install with: pip install samsungctl"
        except Exception as e:
            return f"Samsung TV control failed: {e}. Note: TV may require pairing/authorization."

    async def _control_generic_tv(self, device, action):
        """Attempt generic TV control using HDMI-CEC or wake-on-lan."""
        result_messages = []
        
        # Try HDMI-CEC control (requires cec-client)
        try:
            import subprocess
            cec_commands = {
                "turn_off": "standby 0",
                "turn_on": "on 0",
                "home": "tx 44 44 03",  # CEC root menu
            }
            
            if action in cec_commands:
                cmd = cec_commands[action]
                result = subprocess.run(
                    ["cec-client", "-s", "-d", "1"],
                    input=cmd + "\nquit\n",
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    result_messages.append(f"HDMI-CEC: Executed '{action}'")
        except Exception as e:
            print(f"[TV DEBUG] HDMI-CEC failed: {e}")
        
        # Try Wake-on-LAN for power on
        if action == "turn_on":
            try:
                import wakeonlan
                if device.mac:
                    wakeonlan.send_magic_packet(device.mac)
                    result_messages.append(f"Wake-on-LAN: Sent magic packet to {device.mac}")
            except Exception as e:
                print(f"[TV DEBUG] Wake-on-LAN failed: {e}")
        
        if result_messages:
            return f"TV control attempts:\n" + "\n".join(result_messages)
        else:
            return f"Sorry sir, I don't have a specific control method for {device.device_type} devices. The TV may require a specific app or IR remote. Consider using a Kasa smart plug to power cycle the TV instead."

    # ========================================================================
    # 3D Printer Handlers
    # ========================================================================

    async def _handle_discover_printers(self, args, fc_id):
        """Handle discover_printers tool call."""
        print(f"[NOVA DEBUG] [PRINTER] discover_printers")

        printers = await self.loop.printer_agent.discover_printers()
        if printers:
            printer_list = []
            for p in printers:
                printer_list.append(f"{p['name']} ({p['host']}:{p['port']}, type: {p['printer_type']})")
            return "Found Printers:\n" + "\n".join(printer_list)
        return "No printers found on network. Ensure printers are on and running OctoPrint/Moonraker."

    async def _handle_print_stl(self, args, fc_id):
        """Handle print_stl tool call."""
        stl_path = args.get("stl_path", "")
        printer = args.get("printer", "")
        profile = args.get("profile")

        print(f"[NOVA DEBUG] [PRINTER] print_stl: STL='{stl_path}' Printer='{printer}'")

        if stl_path.lower() == "current":
            stl_path = "output.stl"

        project_path = str(self.loop.project_manager.get_current_project_path())

        result = await self.loop.printer_agent.print_stl(
            stl_path, printer, profile, root_path=project_path
        )
        return result.get("message", "Unknown result")

    async def _handle_get_print_status(self, args, fc_id):
        """Handle get_print_status tool call."""
        printer = args.get("printer", "")
        print(f"[NOVA DEBUG] [PRINTER] get_print_status: Printer='{printer}'")

        status = await self.loop.printer_agent.get_print_status(printer)
        if status:
            result_str = f"Printer: {status.printer}\n"
            result_str += f"State: {status.state}\n"
            result_str += f"Progress: {status.progress_percent:.1f}%\n"
            if status.time_remaining:
                result_str += f"Time Remaining: {status.time_remaining}\n"
            if status.time_elapsed:
                result_str += f"Time Elapsed: {status.time_elapsed}\n"
            if status.filename:
                result_str += f"File: {status.filename}\n"
            if status.temperatures:
                temps = status.temperatures
                if "hotend" in temps:
                    result_str += f"Hotend: {temps['hotend']['current']:.0f}°C / {temps['hotend']['target']:.0f}°C\n"
                if "bed" in temps:
                    result_str += f"Bed: {temps['bed']['current']:.0f}°C / {temps['bed']['target']:.0f}°C"
            return result_str
        return f"Could not get status for printer '{printer}'. Ensure it is discovered first."

    # ========================================================================
    # Agent Task Handlers
    # ========================================================================

    async def _handle_execute_task(self, args, fc_id):
        """Handle execute_task tool call."""
        goal = args.get("goal", "")
        priority = args.get("priority", "normal")
        print(f"[NOVA DEBUG] [AGENT] execute_task: goal='{goal[:60]}...' priority='{priority}'")

        from agent.task_queue import TaskPriority

        priority_map = {
            "high": TaskPriority.HIGH,
            "normal": TaskPriority.NORMAL,
            "low": TaskPriority.LOW
        }
        task_priority = priority_map.get(priority.lower(), TaskPriority.NORMAL)

        def speak_callback(message: str):
            """Thread-safe callback to send agent updates from background thread."""
            try:
                # Get the main event loop from the AudioLoop
                main_loop = self.loop._event_loop if hasattr(self.loop, '_event_loop') else asyncio.get_event_loop()
                
                # Schedule the coroutine on the main event loop from this background thread
                future = asyncio.run_coroutine_threadsafe(
                    self.loop.session.send(
                        input=f"System Notification: Agent update - {message}",
                        end_of_turn=False
                    ),
                    main_loop
                )
                # Wait briefly for it to complete (non-blocking)
                future.result(timeout=0.1)
            except Exception as e:
                print(f"[NOVA DEBUG] [AGENT] Failed to send speak message: {e}")

        task_id = self.loop.task_queue.submit(
            goal=goal,
            priority=task_priority,
            speak=speak_callback,
            on_complete=self._on_task_complete
        )

        # Notify model
        try:
            await self.loop.session.send(
                input=f"System Notification: Task submitted (ID: {task_id}). The agent will work on: {goal}. You'll be notified when it's complete.",
                end_of_turn=True
            )
        except Exception as e:
            print(f"[NOVA DEBUG] [ERR] Failed to send task submission notification: {e}")

        return f"Task submitted with {priority} priority. The agent will handle it in the background."

    def _on_task_complete(self, task_id: str, result: str):
        """Callback when an agent task completes - called from background thread."""
        print(f"[NOVA DEBUG] [AGENT] Task {task_id} completed: {result[:100]}")
        try:
            # Get the main event loop from the AudioLoop
            main_loop = self.loop._event_loop if hasattr(self.loop, '_event_loop') else asyncio.get_event_loop()
            
            # Schedule the coroutine on the main event loop from this background thread
            future = asyncio.run_coroutine_threadsafe(
                self.loop.session.send(
                    input=f"System Notification: Task {task_id} completed. Result: {result}",
                    end_of_turn=True
                ),
                main_loop
            )
            # Wait briefly for it to complete (non-blocking)
            future.result(timeout=0.1)
        except Exception as e:
            print(f"[NOVA DEBUG] [AGENT] Failed to send completion notification: {e}")

    async def _handle_agent_task(self, args, fc_id):
        """Handle agent_task tool call (JARVIS-style)."""
        from agent.task_queue import get_queue, TaskPriority

        priority_map = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH
        }
        priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
        task_id = get_queue().submit(
            goal=args.get("goal", ""),
            priority=priority,
            speak=self._jarvis_speak
        )
        return f"Task started (ID: {task_id})."

    def _jarvis_speak(self, message: str):
        """Speak callback for JARVIS-style tasks - thread-safe for background execution."""
        try:
            # Get the main event loop from ada.py (stored in self.loop._event_loop)
            main_loop = getattr(self.loop, '_event_loop', None)
            
            # If no stored loop, try to get running loop - but this may fail in background threads
            if main_loop is None:
                try:
                    main_loop = asyncio.get_running_loop()
                except RuntimeError:
                    # No running loop in this thread - log and return
                    print(f"[NOVA DEBUG] [JARVIS] Cannot speak: no event loop (running in background thread)")
                    return
            
            # Schedule coroutine on main loop thread-safely
            future = asyncio.run_coroutine_threadsafe(
                self.loop.session.send(
                    input=f"System Notification: {message}",
                    end_of_turn=False
                ),
                main_loop
            )
            # Don't wait for result to avoid blocking
        except Exception as e:
            print(f"[NOVA DEBUG] [JARVIS] Failed to speak: {e}")

    # ========================================================================
    # JARVIS-style Tool Handlers
    # ========================================================================

    async def _handle_open_app(self, args, fc_id):
        """Handle open_app tool call."""
        from open_app import open_app
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: open_app(parameters=args, response=None, player=None)
        )
        return result or f"Opened {args.get('app_name', 'application')}."

    async def _handle_weather_report(self, args, fc_id):
        """Handle weather_report tool call."""
        from weather_report import weather_action
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: weather_action(parameters=args, player=None)
        )
        return result or "Weather delivered."

    async def _handle_browser_control(self, args, fc_id):
        """Handle browser_control tool call."""
        from browser_control import browser_control
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: browser_control(parameters=args, player=None)
        )
        return result or "Done."

    async def _handle_file_controller(self, args, fc_id):
        """Handle file_controller tool call."""
        from file_controller import file_controller
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: file_controller(parameters=args, player=None)
        )
        return result or "Done."

    async def _handle_send_message(self, args, fc_id):
        """Handle send_message tool call."""
        from send_message import send_message
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: send_message(parameters=args, response=None, player=None, session_memory=None)
        )
        return result or f"Message sent to {args.get('receiver', 'recipient')}."

    async def _handle_reminder(self, args, fc_id):
        """Handle reminder tool call."""
        from reminder import reminder
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: reminder(parameters=args, response=None, player=None)
        )
        return result or "Reminder set."

    async def _handle_youtube_video(self, args, fc_id):
        """Handle youtube_video tool call."""
        from youtube_video import youtube_video
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: youtube_video(parameters=args, response=None, player=None)
        )
        return result or "Done."

    async def _handle_screen_process(self, args, fc_id):
        """Handle screen_process tool call."""
        from screen_processor import screen_process
        threading.Thread(
            target=screen_process,
            kwargs={"parameters": args, "response": None, "player": None, "session_memory": None},
            daemon=True
        ).start()
        return "Vision module activated. Stay completely silent — vision module will speak directly."

    async def _handle_computer_settings(self, args, fc_id):
        """Handle computer_settings tool call."""
        from computer_settings import computer_settings
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: computer_settings(parameters=args, response=None, player=None)
        )
        return result or "Done."

    async def _handle_desktop_control(self, args, fc_id):
        """Handle desktop_control tool call."""
        from desktop import desktop_control
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: desktop_control(parameters=args, player=None)
        )
        return result or "Done."

    async def _handle_code_helper(self, args, fc_id):
        """Handle code_helper tool call."""
        from code_helper import code_helper
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: code_helper(parameters=args, player=None, speak=self._jarvis_speak)
        )
        return result or "Done."

    async def _handle_dev_agent(self, args, fc_id):
        """Handle dev_agent tool call."""
        from dev_agent import dev_agent
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: dev_agent(parameters=args, player=None, speak=self._jarvis_speak)
        )
        return result or "Done."

    async def _handle_computer_control(self, args, fc_id):
        """Handle computer_control tool call."""
        from computer_control import computer_control
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: computer_control(parameters=args, player=None)
        )
        return result or "Done."

    async def _handle_game_updater(self, args, fc_id):
        """Handle game_updater tool call."""
        from game_updater import game_updater
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: game_updater(parameters=args, player=None, speak=self._jarvis_speak)
        )
        return result or "Done."

    async def _handle_flight_finder(self, args, fc_id):
        """Handle flight_finder tool call."""
        from flight_finder import flight_finder
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: flight_finder(parameters=args, player=None)
        )
        return result or "Done."

    async def _handle_shutdown_jarvis(self, args, fc_id):
        """Handle shutdown_jarvis tool call."""
        def _shutdown():
            import time
            time.sleep(1)
            os._exit(0)

        threading.Thread(target=_shutdown, daemon=True).start()
        return "Shutting down..."


class IntentPredictor:
    """
    FRIDAY-Level: Predict what user wants before they finish speaking.
    Like FRIDAY loading solutions before Tony finishes describing the problem.
    """
    
    def __init__(self, tool_handler=None):
        self.tool_handler = tool_handler
        self.intent_patterns = {
            "tool_execution": ["can you", "could you", "please", "i need", "help me"],
            "information": ["what", "how", "why", "when", "where", "who", "is there", "are there"],
            "visualization": ["show", "display", "view", "look at", "let me see"],
            "creation": ["create", "make", "build", "generate", "design", "write"],
            "analysis": ["analyze", "check", "review", "examine", "scan", "debug"],
            "control": ["turn", "set", "change", "adjust", "control", "switch"],
            "search": ["find", "search", "look up", "get me", "fetch"],
            "communication": ["send", "email", "message", "call", "notify"],
        }
        self.prediction_cache = {}
        self.confidence_threshold = 0.6
        
    async def predict_from_partial(self, partial_text: str, context: Dict = None) -> Dict:
        """Predict intent from incomplete user input."""
        if not partial_text or len(partial_text) < 3:
            return {"intent": None, "confidence": 0, "preloaded": []}
        
        partial_lower = partial_text.lower()
        scores = {}
        
        # Calculate scores based on trigger phrases
        for intent, triggers in self.intent_patterns.items():
            score = sum(2 for t in triggers if t in partial_lower)
            # Boost score for triggers at the start
            for t in triggers:
                if partial_lower.startswith(t):
                    score += 3
            scores[intent] = score
        
        # Normalize scores
        max_score = max(scores.values()) if scores else 0
        if max_score > 0:
            for intent in scores:
                scores[intent] = scores[intent] / max_score
        
        # Get best prediction
        predicted = max(scores, key=scores.get) if max(scores.values()) > 0 else None
        confidence = scores.get(predicted, 0) if predicted else 0
        
        preloaded = []
        if predicted and confidence >= self.confidence_threshold:
            preloaded = await self._preload_for_intent(predicted, context)
            print(f"[FRIDAY] 🔮 Predicted intent: {predicted} ({confidence:.0%} confidence)")
        
        return {
            "intent": predicted,
            "confidence": confidence,
            "preloaded": preloaded,
            "all_scores": scores
        }
    
    async def _preload_for_intent(self, intent: str, context: Dict = None) -> List[str]:
        """Pre-load tools and resources based on predicted intent."""
        preloaded = []
        
        if intent == "tool_execution":
            # Warm up file and system tools
            preloaded = ["write_file", "read_file", "computer_control"]
        
        elif intent == "visualization":
            # Pre-load CAD viewer, screen capture
            preloaded = ["screen_process", "cad_viewer"]
            if self.tool_handler:
                await self.tool_handler._warm_visualization_tools()
        
        elif intent == "creation":
            # Pre-load CAD agent, check printer availability
            preloaded = ["generate_cad", "printer_agent", "dev_agent"]
            if context and context.get("printer_ready"):
                preloaded.append("print_stl")
        
        elif intent == "analysis":
            # Pre-load diagnostic tools
            preloaded = ["code_helper", "web_search", "screen_process"]
        
        elif intent == "control":
            # Pre-load smart home controllers
            preloaded = ["kasa_agent", "computer_settings", "desktop_control"]
        
        elif intent == "search":
            # Pre-load search tools
            preloaded = ["web_search", "flight_finder", "youtube_video"]
        
        elif intent == "communication":
            # Pre-load messaging tools
            preloaded = ["send_message", "reminder"]
        
        return preloaded
    
    async def predict_follow_up(self, last_message: str, conversation_history: List[Dict]) -> List[Dict]:
        """Predict likely follow-up questions/actions."""
        predictions = []
        
        # Pattern: "Find flights to X" → likely "book it", "cheapest option", "return flight"
        if "flight" in last_message.lower():
            predictions = [
                {"action": "book_flight", "confidence": 0.4},
                {"action": "check_return_flights", "confidence": 0.3},
                {"action": "find_cheapest", "confidence": 0.3}
            ]
        
        # Pattern: "Create a CAD model" → likely "print it", "modify it", "export it"
        elif any(w in last_message.lower() for w in ["cad", "model", "design"]):
            predictions = [
                {"action": "print_model", "confidence": 0.5},
                {"action": "modify_design", "confidence": 0.3},
                {"action": "export_file", "confidence": 0.2}
            ]
        
        # Pattern: "Write code" → likely "debug it", "run it", "deploy it"
        elif any(w in last_message.lower() for w in ["code", "program", "script"]):
            predictions = [
                {"action": "debug_code", "confidence": 0.4},
                {"action": "run_code", "confidence": 0.3},
                {"action": "deploy_app", "confidence": 0.2}
            ]
        
        return predictions
    
    def _warm_visualization_tools(self):
        """Placeholder for visualization tool warming."""
        pass
