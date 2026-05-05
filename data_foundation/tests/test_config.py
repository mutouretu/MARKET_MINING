from pathlib import Path

from market_mining.config import load_config
from market_mining.utils.math import clip, pct_change, safe_divide


def test_load_default_config() -> None:
    config = load_config(Path("data_foundation/configs/default.yaml"))

    assert config.project["name"] == "market_mining"
    assert config.database["url"] == "sqlite:///market_mining.db"


def test_math_helpers() -> None:
    assert safe_divide(10, 2) == 5.0
    assert safe_divide(10, 0) is None
    assert pct_change(110, 100) == 0.1
    assert pct_change(110, 0) is None
    assert clip(12, 0, 10) == 10.0
    assert clip(-2, 0, 10) == 0.0
