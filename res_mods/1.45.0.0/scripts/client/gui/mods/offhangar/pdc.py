import os
import cPickle
import zlib
import constants
from debug_utils import LOG_CURRENT_EXCEPTION
from gui.mods.offhangar.logging import LOG_DEBUG
from gui.mods.offhangar.cache import get_overlay_path

_CACHE_DIR = os.path.join(os.getcwd(), 'cache', 'wgpdc')
_CLIENT_VERSION = getattr(constants, 'CLIENT_VERSION', 'unknown')

_memory = {}

def _get_cache_path(key):
    return os.path.join(_CACHE_DIR, '{}_{}.dat'.format(key, _CLIENT_VERSION))

def _sanitize_sync_data(data):
    try:
        from gui.shared.gui_items import GUI_ITEM_TYPE
        from constants import CustomizationInvData
        from items import vehicles, parseIntCompactDescr, makeIntCompactDescrByID
        inv = data.get('inventory', {})
        cust = inv.get(GUI_ITEM_TYPE.CUSTOMIZATION)
        if isinstance(cust, dict):
            outfits = cust.get(CustomizationInvData.OUTFITS)
            if isinstance(outfits, dict):
                fixed = {}
                for key, value in outfits.iteritems():
                    intCD = None
                    if isinstance(key, (int, long)):
                        try:
                            nationID, vehicleTypeID = vehicles.parseVehicleCompactDescr(key)
                            intCD = makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
                        except Exception:
                            try:
                                itemTypeID, nationID, itemID = parseIntCompactDescr(key)
                                if itemTypeID == GUI_ITEM_TYPE.VEHICLE:
                                    intCD = makeIntCompactDescrByID('vehicle', nationID, itemID)
                                else:
                                    intCD = int(key)
                            except Exception:
                                intCD = None
                    elif isinstance(key, basestring):
                        try:
                            nationID, vehicleTypeID = vehicles.parseVehicleCompactDescr(key)
                            intCD = makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
                        except Exception:
                            try:
                                intCD = int(key)
                            except Exception:
                                intCD = None
                    if intCD:
                        fixed[intCD] = value
                cust[CustomizationInvData.OUTFITS] = fixed
    except Exception:
        LOG_CURRENT_EXCEPTION()
    return data

def load_pdc(key):
    if key in _memory:
        return _memory[key]
    path = _get_cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        if key == 'sync_data':
            overlay = get_overlay_path()
            if os.path.exists(overlay) and os.path.getmtime(overlay) > os.path.getmtime(path):
                LOG_DEBUG('wgpdc: overlay newer than %s, regenerating' % key)
                return None
        with open(path, 'rb') as f:
            compressed = f.read()
        data = cPickle.loads(zlib.decompress(compressed))
        if key == 'sync_data':
            data = _sanitize_sync_data(data)
        _memory[key] = data
        LOG_DEBUG('wgpdc: loaded %s, %d bytes' % (key, len(compressed)))
        return data
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return None

def save_pdc(key, data):
    _memory[key] = data
    try:
        if not os.path.isdir(_CACHE_DIR):
            os.makedirs(_CACHE_DIR)
        compressed = zlib.compress(cPickle.dumps(data, -1), 6)
        with open(_get_cache_path(key), 'wb') as f:
            f.write(compressed)
        LOG_DEBUG('wgpdc: saved %s, %d bytes' % (key, len(compressed)))
    except Exception:
        LOG_CURRENT_EXCEPTION()