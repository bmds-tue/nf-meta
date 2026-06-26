import hashlib
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_ENV_VAR = "NF_META_CACHE_DIR"
GLOBAL_CACHE_DIR: Path = Path(
    os.environ.get(_ENV_VAR) or Path.home() / ".cache" / "nf-meta"
)


def schema_cache_path(url: str, version: str) -> Path:
    key = hashlib.sha256(f"{url}@{version}".encode()).hexdigest()[:16]
    return GLOBAL_CACHE_DIR / "schemas" / f"{key}.json"


def read_schema_cache(url: str, version: str) -> dict | None:
    path = schema_cache_path(url, version)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to read schema cache at %s: %s", path, e)
        return None


def write_schema_cache(url: str, version: str, schema: dict) -> None:
    path = schema_cache_path(url, version)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(schema, f)
    except Exception as e:
        logger.warning("Failed to write schema cache to %s: %s", path, e)
