import os
import json
import time
import fcntl
import law
from threading import Lock
from law.util import no_value

law.contrib.load("wlcg")
CACHE_PATH = f'{os.getenv("LAW_HOME")}/target_exists_cache.json'
DIR_CACHE_PATH = f'{os.getenv("LAW_HOME")}/wlcg_dir_cache.json'

CACHE_LOCK = Lock()

_TARGET_CACHE = {}
_DIR_CACHE = {}

# Track mtime to dynamically reload if another process updated the file
_TARGET_CACHE_MTIME = 0
_DIR_CACHE_MTIME = 0


def _load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json_atomic(path, data):
    # Appending pid prevents multiple workers colliding on the exact same temp file
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


def _update_json_cache_locked(cache_path, key, value_dict):
    lock_path = cache_path + ".lock"

    # Use 'a' (append) to avoid truncating if another process is reading
    with open(lock_path, "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            cache = _load_json(cache_path)
            cache[key] = value_dict
            _save_json_atomic(cache_path, cache)
            return cache
        finally:
            # We release the lock, but leave the file to avoid race conditions
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


def _ensure_dir_cache_loaded():
    global _DIR_CACHE, _DIR_CACHE_MTIME
    try:
        mtime = os.path.getmtime(DIR_CACHE_PATH)
    except OSError:
        mtime = 0

    if not _DIR_CACHE or mtime > _DIR_CACHE_MTIME:
        _DIR_CACHE = _load_json(DIR_CACHE_PATH)
        _DIR_CACHE_MTIME = mtime


def cached_listdir(fs, path, ttl=3600):
    global _DIR_CACHE, _DIR_CACHE_MTIME
    key = f"{fs.name}:{path}"

    with CACHE_LOCK:
        _ensure_dir_cache_loaded()
        entry = _DIR_CACHE.get(key)

        if entry and (ttl is None or time.time() - entry["ts"] < ttl):
            return entry["files"]

    # expensive call outside lock
    files = fs.listdir(path)

    _DIR_CACHE = _update_json_cache_locked(
        DIR_CACHE_PATH,
        key,
        {
            "ts": time.time(),
            "files": files,
        },
    )

    try:
        _DIR_CACHE_MTIME = os.path.getmtime(DIR_CACHE_PATH)
    except OSError:
        pass

    return files


def cache_get_exists(key, ttl):
    entry = _TARGET_CACHE.get(key)
    if not entry:
        return False

    return ttl is None or (time.time() - entry["ts"] < ttl)


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

        # expensive remote check outside lock
        exists = super().exists()

        if exists:
            global _TARGET_CACHE, _TARGET_CACHE_MTIME
            _TARGET_CACHE = _update_json_cache_locked(
                CACHE_PATH, key, {"ts": time.time()}
            )
            try:
                _TARGET_CACHE_MTIME = os.path.getmtime(CACHE_PATH)
            except OSError:
                pass

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

        # If not in cache, perform the actual grid stat
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
        if basenames is None:
            dir_exists = False
            dir_key = self.dir.uri() if hasattr(self.dir, "uri") else str(self.dir.path)

            # 1. Check the cache first
            with CACHE_LOCK:
                _ensure_target_cache_loaded()
                dir_exists = cache_get_exists(dir_key, self.cache_ttl)

            # 2. Only if the cache is empty/expired, do we hit the grid
            if not dir_exists:
                dir_exists = self.dir.exists()
                if dir_exists:
                    # Update the cache so other PIDs see this directory exists
                    _update_json_cache_locked(CACHE_PATH, dir_key, {"ts": time.time()})

            # 3. Proceed with listdir (which is also cached)
            if dir_exists:
                basenames = cached_listdir(self.dir.fs, self.dir.path, self.cache_ttl)
            else:
                basenames = []

        return super()._iter_state(
            existing=existing,
            optional_existing=optional_existing,
            basenames=basenames,
            keys=keys,
            unpack=unpack,
            exists_func=exists_func,
        )

    def _exists_in_basenames(self, target, basenames, optional_existing, target_dirs):
        key = target.uri() if hasattr(target, "uri") else str(target.path)

        with CACHE_LOCK:
            _ensure_target_cache_loaded()
            if cache_get_exists(key, self.cache_ttl):
                return True

        name = os.path.basename(target.path)
        exists = name in basenames

        if exists:
            global _TARGET_CACHE, _TARGET_CACHE_MTIME
            _TARGET_CACHE = _update_json_cache_locked(
                CACHE_PATH, key, {"ts": time.time()}
            )
            try:
                _TARGET_CACHE_MTIME = os.path.getmtime(CACHE_PATH)
            except OSError:
                pass

        return exists


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
        if basenames is None:
            from law.util import flatten

            # 1. Safely collect all unique parent directory targets
            all_targets = flatten(self.targets.values())
            unique_dirs = {t.parent for t in all_targets if hasattr(t, "parent")}

            basenames = {}
            for d in unique_dirs:
                dir_key = d.uri() if hasattr(d, "uri") else str(d.path)

                # 2. Check the JSON existence cache
                with CACHE_LOCK:
                    _ensure_target_cache_loaded()
                    dir_exists = cache_get_exists(dir_key, self.cache_ttl)

                # 3. Grid fallback if not in cache
                if not dir_exists:
                    dir_exists = d.exists()
                    if dir_exists:
                        _update_json_cache_locked(
                            CACHE_PATH, dir_key, {"ts": time.time()}
                        )

                # 4. Populate basenames for this directory
                if dir_exists:
                    # Use your cached_listdir to avoid kXR_dirlist
                    basenames[dir_key] = set(
                        cached_listdir(d.fs, d.path, self.cache_ttl)
                    )
                else:
                    basenames[dir_key] = set()

        # Pass the populated basenames mapping to the parent class logic
        return super()._iter_state(
            existing=existing,
            optional_existing=optional_existing,
            basenames=basenames,
            keys=keys,
            unpack=unpack,
            exists_func=exists_func,
        )

    def _exists_in_basenames(self, target, basenames, optional_existing, target_dirs):
        key = target.uri() if hasattr(target, "uri") else str(target.path)

        with CACHE_LOCK:
            _ensure_target_cache_loaded()
            if cache_get_exists(key, self.cache_ttl):
                return True

        dir_key = target_dirs.get(target)
        if dir_key is None:
            return False

        exists = os.path.basename(target.path) in basenames.get(dir_key, set())

        if exists:
            global _TARGET_CACHE, _TARGET_CACHE_MTIME
            _TARGET_CACHE = _update_json_cache_locked(
                CACHE_PATH, key, {"ts": time.time()}
            )
            try:
                _TARGET_CACHE_MTIME = os.path.getmtime(CACHE_PATH)
            except OSError:
                pass

        return exists
