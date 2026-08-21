import os
import json
import time
import fcntl
import atexit
import law
import hashlib
from threading import Lock
from law.util import no_value, flatten
from law.logger import get_logger

logger = get_logger("custom.caching")

law.contrib.load("wlcg")

CACHE_PATH = f'{os.getenv("LAW_HOME", "/tmp")}/target_exists_cache.json'

CACHE_LOCK = Lock()

_TARGET_CACHE = {}
_TARGET_CACHE_MTIME = 0

MAX_CACHE_ENTRY_AGE = 7 * 86400
FLUSH_BATCH_SIZE = 25
FLUSH_INTERVAL = 5.0

_PENDING_UPDATES = {}
_PENDING_LOCK = Lock()
_LAST_FLUSH_TIME = 0


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


def _prune_expired_entries(cache, cutoff_time):
    expired_keys = [k for k, v in cache.items() if v.get("ts", 0) < cutoff_time]
    for k in expired_keys:
        del cache[k]
    return cache


def _flush_pending_locked():
    global _LAST_FLUSH_TIME, _TARGET_CACHE

    with _PENDING_LOCK:
        if not _PENDING_UPDATES:
            return
        pending_copy = dict(_PENDING_UPDATES)
        _PENDING_UPDATES.clear()

    cache_dir = os.path.dirname(CACHE_PATH)
    if cache_dir and not os.path.exists(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    lock_path = CACHE_PATH + ".lock"
    with open(lock_path, "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            cache = _load_json(CACHE_PATH)
            cache.update(pending_copy)
            cutoff = time.time() - MAX_CACHE_ENTRY_AGE
            cache = _prune_expired_entries(cache, cutoff)
            _save_json_atomic(CACHE_PATH, cache)
            _TARGET_CACHE = cache
            _LAST_FLUSH_TIME = time.time()
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _queue_cache_update(key, value_dict):
    global _TARGET_CACHE, _LAST_FLUSH_TIME

    with _PENDING_LOCK:
        _PENDING_UPDATES[key] = value_dict
        _TARGET_CACHE[key] = value_dict
        should_flush = (
            len(_PENDING_UPDATES) >= FLUSH_BATCH_SIZE
            or (time.time() - _LAST_FLUSH_TIME) >= FLUSH_INTERVAL
        )

    if should_flush:
        with CACHE_LOCK:
            _flush_pending_locked()


def _atexit_flush():
    with CACHE_LOCK:
        _flush_pending_locked()


atexit.register(_atexit_flush)


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
            _queue_cache_update(key, {"ts": time.time()})
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
            _queue_cache_update(key, {"ts": time.time()})
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
            _queue_cache_update(collection_key, {"ts": time.time()})

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
            _queue_cache_update(collection_key, {"ts": time.time()})

        return super()._iter_state(
            existing, optional_existing, basenames, keys, unpack, exists_func
        )
