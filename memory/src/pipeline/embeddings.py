"""
Embedding generation and management for pgvector semantic search.

Uses LiteLLM's embedding API (supports OpenAI, Gemini, Cohere, etc.)
to generate embeddings, and stores them in the memory_embeddings table.

Uses the memory_registry as the single source of truth for embeddable types.
"""

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

import litellm

from src.config import (
    EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, EMBEDDING_BATCH_SIZE,
    EMBEDDINGS_ENABLED,
)
from src.db.models import (
    MemoryEmbedding, Relationship, Message, Conversation,
)
from src.db.session import get_session
from src.memory_registry import embeddable_types, resolve_model


# Minimum content length for a message to be worth embedding
MIN_MESSAGE_CHARS = 50

# Patterns that indicate a trivial/non-embeddable message
_TRIVIAL_PATTERNS = re.compile(
    r"^(ok|okay|yes|no|yeah|nah|sure|thanks|thank you|lol|haha|hmm|"
    r"brb|gtg|bye|hi|hey|hello|good morning|good night|gn|gm|"
    r"👍|❤️|😂|🔥|💀|😭|🙏|✅|👀|😊|🥰|💜)\.?!?\s*$",
    re.IGNORECASE,
)


def _content_hash(text: str) -> str:
    """Generate a short hash for content change detection."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def _is_meaningful_message(content: str) -> bool:
    """Check if a message is worth embedding (not trivial/short)."""
    if not content or len(content.strip()) < MIN_MESSAGE_CHARS:
        return False
    if _TRIVIAL_PATTERNS.match(content.strip()):
        return False
    return True


def generate_embedding(text: str) -> list[float]:
    """
    Generate a single embedding vector using LiteLLM (synchronous).
    """
    response = litellm.embedding(
        model=EMBEDDING_MODEL,
        input=[text],
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0]["embedding"]


def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts (synchronous).
    """
    if not texts:
        return []

    all_embeddings = []

    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i:i + EMBEDDING_BATCH_SIZE]
        print(f"    📡 Batch {i // EMBEDDING_BATCH_SIZE + 1}: {len(batch)} items...")
        response = litellm.embedding(
            model=EMBEDDING_MODEL,
            input=batch,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        batch_embeddings = [item["embedding"] for item in response.data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


# ============================================================================
# Text extraction for each memory type
# ============================================================================

def _embeddable_text(memory_type: str, item: Any) -> str | None:
    """
    Extract the embeddable text from a memory item.
    Returns None if item has no meaningful text to embed.

    Uses the registry's embeddable_fields to auto-build the text.
    Falls back to a manual extractor for message type.
    """
    if memory_type == "messages":
        try:
            return f"[{item.sender_id}] {item.content[:500]}"
        except Exception:
            return None

    from src.memory_registry import get_def, is_known_type

    if not is_known_type(memory_type):
        return None

    defn = get_def(memory_type)
    if not defn.embeddable_fields:
        return None

    try:
        parts = []
        for field_name in defn.embeddable_fields:
            val = getattr(item, field_name, None)
            if val:
                text = str(val)[:500]
                parts.append(text)
        combined = ". ".join(parts)
        return combined if combined.strip() else None
    except Exception:
        return None


# ============================================================================
# Bulk embedding generation for an entity
# ============================================================================

def _get_type_models() -> dict[str, type]:
    """Build the type → Model mapping from the registry (lazy)."""
    result = {}
    for defn in embeddable_types():
        result[defn.key] = resolve_model(defn.key)
    return result


async def embed_entity_memories(
    entity_id: str,
    memory_types: list[str] | None = None,
    force_reembed: bool = False,
) -> dict[str, int]:
    """
    Generate embeddings for all memory items of an entity,
    including relevant chat messages.

    Skips items that already have up-to-date embeddings (same content hash)
    unless force_reembed is True.
    """
    if not EMBEDDINGS_ENABLED:
        return {"status": "disabled"}

    type_models = _get_type_models()
    types_to_process = memory_types or (list(type_models.keys()) + ["messages"])
    stats = {}

    with get_session() as session:
        rel = (
            session.query(Relationship)
            .filter_by(entity_id=entity_id, target_id="user")
            .first()
        )

        # --- Standard memory types ---
        for mem_type in types_to_process:
            if mem_type == "messages":
                continue  # Handle separately below

            Model = type_models.get(mem_type)
            if not Model:
                continue

            # Query items — use registry to determine query strategy
            from src.memory_registry import get_def, is_known_type
            defn = get_def(mem_type) if is_known_type(mem_type) else None
            if defn and defn.needs_relationship:
                if not rel:
                    continue
                items = session.query(Model).filter_by(relationship_id=rel.id).all()
            else:
                items = session.query(Model).filter_by(entity_id=entity_id).all()

            if not items:
                print(f"  ⏭️  {mem_type}: no items, skipping")
                continue

            print(f"  📦 {mem_type}: {len(items)} items found")

            # Get existing embeddings for this type
            existing = {}
            if not force_reembed:
                rows = (
                    session.query(MemoryEmbedding)
                    .filter_by(entity_id=entity_id, memory_type=mem_type)
                    .all()
                )
                existing = {r.memory_id: r for r in rows}

            # Prepare texts needing embedding
            to_embed = []
            for item in items:
                item_id = str(item.id)
                text = _embeddable_text(mem_type, item)
                if not text:
                    continue

                text_hash = _content_hash(text)
                if not force_reembed and item_id in existing:
                    if existing[item_id].content_hash == text_hash:
                        continue

                to_embed.append((item_id, text, text_hash))

            if not to_embed:
                print(f"  ✅ {mem_type}: all up to date")
                continue

            print(f"  🔢 {mem_type}: embedding {len(to_embed)} items...")

            # Generate embeddings in batch (synchronous)
            texts = [t[1] for t in to_embed]
            try:
                vectors = generate_embeddings_batch(texts)
            except Exception as e:
                print(f"  ❌ Embedding failed for {mem_type}: {e}")
                continue

            # Store/update embeddings
            count = 0
            for (item_id, text, text_hash), vector in zip(to_embed, vectors):
                existing_emb = existing.get(item_id)
                if existing_emb:
                    existing_emb.embedding = vector
                    existing_emb.content_hash = text_hash
                    existing_emb.text_preview = text[:200]
                    existing_emb.updated_at = datetime.now(timezone.utc)
                else:
                    emb = MemoryEmbedding(
                        entity_id=entity_id,
                        memory_type=mem_type,
                        memory_id=item_id,
                        content_hash=text_hash,
                        text_preview=text[:200],
                        embedding=vector,
                    )
                    session.add(emb)
                count += 1

            session.flush()
            stats[mem_type] = count
            print(f"  ✅ {mem_type}: {count} embedded")

        # --- Messages (special handling) ---
        if "messages" in types_to_process:
            msg_count = await _embed_messages(session, entity_id, force_reembed)
            if msg_count > 0:
                stats["messages"] = msg_count

    print(f"\n  🔢 Total: {stats}")
    return stats


async def _embed_messages(
    session,
    entity_id: str,
    force_reembed: bool = False,
) -> int:
    """
    Embed meaningful chat messages for an entity.
    Filters out trivial/short messages to only embed relevant content.
    """
    # Get all conversations for this entity
    conversations = (
        session.query(Conversation)
        .filter_by(entity_id=entity_id)
        .all()
    )

    if not conversations:
        print(f"  ⏭️  messages: no conversations found")
        return 0

    conv_ids = [c.id for c in conversations]
    print(f"  📦 messages: scanning {len(conv_ids)} conversations...")

    # Get all messages across conversations
    all_messages = (
        session.query(Message)
        .filter(Message.conversation_id.in_(conv_ids))
        .order_by(Message.timestamp)
        .all()
    )

    # Filter to meaningful messages
    meaningful = [m for m in all_messages if _is_meaningful_message(m.content)]
    print(f"  📦 messages: {len(meaningful)} meaningful out of {len(all_messages)} total")

    if not meaningful:
        return 0

    # Get existing embeddings
    existing = {}
    if not force_reembed:
        rows = (
            session.query(MemoryEmbedding)
            .filter_by(entity_id=entity_id, memory_type="messages")
            .all()
        )
        existing = {r.memory_id: r for r in rows}

    # Prepare texts
    to_embed = []
    for msg in meaningful:
        msg_id = str(msg.id)
        text = _embeddable_text("messages", msg)
        if not text:
            continue

        text_hash = _content_hash(text)
        if not force_reembed and msg_id in existing:
            if existing[msg_id].content_hash == text_hash:
                continue

        to_embed.append((msg_id, text, text_hash))

    if not to_embed:
        print(f"  ✅ messages: all up to date")
        return 0

    print(f"  🔢 messages: embedding {len(to_embed)} messages...")

    # Generate embeddings in batch
    texts = [t[1] for t in to_embed]
    try:
        vectors = generate_embeddings_batch(texts)
    except Exception as e:
        print(f"  ❌ Embedding failed for messages: {e}")
        return 0

    # Store
    count = 0
    for (msg_id, text, text_hash), vector in zip(to_embed, vectors):
        existing_emb = existing.get(msg_id)
        if existing_emb:
            existing_emb.embedding = vector
            existing_emb.content_hash = text_hash
            existing_emb.text_preview = text[:200]
            existing_emb.updated_at = datetime.now(timezone.utc)
        else:
            emb = MemoryEmbedding(
                entity_id=entity_id,
                memory_type="messages",
                memory_id=msg_id,
                content_hash=text_hash,
                text_preview=text[:200],
                embedding=vector,
            )
            session.add(emb)
        count += 1

    session.flush()
    print(f"  ✅ messages: {count} embedded")
    return count


async def embed_single_item(
    entity_id: str,
    memory_type: str,
    memory_id: str,
    text: str,
) -> bool:
    """
    Generate and store embedding for a single memory item.
    Used for real-time embedding when agent writes new items.
    """
    if not EMBEDDINGS_ENABLED:
        return False

    try:
        vector = generate_embedding(text)
        text_hash = _content_hash(text)

        with get_session() as session:
            existing = (
                session.query(MemoryEmbedding)
                .filter_by(
                    entity_id=entity_id,
                    memory_type=memory_type,
                    memory_id=str(memory_id),
                )
                .first()
            )

            if existing:
                existing.embedding = vector
                existing.content_hash = text_hash
                existing.text_preview = text[:200]
                existing.updated_at = datetime.now(timezone.utc)
            else:
                emb = MemoryEmbedding(
                    entity_id=entity_id,
                    memory_type=memory_type,
                    memory_id=str(memory_id),
                    content_hash=text_hash,
                    text_preview=text[:200],
                    embedding=vector,
                )
                session.add(emb)

        return True
    except Exception as e:
        print(f"  ❌ Single embed failed: {e}")
        return False
