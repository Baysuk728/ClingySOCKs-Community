import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, MicOff, Phone, PhoneOff, Volume2, ChevronDown } from 'lucide-react';
import { VoiceModeSession, AudioProcessor, MicrophoneCapture } from '../services/voiceModeApi';
import { getApiUrlSync } from '../services/apiConfig';

interface VoiceModeProps {
    entityId: string;
    userId?: string;
    chatId?: string;
    agentName?: string;
    agentAvatar?: string;
    onClose: () => void;
    onTranscript?: (role: 'user' | 'assistant', text: string) => void;
}

type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

export const VoiceMode: React.FC<VoiceModeProps> = ({
    entityId,
    userId,
    chatId,
    agentName = 'Agent',
    agentAvatar,
    onClose,
    onTranscript,
}) => {
    const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
    const [isMuted, setIsMuted] = useState(false);
    const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
    const [transcript, setTranscript] = useState('');
    const [errorMessage, setErrorMessage] = useState('');
    const [elapsed, setElapsed] = useState(0);
    const [audioLevel, setAudioLevel] = useState(0);
    const [selectedVoice, setSelectedVoice] = useState<string>('');
    const [availableVoices, setAvailableVoices] = useState<string[]>([]);
    const [showVoiceSelect, setShowVoiceSelect] = useState(false);
    const [activeVoice, setActiveVoice] = useState<string>('');

    const sessionRef = useRef<VoiceModeSession | null>(null);
    const audioProcessorRef = useRef<AudioProcessor | null>(null);
    const micRef = useRef<MicrophoneCapture | null>(null);
    const startTimeRef = useRef<number>(0);
    const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
    const animFrameRef = useRef<number>(0);

    // Waveform animation
    const [waveformBars, setWaveformBars] = useState<number[]>(Array(12).fill(0.1));

    const updateWaveform = useCallback((speaking: boolean) => {
        if (speaking) {
            setWaveformBars(prev => prev.map(() => 0.15 + Math.random() * 0.85));
        } else {
            setWaveformBars(prev => prev.map(v => Math.max(0.1, v * 0.85)));
        }
    }, []);

    // Animate waveform
    useEffect(() => {
        if (connectionState !== 'connected') return;
        const animate = () => {
            updateWaveform(isAgentSpeaking);
            animFrameRef.current = requestAnimationFrame(animate);
        };
        animFrameRef.current = requestAnimationFrame(animate);
        return () => cancelAnimationFrame(animFrameRef.current);
    }, [connectionState, isAgentSpeaking, updateWaveform]);

    // Fetch available voices on mount
    useEffect(() => {
        const fetchVoices = async () => {
            try {
                // Ensure API_URL has no trailing slash and build url
                const baseUrl = getApiUrlSync();
                const res = await fetch(`${baseUrl}/voice/voices`);
                if (res.ok) {
                    const data = await res.json();
                    if (data.voices && Array.isArray(data.voices)) {
                        setAvailableVoices(data.voices);
                        if (data.default) setSelectedVoice(data.default);
                    }
                }
            } catch (err) {
                console.error("Failed to load voices:", err);
            }
        };
        fetchVoices();
    }, []);

    // Elapsed timer
    useEffect(() => {
        if (connectionState === 'connected') {
            startTimeRef.current = Date.now();
            timerRef.current = setInterval(() => {
                setElapsed(Math.floor((Date.now() - startTimeRef.current) / 1000));
            }, 1000);
        } else {
            if (timerRef.current) clearInterval(timerRef.current);
            setElapsed(0);
        }
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [connectionState]);

    const formatTime = (secs: number) => {
        const m = Math.floor(secs / 60).toString().padStart(2, '0');
        const s = (secs % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    };

    const startSession = useCallback(async () => {
        setConnectionState('connecting');
        setErrorMessage('');
        setTranscript('');

        const audioProcessor = new AudioProcessor();
        audioProcessor.init();
        audioProcessorRef.current = audioProcessor;

        // Accumulate transcript text for the current agent turn
        let turnTranscript = '';

        const session = new VoiceModeSession({
            onAudio: (b64) => {
                setIsAgentSpeaking(true);
                audioProcessor.playPcm16(b64);
            },
            onText: (text, role) => {
                turnTranscript += (turnTranscript ? ' ' : '') + text;
                setTranscript(turnTranscript);
                // Propagate to chat window (the previous double-push hypothesis was incorrect, chat history only comes from here)
                onTranscript?.(role as any, text);
            },
            onTurnComplete: () => {
                setIsAgentSpeaking(false);
                // Save the completed agent turn to chat history
                if (turnTranscript.trim()) {
                    session.saveMessage('assistant', turnTranscript.trim());
                }
                turnTranscript = '';
            },
            onInterrupted: () => {
                setIsAgentSpeaking(false);
                audioProcessor.stopAll();
                // Save partial transcript if any
                if (turnTranscript.trim()) {
                    session.saveMessage('assistant', turnTranscript.trim());
                }
                turnTranscript = '';
            },
            onError: (msg) => {
                setErrorMessage(msg);
                setConnectionState('error');
            },
            onSetupComplete: (info) => {
                setConnectionState('connected');
                setActiveVoice(info.voice);
                setAvailableVoices(info.voices);
                if (!selectedVoice) setSelectedVoice(info.voice);
                console.log(`Voice mode connected: ${info.model} (voice: ${info.voice})`);
            },
            onDisconnect: () => {
                setConnectionState('disconnected');
                stopMic();
            },
        });

        sessionRef.current = session;
        session.connect(entityId, {
            userId,
            voice: selectedVoice || undefined,
            chatId,
        });

        // Start microphone capture
        try {
            const mic = new MicrophoneCapture();
            await mic.start((b64) => {
                if (!isMuted) {
                    session.sendAudio(b64);
                }
            });
            micRef.current = mic;
        } catch (err: any) {
            setErrorMessage(`Microphone access denied: ${err.message}`);
            setConnectionState('error');
        }
    }, [entityId, userId, chatId, isMuted, selectedVoice, onTranscript]);

    const stopMic = useCallback(() => {
        if (micRef.current) {
            micRef.current.stop();
            micRef.current = null;
        }
    }, []);

    const endSession = useCallback(() => {
        sessionRef.current?.disconnect();
        sessionRef.current = null;
        audioProcessorRef.current?.destroy();
        audioProcessorRef.current = null;
        stopMic();
        setConnectionState('disconnected');
        setIsAgentSpeaking(false);
        setTranscript('');
    }, [stopMic]);

    const toggleMute = useCallback(() => {
        setIsMuted(prev => !prev);
    }, []);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            sessionRef.current?.disconnect();
            audioProcessorRef.current?.destroy();
            micRef.current?.stop();
            if (timerRef.current) clearInterval(timerRef.current);
            cancelAnimationFrame(animFrameRef.current);
        };
    }, []);

    const handleClose = useCallback(() => {
        endSession();
        onClose();
    }, [endSession, onClose]);

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-xl">
            <div className="relative w-full max-w-md mx-4 flex flex-col items-center gap-8 p-8">

                {/* Agent avatar / pulsing indicator */}
                <div className="relative">
                    <div className={`w-28 h-28 rounded-full border-2 flex items-center justify-center overflow-hidden transition-all duration-300 ${
                        isAgentSpeaking
                            ? 'border-nexus-accent shadow-[0_0_30px_rgba(0,242,255,0.4)]'
                            : connectionState === 'connected'
                                ? 'border-white/20'
                                : 'border-white/10'
                    }`}>
                        {agentAvatar ? (
                            <img src={agentAvatar} alt={agentName} className="w-full h-full object-cover" />
                        ) : (
                            <Volume2 className={`w-12 h-12 ${isAgentSpeaking ? 'text-nexus-accent' : 'text-gray-500'}`} />
                        )}
                    </div>
                    {/* Pulsing ring when speaking */}
                    {isAgentSpeaking && (
                        <div className="absolute inset-0 rounded-full border-2 border-nexus-accent/50 animate-ping" />
                    )}
                </div>

                {/* Agent name */}
                <div className="text-center">
                    <h2 className="text-xl font-bold text-white">{agentName}</h2>
                    <p className="text-sm text-gray-400 mt-1">
                        {connectionState === 'connecting' && 'Connecting...'}
                        {connectionState === 'connected' && `Voice mode ${formatTime(elapsed)}`}
                        {connectionState === 'disconnected' && 'Tap to start voice chat'}
                        {connectionState === 'error' && 'Connection error'}
                    </p>
                </div>

                {/* Voice selector — shown before connecting or when connected */}
                {(connectionState === 'disconnected' || connectionState === 'error') && (
                    <div className="relative">
                        <button
                            onClick={() => setShowVoiceSelect(!showVoiceSelect)}
                            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-sm text-gray-300 hover:bg-white/10 transition-all"
                        >
                            <Volume2 className="w-4 h-4" />
                            <span>{selectedVoice || 'Select voice'}</span>
                            <ChevronDown className={`w-4 h-4 transition-transform ${showVoiceSelect ? 'rotate-180' : ''}`} />
                        </button>
                        {showVoiceSelect && (
                            <div className="absolute top-full mt-1 left-1/2 -translate-x-1/2 bg-nexus-800 border border-white/10 rounded-lg shadow-xl z-10 py-1 min-w-[160px]">
                                {(availableVoices.length > 0 ? availableVoices : [
                                    'Charon', 'Fenrir', 'Kore', 'Puck',
                                    'Orus', 'Perseus', 'Zephyr', 'Algieba',
                                    'Enceladus',
                                ]).map((v) => (
                                    <button
                                        key={v}
                                        onClick={() => { setSelectedVoice(v); setShowVoiceSelect(false); }}
                                        className={`w-full text-left px-4 py-2 text-sm hover:bg-white/10 transition-colors ${
                                            v === selectedVoice ? 'text-nexus-accent' : 'text-gray-300'
                                        }`}
                                    >
                                        {v}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* Active voice indicator when connected */}
                {connectionState === 'connected' && activeVoice && (
                    <p className="text-xs text-gray-500">Voice: {activeVoice}</p>
                )}

                {/* Waveform visualizer */}
                {connectionState === 'connected' && (
                    <div className="flex items-end gap-1 h-12">
                        {waveformBars.map((height, i) => (
                            <div
                                key={i}
                                className={`w-1.5 rounded-full transition-all duration-100 ${
                                    isAgentSpeaking ? 'bg-nexus-accent' : 'bg-white/20'
                                }`}
                                style={{ height: `${height * 48}px` }}
                            />
                        ))}
                    </div>
                )}

                {/* Transcript */}
                {transcript && connectionState === 'connected' && (
                    <div className="w-full max-h-24 overflow-y-auto text-center px-4">
                        <p className="text-sm text-gray-300 italic leading-relaxed">{transcript}</p>
                    </div>
                )}

                {/* Error message */}
                {errorMessage && (
                    <div className="w-full px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20">
                        <p className="text-sm text-red-400 text-center">{errorMessage}</p>
                    </div>
                )}

                {/* Controls */}
                <div className="flex items-center gap-6">
                    {connectionState === 'connected' ? (
                        <>
                            {/* Mute button */}
                            <button
                                onClick={toggleMute}
                                className={`w-14 h-14 rounded-full flex items-center justify-center transition-all ${
                                    isMuted
                                        ? 'bg-red-500/20 border border-red-500/40 text-red-400'
                                        : 'bg-white/10 border border-white/20 text-white hover:bg-white/20'
                                }`}
                                title={isMuted ? 'Unmute' : 'Mute'}
                            >
                                {isMuted ? <MicOff className="w-6 h-6" /> : <Mic className="w-6 h-6" />}
                            </button>

                            {/* End call */}
                            <button
                                onClick={handleClose}
                                className="w-16 h-16 rounded-full bg-red-500 flex items-center justify-center text-white hover:bg-red-600 transition-all shadow-lg shadow-red-500/30"
                                title="End voice chat"
                            >
                                <PhoneOff className="w-7 h-7" />
                            </button>
                        </>
                    ) : connectionState === 'connecting' ? (
                        <div className="w-16 h-16 rounded-full bg-nexus-accent/20 border-2 border-nexus-accent/40 flex items-center justify-center">
                            <div className="w-6 h-6 border-2 border-nexus-accent border-t-transparent rounded-full animate-spin" />
                        </div>
                    ) : (
                        <>
                            {/* Start call */}
                            <button
                                onClick={startSession}
                                className="w-16 h-16 rounded-full bg-green-500 flex items-center justify-center text-white hover:bg-green-600 transition-all shadow-lg shadow-green-500/30"
                                title="Start voice chat"
                            >
                                <Phone className="w-7 h-7" />
                            </button>

                            {/* Close without starting */}
                            <button
                                onClick={onClose}
                                className="w-14 h-14 rounded-full bg-white/10 border border-white/20 flex items-center justify-center text-gray-400 hover:text-white hover:bg-white/20 transition-all"
                                title="Close"
                            >
                                <PhoneOff className="w-6 h-6" />
                            </button>
                        </>
                    )}
                </div>

                {/* Connection info */}
                {connectionState === 'connected' && (
                    <p className="text-xs text-gray-600">
                        Gemini Live &middot; {isMuted ? 'Muted' : 'Listening'}
                    </p>
                )}
            </div>
        </div>
    );
};
