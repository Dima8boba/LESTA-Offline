# -- coding: utf-8 --
import functools
import pickle
import zlib
import cPickle
import BigWorld
import AccountCommands
import game
from collections import namedtuple
from gui.mods.offhangar.server import BASE_REQUESTS
from gui.mods.offhangar._constants import REQUEST_CALLBACK_TIME
from gui.mods.offhangar.logging import LOG_DEBUG
from gui.mods.offhangar.data import (
    getOfflineInventory,
    getOfflineStats,
    getOfflineQuestsProgress,
    getOfflineShop,
    getAppliedOutfitsCache,
    updateOutfitForVehicle,
    getVehicleIntCDByInvID,
    rebuildOfflineCachesFromSyncData,
)
from constants import CustomizationInvData
from gui.shared.gui_items import GUI_ITEM_TYPE
from items.components.c11n_constants import SeasonType
from gui.mods.offhangar.cache import (
    load_cache,
    save_cache,
    set_vehicle_overlay,
    merge_vehicle_overlay_dict,
    merge_vehicle_overlay_dict_top,
)
from helpers import dependency
from skeletons.gui.shared import IItemsCache
from post_progression_common import TankSetupLayouts
from gui.mods.offhangar.pdc import load_pdc, save_pdc
from items import vehicles as _items_vehicles
from items import vehicles
from items.customizations import parseOutfitDescr
try:
    from items.components.c11n_constants import CUSTOM_STYLE_POOL_ID
except Exception:
    CUSTOM_STYLE_POOL_ID = 0
RequestResult = namedtuple('RequestResult', ['resultID', 'errorStr', 'data'])

def _normalizeVehicleIntCD(value):
    if value is None:
        return None
    try:
        if isinstance(value, (int, long)):
            cd = int(value)
            try:
                nationID, vehicleTypeID = vehicles.parseVehicleCompactDescr(cd)
                return vehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
            except Exception:
                return cd
        if isinstance(value, basestring):
            try:
                nationID, vehicleTypeID = vehicles.parseVehicleCompactDescr(value)
                return vehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
            except Exception:
                pass
            try:
                return _normalizeVehicleIntCD(int(value))
            except Exception:
                try:
                    return _normalizeVehicleIntCD(long(value))
                except Exception:
                    return None
    except Exception:
        pass
    return value

def _outfitHasStyle(outfitDescr):
    if not outfitDescr:
        return False
    try:
        return bool(parseOutfitDescr(outfitDescr).styleId)
    except Exception:
        return False

def _expandCustomSeasons(season):
    try:
        season = int(season)
    except Exception:
        return [season]
    if season == SeasonType.ALL:
        try:
            return list(SeasonType.SEASONS)
        except Exception:
            return [season]
    try:
        result = [s for s in SeasonType.SEASONS if season & s]
        if result:
            return result
    except Exception:
        pass
    return [season]

def _invalidateOutfitCache(vehicleIntCD, seasons):
    itemsCache = _get_items_cache()
    if itemsCache is None:
        return
    try:
        inventory = itemsCache.items.inventory
        for season in set(list(seasons) + [SeasonType.ALL]):
            try:
                inventory.invalidateItem(GUI_ITEM_TYPE.OUTFIT, (vehicleIntCD, season))
            except Exception:
                pass
        try:
            outfitCache = getattr(inventory, '_InventoryRequester__itemsCache', None)
            if outfitCache is not None and GUI_ITEM_TYPE.OUTFIT in outfitCache:
                outfitCache[GUI_ITEM_TYPE.OUTFIT].clear()
        except Exception:
            pass
    except Exception:
        pass

def _buildOutfitPool(vehicleIntCD):
    pool = []
    try:
        seasons = getAppliedOutfitsCache().get(vehicleIntCD, {})
        styleId = 0
        hasAny = False
        for outfitDescr in seasons.itervalues():
            if outfitDescr:
                hasAny = True
            try:
                outfit = parseOutfitDescr(outfitDescr)
                if outfit.styleId:
                    styleId = outfit.styleId
                    break
            except Exception:
                continue
        if styleId:
            pool = [(styleId, '')]
        elif hasAny:
            pool = [(CUSTOM_STYLE_POOL_ID, '')]
    except Exception:
        pool = []
    return pool

def _refreshCurrentVehicleOutfits(vehInvID):
    try:
        itemsCache = _get_items_cache()
        if itemsCache is None:
            return
        from CurrentVehicle import g_currentVehicle
        veh = getattr(g_currentVehicle, 'item', None)
        if veh is not None and getattr(veh, 'invID', None) == vehInvID:
            veh.createAppliedOutfits(itemsCache.items)
    except Exception:
        pass

def _toVehicleIntCD(compactDescr):
    if compactDescr is None:
        return None
    if isinstance(compactDescr, (int, long)):
        return compactDescr
    try:
        descr = _items_vehicles.VehicleDescr(compactDescr=compactDescr)
        return _items_vehicles.makeIntCompactDescrByID('vehicle', *descr.type.id)
    except Exception:
        return None

def _get_items_cache():
    try:
        return dependency.instance(IItemsCache)
    except Exception:
        return None

def _get_vehicle_by_invID(vehInvID):
    vehTypeCD = getVehicleIntCDByInvID(vehInvID)
    if vehTypeCD is None:
        return None
    itemsCache = _get_items_cache()
    if itemsCache is None:
        return None
    return itemsCache.items.getItemByCD(vehTypeCD)

def _send_vehicle_diff(changes):
    player = BigWorld.player()
    if player is None:
        return
    rev = getattr(player.syncData, 'revision', 0)
    invDiff = {}
    for key, byVeh in changes.iteritems():
        invDiff[key] = byVeh
    diff = {
        'rev': rev,
        'prevRev': rev,
        'inventory': {GUI_ITEM_TYPE.VEHICLE: invDiff},
    }
    BigWorld.callback(0.1, functools.partial(player._update, True, diff))

def _apply_vehicle_changes(vehInvID, changes):
    for key, value in changes.iteritems():
        set_vehicle_overlay(vehInvID, key, value)
    diff = {key: {vehInvID: value} for key, value in changes.iteritems()}
    _send_vehicle_diff(diff)
    itemsCache = _get_items_cache()
    if itemsCache is not None:
        BigWorld.callback(0.3, functools.partial(
            itemsCache.items.inventory.invalidateItem, GUI_ITEM_TYPE.VEHICLE, vehInvID))

def _apply_vehicle_dict_change(vehInvID, key, subKey, value):
    current = merge_vehicle_overlay_dict(vehInvID, key, subKey, value)
    diff = {key: {vehInvID: current}}
    _send_vehicle_diff(diff)
    itemsCache = _get_items_cache()
    if itemsCache is not None:
        BigWorld.callback(0.3, functools.partial(
            itemsCache.items.inventory.invalidateItem, GUI_ITEM_TYPE.VEHICLE, vehInvID))
        
def baseRequest(cmdID):
    def wrapper(func):
        def requester(requestID, *args):
            result = func(requestID, *args)
            return (
                requestID,
                result.resultID,
                result.errorStr,
                result.data,
            )
        BASE_REQUESTS[cmdID] = requester
        return func
    return wrapper

def packStream(requestID, data):
    data = zlib.compress(pickle.dumps(data, protocol=2))
    desc = pickle.dumps((len(data), zlib.crc32(data)), protocol=2)
    return functools.partial(game.onStreamComplete, requestID, desc, data)

_COMPLETE_TUTORIAL_CMD = getattr(AccountCommands, 'CMD_COMPLETE_TUTORIAL', None)
if _COMPLETE_TUTORIAL_CMD is not None:
    @baseRequest(_COMPLETE_TUTORIAL_CMD)
    def completeTutorial(requestID, revision, dataLen, dataCrc):
        return RequestResult(AccountCommands.RES_SUCCESS, '', {})

def _resolveVehicleIntCD(vehInvID):
    vehicleIntCD = getVehicleIntCDByInvID(vehInvID)
    if vehicleIntCD is None:
        cached = load_pdc('sync_data')
        if cached is not None:
            rebuildOfflineCachesFromSyncData(cached)
            vehicleIntCD = getVehicleIntCDByInvID(vehInvID)
    return vehicleIntCD

def _saveAppliedOutfitsToPdc(vehicleIntCD):
    try:
        cached = load_pdc('sync_data')
        if cached is None:
            return
        inv = cached.setdefault('inventory', {})
        cust = inv.setdefault(GUI_ITEM_TYPE.CUSTOMIZATION, {})
        outfits = cust.setdefault(CustomizationInvData.OUTFITS, {})
        seasons = getAppliedOutfitsCache().get(vehicleIntCD, {})
        if seasons:
            outfits[vehicleIntCD] = dict(seasons)
        else:
            outfits.pop(vehicleIntCD, None)
        save_pdc('sync_data', cached)
    except Exception:
        pass

def _expandOutfitSeasons(outfitDescr, baseSeason):
    try:
        baseSeason = int(baseSeason)
    except Exception:
        baseSeason = SeasonType.ALL
    styleThis = False
    try:
        from items.customizations import parseOutfitDescr
        styleThis = bool(outfitDescr and parseOutfitDescr(outfitDescr).styleId)
    except Exception:
        styleThis = False
    if not outfitDescr and baseSeason == SeasonType.ALL:
        return [SeasonType.ALL] + list(SeasonType.SEASONS)
    if styleThis:
        if baseSeason == SeasonType.ALL:
            return [SeasonType.ALL]
        expanded = []
        try:
            for s in SeasonType.SEASONS:
                if baseSeason & s:
                    expanded.append(s)
        except Exception:
            expanded = []
        if not expanded:
            expanded = [baseSeason]
        if SeasonType.ALL not in expanded:
            expanded.append(SeasonType.ALL)
        return expanded
    if baseSeason == SeasonType.ALL:
        return list(SeasonType.SEASONS)
    expanded = []
    try:
        for s in SeasonType.SEASONS:
            if baseSeason & s:
                expanded.append(s)
    except Exception:
        expanded = []
    return expanded or [baseSeason]

def _buildOutfitPool(outfitsData):
    try:
        from items.components.c11n_constants import CUSTOM_STYLE_POOL_ID
    except Exception:
        CUSTOM_STYLE_POOL_ID = 0
    try:
        from items.customizations import parseOutfitDescr
    except Exception:
        return []
    styleId = 0
    hasAny = False
    for outfitDescr in outfitsData.itervalues():
        if outfitDescr:
            hasAny = True
        try:
            parsed = parseOutfitDescr(outfitDescr)
            if parsed.styleId:
                styleId = parsed.styleId
                break
        except Exception:
            pass
    if styleId:
        return [(styleId, '')]
    if hasAny:
        return [(CUSTOM_STYLE_POOL_ID, '')]
    return []

def _invalidateOutfitCache(vehicleIntCD, seasons):
    itemsCache = _get_items_cache()
    if itemsCache is None:
        return
    try:
        inventory = itemsCache.items.inventory
        for season in set(list(seasons) + [SeasonType.ALL]):
            try:
                inventory.invalidateItem(GUI_ITEM_TYPE.OUTFIT, (vehicleIntCD, season))
            except Exception:
                pass
        try:
            outfitCache = getattr(inventory, '_InventoryRequester__itemsCache', None)
            if outfitCache is not None and GUI_ITEM_TYPE.OUTFIT in outfitCache:
                outfitCache[GUI_ITEM_TYPE.OUTFIT].clear()
        except Exception:
            pass
    except Exception:
        pass

def _refreshCurrentVehicleOutfits(vehInvID):
    try:
        itemsCache = _get_items_cache()
        if itemsCache is None:
            return
        from CurrentVehicle import g_currentVehicle
        veh = getattr(g_currentVehicle, 'item', None)
        if veh is not None and getattr(veh, 'invID', None) == vehInvID:
            veh.createAppliedOutfits(itemsCache.items)
    except Exception:
        pass

from gui.mods.offhangar.utils import deepUpdate

@baseRequest(AccountCommands.CMD_SYNC_DATA)
def syncData(requestID, revision, crc, _):
    cached = load_pdc('sync_data')
    if cached is not None:
        rebuildOfflineCachesFromSyncData(cached)
        save_pdc('sync_data', cached)
        data = {'rev': revision + 1}
        data.update(cached)
        return RequestResult(AccountCommands.RES_SUCCESS, '', data)

    invChunk = getOfflineInventory()
    invData = invChunk.get('inventory', {}) if isinstance(invChunk, dict) else {}

    data = {'rev': revision + 1}
    data['inventory'] = invData

    for chunk in (getOfflineStats(), getOfflineQuestsProgress()):
        if chunk:
            deepUpdate(data, chunk)

    to_cache = {k: v for k, v in data.iteritems() if k != 'rev'}
    rebuildOfflineCachesFromSyncData(to_cache)
    save_pdc('sync_data', to_cache)

    return RequestResult(AccountCommands.RES_SUCCESS, '', data)

@baseRequest(AccountCommands.CMD_SYNC_SHOP)
def syncShop(requestID, revision, dataLen, dataCrc):
    cached = load_pdc('sync_shop')
    if cached is None:
        cached = getOfflineShop()
        save_pdc('sync_shop', cached)
    data = {
        'rev': revision + 1,
        'prevRev': revision,
    }
    data.update(cached)
    BigWorld.callback(REQUEST_CALLBACK_TIME, packStream(requestID, data))
    return RequestResult(AccountCommands.RES_STREAM, '', None)
@baseRequest(AccountCommands.CMD_SYNC_DOSSIERS)
def syncDossiers(requestID, revision, maxChangeTime, _):
    BigWorld.callback(
        REQUEST_CALLBACK_TIME,
        packStream(requestID, (revision + 1, []))
    )
    return RequestResult(AccountCommands.RES_STREAM, '', None)

@baseRequest(AccountCommands.CMD_VEH_APPLY_OUTFIT)
def vehApplyOutfit(requestID, intArr, strArr):
    try:
        if not intArr:
            return RequestResult(AccountCommands.RES_SUCCESS, '', None)

        if len(intArr) >= 2:
            vehInvID = intArr[1]
            seasons = list(intArr[2:])
        else:
            vehInvID = intArr[0]
            seasons = []

        vehicleIntCD = _resolveVehicleIntCD(vehInvID)
        if not vehicleIntCD:
            return RequestResult(AccountCommands.RES_SUCCESS, '', None)

        outfitDescrs = list(strArr or [])
        if not outfitDescrs:
            return RequestResult(AccountCommands.RES_SUCCESS, '', None)

        appliedSeasons = []

        for i, rawOutfitDescr in enumerate(outfitDescrs):
            outfitDescr = rawOutfitDescr if rawOutfitDescr is not None else ''
            baseSeason = seasons[i] if i < len(seasons) else (seasons[-1] if seasons else SeasonType.ALL)

            for season in _expandOutfitSeasons(outfitDescr, baseSeason):
                updateOutfitForVehicle(vehicleIntCD, season, outfitDescr)
                appliedSeasons.append(season)

        _saveAppliedOutfitsToPdc(vehicleIntCD)

        player = BigWorld.player()
        if player is not None:
            currentRev = getattr(player.syncData, 'revision', 0)
            outfitsData = getAppliedOutfitsCache().get(vehicleIntCD, {})

            diff = {
                'rev': currentRev,
                'prevRev': currentRev,
                'inventory': {
                    GUI_ITEM_TYPE.CUSTOMIZATION: {
                        CustomizationInvData.OUTFITS: {
                            vehicleIntCD: outfitsData
                        },
                        CustomizationInvData.OUTFITS_POOL: {
                            vehicleIntCD: _buildOutfitPool(outfitsData)
                        }
                    }
                }
            }
            BigWorld.callback(0.1, functools.partial(player._update, True, diff))

        BigWorld.callback(0.2, functools.partial(_invalidateOutfitCache, vehicleIntCD, appliedSeasons))
        BigWorld.callback(0.35, functools.partial(_refreshCurrentVehicleOutfits, vehInvID))
    except Exception:
        LOG_DEBUG('CMD_VEH_APPLY_OUTFIT error')

    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_BUY_C11N_ITEMS)
def buyC11nItems(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_SELL_C11N_ITEMS)
def sellC11nItems(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_RESET_C11N_ITEMS_NOVELTY)
def resetC11nNovelty(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_SET_ACTIVE_VEH_SEASON)
def setActiveVehSeason(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_BUY_PROGRESS_LVL_C11N_ITEMS)
def buyProgressLvlC11nItems(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_MARK_CUSTOMIZATION_ITEM)
def markCustomizationItem(requestID, *args):
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_EQUIP_SHELLS)
def equipShells(requestID, arr):
    if not arr:
        return RequestResult(AccountCommands.RES_SUCCESS, '', None)
    vehInvID = arr[0]
    shells = arr[1:]
    _apply_vehicle_changes(vehInvID, {'shells': shells})
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_EQUIP_EQS)
def equipEqs(requestID, arr):
    if not arr:
        return RequestResult(AccountCommands.RES_SUCCESS, '', None)
    vehInvID = arr[0]
    eqs = arr[1:]
    _apply_vehicle_changes(vehInvID, {'eqs': eqs})
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_SET_AND_FILL_LAYOUTS)
def setAndFillLayouts(requestID, arr):
    if len(arr) < 4:
        return RequestResult(AccountCommands.RES_SUCCESS, '', None)
    try:
        shopRev = arr[0]
        vehInvID = arr[1]
        idx = 2
        lenShells = arr[idx]; idx += 1
        shells = arr[idx:idx + lenShells]; idx += lenShells
        equipmentType = arr[idx]; idx += 1
        lenEqs = arr[idx]; idx += 1
        eqs = arr[idx:idx + lenEqs]
    except Exception:
        return RequestResult(AccountCommands.RES_SUCCESS, '', None)

    changes = {}
    if shells:
        changes['shells'] = shells
    if eqs:
        changes['eqs'] = eqs
    if changes:
        for key, value in changes.iteritems():
            set_vehicle_overlay(vehInvID, key, value)

    # Обновляем лаяуты
    veh = _get_vehicle_by_invID(vehInvID)
    if veh is not None:
        try:
            turretCD = veh.descriptor.turret.compactDescr
            gunCD = veh.descriptor.gun.compactDescr
            if shells:
                merge_vehicle_overlay_dict(vehInvID, TankSetupLayouts.SHELLS, (turretCD, gunCD), [shells])
            if eqs:
                merge_vehicle_overlay_dict(vehInvID, TankSetupLayouts.EQUIPMENT, (turretCD, gunCD), [eqs])
        except Exception:
            pass

    diff = {key: {vehInvID: value} for key, value in changes.iteritems()}
    _send_vehicle_diff(diff)
    itemsCache = _get_items_cache()
    if itemsCache is not None:
        BigWorld.callback(0.3, functools.partial(
            itemsCache.items.inventory.invalidateItem, GUI_ITEM_TYPE.VEHICLE, vehInvID))
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_EQUIP_OPTDEV)
def equipOptDev(requestID, arr):
    # arr = [shopRev, vehInvID, deviceCompDescr, slotIdx, layoutIdx, isAllSetups, isPaidRemoval, useDemountKit]
    if len(arr) < 5:
        return RequestResult(AccountCommands.RES_SUCCESS, '', None)
    try:
        shopRev, vehInvID, deviceCD, slotIdx, layoutIdx = arr[0], arr[1], arr[2], arr[3], arr[4]
    except Exception:
        return RequestResult(AccountCommands.RES_SUCCESS, '', None)

    veh = _get_vehicle_by_invID(vehInvID)
    if veh is None:
        return RequestResult(AccountCommands.RES_SUCCESS, '', None)

    try:
        setups = veh.optDevices.setupLayouts
        capacity = veh.optDevices.layoutCapacity
        layouts = []
        for idx in range(setups.capacity):
            setup = setups.setupByIndex(idx)
            if setup is None:
                layouts.append([0] * capacity)
            else:
                storage = list(setup.getStorage)
                storage = [(x if x else 0) for x in storage]
                if len(storage) < capacity:
                    storage += [0] * (capacity - len(storage))
                layouts.append(storage)
        if 0 <= layoutIdx < len(layouts) and 0 <= slotIdx < capacity:
            layouts[layoutIdx][slotIdx] = deviceCD
        _apply_vehicle_changes(vehInvID, {TankSetupLayouts.OPTIONAL_DEVICES: layouts})
    except Exception:
        pass
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)

@baseRequest(AccountCommands.CMD_SWITCH_LAYOUT)
def switchLayout(requestID, vehInvID, groupID, layoutIdx):
    try:
        current = merge_vehicle_overlay_dict_top(vehInvID, 'layoutIndexes', {groupID: layoutIdx})
        diff = {'layoutIndexes': {vehInvID: current}}
        _send_vehicle_diff(diff)
        itemsCache = _get_items_cache()
        if itemsCache is not None:
            BigWorld.callback(0.3, functools.partial(
                itemsCache.items.inventory.invalidateItem, GUI_ITEM_TYPE.VEHICLE, vehInvID))
    except Exception:
        pass
    return RequestResult(AccountCommands.RES_SUCCESS, '', None)