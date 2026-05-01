# Function definitions
open_app_tool = {
    "name": "open_app",
    "description": "Opens any application on the computer. Use this whenever the user asks to open, launch, or start any app, website, or program. Always call this tool — never just say you opened it.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {"type": "STRING", "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"}
        },
        "required": ["app_name"]
    }
}

web_search_tool = {
    "name": "web_search",
    "description": "Searches the web for any information.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Search query"},
            "mode": {"type": "STRING", "description": "search (default) or compare"},
            "items": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
            "aspect": {"type": "STRING", "description": "price | specs | reviews"}
        },
        "required": ["query"]
    }
}

weather_report_tool = {
    "name": "weather_report",
    "description": "Gives the weather report to user",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {"type": "STRING", "description": "City name"}
        },
        "required": ["city"]
    }
}

send_message_tool = {
    "name": "send_message",
    "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "receiver": {"type": "STRING", "description": "Recipient contact name"},
            "message_text": {"type": "STRING", "description": "The message to send"},
            "platform": {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
        },
        "required": ["receiver", "message_text", "platform"]
    }
}

reminder_tool = {
    "name": "reminder",
    "description": "Sets a timed reminder using Task Scheduler.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "date": {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
            "time": {"type": "STRING", "description": "Time in HH:MM format (24h)"},
            "message": {"type": "STRING", "description": "Reminder message text"}
        },
        "required": ["date", "time", "message"]
    }
}

youtube_video_tool = {
    "name": "youtube_video",
    "description": "Controls YouTube. Use for: playing videos, summarizing a video's content, getting video info, or showing trending videos.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
            "query": {"type": "STRING", "description": "Search query for play action"},
            "save": {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
            "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
            "url": {"type": "STRING", "description": "Video URL for get_info action"}
        },
        "required": []
    }
}

screen_process_tool = {
    "name": "screen_process",
    "description": "Captures and analyzes the screen or webcam image. MUST be called when user asks what is on screen, what you see, analyze my screen, look at camera, etc. You have NO visual ability without this tool. After calling this tool, stay SILENT — the vision module speaks directly.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
            "text": {"type": "STRING", "description": "The question or instruction about the captured image"}
        },
        "required": ["text"]
    }
}

computer_settings_tool = {
    "name": "computer_settings",
    "description": "Controls the computer: volume, brightness, window management, keyboard shortcuts, typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. Use for ANY single computer control command.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "The action to perform"},
            "description": {"type": "STRING", "description": "Natural language description of what to do"},
            "value": {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
        },
        "required": []
    }
}

browser_control_tool = {
    "name": "browser_control",
    "description": "Controls any web browser. Use for: opening websites, searching the web, clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. Always pass the 'browser' parameter when the user specifies a browser.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
            "browser": {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari"},
            "url": {"type": "STRING", "description": "URL for go_to / new_tab action"},
            "query": {"type": "STRING", "description": "Search query for search action"},
            "engine": {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
            "selector": {"type": "STRING", "description": "CSS selector for click/type"},
            "text": {"type": "STRING", "description": "Text to click or type"},
            "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
            "direction": {"type": "STRING", "description": "up | down for scroll"},
            "amount": {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
            "key": {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
            "path": {"type": "STRING", "description": "Save path for screenshot"},
            "incognito": {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
            "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"}
        },
        "required": ["action"]
    }
}

file_controller_tool = {
    "name": "file_controller",
    "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
            "path": {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
            "destination": {"type": "STRING", "description": "Destination path for move/copy"},
            "new_name": {"type": "STRING", "description": "New name for rename"},
            "content": {"type": "STRING", "description": "Content for create_file/write"},
            "name": {"type": "STRING", "description": "File name to search for"},
            "extension": {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
            "count": {"type": "INTEGER", "description": "Number of results for largest"}
        },
        "required": ["action"]
    }
}

desktop_control_tool = {
    "name": "desktop_control",
    "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
            "path": {"type": "STRING", "description": "Image path for wallpaper"},
            "url": {"type": "STRING", "description": "Image URL for wallpaper_url"},
            "mode": {"type": "STRING", "description": "by_type or by_date for organize"},
            "task": {"type": "STRING", "description": "Natural language desktop task"}
        },
        "required": ["action"]
    }
}

code_helper_tool = {
    "name": "code_helper",
    "description": "Writes, edits, explains, runs, or builds code files.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
            "description": {"type": "STRING", "description": "What the code should do or what change to make"},
            "language": {"type": "STRING", "description": "Programming language (default: python)"},
            "output_path": {"type": "STRING", "description": "Where to save the file"},
            "file_path": {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
            "code": {"type": "STRING", "description": "Raw code string for explain"},
            "args": {"type": "STRING", "description": "CLI arguments for run/build"},
            "timeout": {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"}
        },
        "required": ["action"]
    }
}

dev_agent_tool = {
    "name": "dev_agent",
    "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "description": {"type": "STRING", "description": "What the project should do"},
            "language": {"type": "STRING", "description": "Programming language (default: python)"},
            "project_name": {"type": "STRING", "description": "Optional project folder name"},
            "timeout": {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"}
        },
        "required": ["description"]
    }
}

agent_task_tool = {
    "name": "agent_task",
    "description": "Executes complex multi-step tasks requiring multiple different tools. Examples: 'research X and save to file', 'find and organize files'. DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {"type": "STRING", "description": "Complete description of what to accomplish"},
            "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
        },
        "required": ["goal"]
    }
}

computer_control_tool = {
    "name": "computer_control",
    "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
            "text": {"type": "STRING", "description": "Text to type or paste"},
            "x": {"type": "INTEGER", "description": "X coordinate"},
            "y": {"type": "INTEGER", "description": "Y coordinate"},
            "keys": {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
            "key": {"type": "STRING", "description": "Single key e.g. 'enter'"},
            "direction": {"type": "STRING", "description": "up | down | left | right"},
            "amount": {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
            "seconds": {"type": "NUMBER", "description": "Seconds to wait"},
            "title": {"type": "STRING", "description": "Window title for focus_window"},
            "description": {"type": "STRING", "description": "Element description for screen_find/screen_click"},
            "type": {"type": "STRING", "description": "Data type for random_data"},
            "field": {"type": "STRING", "description": "Field for user_data: name|email|city"},
            "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            "path": {"type": "STRING", "description": "Save path for screenshot"}
        },
        "required": ["action"]
    }
}

game_updater_tool = {
    "name": "game_updater",
    "description": "THE ONLY tool for ANY Steam or Epic Games request. Use for: installing, downloading, updating games, listing installed games, checking download status, scheduling updates. ALWAYS call directly for any Steam/Epic/game request. NEVER use agent_task, browser_control, or web_search for Steam/Epic.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
            "platform": {"type": "STRING", "description": "steam | epic | both (default: both)"},
            "game_name": {"type": "STRING", "description": "Game name (partial match supported)"},
            "app_id": {"type": "STRING", "description": "Steam AppID for install (optional)"},
            "hour": {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
            "minute": {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
            "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"}
        },
        "required": []
    }
}

flight_finder_tool = {
    "name": "flight_finder",
    "description": "Searches Google Flights and speaks the best options.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "origin": {"type": "STRING", "description": "Departure city or airport code"},
            "destination": {"type": "STRING", "description": "Arrival city or airport code"},
            "date": {"type": "STRING", "description": "Departure date (any format)"},
            "return_date": {"type": "STRING", "description": "Return date for round trips"},
            "passengers": {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
            "cabin": {"type": "STRING", "description": "economy | premium | business | first"},
            "save": {"type": "BOOLEAN", "description": "Save results to Notepad"}
        },
        "required": ["origin", "destination", "date"]
    }
}

shutdown_jarvis_tool = {
    "name": "shutdown_jarvis",
    "description": "Shuts down the assistant completely. Call this when the user expresses intent to end the conversation, close the assistant, say goodbye, or stop Jarvis. The user can say this in ANY language.",
    "parameters": {
        "type": "OBJECT",
        "properties": {}
    }
}

generate_cad = {
    "name": "generate_cad",
    "description": "Generates a 3D CAD model based on a prompt.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The description of the object to generate."}
        },
        "required": ["prompt"]
    },
    "behavior": "NON_BLOCKING"
}

run_web_agent = {
    "name": "run_web_agent",
    "description": "Opens a web browser and performs a task according to the prompt.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The detailed instructions for the web browser agent."}
        },
        "required": ["prompt"]
    },
    "behavior": "NON_BLOCKING"
}

create_project_tool = {
    "name": "create_project",
    "description": "Creates a new project folder to organize files.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "The name of the new project."}
        },
        "required": ["name"]
    }
}

switch_project_tool = {
    "name": "switch_project",
    "description": "Switches the current active project context.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "The name of the project to switch to."}
        },
        "required": ["name"]
    }
}

list_projects_tool = {
    "name": "list_projects",
    "description": "Lists all available projects.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
}

list_smart_devices_tool = {
    "name": "list_smart_devices",
    "description": "Discovers and lists ALL network-connected devices including smart TVs, phones, speakers, Chromecast, Roku, smart lights, plugs, routers, and other IoT devices. Use this to check for TVs, connected devices, or scan the local network.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
}

control_light_tool = {
    "name": "control_light",
    "description": "Controls a TP-Link Kasa smart home device (smart bulb, smart plug, dimmer switch). ONLY works with Kasa devices - cannot control TVs, Chromecast, computers, or non-Kasa devices. Target can be an IP address or device alias/name from list_smart_devices.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {
                "type": "STRING",
                "description": "Kasa device identifier: IP address (e.g. '192.168.1.100') or device alias/name (e.g. 'Bedroom Light'). Must be a TP-Link Kasa device."
            },
            "action": {
                "type": "STRING",
                "enum": ["turn_on", "turn_off", "set"],
                "description": "Action to perform"
            },
            "brightness": {
                "type": "INTEGER",
                "description": "Brightness level (0-100, optional, only for 'set' action)"
            },
            "color": {
                "type": "STRING",
                "description": "Color name (e.g., 'red', 'blue', 'warm', 'white') or hex code (optional, only for 'set' action)"
            }
        },
        "required": ["target", "action"]
    }
}

control_tv_tool = {
    "name": "control_tv",
    "description": "Controls smart TVs and streaming devices (Chromecast, Roku, smart TVs) on the network. Can turn on/off, change volume, play/pause, or launch apps. Use after list_smart_devices to find available TVs.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {
                "type": "STRING",
                "description": "TV/streaming device identifier: IP address (e.g. '192.168.0.197'), device name, or 'chromecast'/'tv'/'roku' to target detected devices."
            },
            "action": {
                "type": "STRING",
                "enum": ["turn_on", "turn_off", "volume_up", "volume_down", "mute", "play", "pause", "stop", "home", "launch_app"],
                "description": "Action to perform on the TV/streaming device"
            },
            "app_name": {
                "type": "STRING",
                "description": "App name to launch (e.g. 'Netflix', 'YouTube') - only for launch_app action"
            }
        },
        "required": ["target", "action"]
    }
}

discover_printers_tool = {
    "name": "discover_printers",
    "description": "Discovers 3D printers available on the local network.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
}

print_stl_tool = {
    "name": "print_stl",
    "description": "Prints an STL file to a 3D printer. Handles slicing the STL to G-code and uploading to the printer.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "stl_path": {"type": "STRING", "description": "Path to STL file, or 'current' for the most recent CAD model."},
            "printer": {"type": "STRING", "description": "Printer name or IP address."},
            "profile": {"type": "STRING", "description": "Optional slicer profile name."}
        },
        "required": ["stl_path", "printer"]
    }
}

get_print_status_tool = {
    "name": "get_print_status",
    "description": "Gets the current status of a 3D printer including progress, time remaining, and temperatures.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "printer": {"type": "STRING", "description": "Printer name or IP address."}
        },
        "required": ["printer"]
    }
}

iterate_cad_tool = {
    "name": "iterate_cad",
    "description": "Modifies or iterates on the current CAD design based on user feedback. Use this when the user asks to adjust, change, modify, or iterate on the existing 3D model (e.g., 'make it taller', 'add a handle', 'reduce the thickness').",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The changes or modifications to apply to the current design."}
        },
        "required": ["prompt"]
    },
    "behavior": "NON_BLOCKING"
}

execute_task_tool = {
    "name": "execute_task",
    "description": "Execute a complex multi-step task using the agent system. Use this for tasks that require planning, research, file operations, or multiple tools working together (e.g., 'research a topic and save it to a file', 'organize my desktop', 'install a game and notify me when done'). The agent will plan and execute the task autonomously.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {"type": "STRING", "description": "The goal or task to accomplish. Be specific about what you want done."},
            "priority": {"type": "STRING", "description": "Optional priority level: 'low', 'normal', or 'high'. Default is 'normal'."}
        },
        "required": ["goal"]
    },
    "behavior": "NON_BLOCKING"
}

generate_cad_prototype_tool = {
    "name": "generate_cad_prototype",
    "description": "Generates a 3D wireframe prototype based on a user's description. Use this when the user asks to 'visualize', 'prototype', 'create a wireframe', or 'design' something in 3D.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {
                "type": "STRING",
                "description": "The user's description of the object to prototype."
            }
        },
        "required": ["prompt"]
    }
}

write_file_tool = {
    "name": "write_file",
    "description": "Writes content to a file at the specified path. Overwrites if exists.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "The path of the file to write to."
            },
            "content": {
                "type": "STRING",
                "description": "The content to write to the file."
            }
        },
        "required": ["path", "content"]
    }
}

read_directory_tool = {
    "name": "read_directory",
    "description": "Lists the contents of a directory.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "The path of the directory to list."
            }
        },
        "required": ["path"]
    }
}

read_file_tool = {
    "name": "read_file",
    "description": "Reads the content of a file.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "The path of the file to read."
            }
        },
        "required": ["path"]
    }
}

tools_list = [{"function_declarations": [
    generate_cad_prototype_tool,
    write_file_tool,
    read_directory_tool,
    read_file_tool,
    generate_cad,
    run_web_agent,
    create_project_tool,
    switch_project_tool,
    list_projects_tool,
    list_smart_devices_tool,
    control_light_tool,
    control_tv_tool,
    discover_printers_tool,
    print_stl_tool,
    get_print_status_tool,
    iterate_cad_tool,
    execute_task_tool,
    open_app_tool,
    web_search_tool,
    weather_report_tool,
    send_message_tool,
    reminder_tool,
    youtube_video_tool,
    screen_process_tool,
    computer_settings_tool,
    browser_control_tool,
    file_controller_tool,
    desktop_control_tool,
    code_helper_tool,
    dev_agent_tool,
    agent_task_tool,
    computer_control_tool,
    game_updater_tool,
    flight_finder_tool,
    shutdown_jarvis_tool,
    
]}]


