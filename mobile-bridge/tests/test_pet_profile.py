from app import pet_profile
from app.models import PetProfile


def _make_profile(dog_id=1, name="Biscuit"):
    return PetProfile(
        dog_id=dog_id,
        name=name,
        breed="Beagle",
        weight_kg=12.5,
        target_range_low_mg_dl=80.0,
        target_range_high_mg_dl=180.0,
        feeding_schedule=["07:00", "17:00"],
    )


def test_get_profile_returns_none_when_not_found():
    assert pet_profile.get_profile(999) is None


def test_save_and_get_profile_roundtrip(isolate_pet_profile_store):
    profile = _make_profile()
    pet_profile.save_profile(profile)

    fetched = pet_profile.get_profile(1)
    assert fetched == profile
    assert isolate_pet_profile_store.exists()


def test_save_profile_persists_multiple_dogs():
    pet_profile.save_profile(_make_profile(dog_id=1, name="Biscuit"))
    pet_profile.save_profile(_make_profile(dog_id=2, name="Rex"))

    assert pet_profile.get_profile(1).name == "Biscuit"
    assert pet_profile.get_profile(2).name == "Rex"


def test_update_profile_changes_only_given_fields():
    pet_profile.save_profile(_make_profile())

    updated = pet_profile.update_profile(1, weight_kg=13.0)
    assert updated.weight_kg == 13.0
    assert updated.name == "Biscuit"

    refetched = pet_profile.get_profile(1)
    assert refetched.weight_kg == 13.0


def test_update_profile_returns_none_when_not_found():
    assert pet_profile.update_profile(999, weight_kg=10.0) is None
