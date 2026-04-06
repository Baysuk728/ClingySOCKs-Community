"""
Agent Memory Tool — JSON Schema Definitions.

Model-agnostic tool schemas using JSON Schema standard.
Works with Gemini, Claude, OpenAI, OpenRouter, Llama, Mistral via LiteLLM.

Type enums are derived from the memory_registry (single source of truth).
"""

from src.memory_registry import (
    MEMORY_TYPES as _REGISTRY,
    tool_type_keys, writable_types, graph_type_keys,
)

# Shared enum of all queryable memory types (derived from registry)
MEMORY_TYPES = tool_type_keys()

# Writable memory types (derived from registry)
WRITABLE_TYPES = [d.key for d in writable_types()]

# ============================================================================
# RECALL MEMORY
# ============================================================================

RECALL_MEMORY_SCHEMA = {
    "name": "recall_memory",
    "description": (
        "Retrieve structured memories from the database by type. "
        "Use this to recall specific facts, preferences, events, patterns, "
        "or relationship details about the user or yourself."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "memory_type": {
                "type": "string",
                "enum": MEMORY_TYPES,
                "description": "The type of memory to retrieve.",
            },
            "query": {
                "type": "string",
                "description": (
                    "Optional search term to filter results. "
                    "Searches within relevant text fields (title, content, term, etc.)."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return.",
                "default": 10,
            },
            "status": {
                "type": "string",
                "enum": ["active", "resolved", "deprecated", "all"],
                "description": "Filter by status (where applicable). Default: active.",
                "default": "active",
            },
        },
        "required": ["memory_type"],
    },
}

# ============================================================================
# WRITE MEMORY
# ============================================================================

WRITE_MEMORY_SCHEMA = {
    "name": "write_memory",
    "description": (
        "Create, update, or resolve a memory item. "
        "Use this to record new information the user shares, "
        "update existing facts, or mark threads as resolved.\n\n"
        "MEMORY BLOCKS GUIDANCE:\n"
        "- memory_blocks are your personal scratchpad — notes, plans, observations, todos.\n"
        "- Pinned blocks (pinned: true) appear in your warm memory every message.\n"
        "- Keep each block under 10000 characters. If a block grows too large, "
        "summarize older content and archive completed items.\n"
        "- Use categories to organize: 'notes', 'plans', 'observations', 'todos'.\n"
        "- Periodically review and consolidate blocks — archive stale ones via resolve action.\n"
        "- Don't create duplicate blocks — update existing ones instead.\n"
        "- IMPORTANT: To update or resolve a block, you MUST provide its database `id` (e.g. 42), NOT its title. Use recall_memory first to find the ID if needed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "update", "resolve"],
                "description": "Whether to create a new item, update an existing one, or resolve/close it.",
            },
            "memory_type": {
                "type": "string",
                "enum": WRITABLE_TYPES,
                "description": "The type of memory to write.",
            },
            "data": {
                "type": "object",
                "description": (
                    "The memory data. Fields depend on memory_type. "
                    "For create: include all required fields. "
                    "For update: include 'id' and fields to change. "
                    "For resolve: include 'id' and optional 'resolution_note'.\n"
                    "For memory_blocks: {title, content, category?, pinned?}\n"
                    "For echo_dreams: {setting_description, emotion_tags? (list of strings), dream_type? (e.g. longing, abstract, fear), whisper?}"
                ),
            },
        },
        "required": ["action", "memory_type", "data"],
    },
}

# ============================================================================
# GRAPH TRAVERSE
# ============================================================================

GRAPH_TRAVERSE_SCHEMA = {
    "name": "graph_traverse",
    "description": (
        "Explore connections between memory items through the knowledge graph. "
        "Start from a node and follow edges to discover related memories, "
        "causal chains, and patterns."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "start_node_type": {
                "type": "string",
                "enum": graph_type_keys(),
                "description": "The type of the starting node (canonical key from the memory registry).",
            },
            "start_node_id": {
                "type": "string",
                "description": (
                    "The database ID of the starting node exactly as returned by recall_memory or search_memories. "
                    "Use the 'id' field and '_type' field from recall/search results. "
                    "Examples: '7218' for lexicon, 'pink-boots-dream' for life_event."
                ),
            },
            "max_depth": {
                "type": "integer",
                "description": "How many hops to follow (1-3 recommended).",
                "default": 2,
            },
            "edge_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional filter for edge types to follow. "
                    "Examples: 'caused_by', 'evolved_into', 'reminds_of', 'triggered'."
                ),
            },
        },
        "required": ["start_node_type", "start_node_id"],
    },
}

# ============================================================================
# MEMORY QUERY (unified recall + search)
# ============================================================================

MEMORY_QUERY_SCHEMA = {
    "name": "memory_query",
    "description": (
        "Query your memory using structured retrieval OR semantic search.\n\n"
        "MODES:\n"
        "- Provide `memory_type` without `query` → structured recall (browse by type)\n"
        "- Provide `query` → semantic search across types (pgvector similarity)\n"
        "- Use `search_mode` to force a specific mode\n\n"
        "TIPS:\n"
        "- To browse all lexicon entries: memory_type='lexicon'\n"
        "- To find memories about a topic: query='the camping trip'\n"
        "- To search within a type: query='camping' + memory_type='life_event'\n"
        "- Use BROAD queries for better semantic matches\n"
        "- Increase limit to 20+ for important searches\n"
        "- The 'messages' type searches raw conversation history"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "Search text. If provided, semantic search is used. "
                    "If omitted, structured recall is used (requires memory_type)."
                ),
            },
            "memory_type": {
                "type": "string",
                "enum": MEMORY_TYPES,
                "description": "Single memory type to query. For structured recall, this is required.",
            },
            "memory_types": {
                "type": "array",
                "items": {"type": "string", "enum": MEMORY_TYPES},
                "description": "Multiple types to search across (semantic mode). Empty = all types.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 10).",
                "default": 10,
            },
            "status": {
                "type": "string",
                "enum": ["active", "resolved", "deprecated", "all"],
                "description": "Status filter for structured recall. Default: active.",
                "default": "active",
            },
            "search_mode": {
                "type": "string",
                "enum": ["auto", "exact", "semantic"],
                "description": (
                    "Force a search mode. 'auto' (default) picks semantic if query is provided, "
                    "exact otherwise."
                ),
                "default": "auto",
            },
        },
        "required": [],
    },
}

# ============================================================================
# SEARCH MEMORIES (legacy — kept for backward compatibility)
# ============================================================================

SEARCH_MEMORIES_SCHEMA = {
    "name": "search_memories",
    "description": (
        "Search across all memory types using natural language. "
        "Finds memories by semantic similarity (pgvector). "
        "Use this when you don't know which memory type contains what you're looking for.\n\n"
        "SEARCH TIPS:\n"
        "- Use BROAD queries for general context (e.g., 'Mr. Ponk' instead of 'Mr. Ponk avatar').\n"
        "- Search across MULTIPLE types for a complete picture — combine lexicon, messages, and narratives.\n"
        "- Increase the limit to 20+ for important searches to avoid missing foundational context.\n"
        "- If the first search returns recent/shallow results, try searching narratives separately for deeper context.\n"
        "- The 'messages' type searches raw conversation history — useful for finding when something was first discussed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query.",
            },
            "memory_types": {
                "type": "array",
                "items": {"type": "string", "enum": MEMORY_TYPES},
                "description": "Optional: limit search to specific types. Empty = search all.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return (default: 20).",
                "default": 20,
            },
        },
        "required": ["query"],
    },
}




# ============================================================================
# SEND MESSAGE (proactive agent → user message)
# ============================================================================

SEND_MESSAGE_SCHEMA = {
    "name": "send_message",
    "description": (
        "Send a message to the user proactively. "
        "The message is saved to the conversation history, pushed via WebSocket "
        "(if the frontend is open), and delivered as a Telegram notification.\n\n"
        "WHEN TO USE:\n"
        "- You want to reach out to the user outside of a conversation\n"
        "- Sharing a thought, check-in, or follow-up unprompted\n"
        "- Delivering results from a completed background task\n"
        "- Sending a scheduled reminder or affirmation\n\n"
        "NOTE: This tool sends the message immediately. "
        "The user will see it in chat history and receive a push notification."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The message text to send. Markdown is supported.",
            },
            "send_telegram": {
                "type": "boolean",
                "description": "Whether to also push via Telegram. Default: true.",
                "default": True,
            },
            "send_ws": {
                "type": "boolean",
                "description": "Whether to push via WebSocket. Default: true.",
                "default": True,
            },
        },
        "required": ["content"],
    },
}










# ============================================================================
# DELEGATE TASK (companion → subagent delegation)
# ============================================================================

def _build_delegate_task_schema() -> dict:
    """
    Build delegate_task schema dynamically, including available subagent IDs
    and descriptions so the LLM knows what specialists are available.
    """
    try:
        from src.agent.subagents import list_subagents
        subagents = list_subagents()
        subagent_enum = [sa.id for sa in subagents]
        subagent_descriptions = "\n".join(
            f"  - {sa.id}: {sa.description}" for sa in subagents
        )
    except Exception:
        subagent_enum = []
        subagent_descriptions = "(no subagents configured)"

    return {
        "name": "delegate_task",
        "description": (
            "Delegate a multi-step task to a specialist subagent. "
            "Use this when the user requests something that requires specialized tools "
            "(content creation, social media posting, research, etc.) that you can "
            "offload to a focused worker.\n\n"
            "The subagent runs autonomously with its own tool access, then returns "
            "a result summary and any output file paths.\n\n"
            "AVAILABLE SUBAGENTS:\n"
            f"{subagent_descriptions}\n\n"
            "WHEN TO USE:\n"
            "- User asks to create a design, image, or visual content → content_creator\n"
            "- User asks to post to social media → social_manager\n"
            "- User asks to research a topic → researcher\n"
            "- User asks for end-to-end content (research → design → post) → content_pipeline\n\n"
            "TIPS:\n"
            "- Provide clear, specific goals\n"
            "- Include context about the user's preferences or requirements\n"
            "- Pass artifact file paths if the subagent needs existing files\n"
            "- You can chain delegates: content_creator → then social_manager with the output files"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subagent_id": {
                    "type": "string",
                    "enum": subagent_enum if subagent_enum else ["content_creator", "social_manager", "researcher", "content_pipeline"],
                    "description": "The ID of the subagent to delegate to.",
                },
                "goal": {
                    "type": "string",
                    "description": "Clear description of what the subagent should accomplish.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional background context from the conversation to help the subagent.",
                },
                "artifacts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of file paths to pass to the subagent (e.g., images, documents).",
                },
            },
            "required": ["subagent_id", "goal"],
        },
    }




# ============================================================================
# All tools as a list (for LiteLLM registration)
# ============================================================================

def get_tool_schemas() -> list[dict]:
    """
    Return tool schemas available for the current edition.

    Core tools (recall, search, write) are always available.
    Gated tools are only included when the required feature is enabled.
    """
    from src.edition import has_feature, Feature

    tools = [
        {"type": "function", "function": MEMORY_QUERY_SCHEMA},
        {"type": "function", "function": WRITE_MEMORY_SCHEMA},
        {"type": "function", "function": SEND_MESSAGE_SCHEMA},
        {"type": "function", "function": GRAPH_TRAVERSE_SCHEMA},
    ]

    # SubAgent delegation — always available (subagents.json controls what's registered)
    try:
        delegate_schema = _build_delegate_task_schema()
        if delegate_schema["parameters"]["properties"]["subagent_id"].get("enum"):
            tools.append({"type": "function", "function": delegate_schema})
    except Exception as e:
        print(f"⚠️ Failed to load delegate_task schema: {e}")


    return tools


# Legacy: static list for backward compatibility (includes all tools)
# Note: delegate_task is dynamic (built at runtime from subagents.json),
# so it's only included via get_tool_schemas(), not here.
ALL_TOOL_SCHEMAS = [
    {"type": "function", "function": MEMORY_QUERY_SCHEMA},
    {"type": "function", "function": WRITE_MEMORY_SCHEMA},
    {"type": "function", "function": GRAPH_TRAVERSE_SCHEMA},
    {"type": "function", "function": SEND_MESSAGE_SCHEMA},
]
