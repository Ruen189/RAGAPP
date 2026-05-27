from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.deps import get_current_user
from app.models import User, UserProfile
from app.schemas import ProfileOut, ProfileUpdate

router = APIRouter()


async def get_or_create_profile(db: AsyncSession, user: User) -> UserProfile:
    profile = await db.get(UserProfile, user.id)
    if profile:
        return profile
    profile = UserProfile(user_id=user.id)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


def profile_out(user: User, profile: UserProfile) -> ProfileOut:
    return ProfileOut(
        user_id=user.id,
        login=user.login,
        role=user.role,
        full_name=profile.full_name,
        university_group=profile.university_group,
        phone=profile.phone,
        telegram=profile.telegram,
        avatar_data_url=profile.avatar_data_url,
    )


@router.get("", response_model=ProfileOut)
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> ProfileOut:
    profile = await get_or_create_profile(db, user)
    return profile_out(user, profile)


@router.put("", response_model=ProfileOut)
async def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await get_or_create_profile(db, user)
    profile.full_name = payload.full_name.strip() or "-"
    profile.university_group = payload.university_group.strip() or "-"
    profile.phone = payload.phone.strip() or "-"
    profile.telegram = payload.telegram.strip() or "-"
    profile.avatar_data_url = payload.avatar_data_url
    await db.commit()
    await db.refresh(profile)
    return profile_out(user, profile)
