/**
 * Voice Mode API — Real-time bidirectional voice chat via WebSocket.
 *
 * Connects to the backend /voice/live/{entityId} WebSocket endpoint
 * which bridges to the Gemini Live API for audio streaming.
 *
 * Audio format:
 *   - Input:  PCM16, 16kHz, mono (from MediaRecorder / AudioWorklet)
 *   - Output: PCM16, 24kHz, mono (from Gemini, played via Web Audio API)
 */

import { getApiUrlSync } from './apiConfig';

const API_URL = getApiUrlSync();
const API_KEY = import.meta.env.VITE_MEMORY_API_KEY || '';

export interface VoiceModeCallbacks {
    onAudio: (pcm16Base64: string) => void;
    onText: (text: string, role: string) => void;
    onTurnComplete: () => void;
    onInterrupted: () => void;
    onError: (message: string) => void;
    onSetupComplete: (info: { model: string; voice: string; voices: string[] }) => void;
    onDisconnect: () => void;
}

export class VoiceModeSession {
    private ws: WebSocket | null = null;
    private callbacks: VoiceModeCallbacks;
    private keepAliveTimer: ReturnType<typeof setInterval> | null = null;

    constructor(callbacks: VoiceModeCallbacks) {
        this.callbacks = callbacks;
    }

    connect(entityId: string, options?: { userId?: string; voice?: string; chatId?: string }): void {
        const wsBase = API_URL.replace(/^http/, 'ws');
        const params = new URLSearchParams();
        if (options?.userId) params.set('user_id', options.userId);
        if (options?.voice) params.set('voice', options.voice);
        if (options?.chatId) params.set('chat_id', options.chatId);
        if (API_KEY) params.set('api_key', API_KEY);

        const url = `${wsBase}/voice/live/${entityId}?${params.toString()}`;
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            // Start keep-alive pings every 30s
            this.keepAliveTimer = setInterval(() => {
                if (this.ws?.readyState === WebSocket.OPEN) {
                    this.ws.send('ping');
                }
            }, 30_000);
        };

        this.ws.onmessage = (event) => {
            if (event.data === 'pong') return;

            try {
                const msg = JSON.parse(event.data);
                switch (msg.type) {
                    case 'audio':
                        this.callbacks.onAudio(msg.data);
                        break;
                    case 'text':
                        this.callbacks.onText(msg.text, msg.role || 'assistant');
                        break;
                    case 'turn_complete':
                        this.callbacks.onTurnComplete();
                        break;
                    case 'interrupted':
                        this.callbacks.onInterrupted();
                        break;
                    case 'error':
                        this.callbacks.onError(msg.message);
                        break;
                    case 'setup_complete':
                        this.callbacks.onSetupComplete({
                            model: msg.model,
                            voice: msg.voice,
                            voices: msg.voices || [],
                        });
                        break;
                    case 'ping':
                        // Server ping — respond with pong
                        this.ws?.send(JSON.stringify({ type: 'pong' }));
                        break;
                }
            } catch {
                // Ignore non-JSON messages
            }
        };

        this.ws.onerror = () => {
            this.callbacks.onError('WebSocket connection error');
        };

        this.ws.onclose = () => {
            this.cleanup();
            this.callbacks.onDisconnect();
        };
    }

    sendAudio(pcm16Base64: string): void {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'audio', data: pcm16Base64 }));
        }
    }

    sendText(text: string): void {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'text', text }));
        }
    }

    saveMessage(role: 'user' | 'assistant', content: string): void {
        if (this.ws?.readyState === WebSocket.OPEN && content.trim()) {
            this.ws.send(JSON.stringify({ type: 'save_message', role, content }));
        }
    }

    interrupt(): void {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'interrupt' }));
        }
    }

    disconnect(): void {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'end' }));
        }
        this.cleanup();
    }

    private cleanup(): void {
        if (this.keepAliveTimer) {
            clearInterval(this.keepAliveTimer);
            this.keepAliveTimer = null;
        }
        if (this.ws) {
            this.ws.onclose = null; // Prevent callback loop
            if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
                this.ws.close();
            }
            this.ws = null;
        }
    }

    get isConnected(): boolean {
        return this.ws?.readyState === WebSocket.OPEN;
    }
}

/**
 * Audio utilities for PCM16 ↔ Web Audio API conversion.
 */
export class AudioProcessor {
    private audioContext: AudioContext | null = null;
    private nextPlayTime: number = 0;
    private scheduledBuffers: AudioBufferSourceNode[] = [];
    private filterNode: BiquadFilterNode | null = null;

    /** Start the audio context (must be called from user gesture). */
    init(): AudioContext {
        if (!this.audioContext) {
            this.audioContext = new AudioContext({ sampleRate: 24000 });

            // Create a Low-Shelf filter to boost bass
            this.filterNode = this.audioContext.createBiquadFilter();
            this.filterNode.type = 'lowshelf';
            this.filterNode.frequency.value = 300; // Focus on sub-300Hz (man's chest voice)
            this.filterNode.gain.value = 12;       // Boost by 6 decibels

            // Create a High-Cut filter to remove "helium" sizzle
            const highCut = this.audioContext.createBiquadFilter();
            highCut.type = 'lowpass';
            highCut.frequency.value = 4000;      // Cut off sharp high frequencies

            this.filterNode.connect(highCut);
            highCut.connect(this.audioContext.destination);
        }
        return this.audioContext;
    }

    /** Decode base64 PCM16 and schedule playback. */
    playPcm16(base64Data: string): void {
        if (!this.audioContext) return;

        const raw = atob(base64Data);
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) {
            bytes[i] = raw.charCodeAt(i);
        }

        // Convert PCM16 LE to Float32
        const int16 = new Int16Array(bytes.buffer);
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) {
            float32[i] = int16[i] / 32768;
        }

        // Create an AudioBuffer and play
        const buffer = this.audioContext.createBuffer(1, float32.length, 24000);
        buffer.getChannelData(0).set(float32);

        const source = this.audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(this.filterNode!);

        // Schedule seamlessly after previous chunk
        const now = this.audioContext.currentTime;
        const startTime = Math.max(now, this.nextPlayTime);
        source.start(startTime);
        this.nextPlayTime = startTime + buffer.duration;
        this.scheduledBuffers.push(source);

        // Cleanup finished buffers
        source.onended = () => {
            const idx = this.scheduledBuffers.indexOf(source);
            if (idx >= 0) this.scheduledBuffers.splice(idx, 1);
        };
    }

    /** Stop all currently playing audio (for interruption). */
    stopAll(): void {
        for (const source of this.scheduledBuffers) {
            try { source.stop(); } catch { /* already stopped */ }
        }
        this.scheduledBuffers = [];
        this.nextPlayTime = 0;
    }

    /** Clean up the audio context. */
    destroy(): void {
        this.stopAll();
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
    }
}

/**
 * Captures microphone audio as PCM16 16kHz mono chunks.
 * Uses AudioWorklet for low-latency processing.
 */
export class MicrophoneCapture {
    private stream: MediaStream | null = null;
    private audioContext: AudioContext | null = null;
    private sourceNode: MediaStreamAudioSourceNode | null = null;
    private workletNode: AudioWorkletNode | null = null;
    private onChunk: ((base64Pcm16: string) => void) | null = null;

    /** Start capturing microphone audio. Calls onChunk with base64 PCM16 data. */
    async start(onChunk: (base64Pcm16: string) => void): Promise<void> {
        this.onChunk = onChunk;

        this.stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: 16000,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });

        this.audioContext = new AudioContext({ sampleRate: 16000 });
        this.sourceNode = this.audioContext.createMediaStreamSource(this.stream);

        // Use ScriptProcessorNode as fallback (AudioWorklet requires served worklet file)
        // bufferSize=4096 gives ~256ms chunks at 16kHz — good balance of latency vs overhead
        const processor = this.audioContext.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = (e) => {
            const float32 = e.inputBuffer.getChannelData(0);
            // Convert Float32 to PCM16 LE
            const int16 = new Int16Array(float32.length);
            for (let i = 0; i < float32.length; i++) {
                const s = Math.max(-1, Math.min(1, float32[i]));
                int16[i] = s < 0 ? s * 32768 : s * 32767;
            }
            // Base64 encode
            const bytes = new Uint8Array(int16.buffer);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            const b64 = btoa(binary);
            this.onChunk?.(b64);
        };

        this.sourceNode.connect(processor);
        processor.connect(this.audioContext.destination); // Required for processing to run
    }

    /** Stop capturing and release microphone. */
    stop(): void {
        if (this.workletNode) {
            this.workletNode.disconnect();
            this.workletNode = null;
        }
        if (this.sourceNode) {
            this.sourceNode.disconnect();
            this.sourceNode = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(t => t.stop());
            this.stream = null;
        }
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
        this.onChunk = null;
    }
}
