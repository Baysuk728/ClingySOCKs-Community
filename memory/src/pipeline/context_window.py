"""
Rolling Context Window.

Manages the cross-chunk context: stores rolling summaries and
generates the context injection for each new chunk.
"""

from dataclasses import dataclass, field


@dataclass
class ChunkResult:
    """Result from processing a single chunk through Pass 1 + Pass 2."""
    chunk_order: int

    # Pass 1 outputs
    emotional_arcs: dict = field(default_factory=dict)
    relational_shifts: dict = field(default_factory=dict)
    dream_analysis: list = field(default_factory=list)
    narrative_threads: dict = field(default_factory=dict)
    key_moments: list = field(default_factory=list)
    repair_patterns: list = field(default_factory=list)
    state_observations: list = field(default_factory=list)
    unresolved_threads: list = field(default_factory=list)
    rolling_summary: str = ""

    # Pass 2 outputs
    lexicon: list = field(default_factory=list)
    inside_jokes: list = field(default_factory=list)
    artifacts: list = field(default_factory=list)
    life_events: list = field(default_factory=list)
    cold_memories: list = field(default_factory=list)
    permissions: list = field(default_factory=list)
    rituals: list = field(default_factory=list)
    mythology_updates: dict = field(default_factory=dict)
    emotional_patterns: list = field(default_factory=list)
    persona: dict = field(default_factory=dict)
    echo_dreams: list = field(default_factory=list)
    user_dossier: dict = field(default_factory=dict)
    concept_evolutions: list = field(default_factory=list)
    relationship_update: dict = field(default_factory=dict)


class ContextWindow:
    """
    Manages rolling context between chunks.

    After each chunk is processed, the rolling_summary from Pass 1
    becomes the context input for the next chunk's Pass 1.

    This is the key mechanism that fixes the "isolated chunks" problem.
    """

    def __init__(self):
        self._results: list[ChunkResult] = []
        self._current_rolling_summary: str = ""

    @property
    def current_context(self) -> str:
        """Get the current rolling context for the next chunk."""
        return self._current_rolling_summary

    @property
    def chunk_count(self) -> int:
        return len(self._results)

    @property
    def all_results(self) -> list[ChunkResult]:
        return self._results

    def add_result(self, result: ChunkResult) -> None:
        """Add a processed chunk result and update rolling context."""
        self._results.append(result)
        self._current_rolling_summary = result.rolling_summary

    def get_all_rolling_summaries(self) -> list[str]:
        """Get all rolling summaries for the synthesis pass."""
        return [r.rolling_summary for r in self._results if r.rolling_summary]

    def get_all_life_events(self) -> list[dict]:
        """Collect all life events across chunks for dedup."""
        events = []
        for r in self._results:
            events.extend(r.life_events)
        return events

    def get_all_lexicon(self) -> list[dict]:
        """Collect all lexicon across chunks for dedup."""
        terms = []
        for r in self._results:
            terms.extend(r.lexicon)
        return terms

    def get_all_inside_jokes(self) -> list[dict]:
        jokes = []
        for r in self._results:
            jokes.extend(r.inside_jokes)
        return jokes

    def get_all_artifacts(self) -> list[dict]:
        artifacts = []
        for r in self._results:
            artifacts.extend(r.artifacts)
        return artifacts

    def get_all_cold_memories(self) -> list[dict]:
        memories = []
        for r in self._results:
            memories.extend(r.cold_memories)
        return memories

    def get_all_repair_patterns(self) -> list[dict]:
        patterns = []
        for r in self._results:
            patterns.extend(r.repair_patterns)
        return patterns

    def get_all_state_observations(self) -> list[dict]:
        observations = []
        for r in self._results:
            observations.extend(r.state_observations)
        return observations

    def get_all_unresolved_threads(self) -> list[dict]:
        threads = []
        for r in self._results:
            threads.extend(r.unresolved_threads)
        return threads

    def get_all_permissions(self) -> list[dict]:
        permissions = []
        for r in self._results:
            permissions.extend(r.permissions)
        return permissions

    def get_all_rituals(self) -> list[dict]:
        rituals = []
        for r in self._results:
            rituals.extend(r.rituals)
        return rituals

    def get_all_mythology_updates(self) -> list[dict]:
        updates = []
        for r in self._results:
            if r.mythology_updates:
                updates.append(r.mythology_updates)
        return updates

    def get_all_emotional_patterns(self) -> list[dict]:
        patterns = []
        for r in self._results:
            patterns.extend(r.emotional_patterns)
        return patterns

    def get_latest_persona_update(self) -> dict | None:
        """Get the most recent persona update."""
        for r in reversed(self._results):
            if r.persona:
                return r.persona
        return None

    def get_latest_user_dossier(self) -> dict | None:
        """Get the most recent user dossier update."""
        for r in reversed(self._results):
            if r.user_dossier:
                return r.user_dossier
        return None

    def get_all_concept_evolutions(self) -> list[dict]:
        """Collect all concept evolutions across chunks."""
        evolutions = []
        for r in self._results:
            evolutions.extend(r.concept_evolutions)
        return evolutions

    def get_latest_relationship_update(self) -> dict | None:
        """Get the most recent relationship update (trust, attachment, communication)."""
        for r in reversed(self._results):
            if r.relationship_update:
                return r.relationship_update
        return None

    def get_known_lexicon_terms(self) -> list[str]:
        """Get list of already-extracted terms for dedup guidance in Pass 2."""
        terms = set()
        for r in self._results:
            for entry in r.lexicon:
                if isinstance(entry, dict) and "term" in entry:
                    terms.add(entry["term"])
        return sorted(terms)
