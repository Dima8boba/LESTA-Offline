import os
import shutil
import cPickle
from debug_utils import LOG_CURRENT_EXCEPTION
from gui.mods.offhangar.logging import LOG_DEBUG

_CACHE_DIR_NAME = os.path.join('cache', 'wgpdc')
_CACHE_FILE_NAME = 'offhangar_overlay.pkl'
_LEGACY_FILES = (
    os.path.join('cache', 'offhangar_inventory.pkl'),
)
_LEGACY_DIRS = (
    os.path.join('cache', 'pdc'),
)

_cache = None
_cache_path = None

def _get_cache_path():
    global _cache_path
    if _cache_path is None:
        try:
            root = os.getcwd()
            _cache_path = os.path.join(root, _CACHE_DIR_NAME, _CACHE_FILE_NAME)
        except Exception:
            LOG_CURRENT_EXCEPTION()
            _cache_path = _CACHE_FILE_NAME
    return _cache_path

def _cleanup_legacy():
    root = os.getcwd()
    for rel in _LEGACY_FILES:
        path = os.path.join(root, rel)
        try:
            if os.path.isfile(path):
                os.remove(path)
                LOG_DEBUG('wgpdc: removed legacy cache file %s' % path)
        except Exception:
            LOG_CURRENT_EXCEPTION()
    for rel in _LEGACY_DIRS:
        path = os.path.join(root, rel)
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                LOG_DEBUG('wgpdc: removed legacy cache dir %s' % path)
        except Exception:
            LOG_CURRENT_EXCEPTION()

_cleanup_legacy()

def get_overlay_path():
    return _get_cache_path()

def load_cache():
    global _cache
    if _cache is not None:
        return _cache
    path = _get_cache_path()
    try:
        with open(path, 'rb') as f:
            _cache = cPickle.load(f)
    except Exception:
        _cache = {'vehicles': {}}
    return _cache

def save_cache():
    if _cache is None:
        return
    path = _get_cache_path()
    try:
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(path, 'wb') as f:
            cPickle.dump(_cache, f, -1)
    except Exception:
        LOG_CURRENT_EXCEPTION()

def get_vehicle_overlay(vehInvID):
    return load_cache().get('vehicles', {}).get(vehInvID, {})

def set_vehicle_overlay(vehInvID, key, value):
    cache = load_cache()
    vehCache = cache.setdefault('vehicles', {})
    overlay = vehCache.setdefault(vehInvID, {})
    overlay[key] = value
    save_cache()

def merge_vehicle_overlay_dict(vehInvID, key, subKey, value):
    cache = load_cache()
    vehCache = cache.setdefault('vehicles', {})
    overlay = vehCache.setdefault(vehInvID, {})
    current = overlay.get(key, {})
    if not isinstance(current, dict):
        current = {}
    current[subKey] = value
    overlay[key] = current
    save_cache()
    return current

def merge_vehicle_overlay_dict_top(vehInvID, key, value):
    cache = load_cache()
    vehCache = cache.setdefault('vehicles', {})
    overlay = vehCache.setdefault(vehInvID, {})
    current = overlay.get(key, {})
    if not isinstance(current, dict):
        current = {}
    current.update(value)
    overlay[key] = current
    save_cache()
    return current