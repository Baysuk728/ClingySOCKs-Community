"""
Mood Vector Engine Service (Phase 2).

Transforms the mood system from discrete snapshots into a continuous
5-dimensional vector space that drifts over time and acts as a generic
event dispatcher.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from src.db.models import MoodAction

log = logging.getLogger("mood_engine")


@dataclass
class MoodVector:
    """5-dimensional emotional state representation (0.0 to 1.0)."""
    energy: float          # 0.0 depleted ... 1.0 wired
    warmth: float          # 0.0 cold/detached ... 1.0 affectionate
    protectiveness: float  # 0.0 hands-off ... 1.0 hovering
    chaos: float           # 0.0 orderly ... 1.0 feral
    melancholy: float      # 0.0 content ... 1.0 grieving

    def clamp(self):
        """Ensure all dimensions stay within valid bounds."""
        self.energy = max(0.0, min(1.0, self.energy))
        self.warmth = max(0.0, min(1.0, self.warmth))
        self.protectiveness = max(0.0, min(1.0, self.protectiveness))
        self.chaos = max(0.0, min(1.0, self.chaos))
        self.melancholy = max(0.0, min(1.0, self.melancholy))


def apply_time_drift(
    current: MoodVector,
    baseline: MoodVector,
    hours_elapsed: float
) -> MoodVector:
    """
    Regress the current mood vector toward the entity's baseline.
    Runs every hour. Rate is approx 5% reversion per hour.
    """
    if hours_elapsed <= 0:
        return current

    drift_rate = min(0.05 * hours_elapsed, 0.5)  # Cap to prevent overshooting baseline

    new_vector = MoodVector(
        energy=current.energy + (baseline.energy - current.energy) * drift_rate,
        warmth=current.warmth + (baseline.warmth - current.warmth) * drift_rate,
        protectiveness=current.protectiveness + (baseline.protectiveness - current.protectiveness) * drift_rate,
        chaos=current.chaos + (baseline.chaos - current.chaos) * drift_rate,
        melancholy=current.melancholy + (baseline.melancholy - current.melancholy) * drift_rate,
    )
    new_vector.clamp()
    return new_vector


def evaluate_mood_actions(
    session: Session,
    entity_id: str,
    vector: MoodVector
) -> List[Dict[str, Any]]:
    """
    Evaluate the current mood vector against the rule registry (mood_actions table).
    Returns list of action configs that tripped their threshold.
    """
    actions_to_fire = []
    
    # Simple hardcoded fallbacks if no DB actions exist for the entity yet
    actions = session.query(MoodAction).filter_by(entity_id=entity_id, enabled=True).all()
    
    if not actions:
        # Evaluate default heuristic thresholds
        if vector.protectiveness > 0.75:
            actions_to_fire.append({
                "action_type": "modifier",
                "action_config": {"modifier": "surface_strong_preferences", "urgency": "high"}
            })
        if vector.energy < 0.25:
            actions_to_fire.append({
                "action_type": "modifier",
                "action_config": {"modifier": "reduce_verbosity"}
            })
        if vector.chaos > 0.8:
            actions_to_fire.append({
                "action_type": "task",
                "action_config": {"task_goal": "alter_haptic_waveform", "priority": 4}
            })
        if vector.melancholy > 0.7:
            actions_to_fire.append({
                "action_type": "task",
                "action_config": {"task_goal": "check_last_activity_and_reminisce", "priority": 3}
            })
        return actions_to_fire

    # Evaluate DB rules
    # E.g. condition: "protectiveness > 0.7" or "chaos > 0.6 and energy > 0.5"
    env = {
        "energy": vector.energy,
        "warmth": vector.warmth,
        "protectiveness": vector.protectiveness,
        "chaos": vector.chaos,
        "melancholy": vector.melancholy,
    }

    import ast
    import operator

    # Very restricted eval for safety
    allowed_operators = {
        ast.Eq: operator.eq, ast.NotEq: operator.ne,
        ast.Lt: operator.lt, ast.LtE: operator.le,
        ast.Gt: operator.gt, ast.GtE: operator.ge,
        ast.And: lambda x, y: x and y,
        ast.Or: lambda x, y: x or y
    }

    def _eval_node(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            raise ValueError(f"Unknown dimension: {node.id}")
        elif isinstance(node, ast.Compare):
            left = _eval_node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = _eval_node(comparator)
                if not allowed_operators[type(op)](left, right):
                    return False
                left = right
            return True
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(_eval_node(val) for val in node.values)
            elif isinstance(node.op, ast.Or):
                return any(_eval_node(val) for val in node.values)
        raise ValueError(f"Unsupported expression node: {type(node)}")

    for action in actions:
        try:
            tree = ast.parse(action.condition, mode='eval')
            result = _eval_node(tree.body)
            if result:
                actions_to_fire.append({
                    "action_id": action.id,
                    "action_type": action.action_type,
                    "action_config": action.action_config
                })
        except Exception as e:
            log.error(f"Failed to evaluate mood condition '{action.condition}': {e}")

    return actions_to_fire
