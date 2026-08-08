import json

from app.config import PET_PROFILE_STORE_PATH
from app.models import PetProfile


def _load_all() -> dict[str, dict]:
    if not PET_PROFILE_STORE_PATH.exists():
        return {}
    with open(PET_PROFILE_STORE_PATH) as f:
        return json.load(f)


def _save_all(data: dict[str, dict]) -> None:
    PET_PROFILE_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PET_PROFILE_STORE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def save_profile(profile: PetProfile) -> None:
    data = _load_all()
    data[str(profile.dog_id)] = profile.model_dump()
    _save_all(data)


def get_profile(dog_id: int) -> PetProfile | None:
    raw = _load_all().get(str(dog_id))
    if raw is None:
        return None
    return PetProfile.model_validate(raw)


def update_profile(dog_id: int, **updates) -> PetProfile | None:
    profile = get_profile(dog_id)
    if profile is None:
        return None
    updated = profile.model_copy(update={k: v for k, v in updates.items() if v is not None})
    save_profile(updated)
    return updated
