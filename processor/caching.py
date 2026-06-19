import os
import json
import time
import fcntl
import law
import hashlib
from threading import Lock
from law.util import no_value
from law.logger import get_logger

logger = get_logger("custom.caching")

law.contrib.load("wlcg")

# We now only need the target existence cache.
# The directory cache is removed to prevent "partial state" blindness.
CACHE_PATH = f'{os.getenv("LAW_HOME", "/tmp")}/target_exists_cache.json'

CACHE_LOCK = Lock()

_TARGET_CACHE = {}
_TARGET_CACHE_MTIME = 0


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json_atomic(path, data):
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _update_json_cache_locked(cache_path, key, value_dict):
    cache_dir = os.path.dirname(cache_path)
    if cache_dir and not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    lock_path = cache_path + ".lock"

    with open(lock_path, "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            cache = _load_json(cache_path)
            cache[key] = value_dict
            _save_json_atomic(cache_path, cache)
            return cache
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _ensure_target_cache_loaded():
    global _TARGET_CACHE, _TARGET_CACHE_MTIME
    try:
        mtime = os.path.getmtime(CACHE_PATH)
    except OSError:
        mtime = 0

    if not _TARGET_CACHE or mtime > _TARGET_CACHE_MTIME:
        _TARGET_CACHE = _load_json(CACHE_PATH)
        _TARGET_CACHE_MTIME = mtime


def cache_get_exists(key, ttl):
    entry = _TARGET_CACHE.get(key)
    if not entry:
        return False

    hit = ttl is None or (time.time() - entry["ts"] < ttl)
    if hit:
        logger.debug(f"Cache hit for key: {key}")
    return hit


def _get_collection_key(targets):
    """
    Generates a unique SHA-256 hash for a specific set of targets.
    This keeps different collections pointing to the same dir completely separated.
    """
    paths = []
    # Handle both list/tuple of targets and dict of targets
    all_targets = flatten(targets.values() if isinstance(targets, dict) else targets)

    for t in all_targets:
        paths.append(t.uri() if hasattr(t, "uri") else str(t.path))

    paths.sort()
    hash_str = hashlib.sha256(json.dumps(paths).encode("utf-8")).hexdigest()
    return f"collection_{hash_str}"


class CachedWLCGFileTarget(law.wlcg.WLCGFileTarget):
    cache_ttl = 86400

    def _cache_key(self):
        return self.uri() if hasattr(self, "uri") else str(self.path)

    def exists(self):
        key = self._cache_key()

        with CACHE_LOCK:
            _ensure_target_cache_loaded()
            if cache_get_exists(key, self.cache_ttl):
                return True

        exists = super().exists()
        if exists:
            global _TARGET_CACHE
            _TARGET_CACHE = _update_json_cache_locked(
                CACHE_PATH, key, {"ts": time.time()}
            )
        return exists


class CachedWLCGDirectoryTarget(law.wlcg.WLCGDirectoryTarget):
    cache_ttl = 86400

    def _cache_key(self):
        return self.uri() if hasattr(self, "uri") else str(self.path)

    def exists(self):
        key = self._cache_key()
        with CACHE_LOCK:
            _ensure_target_cache_loaded()
            if cache_get_exists(key, self.cache_ttl):
                return True

        exists = super().exists()
        if exists:
            global _TARGET_CACHE
            _TARGET_CACHE = _update_json_cache_locked(
                CACHE_PATH, key, {"ts": time.time()}
            )
        return exists


class CachedSiblingFileCollection(law.target.collection.SiblingFileCollection):
    cache_ttl = 86400

    def _iter_state(
        self,
        existing=True,
        optional_existing=no_value,
        basenames=None,
        keys=False,
        unpack=True,
        exists_func=None,
    ):
        collection_key = _get_collection_key(self.targets)
        all_targets = flatten(
            self.targets.values() if isinstance(self.targets, dict) else self.targets
        )

        # 1. Check if the entire collection is cached as complete
        with CACHE_LOCK:
            _ensure_target_cache_loaded()
            is_cached = cache_get_exists(collection_key, self.cache_ttl)

        if is_cached:
            # Mock the basenames list so the parent class bypasses the grid check automatically
            basenames = {os.path.basename(t.path) for t in all_targets}
            return super()._iter_state(
                existing, optional_existing, basenames, keys, unpack, exists_func
            )

        # 2. If not cached (or incomplete), fetch live directory contents
        if basenames is None:
            if self.dir.exists():
                basenames = set(self.dir.listdir())
            else:
                basenames = set()

        # 3. Check if ALL items are present
        all_present = all(os.path.basename(t.path) in basenames for t in all_targets)

        # 4. Only cache if 100% complete
        if all_present and all_targets:
            with CACHE_LOCK:
                global _TARGET_CACHE
                _TARGET_CACHE = _update_json_cache_locked(
                    CACHE_PATH, collection_key, {"ts": time.time()}
                )

        return super()._iter_state(
            existing, optional_existing, basenames, keys, unpack, exists_func
        )


class CachedNestedSiblingFileCollection(
    law.target.collection.NestedSiblingFileCollection
):
    cache_ttl = 86400

    def _iter_state(
        self,
        existing=True,
        optional_existing=no_value,
        basenames=None,
        keys=False,
        unpack=True,
        exists_func=None,
    ):
        collection_key = _get_collection_key(self.targets)
        all_targets = flatten(
            self.targets.values() if isinstance(self.targets, dict) else self.targets
        )

        # 1. Check if the entire collection is cached as complete
        with CACHE_LOCK:
            _ensure_target_cache_loaded()
            is_cached = cache_get_exists(collection_key, self.cache_ttl)

        if is_cached:
            # Mock the basenames dict mapping {dir_key: set(files)}
            basenames = {}
            for t in all_targets:
                dir_key = (
                    t.parent.uri() if hasattr(t.parent, "uri") else str(t.parent.path)
                )
                basenames.setdefault(dir_key, set()).add(os.path.basename(t.path))
            return super()._iter_state(
                existing, optional_existing, basenames, keys, unpack, exists_func
            )

        # 2. If not cached, fetch live directory contents for all unique directories
        if basenames is None:
            unique_dirs = {t.parent for t in all_targets if hasattr(t, "parent")}
            basenames = {}
            for d in unique_dirs:
                dir_key = d.uri() if hasattr(d, "uri") else str(d.path)
                if d.exists():
                    basenames[dir_key] = set(d.listdir())
                else:
                    basenames[dir_key] = set()

        # 3. Check if ALL items are present across all nested directories
        all_present = True
        for t in all_targets:
            dir_key = t.parent.uri() if hasattr(t.parent, "uri") else str(t.parent.path)
            if os.path.basename(t.path) not in basenames.get(dir_key, set()):
                all_present = False
                break

        # 4. Only cache if 100% complete
        if all_present and all_targets:
            with CACHE_LOCK:
                global _TARGET_CACHE
                _TARGET_CACHE = _update_json_cache_locked(
                    CACHE_PATH, collection_key, {"ts": time.time()}
                )

        return super()._iter_state(
            existing, optional_existing, basenames, keys, unpack, exists_func
        )
