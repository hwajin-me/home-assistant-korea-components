"""Validate the supported translation catalogs."""

import json
from pathlib import Path


INTEGRATION_DIR = Path(__file__).parents[2] / "custom_components" / "korea_incubator"


def _leaf_keys(value: object, prefix: str = "") -> set[str]:
    """Return dot-separated leaf keys from a translation catalog."""
    if not isinstance(value, dict):
        return {prefix}
    keys: set[str] = set()
    for key, child in value.items():
        child_prefix = f"{prefix}.{key}" if prefix else key
        keys.update(_leaf_keys(child, child_prefix))
    return keys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_english_and_korean_have_all_source_keys() -> None:
    """The two supported languages must exactly match strings.json."""
    source_keys = _leaf_keys(_load(INTEGRATION_DIR / "strings.json"))

    for language in ("en", "ko"):
        translation_keys = _leaf_keys(
            _load(INTEGRATION_DIR / "translations" / f"{language}.json")
        )
        assert translation_keys == source_keys


def test_error_translations_show_api_detail() -> None:
    """Errors that represent API failures must render the supplied detail."""
    for filename in ("strings.json", "translations/en.json", "translations/ko.json"):
        errors = _load(INTEGRATION_DIR / filename)["config"]["error"]
        for key in (
            "auth",
            "invalid_auth",
            "cannot_connect",
            "unknown",
            "invalid_api_key",
        ):
            assert "{error}" in errors[key]


def test_all_steps_and_fields_have_descriptions() -> None:
    """Every supported-language form must explain the step and its fields."""
    for filename in ("strings.json", "translations/en.json", "translations/ko.json"):
        catalog = _load(INTEGRATION_DIR / filename)
        for section in ("config", "options"):
            for step_id, step in catalog[section].get("step", {}).items():
                assert step.get("description"), f"{filename}: {section}.{step_id}"
                data_keys = set(step.get("data", {}))
                description_keys = set(step.get("data_description", {}))
                assert description_keys == data_keys, (
                    f"{filename}: {section}.{step_id} field descriptions differ: "
                    f"{description_keys ^ data_keys}"
                )
