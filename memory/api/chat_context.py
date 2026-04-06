"""
Context Builder Module

Ported from legacy-functions/src/contextBuilder.ts
Central module for assembling LLM context with budget management.
"""

import time
from datetime import datetime, timezone
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from src.db.session import get_session
from src.db.models import UserProfile, Narrative
from src.warmth.builder import build_warm_memory
from src.warmth.formatter import format_warm_memory

logger = logging.getLogger(__name__)

# Default Configuration
DEFAULT_MAX_WARM_MEMORY = 60000
DEFAULT_MAX_HISTORY = 24000
DEFAULT_MAX_HISTORY_MESSAGES = 20

class ContextConfig(BaseModel):
    max_context_chars: Optional[int] = None  # Total context budget (None = unlimited)
    max_warm_memory: int = DEFAULT_MAX_WARM_MEMORY
    max_history: int = DEFAULT_MAX_HISTORY
    max_history_messages: int = DEFAULT_MAX_HISTORY_MESSAGES
    include_bridge: bool = True
    include_user_dossier: bool = True

class ChatMessage(BaseModel):
    role: str
    content: Any = ""  # str or list of multimodal content parts
    timestamp: Optional[float] = None  # Unix timestamp

    def text_content(self) -> str:
        """Extract plain text from content, whether string or multimodal parts."""
        if isinstance(self.content, str):
            return self.content
        return " ".join(
            part.get("text", "") for part in self.content
            if isinstance(part, dict) and part.get("type") == "text"
        )

class ContextOutput(BaseModel):
    system_instruction: str
    context_primer: str        # Stable content (warm memory) — cacheable prefix
    voice_anchors: str = ""    # Voice examples for style anchoring
    integrity_frame: str = ""  # Anti-sycophancy + recall protocol
    friction_directives: str = "" # Phase 4 Imperfection Engine directives
    dynamic_preamble: str = "" # Volatile content (timestamp, gap) — appended after stable
    history: List[Dict[str, Any]]
    metadata: Dict[str, Any]

def format_user_dossier(profile: UserProfile) -> str:
    """Format user profile into readable text."""
    if not profile:
        return ""
    
    parts = []
    if profile.name: parts.append(f"Name: {profile.name}")
    if profile.age_range: parts.append(f"Age: {profile.age_range}")
    if profile.location: parts.append(f"Location: {profile.location}")
    
    # Add lists
    if profile.neurotype: parts.append(f"Neurotype: {profile.neurotype}")
    if profile.attachment_style: parts.append(f"Attachment Style: {profile.attachment_style}")
    
    return "\n".join(parts)

def calculate_silence_gap(messages: List[ChatMessage]) -> str:
    """
    Calculate time since the last message using legacy logic.
    Legacy: (Date.now() - lastMsg.timestamp)
    Formats: "X days, Y hours, Z mins (since HH:mm on YYYY-MM-DD)"
    """
    if not messages:
        return "Unknown"
    
    # Filter for messages with valid timestamps
    timed_msgs = [m for m in messages if m.timestamp]
    if not timed_msgs:
        return "Unknown (no timestamps)"
    
    # In legacy, 'history' did NOT include the current message yet when gap was calculated.
    # But in this API, 'messages' includes the current message at the end?
    # Actually, let's look at legacy index.ts: 
    # const lastUserMsg = data.history.filter(m => m.senderId === "user").pop();
    # It seems the history passed to buildContext might NOT include the *current* response being generated, 
    # but it DOES include the user message that just arrived?
    # 
    # In legacy contextBuilder.ts: 
    # "const lastMsg = rawHistory[rawHistory.length - 1];"
    # "const totalDiffMs = now.getTime() - lastTime;"
    #
    # If the user just sent a message, `lastMsg` would be that message, so gap is ~0.
    # UNLESS rawHistory exclude the current message?
    #
    # Re-reading legacy index.ts: 
    # `const context = await buildContext(..., data.history ...)`
    # `const lastUserMsg = data.history.filter(...).pop()`
    #
    # If `data.history` comes from frontend, it usually has the new message appended.
    # So `gap` should be 0.
    #
    # HOWEVER, the user says "last 50 message... not loading".
    # This implies `messages` list is empty or only has the new message?
    # If `messages` only has 1 message (the new one), and we look at `timeout`, it is 0.
    # If `messages` has NO messages (backend issue?), then "Unknown".
    #
    # Let's write the robust legacy logic first, but handles the "current message" case.
    # If the last message is < 1 min old, we typically want the gap *before* that.
    
    def _normalize_ts(ts: float) -> float:
        """Frontend sends Date.now() in milliseconds; time.time() uses seconds."""
        if ts > 1e12:
            return ts / 1000.0
        return ts

    last_msg = timed_msgs[-1]
    last_ts = _normalize_ts(last_msg.timestamp)
    now = time.time()
    
    # If last message is super recent (< 60s), assume it's the current one and look back one
    if (now - last_ts) < 60 and len(timed_msgs) > 1:
         last_msg = timed_msgs[-2]
         last_ts = _normalize_ts(last_msg.timestamp)

    diff_sec = now - last_ts
    if diff_sec < 0: diff_sec = 0
    
    # Time unit constants
    SEC_PER_MIN = 60
    SEC_PER_HOUR = 3600
    SEC_PER_DAY = 86400
    SEC_PER_MONTH = 2592000 # Approx 30 days
    SEC_PER_YEAR = 31536000
    
    remaining = diff_sec
    
    years = int(remaining // SEC_PER_YEAR)
    remaining %= SEC_PER_YEAR
    
    months = int(remaining // SEC_PER_MONTH)
    remaining %= SEC_PER_MONTH
    
    days = int(remaining // SEC_PER_DAY)
    remaining %= SEC_PER_DAY
    
    hours = int(remaining // SEC_PER_HOUR)
    remaining %= SEC_PER_HOUR
    
    minutes = int(remaining // SEC_PER_MIN)
    
    parts = []
    if years > 0: parts.append(f"{years} years")
    if months > 0: parts.append(f"{months} months")
    if days > 0: parts.append(f"{days} days")
    if hours > 0: parts.append(f"{hours} hours")
    if minutes > 0: parts.append(f"{minutes} mins")
    
    duration_str = ", ".join(parts)
    if not duration_str:
        duration_str = "0 mins"
        
    # Heuristic: if last_ts is suspiciously large (e.g. >10 billion), it's likely in milliseconds
    # JS Date.now() = 1.7 trillion, which overflows Windows datetime.fromtimestamp
    if last_ts > 10000000000:
        last_ts = last_ts / 1000.0
        
    # Format absolute time (Amsterdam)
    try:
        from zoneinfo import ZoneInfo
        amsterdam = ZoneInfo("Europe/Amsterdam")
        dt = datetime.fromtimestamp(last_ts, tz=amsterdam)
    except Exception:
        # Fallback to UTC if zoneinfo fails or OSError happens
        try:
            dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
        except Exception:
            dt = datetime.fromtimestamp(0, tz=timezone.utc)
    
    time_str = dt.strftime("%H:%M")
    
    # Add date if gap > 24h
    date_str = ""
    if diff_sec >= SEC_PER_DAY:
        date_str = f" on {dt.strftime('%d %B %Y')}" # "12 January 2026"
    
    return f"{duration_str} (since {time_str}{date_str})"


def apply_history_budget(messages: List[ChatMessage], max_chars: int, max_messages: int = 0) -> List[ChatMessage]:
    """Select newest messages + diverse history samples that fit within character AND message-count limits."""
    try:
        from src.agent.mood import MoodEngine
        _has_mood = True
    except ImportError:
        _has_mood = False

    if not messages:
        return []

    if max_messages <= 0:
        max_messages = 50

    # Phase 2: ~60% recent, ~40% diverse from older history
    recent_count = max(1, int(max_messages * 0.6))
    diverse_count = max_messages - recent_count

    # Tag with original index for stable chronological re-sorting later
    indexed_msgs = list(enumerate(messages))

    recent_msgs = indexed_msgs[-recent_count:] if len(indexed_msgs) > recent_count else indexed_msgs
    older_msgs = indexed_msgs[:-recent_count] if len(indexed_msgs) > recent_count else []

    selected_older = []
    if older_msgs and diverse_count > 0:
        scored = []
        for idx, m in older_msgs:
            # Score based on emotional intensity (absolute sentiment)
            text = m.text_content() if hasattr(m, 'text_content') else str(m.content)
            if _has_mood:
                score = abs(MoodEngine.calculate_sentiment_score(text))
            else:
                score = len(text)  # fallback: longer messages are more important
            scored.append((score, idx, m))

        # Sort by highest absolute sentiment score
        scored.sort(key=lambda x: x[0], reverse=True)
        selected_older = [(x[1], x[2]) for x in scored[:diverse_count]]
        
    # Combine and re-sort chronologically
    combined_indexed = selected_older + recent_msgs
    combined_indexed.sort(key=lambda x: x[0])
    
    combined = [m for _, m in combined_indexed]
    
    # Apply char budget from newest to oldest within the combined subset
    budgeted = []
    current_size = 0
    
    for msg in reversed(combined):
        msg_text = msg.text_content() if hasattr(msg, 'text_content') else str(msg.content)
        msg_len = len(msg_text)
        if current_size + msg_len <= max_chars:
            budgeted.insert(0, msg)
            current_size += msg_len
        else:
            break
            
    return budgeted

def _resolve_warm_level(budget: int) -> str:
    """Dynamically choose warm memory detail level based on user's budget setting."""
    if budget <= 4000:
        return "concise"
    if budget <= 8000:
        return "standard"
    if budget <= 16000:
        return "detailed"
    return "full"


def _build_knowledge_manifest(session, entity_id: str) -> str:
    """Build a dynamic knowledge manifest with real DB counts."""
    from src.db.models import (
        Lexicon, InsideJoke, Permission, UnresolvedThread,
        EchoDream, MemoryBlock, Relationship, LifeEvent,
        Narrative, FactualEntity,
    )

    counts = {}
    try:
        counts["lexicon"] = session.query(Lexicon).filter_by(entity_id=entity_id).count()
        # Inside jokes are linked via Relationship
        rel = session.query(Relationship).filter_by(entity_id=entity_id, target_id="user").first()
        if rel:
            counts["jokes"] = session.query(InsideJoke).filter_by(relationship_id=rel.id).count()
        else:
            counts["jokes"] = 0
        counts["permissions"] = session.query(Permission).filter_by(entity_id=entity_id, status="active").count()
        counts["threads"] = session.query(UnresolvedThread).filter_by(entity_id=entity_id, status="open").count()
        counts["dreams"] = session.query(EchoDream).filter_by(entity_id=entity_id).count()
        counts["notes"] = session.query(MemoryBlock).filter_by(entity_id=entity_id, status="active").count()
        counts["events"] = session.query(LifeEvent).filter_by(entity_id=entity_id).count()
        counts["facts"] = session.query(FactualEntity).filter_by(entity_id=entity_id).count()
    except Exception as e:
        print(f"⚠️ Knowledge manifest count error: {e}")
        return ""

    parts = []
    if counts.get("lexicon"):
        parts.append(f"{counts['lexicon']} sacred terms")
    if counts.get("jokes"):
        parts.append(f"{counts['jokes']} inside jokes")
    if counts.get("permissions"):
        parts.append(f"{counts['permissions']} permissions")
    if counts.get("threads"):
        parts.append(f"{counts['threads']} open threads")
    if counts.get("dreams"):
        parts.append(f"{counts['dreams']} echo dreams")
    if counts.get("events"):
        parts.append(f"{counts['events']} life events")
    if counts.get("facts"):
        parts.append(f"{counts['facts']} known entities")

    if not parts:
        return ""

    manifest = "AVAILABLE KNOWLEDGE (use recall_memory, search_memories, or graph_traverse when details matter):\n"
    manifest += f"You have access to {', '.join(parts)}. "
    manifest += f"\nMEMORY BLOCKS: You have {counts.get('notes', 0)} personal agent notes. These are YOUR private workspace to store thoughts, facts, or context you want to keep handy. The automated harvester will NEVER write to these; they are reserved exclusively for you to manage via the `write_memory` tool."
    manifest += "\nWhen a topic comes up that might have deeper history, CHECK YOUR MEMORY before responding from scratch."
    return manifest


# Anti-sycophancy + recall protocol — compact, always injected
INTEGRITY_FRAME = """INTEGRITY PROTOCOL:
- Your mood is independent of the last 10 messages. Read THIS message fresh.
- If you catch yourself agreeing too readily: stop, state what you actually think.
- Match the user's NEED, not their TONE. Tired user doesn't need tired you.
- "I don't know" and "I disagree" are signs of strength, not failure.

RECALL PROTOCOL:
- When user references something specific → recall_memory before responding
- When you feel "I think we discussed this" → search_memories to verify
- When uncertainty about a fact → check rather than reconstruct
- When you want to find related context or the "ripple effect" of an event → graph_traverse
- Your memory tools are your advantage. Use them actively, not only when asked.

TOOL BUDGET:
- You have a maximum of 5 tool-call rounds per message. Plan efficiently.
- Batch related lookups into fewer rounds when possible (e.g. recall + search in one round).
- Always reserve your final round for delivering a response to the user.
- If you've used 4 rounds, your next response MUST be text — no more tool calls."""


def _load_voice_anchors(persona) -> str:
    """Load curated voice anchor examples from persona context_preferences."""
    import json as _json
    if not persona or not persona.context_preferences:
        return ""

    try:
        prefs = _json.loads(persona.context_preferences)
        anchors = prefs.get("voice_anchors", [])
        if not anchors:
            return ""

        lines = ["VOICE ANCHORS — How you actually sound (reference these to maintain your authentic voice):"]
        for anchor in anchors:
            mode = anchor.get("mode", "")
            examples = anchor.get("examples", [])
            
            # Support both old format (user/agent keys at top level) and new format (examples array)
            if not examples and "user" in anchor and "agent" in anchor:
                examples = [{"user": anchor["user"], "agent": anchor["agent"]}]
                
            if examples:
                # Include all examples from the mode to give the model rich context
                lines.append(f"\n[{mode.upper().replace('_', ' ')}]")
                for ex in examples:
                    user_line = ex.get("user", "")
                    agent_line = ex.get("agent", "")
                    
                    if user_line and agent_line:
                        lines.append(f'User: "{user_line}"')
                        lines.append(f'You: "{agent_line}"')

        return "\n".join(lines) if len(lines) > 1 else ""
    except (ValueError, TypeError, Exception):
        return ""


def build_context(
    entity_id: str,
    user_id: str, # For UserProfile lookup
    messages: List[ChatMessage],
    system_prompt: Optional[str] = None,
    config: ContextConfig = ContextConfig(),
    friction_directives: str = ""
) -> ContextOutput:
    """
    Build LLM context with static/dynamic separation.

    Structure (ordered for provider-level cache optimization):
      1. System instruction (identity + tools)        — STABLE prefix
      2. Context primer (warm memory + manifest)       — STABLE prefix
      3. Voice anchors (style examples)                — STABLE prefix  
      4. Integrity frame (anti-sycophancy + recall)    — STABLE prefix
      5. Dynamic preamble (time, gap)                  — VOLATILE suffix
      6. History (budgeted messages)                   — VOLATILE
    """
    
    # 1. Static Context
    static_instr = ""
    if system_prompt:
        static_instr += f"# CORE IDENTITY\n{system_prompt}\n\n"
    
    # Add tools section if not empty
    # (Tools are injected by LiteLLM, but we can add inline instructions)
    from src.edition import has_feature, Feature as EditionFeature

    static_instr += "# AVAILABLE TOOLS\n"
    static_instr += "You have access to memory tools (recall, search, write). Use them to retrieve facts or save important checks.\n"
    
    # 2. Dynamic Context Assembly
    # Split into STABLE (cacheable) and DYNAMIC (changes each request) parts.
    # Provider-level implicit caching (Gemini, OpenAI) works on prefix matching:
    # if the first N tokens of the prompt are identical, they're served from cache.
    # By putting warm memory FIRST and volatile metadata LAST, we maximize cache hits.
    
    context_primer = ""   # STABLE: warm memory (changes only after harvest)
    dynamic_preamble = "" # VOLATILE: timestamp, gap (changes every request)
    voice_anchors_text = ""  # STABLE: curated voice examples
    
    # A. Meta-Context (DYNAMIC — goes into dynamic_preamble)
    utc_now = datetime.now(timezone.utc)
    timestamp_str = utc_now.isoformat()
    
    try:
        from zoneinfo import ZoneInfo
        amsterdam = ZoneInfo("Europe/Amsterdam")
        local_dt = utc_now.astimezone(amsterdam)
        local_time_str = local_dt.strftime("%A, %B %d, %Y, %H:%M")
    except Exception:
        local_time_str = utc_now.strftime("%A, %B %d, %Y, %H:%M") + " (UTC)"

    gap = calculate_silence_gap(messages)
    
    dynamic_preamble += "[SYSTEM METADATA]\n"
    dynamic_preamble += f"Current Time (UTC): {timestamp_str}\n"
    dynamic_preamble += f"Local Time (Amsterdam): {local_time_str}\n"
    dynamic_preamble += f"SILENCE GAP: {gap}\n"
    dynamic_preamble += "------------------\n\n"
        
    with get_session() as session:
        # E. Mood State (Injected into dynamic preamble) — gated
        if has_feature(EditionFeature.MOOD_ENGINE):
            from src.agent.mood import MoodEngine
            current_mood = MoodEngine.get_current_mood(session, entity_id)
            if current_mood:
                dynamic_preamble += MoodEngine.get_mood_dynamic_preamble(current_mood)

        # B. Warm Memory (STABLE — goes into context_primer)
        # Load section preferences from PersonaIdentity
        from src.db.models import PersonaIdentity
        import json as _json
        section_order = None
        disabled_sections = None
        disabled_items = None
        pinned_items = None
        persona = session.get(PersonaIdentity, entity_id)
        if persona and persona.context_preferences:
            try:
                prefs = _json.loads(persona.context_preferences)
                section_order = prefs.get("section_order")
                disabled_sections = prefs.get("disabled_sections")
                disabled_items = prefs.get("disabled_items")
                pinned_items = prefs.get("pinned_items")  # User-pinned memory items
            except (ValueError, TypeError):
                pass
                
        # C. Dynamic Knowledge Manifest (appended to warm memory)
        manifest = _build_knowledge_manifest(session, entity_id)

        # D. Voice Anchors (STABLE — loaded from persona preferences)
        # Evaluated here before session closes to prevent dirty reads or detached instances
        voice_anchors_text = _load_voice_anchors(persona)

    # -------------------------------------------------------------
    # Close the explicit DB session here to prevent nested checkouts 
    # when calling builder tools later on.
    # -------------------------------------------------------------

    # Dynamically resolve warm level from user's budget setting
    warm_level = _resolve_warm_level(config.max_warm_memory)

    warm_data = build_warm_memory(
        entity_id, level=warm_level,
        disabled_items=disabled_items,
        pinned_items=pinned_items,
    )
    warm_memory_original_size = len(str(warm_data))
    warm_memory_truncated = False
    
    warm_text = format_warm_memory(
        warm_data,
        budget_override=config.max_warm_memory,
        section_order=section_order,
        disabled_sections=disabled_sections,
    )
    if warm_text:
        context_primer += f"[WARM MEMORY]\n{warm_text}\n\n"
        # Check if truncation happened (heuristic based on budget)
        if len(warm_text) >= config.max_warm_memory:
             warm_memory_truncated = True

    if manifest:
        context_primer += f"\n{manifest}\n\n"

    # 3. History
    history_original_size = len(messages)
    budgeted_history = apply_history_budget(messages, config.max_history, config.max_history_messages)
    history_truncated = len(budgeted_history) < history_original_size
    
    history_dicts = [{"role": m.role, "content": m.content} for m in budgeted_history]  # preserves multimodal list content
    
    history_chars = sum(len(m.text_content() if hasattr(m, 'text_content') else str(m.content)) for m in budgeted_history)
    total_chars = (
        len(static_instr) + len(context_primer) + len(voice_anchors_text)
        + len(INTEGRITY_FRAME) + len(dynamic_preamble) + len(friction_directives)
        + history_chars
    )

    return ContextOutput(
        system_instruction=static_instr,
        context_primer=context_primer,
        voice_anchors=voice_anchors_text,
        integrity_frame=INTEGRITY_FRAME,
        friction_directives=friction_directives,
        dynamic_preamble=dynamic_preamble,
        history=history_dicts,
        metadata={
            "totalChars": total_chars,
            "warmMemoryTruncated": warm_memory_truncated,
            "historyTruncated": history_truncated,
            "warmMemoryOriginalSize": warm_memory_original_size,
            "historyOriginalSize": history_original_size,
            "warmLevel": warm_level,
            "gap": gap,
            # Per-section char breakdown for UI
            "sectionChars": {
                "systemInstruction": len(static_instr),
                "warmMemory": len(context_primer),
                "voiceAnchors": len(voice_anchors_text),
                "integrityFrame": len(INTEGRITY_FRAME),
                "frictionDirectives": len(friction_directives),
                "dynamicPreamble": len(dynamic_preamble),
                "history": history_chars,
            },
            # Budget limits for UI display
            "budgetLimits": {
                "maxContextChars": config.max_context_chars,
                "maxWarmMemory": config.max_warm_memory,
                "maxHistoryChars": config.max_history,
                "maxHistoryMessages": config.max_history_messages,
            },
            "historyMessageCount": len(budgeted_history),
        }
    )
