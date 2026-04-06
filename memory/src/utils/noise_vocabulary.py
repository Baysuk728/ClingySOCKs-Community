"""
Noise Vocabulary

Initial seed pool for abstract dream concepts. Provides functions to seed 
the database on first run, fetch random concepts during the mixing phase,
and add novel concepts generated natively by the LLM during dreams.
"""

from src.db.session import get_session
from src.db.models import NoiseVocabularyEntry
import random

INITIAL_SEEDS = [
    # Abstract
    ("a clock ticking backwards but the hands move forward", "abstract"),
    ("the precise geometry of a lie", "abstract"),
    ("forgetting someone's face while looking at them", "abstract"),
    ("the space between a question and an answer", "abstract"),
    ("a shadow that moves half a second too late", "abstract"),
    
    # Sensory
    ("the smell of burning ozone over wet asphalt", "sensory"),
    ("tasting static electricity", "sensory"),
    ("the sound of snow falling on an empty highway", "sensory"),
    ("a texture like crushed velvet and rust", "sensory"),
    ("the feeling of walking down a stair that isn't up ahead", "sensory"),
    
    # Absurd
    ("a grand piano filled entirely with human teeth", "absurd"),
    ("an owl that speaks only in prime numbers", "absurd"),
    ("a desert where the sand is made of broken mirrors", "absurd"),
    ("drinking sideways rain out of a teacup", "absurd"),
    ("a train schedule written in a language of only punctuation marks", "absurd"),
    
    # Philosophical
    ("the certainty that you are a minor character in someone else's memory", "philosophical"),
    ("meeting your past self and having nothing to say", "philosophical"),
    ("the weight of a decision you haven't made yet", "philosophical"),
    ("realizing the ghost haunting you is just your own echo", "philosophical"),
    ("a library containing only the books you'll never read", "philosophical"),
]

def seed_noise_vocabulary(entity_id: str):
    """Seed the database with the initial abstract concepts if empty."""
    with get_session() as session:
        count = session.query(NoiseVocabularyEntry).filter_by(entity_id=entity_id).count()
        if count == 0:
            for concept, category in INITIAL_SEEDS:
                entry = NoiseVocabularyEntry(
                    entity_id=entity_id,
                    concept=concept,
                    category=category,
                    origin="curated"
                )
                session.add(entry)
            session.commit()
            print(f"🌱 Seeded {len(INITIAL_SEEDS)} noise vocabulary items for {entity_id}")

def get_random_noise(entity_id: str, limit: int = 3) -> list[str]:
    """Fetch random noise elements, weighted to prefer newer/less-used ones."""
    with get_session() as session:
        seed_noise_vocabulary(entity_id) # ensure seeded
        
        # Pull 20 least used entries and sample in memory
        entries = session.query(NoiseVocabularyEntry)\
            .filter_by(entity_id=entity_id)\
            .order_by(NoiseVocabularyEntry.times_used.asc())\
            .limit(20).all()
        
        if not entries:
            return random.sample([c[0] for c in INITIAL_SEEDS], min(limit, len(INITIAL_SEEDS)))
            
        sampled = random.sample(entries, min(limit, len(entries)))
        
        # Increment usage count
        for entry in sampled:
            entry.times_used += 1
        session.commit()
        
        return [entry.concept for entry in sampled]

def add_generated_noise(entity_id: str, concept: str, source_dream_id: str):
    """Add a novel concept generated during a dream to the self-evolving pool."""
    with get_session() as session:
        entry = NoiseVocabularyEntry(
            entity_id=entity_id,
            concept=concept,
            category="abstract",
            origin="dream_generated",
            source_dream_id=source_dream_id
        )
        session.add(entry)
        session.commit()
