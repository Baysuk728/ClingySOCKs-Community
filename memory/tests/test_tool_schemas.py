"""Tests for Tool Schemas (new tools in schemas.py)."""


class TestNewToolSchemas:
    """Verify the new tool schemas are properly registered."""

    def test_surface_memories_schema_exists(self):
        from src.tools.schemas import SURFACE_MEMORIES_SCHEMA
        assert SURFACE_MEMORIES_SCHEMA["name"] == "surface_memories"
        assert "query" in SURFACE_MEMORIES_SCHEMA["parameters"]["properties"]
        assert "query" in SURFACE_MEMORIES_SCHEMA["parameters"]["required"]

    def test_timeline_schema_exists(self):
        from src.tools.schemas import TIMELINE_SCHEMA
        assert TIMELINE_SCHEMA["name"] == "trace_timeline"
        assert "topic" in TIMELINE_SCHEMA["parameters"]["properties"]
        assert "topic" in TIMELINE_SCHEMA["parameters"]["required"]

    def test_manage_thread_schema_exists(self):
        from src.tools.schemas import MANAGE_THREAD_SCHEMA
        assert MANAGE_THREAD_SCHEMA["name"] == "manage_thread"
        props = MANAGE_THREAD_SCHEMA["parameters"]["properties"]
        assert "action" in props
        assert props["action"]["enum"] == ["create", "update", "resolve"]

    def test_all_tool_schemas_includes_new(self):
        from src.tools.schemas import ALL_TOOL_SCHEMAS
        names = [t["function"]["name"] for t in ALL_TOOL_SCHEMAS]

        assert "surface_memories" in names
        assert "trace_timeline" in names
        assert "manage_thread" in names

    def test_get_tool_schemas_includes_new(self):
        from src.tools.schemas import get_tool_schemas
        tools = get_tool_schemas()
        names = [t["function"]["name"] for t in tools]

        assert "surface_memories" in names
        assert "trace_timeline" in names
        assert "manage_thread" in names

    def test_schemas_have_required_fields(self):
        """All schemas must have name, description, parameters."""
        from src.tools.schemas import SURFACE_MEMORIES_SCHEMA, TIMELINE_SCHEMA, MANAGE_THREAD_SCHEMA

        for schema in [SURFACE_MEMORIES_SCHEMA, TIMELINE_SCHEMA, MANAGE_THREAD_SCHEMA]:
            assert "name" in schema
            assert "description" in schema
            assert "parameters" in schema
            assert schema["parameters"]["type"] == "object"
            assert "properties" in schema["parameters"]
