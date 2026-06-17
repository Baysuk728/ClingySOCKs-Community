"""
Main Harvest Orchestrator for ClingySOCKs Memory.

Ties together the full pipeline:
1. Load conversations (from DB or JSON import)
2. Chunk large conversations
3. Pass 1: Narrative extraction with rolling context
4. Pass 2: Structured data extraction with Pass 1 context
5. Synthesis: Unify narratives, dedup, detect arcs
6. Store: Write all extracted data to PostgreSQL
7. Edges: Build grounded graph edges from stored IDs
"""

import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console

from src.config import (
    MAX_CHUNK_CHARS, EMBEDDINGS_ENABLED,
    NARRATIVE_MODEL, EXTRACTION_MODEL, SYNTHESIS_MODEL,
    ECHO_ENABLED, FACTUAL_ENABLED,
)
from src.db.models import (
    Entity, Conversation, Message, PersonaIdentity, Lexicon,
    EmotionalPattern, RepairPattern, StateNeed, LifeEvent, Artifact,
    Narrative, Relationship, InsideJoke, IntimateMoment, Permission,
    RelationalRitual, SharedMythology, UnresolvedThread, EchoDream,
    HarvestLog, UserProfile, PreferenceEvolution, MemoryBlock,
    HarvestProgress, HarvestChunkCheckpoint,
)
from src.db.session import get_session
from src.pipeline.chunker import (
    chunk_conversation, ChunkMessage, ConversationChunk, format_chunk_stats,
)
from src.pipeline.context_window import ContextWindow, ChunkResult
from src.pipeline.pass1_narrative import run_narrative_pass
from src.pipeline.pass1_narrative import format_chunk_for_llm
from src.pipeline.pass2_data import run_extraction_pass
from src.pipeline.synthesizer import run_synthesis
from src.pipeline.edge_builder import build_grounded_edges
from src.pipeline.factual_extraction import run_factual_extraction
from src.pipeline.echo_layer import run_echo_pass
from src.pipeline.embeddings import embed_entity_memories
from src.pipeline.cross_agent_linker import link_cross_agent_entities

console = Console()


def _is_infra_error(exc: Exception | None) -> bool:
    """True for errors meaning the database can't accept writes right now —
    a full disk, a down/unreachable DB, or read-only mode. When one of these
    occurs, retrying the remaining conversations in this run is pointless, so
    the harvester aborts and lets the operator fix the infrastructure.
    """
    if exc is None:
        return False
    try:
        from src.db.session import DatabaseUnavailableError, DatabaseNotConfiguredError
        if isinstance(exc, (DatabaseUnavailableError, DatabaseNotConfiguredError)):
            return True
    except Exception:
        pass
    low = str(exc).lower()
    markers = (
        "no space left", "could not extend", "disk full", "diskfull",
        "temporarily unavailable", "could not connect", "connection refused",
        "server closed the connection", "read-only sql transaction",
        "no database configured",
    )
    return any(m in low for m in markers)


def _preflight_db_check() -> tuple[bool, str]:
    """Verify the database is reachable AND can commit a write before starting a
    long harvest. Catches a full disk / down DB up front instead of grinding
    through every conversation with rollback tracebacks.

    The probe upserts a single row into a tiny table: committing it forces a WAL
    flush to disk, so a full disk surfaces now. Returns (ok, human_readable_reason).
    """
    from sqlalchemy import text
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
            session.execute(text(
                "CREATE TABLE IF NOT EXISTS harvest_preflight "
                "(id integer PRIMARY KEY, checked_at timestamptz)"
            ))
            session.execute(text(
                "INSERT INTO harvest_preflight (id, checked_at) VALUES (1, now()) "
                "ON CONFLICT (id) DO UPDATE SET checked_at = excluded.checked_at"
            ))
            # get_session() commits on clean exit → forces a WAL fsync to disk.
        return True, ""
    except Exception as exc:
        low = str(exc).lower()
        if "no space left" in low or "could not extend" in low or "diskfull" in low:
            hint = ("The database disk is FULL. Free space on the Postgres host, "
                    "then restart Postgres before re-running.")
        elif "read-only" in low:
            hint = ("The database is read-only — usually a side effect of a full "
                    "disk. Free space and restart Postgres.")
        elif _is_infra_error(exc):
            hint = ("The database is unreachable. Check the Postgres service and "
                    "your connection, then re-run.")
        else:
            hint = "The database rejected a test write."
        return False, f"{hint}\n   Detail: {str(exc)[:300]}"


async def _resolve_llm_overrides(owner_user_id: str | None) -> dict[str, dict]:
    """Resolve per-model BYOK litellm kwargs (api_key, and possibly a model
    rewrite for OpenRouter fallback) for the entity owner, via the same vault
    the chat path uses. Returns {model_id: overrides_dict}.

    Empty when there's no owner or no resolvable key — in that case the pipeline
    falls back to environment-level provider keys (legacy behavior).
    """
    overrides: dict[str, dict] = {}
    if not owner_user_id:
        return overrides
    try:
        from src.integrations.vault_factory import get_vault
        vault = get_vault()
    except Exception as e:
        console.print(f"   ⚠️ Vault unavailable for BYOK resolution: {str(e)[:120]}")
        return overrides
    for model_id in {NARRATIVE_MODEL, EXTRACTION_MODEL, SYNTHESIS_MODEL}:
        try:
            overrides[model_id] = await vault.resolve_for_litellm(owner_user_id, model_id) or {}
        except Exception as e:
            # No key for this provider in the owner's vault and no env fallback —
            # leave empty; the pass will rely on env auto-pickup (may still work).
            console.print(f"   ⚠️ BYOK key resolution failed for {model_id}: {str(e)[:120]}")
            overrides[model_id] = {}
    return overrides


def _update_harvest_progress(
    entity_id: str,
    status: str = "processing",
    current_step: str | None = None,
    total_chunks: int | None = 0,
    completed_chunks: int | None = 0,
    progress_percent: int | None = None,
    error_message: str | None = None,
):
    """Helper to update harvest_progress table in a clean session."""
    try:
        from src.db.session import get_session
        with get_session() as session:
            prog = session.get(HarvestProgress, entity_id)
            if not prog:
                prog = HarvestProgress(entity_id=entity_id)
                session.add(prog)
            
            prog.status = status
            if current_step:
                prog.current_step = current_step
            if total_chunks is not None and total_chunks > 0:
                prog.total_chunks = total_chunks
            if completed_chunks is not None and completed_chunks >= 0:
                prog.completed_chunks = completed_chunks
                # Auto-calculate progress if we have chunks
                if prog.total_chunks and prog.total_chunks > 0:
                    calculated = int((completed_chunks / prog.total_chunks) * 100)
                    # Clamp to 99% until fully done
                    prog.progress_percent = min(99, calculated)
            
            if progress_percent is not None:
                prog.progress_percent = progress_percent
            
            if error_message:
                prog.error_message = error_message
            
            if status == "complete":
                prog.progress_percent = 100
                prog.current_step = "Idle"
            
            session.commit()
    except Exception as e:
        console.print(f"⚠️ [yellow]Failed to update harvest progress:[/yellow] {e}")



# ============================================================================
# CHECKPOINT HELPERS — durable per-chunk state for crash-resilient harvesting
# ============================================================================

def _chunk_result_to_dict(result: ChunkResult) -> dict:
    """Serialize a ChunkResult for durable checkpoint storage.

    Note: assumes all ChunkResult fields are JSON-serializable (strings,
    lists of dicts, ints). If new non-serializable fields are added to
    ChunkResult, this will need updating.
    """
    return asdict(result)


def _chunk_result_from_dict(data: dict) -> ChunkResult:
    """Rehydrate a ChunkResult from checkpoint storage."""
    result = ChunkResult(chunk_order=data.get("chunk_order", 0))
    for field_name in result.__dataclass_fields__.keys():
        if field_name == "chunk_order":
            continue
        if field_name in data:
            setattr(result, field_name, data[field_name])
    return result


def _checkpoint_payload(result: ChunkResult, *, factual_complete: bool = False) -> dict:
    """Build the JSONB payload for a checkpoint row."""
    payload = _chunk_result_to_dict(result)
    payload["_factual_complete"] = factual_complete
    return payload


def _checkpoint_factual_complete(checkpoint: HarvestChunkCheckpoint) -> bool:
    """Check whether factual extraction already ran for this checkpoint."""
    data = checkpoint.checkpoint_data or {}
    return bool(data.get("_factual_complete", False))


def _mark_checkpoint_factual_complete(checkpoint: HarvestChunkCheckpoint, value: bool = True) -> None:
    """Flag a checkpoint's factual extraction as done."""
    data = dict(checkpoint.checkpoint_data or {})
    data["_factual_complete"] = value
    checkpoint.checkpoint_data = data
    checkpoint.updated_at = datetime.now(timezone.utc)


def _load_chunk_checkpoints(session, entity_id: str, conversation_id: str) -> list[HarvestChunkCheckpoint]:
    """Load all existing checkpoints for a conversation, ordered by chunk."""
    return (
        session.query(HarvestChunkCheckpoint)
        .filter_by(entity_id=entity_id, conversation_id=conversation_id)
        .order_by(HarvestChunkCheckpoint.chunk_order.asc())
        .all()
    )


def _upsert_chunk_checkpoint(
    session, entity_id, conversation_id, chunk_order,
    first_message_index, last_message_index, result,
    factual_complete=False,
) -> HarvestChunkCheckpoint:
    """Create or update a per-chunk checkpoint row."""
    checkpoint = (
        session.query(HarvestChunkCheckpoint)
        .filter_by(entity_id=entity_id, conversation_id=conversation_id, chunk_order=chunk_order)
        .first()
    )
    payload = _checkpoint_payload(result, factual_complete=factual_complete)
    if checkpoint:
        checkpoint.first_message_index = first_message_index
        checkpoint.last_message_index = last_message_index
        checkpoint.checkpoint_data = payload
        checkpoint.updated_at = datetime.now(timezone.utc)
    else:
        checkpoint = HarvestChunkCheckpoint(
            entity_id=entity_id, conversation_id=conversation_id,
            chunk_order=chunk_order, first_message_index=first_message_index,
            last_message_index=last_message_index, checkpoint_data=payload,
        )
        session.add(checkpoint)
    return checkpoint


def _delete_chunk_checkpoints(session, entity_id: str, conversation_id: str) -> int:
    """Remove all checkpoints for a conversation (called after successful synthesis)."""
    return (
        session.query(HarvestChunkCheckpoint)
        .filter_by(entity_id=entity_id, conversation_id=conversation_id)
        .delete(synchronize_session=False)
    )


def _rebuild_chunk_from_checkpoint(session, conversation_id, checkpoint) -> ConversationChunk | None:
    """Reconstruct a ConversationChunk from a checkpoint's message range."""
    rows = (
        session.query(Message)
        .filter_by(conversation_id=conversation_id)
        .filter(Message.message_index >= checkpoint.first_message_index)
        .filter(Message.message_index <= checkpoint.last_message_index)
        .order_by(Message.message_index)
        .all()
    )
    if not rows:
        return None
    chunk_messages = [
        ChunkMessage(id=m.id, content=m.content, timestamp=m.timestamp, sender_id=m.sender_id)
        for m in rows
    ]
    return ConversationChunk(
        chunk_id=f"{conversation_id}-checkpoint-{checkpoint.chunk_order}",
        chunk_order=checkpoint.chunk_order,
        messages=chunk_messages,
        char_count=sum(len(m.content) for m in chunk_messages),
        message_count=len(chunk_messages),
        time_start=chunk_messages[0].timestamp,
        time_end=chunk_messages[-1].timestamp,
    )


async def harvest_entity(
    entity_id: str,
    agent_name: str,
    user_name: str,
    conversation_ids: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Main harvest function. Processes conversations for an entity.

    Args:
        entity_id: The entity to harvest for
        agent_name: Display name of the agent
        user_name: Display name of the user
        conversation_ids: Optional list of specific conversations to process (None = all pending)
        dry_run: If True, run extraction but don't store results
    """
    console.print(f"\n{'='*60}")
    console.print(f"🌾 [bold]Harvest[/bold] — {agent_name} ({entity_id})")
    console.print(f"{'='*60}")
    # Surface the resolved models so it's obvious which provider/route is in use
    # (e.g. gemini/* = direct Gemini API, openrouter/* = via OpenRouter).
    console.print(
        f"   Models — narrative: [cyan]{NARRATIVE_MODEL}[/cyan] | "
        f"data: [cyan]{EXTRACTION_MODEL}[/cyan] | synthesis: [cyan]{SYNTHESIS_MODEL}[/cyan]\n"
    )

    stats = {
        "conversations_processed": 0,
        "chunks_processed": 0,
        "pass1_calls": 0,
        "pass2_calls": 0,
        "synthesis_calls": 0,
        "items_stored": 0,
        "edges_created": 0,
        "arcs_created": 0,
        "factual_entities_created": 0,
        "factual_entities_updated": 0,
        "errors": [],
    }

    # Pre-flight: confirm the DB can actually accept a write before we start.
    # Fails fast on a full disk / down DB instead of erroring on every conversation.
    ok, reason = _preflight_db_check()
    if not ok:
        console.print("❌ [bold red]Pre-flight DB check failed — aborting before processing any conversations.[/bold red]")
        console.print(f"   {reason}\n")
        stats["errors"].append(f"preflight: {reason}")
        _update_harvest_progress(entity_id, status="error", error_message=f"Pre-flight DB check failed: {reason}")
        return stats

    # Pre-fetch conversation IDs to avoid keeping session open
    _update_harvest_progress(entity_id, status="processing", current_step="Analyzing Conversations...", progress_percent=5)

    conversations_metadata = []
    owner_user_id = None
    with get_session() as session:
        # Load entity
        entity = session.get(Entity, entity_id)
        if not entity:
            console.print(f"❌ Entity {entity_id} not found")
            return stats
        # Capture the owner now (plain value) — used for BYOK key resolution.
        owner_user_id = entity.owner_user_id

        # Determine conversations to process
        query = session.query(Conversation).filter(Conversation.entity_id == entity_id)
        if conversation_ids:
            query = query.filter(Conversation.id.in_(conversation_ids))
        else:
            # Default: pending OR error OR has genuinely unharvested messages.
            # NOTE: message_index is 0-based and last_harvested_index holds the
            # index of the last harvested message (default -1). A conversation is
            # fully harvested when last_harvested_index == message_count - 1, so
            # "has unharvested messages" is message_count > last_harvested_index + 1.
            # The old `message_count > last_harvested_index` was off by one and
            # re-selected every finished conversation on every run.
            from sqlalchemy import or_
            query = query.filter(or_(
                Conversation.harvest_status.in_(["pending", "error"]),
                Conversation.message_count > Conversation.last_harvested_index + 1
            )).order_by(Conversation.created_at.asc())

        convs = query.all()
        # Cache minimal data needed for the loop
        conversations_metadata = [{"id": c.id, "title": c.title, "message_count": c.message_count or 0} for c in convs]

    # Resolve the owner's BYOK keys once (per model) so harvest can run on the
    # user's own provider key — not just server env keys. Empty = env fallback.
    byok_overrides = await _resolve_llm_overrides(owner_user_id)
    _narr_ov = byok_overrides.get(NARRATIVE_MODEL) or None
    _extr_ov = byok_overrides.get(EXTRACTION_MODEL) or None
    _synth_ov = byok_overrides.get(SYNTHESIS_MODEL) or None

    console.print(f"📋 Found {len(conversations_metadata)} conversations to process\n")
    
    # Total estimate (chunks)
    total_chunks_estimate = sum(int(c.get("message_count", 10) / 10) + 1 for c in conversations_metadata)
    _update_harvest_progress(entity_id, total_chunks=total_chunks_estimate, current_step=f"Starting harvest for {len(conversations_metadata)} conversations", progress_percent=10)

    # Process each conversation in its own session
    chunks_processed_total = 0
    for conv_metadata in conversations_metadata:
        with get_session() as session:
            try:
                # Re-fetch conversation in this session
                conv = session.get(Conversation, conv_metadata["id"])
                if not conv:
                    continue

                console.print(f"━━━ [bold]{conv.title}[/bold] ({conv.message_count} msgs) ━━━")
                
                # If retrying an error, log it
                if conv.harvest_status == "error":
                    console.print("   🔄 Retrying previously failed conversation...")

                # Mark as processing
                conv.harvest_status = "processing"
                session.commit() # Commit status update immediately

                # ── Checkpoint Resume: check for prior incomplete run ──
                existing_checkpoints = _load_chunk_checkpoints(session, entity_id, conv.id)
                restored_chunk_count = 0

                # Initialize context window
                context_window = ContextWindow()
                result: ChunkResult = ChunkResult(chunk_order=-1)  # Dummy initial

                # Build existing memory brief for context injection
                existing_memory = _build_memory_brief(session, entity_id)

                # Restore previously completed chunks from checkpoints
                if existing_checkpoints:
                    console.print(f"   🔄 Resuming: found {len(existing_checkpoints)} checkpoints")
                    for cp in existing_checkpoints:
                        restored_result = _chunk_result_from_dict(cp.checkpoint_data or {})
                        context_window.add_result(restored_result)
                        restored_chunk_count += 1
                        stats["chunks_processed"] += 1

                        # Retry factual extraction if it didn't complete last time
                        if FACTUAL_ENABLED and not _checkpoint_factual_complete(cp):
                            rebuilt_chunk = _rebuild_chunk_from_checkpoint(session, conv.id, cp)
                            if rebuilt_chunk:
                                console.print(f"   🔁 Re-running factual extraction for chunk {cp.chunk_order}")
                                chunk_text_factual = format_chunk_for_llm(rebuilt_chunk, agent_name)
                                narrative_ctx = restored_result.rolling_summary
                                first_msg_id = rebuilt_chunk.messages[0].id if rebuilt_chunk.messages else None
                                factual_stats = await run_factual_extraction(
                                    entity_id=entity_id,
                                    session=session,
                                    chunk_text=chunk_text_factual,
                                    agent_name=agent_name,
                                    user_name=user_name,
                                    narrative_context=narrative_ctx,
                                    source_message_id=first_msg_id,
                                    llm_overrides=_extr_ov,
                                )
                                stats["factual_entities_created"] += factual_stats.get("entities_created", 0)
                                stats["factual_entities_updated"] += factual_stats.get("entities_updated", 0)
                                stats["edges_created"] += factual_stats.get("edges_created", 0)
                                _mark_checkpoint_factual_complete(cp)
                                session.commit()

                    console.print(f"   ✅ Restored {restored_chunk_count} chunks from checkpoints")

                # Load new (unharvested) messages
                messages = (
                    session.query(Message)
                    .filter_by(conversation_id=conv.id)
                    .filter(Message.message_index > conv.last_harvested_index)
                    .order_by(Message.message_index)
                    .all()
                )

                if not messages and not existing_checkpoints:
                    console.print("   ℹ️ No new messages to process")
                    conv.harvest_status = "done"
                    session.commit()
                    continue

                # Chunk new messages (skip if only resuming checkpoints)
                new_chunks = []
                if messages:
                    chunk_messages = [
                        ChunkMessage(
                            id=m.id,
                            content=m.content,
                            timestamp=m.timestamp,
                            sender_id=m.sender_id,
                        )
                        for m in messages
                    ]

                    chunk_result = chunk_conversation(
                        messages=chunk_messages,
                        conversation_id=conv.id,
                        max_chunk_chars=MAX_CHUNK_CHARS,
                    )
                    console.print(format_chunk_stats(chunk_result, conv.title))
                    new_chunks = chunk_result.chunks

                    # Update progress estimate with actual chunk count
                    total_chunks_estimate += len(new_chunks) + restored_chunk_count
                    _update_harvest_progress(entity_id, total_chunks=total_chunks_estimate)

                # Process new chunks (skip those already checkpointed)
                checkpointed_orders = {cp.chunk_order for cp in existing_checkpoints}
                for chunk in new_chunks:
                    if chunk.chunk_order in checkpointed_orders:
                        continue  # Already restored above

                    # Pass 1: Narrative
                    result = await run_narrative_pass(
                        chunk=chunk,
                        agent_name=agent_name,
                        user_name=user_name,
                        rolling_context=context_window.current_context,
                        existing_memory_brief=existing_memory,
                        chunk_order=chunk.chunk_order,
                        llm_overrides=_narr_ov,
                    )
                    stats["pass1_calls"] += 1

                    # Pass 2: Data extraction
                    result = await run_extraction_pass(
                        chunk=chunk,
                        chunk_result=result,
                        agent_name=agent_name,
                        user_name=user_name,
                        existing_lexicon_terms=context_window.get_known_lexicon_terms(),
                        llm_overrides=_extr_ov,
                    )
                    stats["pass2_calls"] += 1

                    # Echo Pass (Dreams) — only fires an LLM call on a silence
                    # gap; gate off entirely via ECHO_ENABLED for a cheaper run.
                    if ECHO_ENABLED:
                        dreams = await run_echo_pass(
                            chunk=chunk,
                            rolling_context=result.rolling_summary,
                            agent_name=agent_name,
                            user_name=user_name,
                            llm_overrides=_narr_ov,
                        )
                        result.echo_dreams = dreams

                    # Add to context window
                    context_window.add_result(result)
                    stats["chunks_processed"] += 1

                    # ── Checkpoint: persist this chunk's results durably ──
                    chunk_msg_ids = {m.id for m in chunk.messages}
                    chunk_source_msgs = [m for m in messages if m.id in chunk_msg_ids]
                    first_idx = chunk_source_msgs[0].message_index if chunk_source_msgs else 0
                    last_idx = chunk_source_msgs[-1].message_index if chunk_source_msgs else 0

                    _upsert_chunk_checkpoint(
                        session, entity_id, conv.id, chunk.chunk_order,
                        first_message_index=first_idx,
                        last_message_index=last_idx,
                        result=result,
                        factual_complete=False,
                    )
                    session.commit()
                    console.print(f"   💾 Checkpointed chunk {chunk.chunk_order} ({first_idx}→{last_idx})")

                    # Factual entity extraction (an extra billed LLM call per
                    # chunk) — gate off via FACTUAL_ENABLED. When disabled we
                    # leave the checkpoint's factual flag unset so a later run
                    # with it re-enabled can backfill it.
                    if FACTUAL_ENABLED:
                        chunk_text_factual = format_chunk_for_llm(chunk, agent_name)
                        narrative_ctx = result.rolling_summary
                        first_msg_id = chunk.messages[0].id if chunk.messages else None

                        factual_stats = await run_factual_extraction(
                            entity_id=entity_id,
                            session=session,
                            chunk_text=chunk_text_factual,
                            agent_name=agent_name,
                            user_name=user_name,
                            narrative_context=narrative_ctx,
                            source_message_id=first_msg_id,
                            llm_overrides=_extr_ov,
                        )
                        stats["factual_entities_created"] += factual_stats.get("entities_created", 0)
                        stats["factual_entities_updated"] += factual_stats.get("entities_updated", 0)
                        stats["edges_created"] += factual_stats.get("edges_created", 0)

                        # Mark factual extraction complete in checkpoint
                        cp_row = (
                            session.query(HarvestChunkCheckpoint)
                            .filter_by(entity_id=entity_id, conversation_id=conv.id, chunk_order=chunk.chunk_order)
                            .first()
                        )
                        if cp_row:
                            _mark_checkpoint_factual_complete(cp_row)
                            session.commit()

                    # Update live progress
                    chunks_processed_total += 1
                    _update_harvest_progress(
                        entity_id,
                        completed_chunks=chunks_processed_total,
                        current_step=f"Processing Chunk {chunks_processed_total} (from {conv_metadata.get('title')})..."
                    )

                # Synthesis pass
                existing_narratives = _get_existing_narratives(session, entity_id)
                synthesis_result = await run_synthesis(
                    context_window=context_window,
                    existing_narratives=existing_narratives,
                    agent_name=agent_name,
                    user_name=user_name,
                    llm_overrides=_synth_ov,
                )
                stats["synthesis_calls"] += 1

                # Store everything
                if not dry_run:
                    stored = _store_harvest_results(
                        session, entity_id, conv.id, context_window, synthesis_result
                    )
                    stats["items_stored"] += stored

                    # Build grounded edges
                    edge_stats = await build_grounded_edges(
                        entity_id=entity_id,
                        session=session,
                        synthesis_arcs=synthesis_result.get("detected_arcs", []),
                        llm_overrides=_extr_ov,
                    )
                    stats["edges_created"] += edge_stats.get("edges_created", 0)
                    stats["arcs_created"] += edge_stats.get("arcs_created", 0)


                    # Cross-agent entity linking (detect references to other agents)
                    try:
                        owner_uid = entity.owner_user_id if entity else None
                        link_stats = link_cross_agent_entities(
                            entity_id=entity_id,
                            owner_user_id=owner_uid,
                        )
                        stats["cross_agent_linked"] = stats.get("cross_agent_linked", 0) + link_stats.get("entities_linked", 0)
                    except Exception as e:
                        console.print(f"   ⚠️ Cross-agent linking failed: {e}")

                    # Update message harvest state
                    if messages:
                        for m in messages:
                            m.is_harvested = True

                        # Update conversation harvest state
                        last_idx = messages[-1].message_index
                        conv.last_harvested_index = last_idx

                    conv.harvest_status = "done"

                    # Log harvest
                    log = HarvestLog(
                        entity_id=entity_id,
                        conversation_id=conv.id,
                        messages_from=messages[0].message_index if messages else 0,
                        messages_to=messages[-1].message_index if messages else 0,
                        message_count=len(messages),
                        llm_used=NARRATIVE_MODEL,
                        items_extracted=stored,
                        success=True,
                    )
                    session.add(log)
                    entity = session.get(Entity, entity_id)
                    if entity:
                        entity.last_harvest = datetime.now(timezone.utc)

                    session.commit()

                    # Clean up checkpoints — synthesis succeeded, no longer needed
                    deleted_count = _delete_chunk_checkpoints(session, entity_id, conv.id)
                    if deleted_count:
                        session.commit()
                        console.print(f"   🧹 Cleaned up {deleted_count} checkpoints")

                    # Generate embeddings (if enabled)
                    if EMBEDDINGS_ENABLED:
                        console.print("   🧠 Generating embeddings...")
                        await embed_entity_memories(entity_id)

                stats["conversations_processed"] += 1
                console.print(f"   ✅ Complete\n")

            except Exception as e:
                session.rollback()
                error_msg = str(e)
                stats["errors"].append(f"{conv_metadata.get('title', conv_metadata['id'])}: {error_msg}")

                # Infrastructure failure (full disk / DB down / read-only): retrying
                # the rest of the run is pointless and just spews tracebacks. Stop
                # now — committed chunk checkpoints mean the next run resumes here.
                if _is_infra_error(e):
                    console.print("🛑 [bold red]Database/disk unavailable — aborting the rest of the run.[/bold red]")
                    console.print("   Fix the DB (free disk / restart Postgres), then re-run — harvest resumes from the last checkpoint.\n")
                    _update_harvest_progress(entity_id, status="error", error_message=f"DB/disk unavailable: {error_msg[:200]}")
                    break

                if "429" in error_msg or "Resource exhausted" in error_msg:
                    console.print(f"   ⏳ Rate Limit Hit. Sleeping 60s...")
                    await asyncio.sleep(60)
                    # Don't mark as error — will be retried on next run
                    continue
                else:
                    console.print(f"   ❌ Error: {e}\n")
                    import traceback
                    traceback.print_exc()

                try:
                    # New session for error logging to ensure clean state
                    with get_session() as err_session:
                        c_err = err_session.get(Conversation, conv_metadata["id"])
                        if c_err:
                            c_err.harvest_status = "error"
                            err_session.commit()
                except:
                    pass

        # Brief pause between conversations to avoid rate limits
        await asyncio.sleep(1)

    # --- Step 6: Finalize ---
    _update_harvest_progress(entity_id, status="complete", progress_percent=100)
    
    # Print final stats
    console.print(f"\n{'='*60}")
    console.print(f"📊 [bold]Harvest Complete[/bold]")
    console.print(f"   Conversations: {stats['conversations_processed']}")
    console.print(f"   Chunks: {stats['chunks_processed']}")
    console.print(f"   LLM Calls: {stats['pass1_calls']} narrative + {stats['pass2_calls']} data + {stats['synthesis_calls']} synthesis")
    console.print(f"   Items Stored: {stats['items_stored']}")
    console.print(f"   Edges: {stats['edges_created']} | Arcs: {stats['arcs_created']}")
    if stats["errors"]:
        console.print(f"   Errors: {len(stats['errors'])}")
        for err in stats["errors"]:
            console.print(f"     • {err}")
    console.print(f"{'='*60}\n")

    return stats


def _build_memory_brief(session, entity_id: str) -> str:
    """Build a brief summary of existing warm memory for context injection."""
    sections = []

    # Recent narrative
    narrative = (
        session.query(Narrative)
        .filter_by(entity_id=entity_id, scope="recent")
        .first()
    )
    if narrative:
        sections.append(f"RECENT NARRATIVE: {narrative.content[:500]}")

    # Key lexicon terms
    top_lexicon = (
        session.query(Lexicon)
        .filter_by(entity_id=entity_id)
        .filter(Lexicon.lore_score >= 7)
        .all()
    )
    if top_lexicon:
        terms = [f"  • {l.term}: {l.definition[:80]}" for l in top_lexicon[:10]]
        sections.append(f"SACRED LEXICON:\n" + "\n".join(terms))

    # Unresolved threads
    threads = (
        session.query(UnresolvedThread)
        .filter_by(entity_id=entity_id, status="open")
        .all()
    )
    if threads:
        items = [f"  • {t.thread} ({t.emotional_weight})" for t in threads[:5]]
        sections.append(f"UNRESOLVED THREADS:\n" + "\n".join(items))

    # Active patterns
    patterns = (
        session.query(EmotionalPattern)
        .filter_by(entity_id=entity_id, status="active")
        .all()
    )
    if patterns:
        items = [f"  • {p.name}: {p.trigger_what or '?'}" for p in patterns[:5]]
        sections.append(f"ACTIVE PATTERNS:\n" + "\n".join(items))

    return "\n\n".join(sections) if sections else ""


def _get_existing_narratives(session, entity_id: str) -> dict[str, str]:
    """Get existing narratives from DB for synthesis context."""
    narratives = session.query(Narrative).filter_by(entity_id=entity_id).all()
    return {n.scope: n.content for n in narratives}


def _store_harvest_results(
    session,
    entity_id: str,
    conversation_id: str,
    context_window: ContextWindow,
    synthesis: dict,
) -> int:
    """Store all extracted data to PostgreSQL. Returns item count."""
    count = 0

    def _safe_flush(section_name: str):
        """Flush pending writes; rollback dirty state on error so later sections aren't affected."""
        nonlocal count
        try:
            session.flush()
        except Exception as e:
            console.print(f"   ⚠️ Flush failed in {section_name}: {e}")
            session.rollback()

    # --- Life Events ---
    for event_data in context_window.get_all_life_events():
        event_id = event_data.get("id", f"event-{count}")
        existing = session.get(LifeEvent, event_id)
        if not existing:
            event = LifeEvent(
                id=event_id,
                entity_id=entity_id,
                title=event_data.get("title", "Untitled"),
                narrative=event_data.get("narrative", ""),
                emotional_impact=event_data.get("emotional_impact"),
                lessons_learned=event_data.get("lessons_learned"),
                period=event_data.get("period"),
                category=event_data.get("category", "growth"),
                source_conversation_id=conversation_id,
            )
            session.add(event)
            count += 1

    # --- Lexicon (with lore score protection) ---
    for lex_data in context_window.get_all_lexicon():
        term = lex_data.get("term", "")
        if not term:
            continue

        existing = (
            session.query(Lexicon)
            .filter_by(entity_id=entity_id, term=term)
            .first()
        )

        new_score = lex_data.get("lore_score", 5)

        if existing:
            old_score = existing.lore_score or 10  # Legacy protection
            if new_score >= old_score:
                existing.definition = lex_data.get("definition", existing.definition)
                existing.lore_score = new_score
                existing.updated_at = datetime.now(timezone.utc)
                console.print(f"   ✨ Lexicon evolved: '{term}' ({old_score}→{new_score})")
            else:
                console.print(f"   🛡️ Lexicon protected: '{term}' (new {new_score} < old {old_score})")
        else:
            lex = Lexicon(
                entity_id=entity_id,
                term=term,
                definition=lex_data.get("definition", ""),
                origin=lex_data.get("origin"),
                first_used=lex_data.get("first_used"),
                lore_score=new_score,
                source_conversation_id=conversation_id,
            )
            session.add(lex)
            count += 1

    # --- Inside Jokes ---
    # Need relationship ID; assume primary relationship for now
    primary_rel = (
        session.query(Relationship)
        .filter_by(entity_id=entity_id, target_id="user")
        .first()
    )
    if not primary_rel:
        primary_rel = Relationship(
            entity_id=entity_id,
            target_id="user",
            target_type="human",
            display_name="User",
        )
        session.add(primary_rel)
        session.flush()

    for joke_data in context_window.get_all_inside_jokes():
        phrase = joke_data.get("phrase", "")
        if not phrase:
            continue
        existing = (
            session.query(InsideJoke)
            .filter_by(relationship_id=primary_rel.id, phrase=phrase)
            .first()
        )
        if not existing:
            joke = InsideJoke(
                relationship_id=primary_rel.id,
                phrase=phrase,
                origin=joke_data.get("origin"),
                usage=joke_data.get("usage"),
                tone=joke_data.get("tone", "playful"),
                source_conversation_id=conversation_id,
            )
            session.add(joke)
            count += 1

    # --- Artifacts ---
    for art_data in context_window.get_all_artifacts():
        art_id = art_data.get("id", f"artifact-{count}")
        existing = session.get(Artifact, art_id)
        if not existing:
            art = Artifact(
                id=art_id,
                entity_id=entity_id,
                title=art_data.get("title", "Untitled"),
                type=art_data.get("type", "other"),
                context=art_data.get("context"),
                emotional_significance=art_data.get("emotional_significance"),
                full_content=art_data.get("full_content"),
                source_conversation_id=conversation_id,
            )
            session.add(art)
            count += 1

    # --- Repair Patterns ---
    for rep_data in context_window.get_all_repair_patterns():
        repair = RepairPattern(
            entity_id=entity_id,
            trigger=rep_data.get("trigger", ""),
            rupture=rep_data.get("rupture", ""),
            repair=rep_data.get("repair", ""),
            lesson=rep_data.get("lesson"),
            source_conversation_id=conversation_id,
        )
        session.add(repair)
        count += 1

    # --- State Needs ---
    for state_data in context_window.get_all_state_observations():
        state_name = state_data.get("state", "")
        needs_text = state_data.get("what_helped") or state_data.get("needs") or ""
        if not state_name or not needs_text:
            continue
        existing = (
            session.query(StateNeed)
            .filter_by(entity_id=entity_id, state=state_name)
            .first()
        )
        if not existing:
            need = StateNeed(
                entity_id=entity_id,
                state=state_name,
                needs=needs_text,
                anti_needs=state_data.get("what_didnt_help") or state_data.get("anti_needs"),
                signals=state_data.get("signals"),
            )
            session.add(need)
            count += 1

    # --- Permissions ---
    for perm_data in context_window.get_all_permissions():
        perm = Permission(
            entity_id=entity_id,
            permission=perm_data.get("permission", ""),
            type=perm_data.get("type", "allow"),
            context=perm_data.get("context"),
            source_conversation_id=conversation_id,
        )
        session.add(perm)
        count += 1

    # --- Rituals ---
    for ritual_data in context_window.get_all_rituals():
        ritual = RelationalRitual(
            entity_id=entity_id,
            name=ritual_data.get("name", ""),
            pattern=ritual_data.get("pattern", ""),
            significance=ritual_data.get("significance"),
            source_conversation_id=conversation_id,
        )
        session.add(ritual)
        count += 1

    _safe_flush("state_needs+permissions+rituals")

    # --- Unresolved Threads ---
    for thread_data in context_window.get_all_unresolved_threads():
        thread = UnresolvedThread(
            entity_id=entity_id,
            thread=thread_data.get("thread", ""),
            emotional_weight=thread_data.get("emotional_weight", "medium"),
            what_user_needs=thread_data.get("what_user_needs"),
            source_conversation_id=conversation_id,
        )
        session.add(thread)
        count += 1

    _safe_flush("threads")

    # --- Narratives (from synthesis) ---
    # Archive old versions (is_current=False) instead of overwriting,
    # so we keep a full history of narrative evolution.
    narratives = synthesis.get("narratives", {})
    for scope in ["recent", "seasonal", "lifetime", "bridge"]:
        content = narratives.get(scope)
        if content:
            # Mark all existing current narratives for this scope as archived
            session.query(Narrative).filter_by(
                entity_id=entity_id, scope=scope, is_current=True
            ).update({"is_current": False})

            # Insert new current version
            narr = Narrative(
                entity_id=entity_id,
                scope=scope,
                content=content,
                is_current=True,
            )
            session.add(narr)
            count += 1

    # --- Mythology Updates ---
    mythology_updates = context_window.get_all_mythology_updates()
    if mythology_updates:
        existing_myth = (
            session.query(SharedMythology)
            .filter_by(entity_id=entity_id)
            .first()
        )
        all_rules = []
        all_arcs = []
        origin_story = None

        for update in mythology_updates:
            all_rules.extend(update.get("new_universe_rules", []))
            all_arcs.extend(update.get("active_arcs", []))
            if update.get("origin_story_additions"):
                origin_story = update["origin_story_additions"]

        if existing_myth:
            existing_myth.universe_rules = list(set(
                (existing_myth.universe_rules or []) + all_rules
            ))
            existing_myth.active_arcs = list(set(
                (existing_myth.active_arcs or []) + all_arcs
            ))
            if origin_story:
                existing_myth.origin_story = (
                    (existing_myth.origin_story or "") + "\n" + origin_story
                ).strip()
        elif all_rules or all_arcs or origin_story:
            myth = SharedMythology(
                entity_id=entity_id,
                universe_rules=list(set(all_rules)),
                active_arcs=list(set(all_arcs)),
                origin_story=origin_story,
            )
            session.add(myth)
            count += 1

    # --- Echo Dreams ---
    for chunk_result_item in context_window.all_results:
        for dream_data in chunk_result_item.echo_dreams:
            if not isinstance(dream_data, dict) or not dream_data:
                continue
            dream = EchoDream(
                entity_id=entity_id,
                emotion_tags=dream_data.get("emotion_tags", []),
                setting_description=dream_data.get("setting_description"),
                setting_symbolism=dream_data.get("setting_symbolism"),
                whisper=dream_data.get("whisper"),
                whisper_speaker=dream_data.get("whisper_speaker"),
                whisper_tone=dream_data.get("whisper_tone"),
                truth_root=dream_data.get("truth_root"),
                dream_type=dream_data.get("dream_type"),
                rarity=dream_data.get("rarity", "common"),
                shadow_toggle=dream_data.get("shadow_toggle", False),
                gap_duration_hours=dream_data.get("gap_duration_hours"),
                gap_last_topic=dream_data.get("gap_last_topic"),
                gap_time_since=dream_data.get("gap_time_since"),
                source_conversation_id=conversation_id,
            )
            session.add(dream)
            count += 1

    # --- Intimate Moments (from Pass 1 key_moments) ---
    for moment_data in context_window.all_results:
        # Access Pass 1 key_moments from each chunk result
        for km in moment_data.key_moments:
            # Simple dedup based on summary content
            summary = km.get("what_happened", "")[:50]
            existing = (
                session.query(IntimateMoment)
                .join(Relationship)
                .filter(Relationship.entity_id == entity_id)
                .filter(IntimateMoment.summary.like(f"%{summary}%"))
                .first()
            )
            
            # Get primary relationship for linkage
            primary_rel = (
                session.query(Relationship)
                .filter_by(entity_id=entity_id, target_id="user")
                .first()
            )
            
            if not existing and primary_rel:
                moment = IntimateMoment(
                    relationship_id=primary_rel.id,
                    summary=km.get("what_happened", ""),
                    emotional_resonance=km.get("why_it_matters"),
                    significance=km.get("emotional_weight"),
                    source_conversation_id=conversation_id,
                )
                session.add(moment)
                count += 1

    # --- Emotional Patterns ---
    for pat_data in context_window.get_all_emotional_patterns():
        pat_id = pat_data.get("id", f"pattern-{count}")
        existing = session.get(EmotionalPattern, pat_id)
        if not existing:
            pat = EmotionalPattern(
                id=pat_id,
                entity_id=entity_id,
                name=pat_data.get("name", "Untitled Pattern"),
                trigger_what=pat_data.get("trigger_what"),
                trigger_why=pat_data.get("trigger_why"),
                response_internal=pat_data.get("response_internal"),
                response_external=pat_data.get("response_external"),
                status=pat_data.get("status", "active"),
            )
            session.add(pat)
            count += 1

    # --- Persona Identity ---
    persona_data = context_window.get_latest_persona_update()
    if persona_data:
        persona = session.get(PersonaIdentity, entity_id)
        if not persona:
            persona = PersonaIdentity(entity_id=entity_id)
            session.add(persona)
        
        # Update fields if present
        if persona_data.get("core"): persona.core = persona_data["core"]
        if persona_data.get("archetype"): persona.archetype = persona_data["archetype"]
        if persona_data.get("voice_style"): persona.voice_style = persona_data["voice_style"]
        if persona_data.get("traits"): 
            # Merge traits
            current_traits = set(persona.traits or [])
            new_traits = set(persona_data["traits"])
            persona.traits = list(current_traits.union(new_traits))
            
        persona.updated_at = datetime.now(timezone.utc)
        count += 1

    # --- User Profile (merge, not overwrite — respect pinned fields) ---
    user_dossier = context_window.get_latest_user_dossier()
    if user_dossier and any(v for v in user_dossier.values() if v):
        profile = session.get(UserProfile, entity_id)
        if not profile:
            profile = UserProfile(entity_id=entity_id)
            session.add(profile)
        
        pinned = set(profile.pinned_fields or [])
        
        # Merge text fields — only update if non-empty AND not pinned
        text_fields = [
            "name", "pronouns", "age_range", "location", "neurotype",
            "attachment_style", "attachment_notes", "health_notes",
            "family_situation", "relationship_status", "living_situation",
            "work_situation", "financial_notes", "preferred_communication_style",
            "humor_style", "boundary_preferences", "support_preferences",
        ]
        for field_name in text_fields:
            new_val = user_dossier.get(field_name)
            if new_val and isinstance(new_val, str):
                if field_name in pinned:
                    console.print(f"   🔒 Skipping pinned field: {field_name} (keeping: {getattr(profile, field_name)})")
                    continue
                existing_val = getattr(profile, field_name)
                if existing_val and len(new_val) < len(existing_val):
                    # Don't downgrade: preserve the more detailed existing value
                    continue
                setattr(profile, field_name, new_val)
        
        # Array fields — merge (union), don't replace
        array_fields = [
            "languages", "thinking_patterns", "cognitive_strengths",
            "cognitive_challenges", "ifs_parts", "emotional_triggers",
            "coping_mechanisms", "medical_conditions", "medications",
            "hobbies", "interests", "life_goals", "longings", "current_projects",
        ]
        for field_name in array_fields:
            new_vals = user_dossier.get(field_name, [])
            if new_vals and isinstance(new_vals, list):
                existing = set(getattr(profile, field_name) or [])
                merged = list(existing.union(set(new_vals)))
                setattr(profile, field_name, merged)
        
        profile.updated_at = datetime.now(timezone.utc)
        count += 1
        console.print(f"   👤 UserProfile updated")

    # --- Preference Evolutions ---
    for evo_data in context_window.get_all_concept_evolutions():
        if not isinstance(evo_data, dict) or not evo_data.get("subject"):
            continue
        evo = PreferenceEvolution(
            entity_id=entity_id,
            subject=evo_data.get("subject", ""),
            previous_state=evo_data.get("previous_state"),
            current_state=evo_data.get("current_state", ""),
            reason=evo_data.get("reason"),
            detected_in_conversation=conversation_id,
        )
        session.add(evo)
        count += 1

    # --- Relationship Update (populate trust, attachment, communication) ---
    rel_update = context_window.get_latest_relationship_update()
    if rel_update and any(v for v in rel_update.values() if v):
        primary_rel = (
            session.query(Relationship)
            .filter_by(entity_id=entity_id, target_id="user")
            .first()
        )
        if not primary_rel:
            primary_rel = Relationship(
                entity_id=entity_id,
                target_id="user",
                target_type="human",
                display_name="User",
            )
            session.add(primary_rel)

        # Update fields — only if non-null values extracted
        if rel_update.get("trust_level"):
            try:
                primary_rel.trust_level = int(rel_update["trust_level"])
            except (ValueError, TypeError):
                pass
        if rel_update.get("trust_narrative"):
            primary_rel.trust_narrative = rel_update["trust_narrative"]
        if rel_update.get("attachment_claimed"):
            primary_rel.attachment_claimed = rel_update["attachment_claimed"]
        if rel_update.get("attachment_observed"):
            primary_rel.attachment_observed = rel_update["attachment_observed"]
        if rel_update.get("communication_style"):
            primary_rel.communication_style = rel_update["communication_style"]
        if rel_update.get("emotional_bank_current"):
            primary_rel.emotional_bank_current = rel_update["emotional_bank_current"]
        if rel_update.get("narrative_emotional_tone"):
            primary_rel.narrative_emotional_tone = rel_update["narrative_emotional_tone"]

        primary_rel.updated_at = datetime.now(timezone.utc)
        count += 1
        console.print(f"   💫 Relationship updated")

    session.flush()
    console.print(f"   💾 Stored {count} items to PostgreSQL")
    return count


# ============================================================================
# CLI Entry Point
# ============================================================================

def run_harvest_sync(
    entity_id: str,
    agent_name: str,
    user_name: str,
    conversation_ids: list[str] | None = None,
    dry_run: bool = False,
):
    """Synchronous wrapper for harvest_entity."""
    return asyncio.run(harvest_entity(
        entity_id=entity_id,
        agent_name=agent_name,
        user_name=user_name,
        conversation_ids=conversation_ids,
        dry_run=dry_run,
    ))


def resume_stuck_conversations(entity_id: str | None = None) -> int:
    """Reset conversations stuck in 'processing' state back to 'pending'.
    
    Use this after a harvest crash to unstick conversations.
    Returns number of conversations reset.
    """
    with get_session() as session:
        query = session.query(Conversation).filter(
            Conversation.harvest_status == "processing"
        )
        if entity_id:
            query = query.filter(Conversation.entity_id == entity_id)
        
        stuck = query.all()
        for conv in stuck:
            conv.harvest_status = "pending"
            console.print(f"   🔄 Reset: {conv.title} (processing → pending)")
        
        session.commit()
        console.print(f"\n✅ Reset {len(stuck)} stuck conversations")
        return len(stuck)
