"""
Conversation Chunker for ClingySOCKs Memory.

Splits large conversations into manageable chunks for LLM processing.
Uses time-based chunking (6hr gaps) with character limits (50K max per chunk).

Ported from legacy TypeScript: harvestChunker.ts
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.config import (
    MAX_CHUNK_CHARS, TIME_GAP_HOURS, MIN_CHUNK_MESSAGES,
    MAX_CHUNK_MESSAGES, CHUNK_THRESHOLD_CHARS, CHUNK_THRESHOLD_MESSAGES
)


@dataclass
class ChunkMessage:
    id: str
    content: str
    timestamp: datetime
    sender_id: str


@dataclass
class ConversationChunk:
    chunk_id: str
    chunk_order: int
    messages: list[ChunkMessage]
    char_count: int
    message_count: int
    time_start: datetime
    time_end: datetime


@dataclass
class ChunkingResult:
    should_chunk: bool
    chunks: list[ConversationChunk]
    total_chars: int
    total_messages: int

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def avg_chunk_size(self) -> int:
        return self.total_chars // max(self.chunk_count, 1)


def chunk_conversation(
    messages: list[ChunkMessage],
    conversation_id: str,
    max_chunk_chars: int = MAX_CHUNK_CHARS,
    time_gap_hours: int = TIME_GAP_HOURS,
    min_chunk_messages: int = MIN_CHUNK_MESSAGES,
    max_chunk_messages: int = MAX_CHUNK_MESSAGES,
) -> ChunkingResult:
    """
    Chunk a conversation into manageable pieces for LLM processing.

    Strategy:
    - Conversations < threshold: No chunking
    - Larger: Smart chunking by time gaps + size limits
    """
    total_chars = sum(len(m.content) for m in messages)
    total_messages = len(messages)

    should_chunk = (
        total_chars >= CHUNK_THRESHOLD_CHARS or
        total_messages >= CHUNK_THRESHOLD_MESSAGES
    )

    if not should_chunk:
        single_chunk = _create_chunk(messages, conversation_id, 0)
        return ChunkingResult(
            should_chunk=False,
            chunks=[single_chunk],
            total_chars=total_chars,
            total_messages=total_messages,
        )

    chunks = _split_by_time_and_size(
        messages, conversation_id,
        max_chunk_chars, time_gap_hours,
        min_chunk_messages, max_chunk_messages,
    )

    return ChunkingResult(
        should_chunk=True,
        chunks=chunks,
        total_chars=total_chars,
        total_messages=total_messages,
    )


def _split_by_time_and_size(
    messages: list[ChunkMessage],
    conversation_id: str,
    max_chunk_chars: int,
    time_gap_hours: int,
    min_chunk_messages: int,
    max_chunk_messages: int,
) -> list[ConversationChunk]:
    """Split messages using time gaps + size limits."""
    chunks: list[ConversationChunk] = []
    current_msgs: list[ChunkMessage] = []
    current_chars = 0
    chunk_order = 0

    time_gap_seconds = time_gap_hours * 3600

    for i, msg in enumerate(messages):
        # Check for time gap (natural conversation break)
        if i > 0 and len(current_msgs) >= min_chunk_messages:
            prev_ts = messages[i - 1].timestamp.timestamp()
            curr_ts = msg.timestamp.timestamp()
            gap = curr_ts - prev_ts

            if gap >= time_gap_seconds:
                chunks.append(_create_chunk(current_msgs, conversation_id, chunk_order))
                chunk_order += 1
                current_msgs = []
                current_chars = 0

        current_msgs.append(msg)
        current_chars += len(msg.content)

        # Hard limit check
        at_hard_limit = (
            current_chars >= max_chunk_chars * 2 or
            len(current_msgs) >= max_chunk_messages * 2
        )

        if at_hard_limit and len(current_msgs) >= min_chunk_messages:
            chunks.append(_create_chunk(current_msgs, conversation_id, chunk_order))
            chunk_order += 1
            current_msgs = []
            current_chars = 0

        # Soft limit — look for breakpoint
        elif (current_chars >= max_chunk_chars and
              len(current_msgs) >= min_chunk_messages):
            if i < len(messages) - 1:
                next_ts = messages[i + 1].timestamp.timestamp()
                next_gap = next_ts - msg.timestamp.timestamp()

                if next_gap >= time_gap_seconds / 2:
                    chunks.append(_create_chunk(current_msgs, conversation_id, chunk_order))
                    chunk_order += 1
                    current_msgs = []
                    current_chars = 0

    # Save final chunk
    if current_msgs:
        chunks.append(_create_chunk(current_msgs, conversation_id, chunk_order))

    return chunks


def _create_chunk(
    messages: list[ChunkMessage],
    conversation_id: str,
    order: int,
) -> ConversationChunk:
    """Create a chunk from a list of messages."""
    return ConversationChunk(
        chunk_id=f"{conversation_id}_chunk_{order:03d}",
        chunk_order=order,
        messages=messages,
        char_count=sum(len(m.content) for m in messages),
        message_count=len(messages),
        time_start=messages[0].timestamp,
        time_end=messages[-1].timestamp,
    )


def format_chunk_stats(result: ChunkingResult, title: str = "") -> str:
    """Format chunking stats for logging."""
    prefix = f"[{title}] " if title else ""
    lines = [
        f"📦 Chunking {prefix}:",
        f"   Total: {result.total_messages} msgs, {result.total_chars / 1000:.1f}K chars",
        f"   Chunks: {result.chunk_count} (avg {result.avg_chunk_size / 1000:.1f}K chars each)",
    ]

    if result.should_chunk:
        for i, chunk in enumerate(result.chunks):
            duration_hrs = (chunk.time_end.timestamp() - chunk.time_start.timestamp()) / 3600
            lines.append(
                f"   [{i+1}] {chunk.message_count} msgs, "
                f"{chunk.char_count / 1000:.1f}K chars, "
                f"{duration_hrs:.1f}h span"
            )

    return "\n".join(lines)
