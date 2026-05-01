import React, { useState, useEffect, useRef } from 'react';
import { X, GripVertical } from 'lucide-react';

const TOOLS = [
    // Core Nova tools
    { id: 'generate_cad_prototype', label: 'Generate CAD Prototype' },
    { id: 'generate_cad', label: 'Generate CAD' },
    { id: 'iterate_cad', label: 'Iterate CAD' },
    { id: 'run_web_agent', label: 'Web Agent' },
    { id: 'write_file', label: 'Write File' },
    { id: 'read_directory', label: 'Read Directory' },
    { id: 'read_file', label: 'Read File' },
    { id: 'create_project', label: 'Create Project' },
    { id: 'switch_project', label: 'Switch Project' },
    { id: 'list_projects', label: 'List Projects' },
    { id: 'list_smart_devices', label: 'List Devices' },
    { id: 'control_light', label: 'Control Light' },
    { id: 'discover_printers', label: 'Discover Printers' },
    { id: 'print_stl', label: 'Print 3D Model' },
    { id: 'get_print_status', label: 'Get Print Status' },
    { id: 'execute_task', label: 'Execute Task' },
    // JARVIS-style tools
    { id: 'open_app', label: 'Open App' },
    { id: 'web_search', label: 'Web Search' },
    { id: 'weather_report', label: 'Weather Report' },
    { id: 'send_message', label: 'Send Message' },
    { id: 'reminder', label: 'Reminder' },
    { id: 'youtube_video', label: 'YouTube Video' },
    { id: 'screen_process', label: 'Screen Process' },
    { id: 'computer_settings', label: 'Computer Settings' },
    { id: 'browser_control', label: 'Browser Control' },
    { id: 'file_controller', label: 'File Controller' },
    { id: 'desktop_control', label: 'Desktop Control' },
    { id: 'code_helper', label: 'Code Helper' },
    { id: 'dev_agent', label: 'Dev Agent' },
    { id: 'agent_task', label: 'Agent Task' },
    { id: 'computer_control', label: 'Computer Control' },
    { id: 'game_updater', label: 'Game Updater' },
    { id: 'flight_finder', label: 'Flight Finder' },
    { id: 'shutdown_jarvis', label: 'Shutdown Jarvis' },
    { id: 'save_memory', label: 'Save Memory' },
];

const SettingsWindow = ({
    socket,
    micDevices,
    speakerDevices,
    webcamDevices,
    selectedMicId,
    setSelectedMicId,
    selectedSpeakerId,
    setSelectedSpeakerId,
    selectedWebcamId,
    setSelectedWebcamId,
    cursorSensitivity,
    setCursorSensitivity,
    isCameraFlipped,
    setIsCameraFlipped,
    handleFileUpload,
    onClose
}) => {
    const [permissions, setPermissions] = useState({});
    const [faceAuthEnabled, setFaceAuthEnabled] = useState(false);
    
    // Drag state
    const [position, setPosition] = useState({ x: null, y: 20 });
    const [isDragging, setIsDragging] = useState(false);
    const dragRef = useRef({ startX: 0, startY: 0, initialX: 0, initialY: 0 });
    const windowRef = useRef(null);

    useEffect(() => {
        // Request initial permissions
        socket.emit('get_settings');

        // Listen for updates
        const handleSettings = (settings) => {
            console.log("Received settings:", settings);
            if (settings) {
                if (settings.tool_permissions) setPermissions(settings.tool_permissions);
                if (typeof settings.face_auth_enabled !== 'undefined') {
                    setFaceAuthEnabled(settings.face_auth_enabled);
                    localStorage.setItem('face_auth_enabled', settings.face_auth_enabled);
                }
            }
        };

        socket.on('settings', handleSettings);
        // Also listen for legacy tool_permissions if needed, but 'settings' covers it
        // socket.on('tool_permissions', handlePermissions); 

        return () => {
            socket.off('settings', handleSettings);
        };
    }, [socket]);

    const togglePermission = (toolId) => {
        const currentVal = permissions[toolId] !== false; // Default True
        const nextVal = !currentVal;

        // Update local mostly for responsiveness, but socket roundtrip handles truth
        // setPermissions(prev => ({ ...prev, [toolId]: nextVal }));

        // Send update
        socket.emit('update_settings', { tool_permissions: { [toolId]: nextVal } });
    };

    const toggleFaceAuth = () => {
        const newVal = !faceAuthEnabled;
        setFaceAuthEnabled(newVal); // Optimistic Update
        localStorage.setItem('face_auth_enabled', newVal);
        socket.emit('update_settings', { face_auth_enabled: newVal });
    };

    const toggleCameraFlip = () => {
        const newVal = !isCameraFlipped;
        setIsCameraFlipped(newVal);
        socket.emit('update_settings', { camera_flipped: newVal });
    };
    
    // Drag handlers
    const handleMouseDown = (e) => {
        if (e.target.closest('button') || e.target.closest('select') || e.target.closest('input')) return;
        setIsDragging(true);
        dragRef.current = {
            startX: e.clientX,
            startY: e.clientY,
            initialX: position.x ?? windowRef.current?.getBoundingClientRect().left ?? 0,
            initialY: position.y ?? 80
        };
    };
    
    const handleMouseMove = (e) => {
        if (!isDragging) return;
        const deltaX = e.clientX - dragRef.current.startX;
        const deltaY = e.clientY - dragRef.current.startY;
        setPosition({
            x: dragRef.current.initialX + deltaX,
            y: Math.max(0, dragRef.current.initialY + deltaY)
        });
    };
    
    const handleMouseUp = () => {
        setIsDragging(false);
    };
    
    useEffect(() => {
        if (isDragging) {
            window.addEventListener('mousemove', handleMouseMove);
            window.addEventListener('mouseup', handleMouseUp);
            return () => {
                window.removeEventListener('mousemove', handleMouseMove);
                window.removeEventListener('mouseup', handleMouseUp);
            };
        }
    }, [isDragging]);

    const leftPos = position.x ?? undefined;
    const rightPos = position.x === null ? 40 : undefined;
    const topPos = position.y ?? 80;

    return (
        <div 
            ref={windowRef}
            style={{ 
                left: leftPos, 
                right: rightPos, 
                top: topPos,
                position: 'fixed'
            }}
            className="bg-black/90 border border-cyan-500/50 rounded-lg z-50 w-80 max-h-[calc(100vh-120px)] backdrop-blur-xl shadow-[0_0_30px_rgba(6,182,212,0.2)] flex flex-col select-none"
        >
            <div 
                className="flex justify-between items-center p-4 pb-2 border-b border-cyan-900/50 shrink-0 cursor-move hover:bg-cyan-900/20 transition-colors"
                onMouseDown={handleMouseDown}
                title="Drag to move"
            >
                <div className="flex items-center gap-2">
                    <GripVertical size={16} className="text-cyan-600" />
                    <h2 className="text-cyan-400 font-bold text-sm uppercase tracking-wider">Settings</h2>
                </div>
                <button onClick={onClose} className="text-cyan-600 hover:text-cyan-400">
                    <X size={16} />
                </button>
            </div>
            <div className="p-4 overflow-y-auto custom-scrollbar">

            {/* Authentication Section */}
            <div className="mb-6">
                <h3 className="text-cyan-400 font-bold mb-3 text-xs uppercase tracking-wider opacity-80">Security</h3>
                <div className="flex items-center justify-between text-xs bg-gray-900/50 p-2 rounded border border-cyan-900/30">
                    <span className="text-cyan-100/80">Face Authentication</span>
                    <button
                        onClick={toggleFaceAuth}
                        className={`relative w-8 h-4 rounded-full transition-colors duration-200 ${faceAuthEnabled ? 'bg-cyan-500/80' : 'bg-gray-700'}`}
                    >
                        <div
                            className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform duration-200 ${faceAuthEnabled ? 'translate-x-4' : 'translate-x-0'}`}
                        />
                    </button>
                </div>
            </div>

            {/* Microphone Section */}
            <div className="mb-4">
                <h3 className="text-cyan-400 font-bold mb-2 text-xs uppercase tracking-wider opacity-80">Microphone</h3>
                <select
                    value={selectedMicId}
                    onChange={(e) => setSelectedMicId(e.target.value)}
                    className="w-full bg-gray-900 border border-cyan-800 rounded p-2 text-xs text-cyan-100 focus:border-cyan-400 outline-none"
                >
                    {micDevices.map((device, i) => (
                        <option key={device.deviceId} value={device.deviceId}>
                            {device.label || `Microphone ${i + 1}`}
                        </option>
                    ))}
                </select>
            </div>

            {/* Speaker Section */}
            <div className="mb-4">
                <h3 className="text-cyan-400 font-bold mb-2 text-xs uppercase tracking-wider opacity-80">Speaker</h3>
                <select
                    value={selectedSpeakerId}
                    onChange={(e) => setSelectedSpeakerId(e.target.value)}
                    className="w-full bg-gray-900 border border-cyan-800 rounded p-2 text-xs text-cyan-100 focus:border-cyan-400 outline-none"
                >
                    {speakerDevices.map((device, i) => (
                        <option key={device.deviceId} value={device.deviceId}>
                            {device.label || `Speaker ${i + 1}`}
                        </option>
                    ))}
                </select>
            </div>

            {/* Webcam Section */}
            <div className="mb-6">
                <h3 className="text-cyan-400 font-bold mb-2 text-xs uppercase tracking-wider opacity-80">Webcam</h3>
                <select
                    value={selectedWebcamId}
                    onChange={(e) => setSelectedWebcamId(e.target.value)}
                    className="w-full bg-gray-900 border border-cyan-800 rounded p-2 text-xs text-cyan-100 focus:border-cyan-400 outline-none"
                >
                    {webcamDevices.map((device, i) => (
                        <option key={device.deviceId} value={device.deviceId}>
                            {device.label || `Camera ${i + 1}`}
                        </option>
                    ))}
                </select>
            </div>

            {/* Cursor Section */}
            <div className="mb-6">
                <div className="flex justify-between mb-2">
                    <h3 className="text-cyan-400 font-bold text-xs uppercase tracking-wider opacity-80">Cursor Sensitivity</h3>
                    <span className="text-xs text-cyan-500">{cursorSensitivity}x</span>
                </div>
                <input
                    type="range"
                    min="1.0"
                    max="5.0"
                    step="0.1"
                    value={cursorSensitivity}
                    onChange={(e) => setCursorSensitivity(parseFloat(e.target.value))}
                    className="w-full accent-cyan-400 cursor-pointer h-1 bg-gray-800 rounded-lg appearance-none"
                />
            </div>

            {/* Gesture Control Section */}
            <div className="mb-6">
                <h3 className="text-cyan-400 font-bold mb-3 text-xs uppercase tracking-wider opacity-80">Gesture Control</h3>
                <div className="flex items-center justify-between text-xs bg-gray-900/50 p-2 rounded border border-cyan-900/30">
                    <span className="text-cyan-100/80">Flip Camera Horizontal</span>
                    <button
                        onClick={toggleCameraFlip}
                        className={`relative w-8 h-4 rounded-full transition-colors duration-200 ${isCameraFlipped ? 'bg-cyan-500/80' : 'bg-gray-700'}`}
                    >
                        <div
                            className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform duration-200 ${isCameraFlipped ? 'translate-x-4' : 'translate-x-0'}`}
                        />
                    </button>
                </div>
            </div>

            {/* Tool Permissions Section */}
            <div className="mb-6">
                <div className="flex items-center justify-between mb-3">
                    <h3 className="text-cyan-400 font-bold text-xs uppercase tracking-wider opacity-80">Tool Confirmations</h3>
                </div>
                
                {/* Auto-allow All Switch */}
                <div className="flex items-center justify-between text-xs bg-cyan-900/30 p-2 rounded border border-cyan-500/30 mb-3">
                    <span className="text-cyan-100 font-medium">Auto-allow All Tools</span>
                    <button
                        onClick={() => {
                            // Check if all tools are currently auto-allowed (permission === false)
                            const allAutoAllowed = TOOLS.every(tool => permissions[tool.id] === false);
                            // If all auto-allowed, turn OFF auto-allow (set to true = confirmation required)
                            // Otherwise, turn ON auto-allow (set to false = auto-allowed)
                            const newValue = allAutoAllowed ? true : false;
                            const updates = {};
                            TOOLS.forEach(tool => {
                                updates[tool.id] = newValue;
                            });
                            console.log(`Auto-allow toggle: allAutoAllowed=${allAutoAllowed}, setting all to ${newValue}`);
                            socket.emit('update_settings', { tool_permissions: updates });
                        }}
                        className={`relative w-8 h-4 rounded-full transition-colors duration-200 ${TOOLS.every(tool => permissions[tool.id] === false) ? 'bg-cyan-500/80' : 'bg-gray-700'}`}
                    >
                        <div
                            className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform duration-200 ${TOOLS.every(tool => permissions[tool.id] === false) ? 'translate-x-4' : 'translate-x-0'}`}
                        />
                    </button>
                </div>
                
                <div className="space-y-2 max-h-40 overflow-y-auto pr-2 custom-scrollbar">
                    {TOOLS.map(tool => {
                        const isRequired = permissions[tool.id] !== false; // Default True
                        return (
                            <div key={tool.id} className="flex items-center justify-between text-xs bg-gray-900/50 p-2 rounded border border-cyan-900/30">
                                <span className="text-cyan-100/80">{tool.label}</span>
                                <button
                                    onClick={() => togglePermission(tool.id)}
                                    className={`relative w-8 h-4 rounded-full transition-colors duration-200 ${isRequired ? 'bg-cyan-500/80' : 'bg-gray-700'}`}
                                >
                                    <div
                                        className={`absolute top-0.5 left-0.5 w-3 h-3 bg-white rounded-full transition-transform duration-200 ${isRequired ? 'translate-x-4' : 'translate-x-0'}`}
                                    />
                                </button>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Memory Section */}
            <div>
                <h3 className="text-cyan-400 font-bold mb-2 text-xs uppercase tracking-wider opacity-80">Memory Data</h3>
                <div className="flex flex-col gap-2">
                    <label className="text-[10px] text-cyan-500/60 uppercase">Upload Memory Text</label>
                    <input
                        type="file"
                        accept=".txt"
                        onChange={handleFileUpload}
                        className="text-xs text-cyan-100 bg-gray-900 border border-cyan-800 rounded p-2 file:mr-2 file:py-1 file:px-2 file:rounded-full file:border-0 file:text-[10px] file:font-semibold file:bg-cyan-900 file:text-cyan-400 hover:file:bg-cyan-800 cursor-pointer"
                    />
                </div>
            </div>
            </div>
        </div>
    );
};

export default SettingsWindow;
