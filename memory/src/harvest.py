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
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console

from src.config import MAX_CHUNK_CHARS, EMBEDDINGS_ENABLED
from src.db.models import (
    Entity, Conversation, Message, PersonaIdentity, Lexicon,
    EmotionalPattern, RepairPattern, StateNeed, LifeEvent, Artifact,
    Narrative, Relationship, InsideJoke, IntimateMoment, Permission,
    RelationalRitual, SharedMythology, UnresolvedThread, EchoDream,
    HarvestLog, UserProfile, PreferenceEvolution, MemoryBlock,
    HarvestProgress,
)
from src.db.session import get_session
from src.pipeline.chunker import (
    chunk_conversation, ChunkMessage, format_chunk_stats,
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
    console.print(f"{'='*60}\n")

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

    # Pre-fetch conversation IDs to avoid keeping session open
    _update_harvest_progress(entity_id, status="processing", current_step="Analyzing Conversations...", progress_percent=5)
    
    conversations_metadata = []
    with get_session() as session:
        # Load entity
        entity = session.get(Entity, entity_id)
        if not entity:
            console.print(f"❌ Entity {entity_id} not found")
            return stats
            
        # Determine conversations to process
        query = session.query(Conversation).filter(Conversation.entity_id == entity_id)
        if conversation_ids:
            query = query.filter(Conversation.id.in_(conversation_ids))
        else:
            # Default: pending OR error OR has unharvested messages, then oldest updated
            # We retry errors automatically on next run
            from sqlalchemy import or_
            query = query.filter(or_(
                Conversation.harvest_status.in_(["pending", "error"]),
                Conversation.message_count > Conversation.last_harvested_index
            )).order_by(Conversation.created_at.asc())
            
        convs = query.all()
        # Cache minimal data needed for the loop
        conversations_metadata = [{"id": c.id, "title": c.title} for c in convs]
        
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

                # Load messages
                messages = (
                    session.query(Message)
                    .filter_by(conversation_id=conv.id)
                    .filter(Message.message_index > conv.last_harvested_index)
                    .order_by(Message.message_index)
                    .all()
                )

                if not messages:
                    console.print("   ℹ️ No new messages to process")
                    conv.harvest_status = "done"
                    session.commit()
                    continue

                # Convert to ChunkMessages
                chunk_messages = [
                    ChunkMessage(
                        id=m.id,
                        content=m.content,
                        timestamp=m.timestamp,
                        sender_id=m.sender_id,
                    )
                    for m in messages
                ]

                # Chunk the conversation
                chunk_result = chunk_conversation(
                    messages=chunk_messages,
                    conversation_id=conv.id,
                    max_chunk_chars=MAX_CHUNK_CHARS,
                )
                console.print(format_chunk_stats(chunk_result, conv.title))

                # Initialize context window
                context_window = ContextWindow()
                result: ChunkResult = ChunkResult(chunk_order=-1) # Dummy initial

                # Build existing memory brief for context injection
                existing_memory = _build_memory_brief(session, entity_id)

                # Process chunks
                for chunk in chunk_result.chunks:
                    # Pass 1: Narrative
                    result = await run_narrative_pass(
                        chunk=chunk,
                        agent_name=agent_name,
                        user_name=user_name,
                        rolling_context=context_window.current_context,
                        existing_memory_brief=existing_memory,
                        chunk_order=chunk.chunk_order,
                    )
                    stats["pass1_calls"] += 1

                    # Pass 2: Data extraction
                    result = await run_extraction_pass(
                        chunk=chunk,
                        chunk_result=result,
                        agent_name=agent_name,
                        user_name=user_name,
                        existing_lexicon_terms=context_window.get_known_lexicon_terms(),
                    )
                    stats["pass2_calls"] += 1
                    
                    # Echo Pass (Dreams)
                    dreams = await run_echo_pass(
                        chunk=chunk,
                        rolling_context=result.rolling_summary,
                        agent_name=agent_name,
                        user_name=user_name,
                    )
                    result.echo_dreams = dreams

                    # Add to context window
                    context_window.add_result(result)
                    stats["chunks_processed"] += 1
                    
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
                    )
                    stats["edges_created"] += edge_stats.get("edges_created", 0)
                    stats["arcs_created"] += edge_stats.get("arcs_created", 0)

                    # Factual entity extraction (per chunk)
                    for chunk in chunk_result.chunks:
                        chunk_text = format_chunk_for_llm(chunk, agent_name)
                        # Get rolling context from the matching chunk result
                        chunk_idx = chunk.chunk_order
                        results_list = context_window.all_results
                        narrative_ctx = (
                            results_list[chunk_idx].rolling_summary
                            if chunk_idx < len(results_list)
                            else ""
                        )
                        first_msg_id = (
                            chunk.messages[0].id if chunk.messages else None
                        )
                        factual_stats = await run_factual_extraction(
                            entity_id=entity_id,
                            session=session,
                            chunk_text=chunk_text,
                            agent_name=agent_name,
                            user_name=user_name,
                            narrative_context=narrative_ctx,
                            source_message_id=first_msg_id,
                        )
                        stats["edges_created"] += factual_stats.get("edges_created", 0)
                        stats["factual_entities_created"] += factual_stats.get("entities_created", 0)
                        stats["factual_entities_updated"] += factual_stats.get("entities_updated", 0)

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
                        messages_from=messages[0].message_index,
                        messages_to=last_idx,
                        message_count=len(messages),
                        llm_used="gemini",
                        items_extracted=stored,
                        success=True,
                    )
                    session.add(log)
                    entity = session.get(Entity, entity_id)
                    if entity:
                        entity.last_harvest = datetime.now(timezone.utc)

                    session.commit()

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
