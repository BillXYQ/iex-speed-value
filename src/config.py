"""Single source of truth for file paths.

Resolution order for each key:
  1. Environment variable (IEX_SPEED_RAW_DATA for raw_data_dir)
  2. config/config.local.yaml (gitignored, per machine)
  3. config/config.example.yaml (committed defaults)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
ENV_OVERRIDES = {"raw_data_dir": "IEX_SPEED_RAW_DATA"}


@lru_cache(maxsize=1)
def load_config() -> dict:
    cfg: dict = {}
    for name in ("config.example.yaml", "config.local.yaml"):
        path = CONFIG_DIR / name
        if path.exists():
            cfg.update(yaml.safe_load(path.read_text()) or {})
    for key, env in ENV_OVERRIDES.items():
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


def _path(key: str) -> Path:
    p = Path(load_config()[key]).expanduser()
    return p if p.is_absolute() else REPO_ROOT / p


def raw_data_dir() -> Path:
    return _path("raw_data_dir")


def sample_data_dir() -> Path:
    return _path("sample_data_dir")


def parsed_data_dir() -> Path:
    return _path("parsed_data_dir")


def results_dir() -> Path:
    return _path("results_dir")
