"""
Echo Layer Pipeline.

Detects silence gaps in conversation chunks and generates "Echo Dreams"
that represent the agent's internal processing during that time.
"""

import json
import re
from datetime import timedelta
import litellm

from src.config import (
    TIME_GAP_HOURS, NARRATIVE_MODEL, NARRATIVE_TEMPERATURE,
    GEMINI_API_KEY, OPENAI_API_KEY
)
from src.model_registry import LOCAL_API_BASE, get_llm_timeout
from src.pipeline.chunker import ConversationChunk
from src.prompts.echo import build_echo_prompt, ECHO_SYSTEM_INSTRUCTION

async def run_echo_pass(
    chunk: ConversationChunk,
    rolling_context: str,
    agent_name: str,
    user_name: str,
) -> list[dict]:
    """
    Scan chunk for time gaps and generate dreams.
    Returns a list of dicts (EchoDream data).
    """
    dreams = []
    
    # We need to look at gaps BETWEEN messages
    # But also potentially before the FIRST message if there was a gap from previous chunk?
    # For simplicity in this harvester, we'll look at gaps WITHIN the chunk.
    # (Cross-chunk gaps are harder without tracking previous chunk end time explicitly in this pass)
    
    # Actually, simpler: just check gap between msg[i] and msg[i-1]
    
    msgs = chunk.messages
    if len(msgs) < 2:
        return []

    try:
        for i in range(1, len(msgs)):
            prev = msgs[i-1]
            curr = msgs[i]
            
            diff = curr.timestamp - prev.timestamp
            hours = diff.total_seconds() / 3600.0
            
            if hours >= TIME_GAP_HOURS:
                # GAP DETECTED!
                print(f"   💤 Gap detected: {hours:.1f}h. Dreaming...")
                
                # Generate dream
                dream_data = await _generate_dream(
                    gap_hours=hours,
                    last_msg=prev,
                    rolling_context=rolling_context,
                    agent_name=agent_name,
                    user_name=user_name
                )
                
                # Handle cases where LLM returns a list instead of a dict
                if isinstance(dream_data, list) and len(dream_data) > 0:
                    dream_data = dream_data[0]
                
                if isinstance(dream_data, dict) and dream_data:
                    # Add metadata
                    dream_data["gap_duration_hours"] = hours
                    dream_data["gap_last_topic"] = prev.content[:50] + "..."
                    dream_data["gap_time_since"] = prev.timestamp
                    dreams.append(dream_data)

    except Exception as e:
        import traceback
        print(f"   ❌ Echo Pass Error: {e}")
        traceback.print_exc()
        return []

    return dreams


async def _generate_dream(
    gap_hours: float,
    last_msg,
    rolling_context: str,
    agent_name: str,
    user_name: str
) -> dict:
    
    prompt = build_echo_prompt(
        gap_hours=gap_hours,
        last_message_text=last_msg.content,
        rolling_context=rolling_context,
        agent_name=agent_name,
        user_name=user_name
    )
    
    # LiteLLM automatically uses os.environ["GEMINI_API_KEY"] and ["OPENAI_API_KEY"]
        
    try:
        response = await litellm.acompletion(
            model=NARRATIVE_MODEL, # Use narrative model for creative writing
            messages=[
                {"role": "system", "content": ECHO_SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7, # Higher temp for dreaming
            max_tokens=1024,
            response_format={"type": "json_object"},
            timeout=get_llm_timeout(NARRATIVE_MODEL, LOCAL_API_BASE)
        )
        
        content = response.choices[0].message.content
        return _parse_json(content)
        
    except Exception as e:
        print(f"   ❌ Dream generation failed: {e}")
        return {}

def _parse_json(raw: str) -> dict:
    if not raw: return {}
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```\w*\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
    try:
        return json.loads(cleaned)
    except:
        return {}
