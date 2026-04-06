"""
User Profile routes — editable user profile.

Endpoints:
  GET  /user-profile/{entity_id}      Get user profile
  GET  /user-profile/me               Get current user's profile
  PUT  /user-profile/{entity_id}      Update user profile (merge with harvested data)
  GET  /user-profile/{entity_id}/locked    Get locked fields (pinned_fields)
  GET  /user-profile/me/locked        Get current user's locked fields
  PUT  /user-profile/{entity_id}/locked    Update locked fields (pinned_fields)
  PUT  /user-profile/me/locked        Update current user's locked fields
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from api.auth import require_api_key
from src.db.session import get_session
from src.db.models import Entity, UserProfile


router = APIRouter(dependencies=[Depends(require_api_key)])


class UserProfileUpdateRequest(BaseModel):
    """All fields optional — only provided fields are updated (merge semantics)."""
    # Core Identity
    name: Optional[str] = None
    pronouns: Optional[str] = None
    age_range: Optional[str] = None
    location: Optional[str] = None
    languages: Optional[list[str]] = None

    # Neurotype & Cognition
    neurotype: Optional[str] = None
    thinking_patterns: Optional[list[str]] = None
    cognitive_strengths: Optional[list[str]] = None
    cognitive_challenges: Optional[list[str]] = None

    # Attachment & Emotional
    attachment_style: Optional[str] = None
    attachment_notes: Optional[str] = None
    ifs_parts: Optional[list[str]] = None
    emotional_triggers: Optional[list[str]] = None
    coping_mechanisms: Optional[list[str]] = None

    # Health & Wellness
    medical_conditions: Optional[list[str]] = None
    medications: Optional[list[str]] = None
    health_notes: Optional[str] = None

    # Life Situation
    family_situation: Optional[str] = None
    relationship_status: Optional[str] = None
    living_situation: Optional[str] = None
    work_situation: Optional[str] = None
    financial_notes: Optional[str] = None

    # Interests & Goals
    hobbies: Optional[list[str]] = None
    interests: Optional[list[str]] = None
    life_goals: Optional[list[str]] = None
    longings: Optional[list[str]] = None
    current_projects: Optional[list[str]] = None

    # Communication
    preferred_communication_style: Optional[str] = None
    humor_style: Optional[str] = None
    boundary_preferences: Optional[str] = None
    support_preferences: Optional[str] = None


class LockedFieldsRequest(BaseModel):
    """Update request for locked fields (fields protected from harvester updates)."""
    locked_fields: List[str] = []


def _get_user_entity_id(session, user_id: str) -> str:
    """
    Resolve a user's main entity ID.
    
    Finds the entity owned by this user that has a UserProfile attached.
    Falls back to the first entity owned by this user, then to user_id itself.
    """
    from sqlalchemy import select

    # First: find entity owned by this user that already has a user profile
    stmt = (
        select(Entity)
        .join(UserProfile, Entity.id == UserProfile.entity_id)
        .where(Entity.owner_user_id == user_id)
    )
    entity_with_profile = session.execute(stmt).scalars().first()
    if entity_with_profile:
        return entity_with_profile.id

    # Second: find any entity owned by this user
    stmt = select(Entity).where(Entity.owner_user_id == user_id)
    any_entity = session.execute(stmt).scalars().first()
    if any_entity:
        return any_entity.id

    # Third (dev-mode fallback): if no owner match, find any entity with a profile
    stmt = (
        select(Entity)
        .join(UserProfile, Entity.id == UserProfile.entity_id)
    )
    any_profile_entity = session.execute(stmt).scalars().first()
    if any_profile_entity:
        return any_profile_entity.id

    # Last resort: find any entity at all
    stmt = select(Entity)
    first_entity = session.execute(stmt).scalars().first()
    if first_entity:
        return first_entity.id

    return user_id



def _profile_to_dict(profile: UserProfile) -> dict:
    """Convert UserProfile ORM object to response dict."""
    return {
        "entity_id": profile.entity_id,
        "name": profile.name,
        "pronouns": profile.pronouns,
        "age_range": profile.age_range,
        "location": profile.location,
        "languages": profile.languages or [],
        "neurotype": profile.neurotype,
        "thinking_patterns": profile.thinking_patterns or [],
        "cognitive_strengths": profile.cognitive_strengths or [],
        "cognitive_challenges": profile.cognitive_challenges or [],
        "attachment_style": profile.attachment_style,
        "attachment_notes": profile.attachment_notes,
        "ifs_parts": profile.ifs_parts or [],
        "emotional_triggers": profile.emotional_triggers or [],
        "coping_mechanisms": profile.coping_mechanisms or [],
        "medical_conditions": profile.medical_conditions or [],
        "medications": profile.medications or [],
        "health_notes": profile.health_notes,
        "family_situation": profile.family_situation,
        "relationship_status": profile.relationship_status,
        "living_situation": profile.living_situation,
        "work_situation": profile.work_situation,
        "financial_notes": profile.financial_notes,
        "hobbies": profile.hobbies or [],
        "interests": profile.interests or [],
        "life_goals": profile.life_goals or [],
        "longings": profile.longings or [],
        "current_projects": profile.current_projects or [],
        "preferred_communication_style": profile.preferred_communication_style,
        "humor_style": profile.humor_style,
        "boundary_preferences": profile.boundary_preferences,
        "support_preferences": profile.support_preferences,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


# ============================================================================
# Special "me" endpoints - for current user (resolved by auth)
# ============================================================================

@router.get("/me")
async def get_current_user_profile(user_id: str = Depends(require_api_key)):
    """Get current user's profile."""
    with get_session() as session:
        entity_id = _get_user_entity_id(session, user_id)
        entity = session.get(Entity, entity_id)
        if not entity:
            return {"success": True, "profile": None, "message": "No profile yet"}

        profile = session.get(UserProfile, entity_id)
        if not profile:
            return {"success": True, "profile": None, "message": "No profile yet"}

        return {"success": True, "profile": _profile_to_dict(profile)}


@router.put("/me")
async def update_current_user_profile(req: UserProfileUpdateRequest, user_id: str = Depends(require_api_key)):
    """Update current user's profile."""
    with get_session() as session:
        entity_id = _get_user_entity_id(session, user_id)

        # Get or create profile
        profile = session.get(UserProfile, entity_id)
        if not profile:
            profile = UserProfile(entity_id=entity_id)
            session.add(profile)

        # Merge: only update fields that are explicitly provided
        update_data = req.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(profile, field, value)

        profile.updated_at = datetime.now(timezone.utc)
        session.commit()

        return {"success": True, "profile": _profile_to_dict(profile)}


@router.get("/me/locked")
async def get_current_user_locked_fields(user_id: str = Depends(require_api_key)):
    """Get current user's locked fields (pinned_fields)."""
    with get_session() as session:
        entity_id = _get_user_entity_id(session, user_id)
        profile = session.get(UserProfile, entity_id)
        locked_fields = profile.pinned_fields if profile else []

        return {
            "success": True,
            "locked_fields": locked_fields or [],
            "message": "Retrieved locked fields"
        }


@router.put("/me/locked")
async def update_current_user_locked_fields(req: LockedFieldsRequest, user_id: str = Depends(require_api_key)):
    """Update current user's locked fields (pinned_fields)."""
    with get_session() as session:
        entity_id = _get_user_entity_id(session, user_id)

        # Get or create profile
        profile = session.get(UserProfile, entity_id)
        if not profile:
            profile = UserProfile(entity_id=entity_id)
            session.add(profile)

        # Update locked/pinned fields
        profile.pinned_fields = req.locked_fields
        profile.updated_at = datetime.now(timezone.utc)
        session.commit()

        return {
            "success": True,
            "locked_fields": profile.pinned_fields or [],
            "message": f"Updated {len(profile.pinned_fields or [])} locked fields"
        }


# ============================================================================
# Generic entity routes - match specific entity_id (comes after /me for priority)
# ============================================================================

@router.get("/{entity_id}")
async def get_user_profile(entity_id: str):
    """Get user profile for an entity."""
    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

        profile = session.get(UserProfile, entity_id)
        if not profile:
            return {"success": True, "profile": None, "message": "No profile yet"}

        return {"success": True, "profile": _profile_to_dict(profile)}


@router.put("/{entity_id}")
async def update_user_profile(entity_id: str, req: UserProfileUpdateRequest):
    """
    Update user profile with merge semantics.
    Only provided fields are updated — None fields are skipped.
    This allows both harvester and user to contribute to the profile.
    """
    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

        # Get or create profile
        profile = session.get(UserProfile, entity_id)
        if not profile:
            profile = UserProfile(entity_id=entity_id)
            session.add(profile)

        # Merge: only update fields that are explicitly provided
        update_data = req.model_dump(exclude_none=True)
        for field, value in update_data.items():
            setattr(profile, field, value)

        profile.updated_at = datetime.now(timezone.utc)
        session.commit()

        return {"success": True, "profile": _profile_to_dict(profile)}


@router.get("/{entity_id}/locked")
async def get_locked_fields(entity_id: str):
    """Get locked fields (pinned_fields) for a user profile."""
    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

        profile = session.get(UserProfile, entity_id)
        locked_fields = profile.pinned_fields if profile else []

        return {
            "success": True,
            "locked_fields": locked_fields or [],
            "message": "Retrieved locked fields"
        }


@router.put("/{entity_id}/locked")
async def update_locked_fields(entity_id: str, req: LockedFieldsRequest):
    """
    Update locked fields (pinned_fields) - fields protected from harvester updates.
    """
    with get_session() as session:
        entity = session.get(Entity, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

        # Get or create profile
        profile = session.get(UserProfile, entity_id)
        if not profile:
            profile = UserProfile(entity_id=entity_id)
            session.add(profile)

        # Update locked/pinned fields
        profile.pinned_fields = req.locked_fields
        profile.updated_at = datetime.now(timezone.utc)
        session.commit()

        return {
            "success": True,
            "locked_fields": profile.pinned_fields or [],
            "message": f"Updated {len(profile.pinned_fields or [])} locked fields"
        }



