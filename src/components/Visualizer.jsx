import React, { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

const Visualizer = ({ audioData, isListening, intensity = 0, width = 600, height = 400 }) => {
    const canvasRef = useRef(null);
    const matrixCanvasRef = useRef(null);

    // Use a ref for audioData to avoid re-creating the animation loop on every frame
    const audioDataRef = useRef(audioData);
    const intensityRef = useRef(intensity);
    const isListeningRef = useRef(isListening);

    useEffect(() => {
        audioDataRef.current = audioData;
        intensityRef.current = intensity;
        isListeningRef.current = isListening;
    }, [audioData, intensity, isListening]);

    // Matrix Falling Code Effect
    useEffect(() => {
        const canvas = matrixCanvasRef.current;
        if (!canvas) return;

        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext('2d');
        
        // Matrix characters - mix of Katakana, Latin, numbers
        const chars = 'アァカサタナハマヤャラワガザダバパイィキシチニヒミリヰギジヂビピウゥクスツヌフムユュルグズブヅプエェケセテネヘメレヱゲゼデベペオォコソトノホモヨョロヲゴゾドボポヴッン0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        
        const fontSize = 14;
        const columns = Math.floor(canvas.width / fontSize);
        
        // Array to track the y position of each column
        const drops = Array(columns).fill(1);
        
        let animationId;
        let frameCount = 0;
        
        const drawMatrix = () => {
            // Only update every 2nd frame for performance
            frameCount++;
            if (frameCount % 2 !== 0) {
                animationId = requestAnimationFrame(drawMatrix);
                return;
            }
            
            // Semi-transparent black to create trail effect
            ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            
            ctx.fillStyle = '#0F0'; // Matrix green
            ctx.font = `${fontSize}px monospace`;
            
            for (let i = 0; i < drops.length; i++) {
                // Random character
                const char = chars[Math.floor(Math.random() * chars.length)];
                
                // Varying shades of cyan/green for depth
                const alpha = Math.random() * 0.5 + 0.5;
                const isHead = Math.random() > 0.95;
                
                if (isHead) {
                    ctx.fillStyle = `rgba(34, 211, 238, ${alpha})`; // Bright cyan for head
                    ctx.shadowBlur = 10;
                    ctx.shadowColor = '#22d3ee';
                } else {
                    ctx.fillStyle = `rgba(6, 182, 212, ${alpha * 0.6})`; // Dimmed cyan
                    ctx.shadowBlur = 0;
                }
                
                // Draw character
                ctx.fillText(char, i * fontSize, drops[i] * fontSize);
                ctx.shadowBlur = 0;
                
                // Move drop down
                if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                    drops[i] = 0;
                }
                drops[i]++;
            }
            
            animationId = requestAnimationFrame(drawMatrix);
        };

        drawMatrix();
        return () => cancelAnimationFrame(animationId);
    }, [width, height]);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;

        // Ensure canvas internal resolution matches display size for sharpness
        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext('2d');
        let animationId;

        const draw = () => {
            const w = canvas.width;
            const h = canvas.height;
            const centerX = w / 2;
            const centerY = h / 2;
            const currentIntensity = intensityRef.current;
            const currentIsListening = isListeningRef.current;
            const baseRadius = Math.min(w, h) * 0.25;
            const radius = baseRadius + (currentIntensity * 40);

            ctx.clearRect(0, 0, w, h);

            // Base Circle (Glow)
            ctx.beginPath();
            ctx.arc(centerX, centerY, radius - 10, 0, Math.PI * 2);
            ctx.strokeStyle = 'rgba(6, 182, 212, 0.1)';
            ctx.lineWidth = 2;
            ctx.stroke();

            if (!currentIsListening) {
                // Idle State: Breathing Circle
                const time = Date.now() / 1000;
                const breath = Math.sin(time * 2) * 5;

                ctx.beginPath();
                ctx.arc(centerX, centerY, radius + breath, 0, Math.PI * 2);
                ctx.strokeStyle = 'rgba(34, 211, 238, 0.5)';
                ctx.lineWidth = 4;
                ctx.shadowBlur = 20;
                ctx.shadowColor = '#22d3ee';
                ctx.stroke();
                ctx.shadowBlur = 0;
            } else {
                // Active State: Just the Circle causing the pulse
                ctx.beginPath();
                ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
                ctx.strokeStyle = 'rgba(34, 211, 238, 0.8)';
                ctx.lineWidth = 4;
                ctx.shadowBlur = 20;
                ctx.shadowColor = '#22d3ee';
                ctx.stroke();
                ctx.shadowBlur = 0;
            }

            animationId = requestAnimationFrame(draw);
        };

        draw();
        return () => cancelAnimationFrame(animationId);
    }, [width, height]);

    return (
        <div className="relative" style={{ width, height }}>
            {/* Matrix Falling Code Background */}
            <canvas
                ref={matrixCanvasRef}
                className="absolute inset-0 z-0"
                style={{ width: '100%', height: '100%', opacity: 0.5 }}
            />

            {/* Central Logo/Text */}
            <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
                <motion.div
                    animate={{ scale: isListening ? [1, 1.1, 1] : 1 }}
                    transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                    className="text-cyan-100 font-bold tracking-widest drop-shadow-[0_0_15px_rgba(34,211,238,0.8)]"
                    style={{ fontSize: Math.min(width, height) * 0.1 }}
                >
                    NOVA
                </motion.div>
            </div>

            <canvas
                ref={canvasRef}
                className="absolute inset-0 z-5"
                style={{ width: '100%', height: '100%' }}
            />
        </div>
    );
};

export default Visualizer;
