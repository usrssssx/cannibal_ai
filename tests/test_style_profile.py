from cannibal_core.style_profile import (
    StyleProfileCache,
    build_style_profile,
    format_style_profile,
)


def test_build_style_profile_basic() -> None:
    texts = [
        "Факт: Рынок вырос. Апдейт: импульс слабый.",
        "Рынок вырос. Дальше рост.",
    ]
    profile = build_style_profile(texts)

    assert profile["sample_size"] == 2
    assert profile["avg_chars"] > 0
    assert profile["tempo"] in {"short", "medium", "long"}
    assert profile["colon_ratio"] == 0.5
    assert "Факт" in profile["top_labels"]


def test_format_style_profile() -> None:
    profile = build_style_profile(
        ["Факт: Рост.", "Апдейт: Рынок стабилен. Еще один апдейт."]
    )
    formatted = format_style_profile(profile)
    assert formatted
    assert "Sample size" in formatted


def test_style_profile_cache() -> None:
    cache = StyleProfileCache({123: "profile-id"}, {"channel": "profile-name"})
    assert cache.get(123, "channel") == "profile-id"
    assert cache.get(None, "channel") == "profile-name"
    assert cache.get(999, "missing") is None
