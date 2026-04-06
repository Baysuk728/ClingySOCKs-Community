export const AVAILABLE_MODELS: Record<string, string[]> = {
  gemini: [
    'gemini/gemini-2.5-flash',
    'gemini/gemini-2.5-pro',
    'gemini/gemini-3-flash-preview',
    'gemini/gemini-3.1-pro-preview',
  ],
  openai: [
    'openai/gpt-4o',
    'openai/gpt-4o-mini',
    'openai/gpt-5',
    'openai/o3',
    'openai/o4-mini',
    'openai/gpt-4.1',
  ],
  claude: [
    'anthropic/claude-sonnet-4-6',
    'anthropic/claude-opus-4-6',
    'anthropic/claude-sonnet-4-5-20250514',
    'anthropic/claude-haiku-4-5-20250414',
  ],
  grok: [
    'xai/grok-2-1212',
    'xai/grok-2-vision-1212',
    'xai/grok-beta',
  ],
  openrouter: [
    'openrouter/google/gemini-2.5-flash',
    'openrouter/anthropic/claude-sonnet-4-5',
    'openrouter/openai/gpt-4o',
    'openrouter/x-ai/grok-2-1212',
  ],
  local: [
    // Populated dynamically from Ollama / LM Studio discovery.
    // These are common fallbacks shown when the backend is unreachable.
    'ollama_chat/llama3.1',
    'ollama_chat/mistral',
    'ollama_chat/gemma2',
    'ollama_chat/qwen2.5',
  ],
  elevenlabs: [
    'eleven_turbo_v2_5',
    'eleven_multilingual_v2',
  ]
};

// ─── TTS Voice Presets ──────────────────────────────
// Default voices per provider, shown as dropdown options in PersonaDeck

export interface VoiceOption {
  id: string;       // Value sent to API
  label: string;    // Display label
}

export const TTS_PROVIDERS = [
  { value: 'google',     label: 'Google TTS',             description: 'Budget — $4/1M chars' },
  { value: 'openai',     label: 'OpenAI TTS',             description: 'Great quality — $15/1M chars' },
  { value: 'elevenlabs', label: 'ElevenLabs',             description: 'Premium — $30/1M chars' },
  { value: 'local',      label: 'Local (Kokoro/Sesame)',  description: 'Free — requires GPU server' },
] as const;

export const TTS_VOICES: Record<string, VoiceOption[]> = {
  google: [
    { id: 'en-US-Neural2-D', label: 'Neural2-D (Male, US)' },
    { id: 'en-US-Neural2-F', label: 'Neural2-F (Female, US)' },
    { id: 'en-US-Neural2-A', label: 'Neural2-A (Male, US)' },
    { id: 'en-US-Neural2-C', label: 'Neural2-C (Female, US)' },
    { id: 'en-US-Neural2-H', label: 'Neural2-H (Female, US)' },
    { id: 'en-US-Neural2-I', label: 'Neural2-I (Male, US)' },
    { id: 'en-US-Studio-O',  label: 'Studio-O (Female, US)' },
    { id: 'en-US-Studio-Q',  label: 'Studio-Q (Male, US)' },
    { id: 'en-GB-Neural2-A', label: 'Neural2-A (Female, GB)' },
    { id: 'en-GB-Neural2-B', label: 'Neural2-B (Male, GB)' },
    { id: 'en-GB-Neural2-D', label: 'Neural2-D (Female, GB)' },
    { id: 'nl-NL-Neural2-A', label: 'Neural2-A (Female, NL)' },
    { id: 'nl-NL-Neural2-B', label: 'Neural2-B (Male, NL)' },
    { id: 'nl-NL-Neural2-C', label: 'Neural2-C (Male, NL)' },
    { id: 'nl-NL-Neural2-D', label: 'Neural2-D (Female, NL)' },
  ],
  openai: [
    { id: 'alloy',   label: 'Alloy (Neutral)' },
    { id: 'ash',     label: 'Ash (Warm male)' },
    { id: 'ballad',  label: 'Ballad (Soft)' },
    { id: 'coral',   label: 'Coral (Warm female)' },
    { id: 'echo',    label: 'Echo (Neutral male)' },
    { id: 'fable',   label: 'Fable (Expressive)' },
    { id: 'onyx',    label: 'Onyx (Deep male)' },
    { id: 'nova',    label: 'Nova (Energetic female)' },
    { id: 'sage',    label: 'Sage (Authoritative)' },
    { id: 'shimmer', label: 'Shimmer (Warm female)' },
  ],
  elevenlabs: [
    { id: 'JBFqnCBsd6RMkjVDRZzb', label: 'George (Warm British)' },
    { id: 'EXAVITQu4vr4xnSDxMaL', label: 'Sarah (Soft American)' },
    { id: '21m00Tcm4TlvDq8ikWAM', label: 'Rachel (Calm)' },
    { id: 'pNInz6obpgDQGcFmaJgB', label: 'Adam (Narrative)' },
    { id: 'yoZ06aMxZJJ28mfd3POQ', label: 'Sam (Raspy)' },
    { id: 'onwK4e9ZLuTAKqWW03F9', label: 'Daniel (Authoritative British)' },
    { id: 'XB0fDUnXU5powFXDhCwa', label: 'Charlotte (Seductive)' },
  ],
  local: [
    { id: 'af_heart',   label: 'Heart (Female, warm)' },
    { id: 'af_bella',   label: 'Bella (Female, calm)' },
    { id: 'af_nicole',  label: 'Nicole (Female, whisper)' },
    { id: 'am_adam',    label: 'Adam (Male)' },
    { id: 'am_michael', label: 'Michael (Male, deep)' },
    { id: 'bf_emma',    label: 'Emma (British female)' },
    { id: 'bm_george',  label: 'George (British male)' },
  ],
};
