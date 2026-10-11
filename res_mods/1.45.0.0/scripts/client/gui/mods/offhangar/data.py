# -- coding: utf-8 --
import nations
import items
from constants import ACCOUNT_ATTR
from items import vehicles, tankmen, makeIntCompactDescrByID
from items.vehicles import g_list, g_cache
from constants import SkinInvData, CustomizationInvData
from items.components.c11n_constants import CustomizationType, EMPTY_ITEM_ID, UNBOUND_VEH_KEY
from gui.shared.gui_items import GUI_ITEM_TYPE
from gui.shared.gui_items.Vehicle import Vehicle
from gui.shared.money import Currency
from skeletons.gui.shared import IItemsCache
from post_progression_common import TankSetupLayouts
from helpers import dependency
from gui.mods.offhangar.logging import LOG_DEBUG
from gui.mods.offhangar.utils import *
from gui.mods.offhangar._constants import *
from gui.mods.offhangar.cache import load_cache
_invID_to_intCD = {}

def _normalizeVehicleIntCD(value):
    if isinstance(value, (int, long)):
        try:
            nationID, vehicleTypeID = vehicles.parseVehicleCompactDescr(value)
            return vehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
        except Exception:
            pass
        try:
            itemTypeID, nationID, itemID = items.parseIntCompactDescr(value)
            if itemTypeID == GUI_ITEM_TYPE.VEHICLE:
                return vehicles.makeIntCompactDescrByID('vehicle', nationID, itemID)
            return int(value)
        except Exception:
            return 0
    if isinstance(value, basestring):
        try:
            nationID, vehicleTypeID = vehicles.parseVehicleCompactDescr(value)
            return vehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
        except Exception:
            pass
        try:
            return int(value)
        except Exception:
            return 0
    try:
        return int(value)
    except Exception:
        return 0

def normalizeVehicleIntCD(value):
    return _normalizeVehicleIntCD(value)

def _toVehicleIntCD(value):
    if isinstance(value, (int, long)):
        try:
            nationID, vehicleTypeID = vehicles.parseVehicleCompactDescr(value)
            return vehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
        except Exception:
            return value
    return value
from post_progression_common import TankSetupLayouts
def getVehicleIntCDByInvID(invID):
    value = _invID_to_intCD.get(invID)
    if value is None:
        return None
    return _normalizeVehicleIntCD(value)
_vehicleShellsByInvID = {}
_applied_outfits_cache = {}
_offlineInventoryCache = None 

def rebuildOfflineCachesFromSyncData(syncData):
    try:
        if not isinstance(syncData, dict):
            return
        inv = syncData.get('inventory')
        if not isinstance(inv, dict):
            inv = {}
        vehData = inv.get(GUI_ITEM_TYPE.VEHICLE)
        if not isinstance(vehData, dict):
            vehData = {}
        compDescr = vehData.get('compDescr')
        if not isinstance(compDescr, dict):
            compDescr = {}
        _invID_to_intCD.clear()
        for invID, cd in compDescr.iteritems():
            intCD = _normalizeVehicleIntCD(cd)
            if intCD:
                _invID_to_intCD[invID] = intCD
        cust = inv.get(GUI_ITEM_TYPE.CUSTOMIZATION)
        if not isinstance(cust, dict):
            cust = {}
        outfits = cust.get(CustomizationInvData.OUTFITS)
        if not isinstance(outfits, dict):
            outfits = {}
        fixedOutfits = {}
        _applied_outfits_cache.clear()
        for key, seasons in outfits.iteritems():
            vehIntCD = _normalizeVehicleIntCD(key)
            if not vehIntCD or not isinstance(seasons, dict):
                continue
            fixedSeasons = {}
            for season, outfitDescr in seasons.iteritems():
                try:
                    seasonKey = int(season)
                except Exception:
                    seasonKey = season
                fixedSeasons[seasonKey] = outfitDescr
            fixedOutfits[vehIntCD] = fixedSeasons
            _applied_outfits_cache[vehIntCD] = dict(fixedSeasons)
        cust[CustomizationInvData.OUTFITS] = fixedOutfits
        inv[GUI_ITEM_TYPE.CUSTOMIZATION] = cust
        syncData['inventory'] = inv
    except Exception:
        LOG_CURRENT_EXCEPTION()

def getOfflineVehicleShellsByInvID(invID):
    return list(_vehicleShellsByInvID.get(invID, []))

def getAppliedOutfitsCache():
    """Возвращает текущее состояние кэша применённых outfit'ов."""
    return _applied_outfits_cache

def updateOutfitForVehicle(vehicleIntCD, season, outfitDescr):
    vehicleIntCD = _normalizeVehicleIntCD(vehicleIntCD)
    if not vehicleIntCD:
        return
    if vehicleIntCD not in _applied_outfits_cache:
        _applied_outfits_cache[vehicleIntCD] = {}
    _applied_outfits_cache[vehicleIntCD][season] = outfitDescr

def _g(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key)

def _generateCrewForVehicle(nationID, vehicleTypeID, vType):
    roles = vType.crewRoles
    return tankmen.generateTankmen(nationID, vehicleTypeID, roles, False, tankmen.MAX_SKILL_LEVEL, tankmen.ALL_SKILLS_MASK)

def outfitDescrToInt(value):
    if isinstance(value, (int, long)):
        return int(value)
    if isinstance(value, basestring):
        try:
            from items.customization import outfits
            return int(outfits.makeIntCompactDescr(value))
        except Exception:
            pass
        try:
            import struct
            raw = value[:8]
            if len(raw) < 8:
                raw = raw + '\x00' * (8 - len(raw))
            return int(struct.unpack('<Q', raw)[0])
        except Exception:
            pass
    return 0

def sanitizeOutfitsData(outfitsData):
    result = {}
    for vehIntCD, seasons in (outfitsData or {}).iteritems():
        if not isinstance(seasons, dict):
            continue
        result[vehIntCD] = dict((season, outfitDescrToInt(cd)) for season, cd in seasons.iteritems())
    return result

_C11N_STOCK_COUNT = 20

_C11N_OWNABLE_TYPES = (
    CustomizationType.PAINT,
    CustomizationType.CAMOUFLAGE,
    CustomizationType.DECAL,
    CustomizationType.PROJECTION_DECAL,
    CustomizationType.PERSONAL_NUMBER,
    CustomizationType.STYLE,
    CustomizationType.MODIFICATION,
    CustomizationType.INSIGNIA,
)

def _normalizeOutfitDescr(value):
    if isinstance(value, basestring):
        if not value:
            return None
        return value
    if isinstance(value, (int, long)):
        try:
            from items import ITEM_TYPES
            from items.components.c11n_constants import CustomizationType
            from serializable_types.customizations import CustomizationOutfit
            itemTypeID = int(value & 15)
            if itemTypeID == 0:
                itemTypeID = int(value >> 24 & 255)
            if itemTypeID == ITEM_TYPES.customizationItem:
                cType = int(value >> 4 & 15)
                itemId = int(value >> 8 & 65535)
                if cType == CustomizationType.STYLE:
                    descr = CustomizationOutfit(styleId=itemId).makeCompDescr()
                    if descr:
                        return descr
        except Exception:
            pass
    return None

def sanitizeOutfitsData(outfitsData):
    result = {}
    for vehKey, seasons in (outfitsData or {}).iteritems():
        try:
            vehIntCD = int(vehKey)
        except Exception:
            try:
                vehIntCD = long(vehKey)
            except Exception:
                continue
        if vehIntCD <= 0 or not isinstance(seasons, dict):
            continue
        fixedSeasons = {}
        for season, outfitCD in seasons.iteritems():
            normalized = _normalizeOutfitDescr(outfitCD)
            if not normalized:
                continue
            fixedSeasons[season] = normalized
        if fixedSeasons:
            result[vehIntCD] = fixedSeasons
    return result

def getOfflineCustomization():
    customizationCache = vehicles.g_cache.customization20()
    itemsByType = {}
    for cType in _C11N_OWNABLE_TYPES:
        storage = customizationCache.itemTypes.get(cType)
        if not storage:
            continue
        typeItems = {}
        for itemId in storage.iterkeys():
            if itemId == EMPTY_ITEM_ID:
                continue
            typeItems[itemId] = {UNBOUND_VEH_KEY: _C11N_STOCK_COUNT}
        if typeItems:
            itemsByType[cType] = typeItems

    fixedOutfits = {}
    for vehIntCD, seasons in _applied_outfits_cache.iteritems():
        fixedOutfits[_toVehicleIntCD(vehIntCD)] = seasons

    return {
        CustomizationInvData.ITEMS: itemsByType,
        CustomizationInvData.DRESSED: {},
        CustomizationInvData.NOVELTY_DATA: {},
        CustomizationInvData.PROGRESSION: {},
        CustomizationInvData.ORDERING: {},
        CustomizationInvData.TAG_MASK: {},
        CustomizationInvData.OUTFITS: fixedOutfits,
        CustomizationInvData.OUTFITS_POOL: {},
        CustomizationInvData.SERIAL_NUMBERS: {},
    }

def getOfflineInventory():
    itemsCache = dependency.instance(IItemsCache)
    itemsProxy = itemsCache.items if itemsCache is not None else None
    data = {i: {} for i in range(1, 100)}
    compDescr = {}
    crewMap = {}
    tankmanCompDescr = {}
    tankmanVehicle = {}
    eqsMap = {}
    shellsMap = {}
    shellsLayoutMap = {}
    equipmentLayoutMap = {}
    optDevicesLayoutMap = {}
    battleBoostersLayoutMap = {}
    lockMap = {}
    settingsMap = {}
    repairMap = {}
    customizationExpiryMap = {}
    postProgressionMap = {}
    vehicleStateMap = {}
    layoutIndexesMap = {}
    vehicleIDs = getattr(g_list, '_VehicleList__ids', {})
    for value in list(vehicleIDs.values()):
        try:
            vehicle = vehicles.VehicleDescr(typeID=value)
            intCompDescr = vehicles.makeIntCompactDescrByID('vehicle', *value)
            item = Vehicle(typeCompDescr=intCompDescr, proxy=itemsProxy)
            vDesc = vehicle
            vType = vDesc.type
            turrets = _g(vType, 'turrets')
            turretv = turrets[-1][-1]
            guns = _g(turretv, 'guns')
            gunv = guns[-1]
            gun_id = _g(gunv, 'id')
            turret_id = _g(turretv, 'id')
            engines = _g(vType, 'engines')
            engine_id = _g(engines[-1], 'id')
            radios = _g(vType, 'radios')
            radio_id = _g(radios[-1], 'id')
            chassis_list = _g(vType, 'chassis')
            chassis_id = _g(chassis_list[-1], 'id')
            gunIDv = makeIntCompactDescrByID('vehicleGun', gun_id[0], gun_id[1])
            turretIDv = makeIntCompactDescrByID('vehicleTurret', turret_id[0], turret_id[1])
            engineIDv = makeIntCompactDescrByID('vehicleEngine', engine_id[0], engine_id[1])
            radioIDv = makeIntCompactDescrByID('vehicleRadio', radio_id[0], radio_id[1])
            chassisIDv = makeIntCompactDescrByID('vehicleChassis', chassis_id[0], chassis_id[1])
            vDesc.installComponent(chassisIDv)
            vDesc.installComponent(engineIDv)
            vDesc.installTurret(turretIDv, gunIDv)
            vDesc.installComponent(radioIDv)
            isEvent = getattr(item, 'isOnlyForEventBattles', False)
            isIGR = getattr(item, 'isPremiumIGR', False)
            if not isEvent and not isIGR:
                vehicleInvID = len(compDescr)
                fullCompDescr = vDesc.makeCompactDescr()
                compDescr[vehicleInvID] = fullCompDescr
                _invID_to_intCD[vehicleInvID] = intCompDescr
                defaultAmmo = vehicles.getDefaultAmmoForGun(vDesc.gun)
                shellsMap[vehicleInvID] = defaultAmmo
                _vehicleShellsByInvID[vehicleInvID] = list(defaultAmmo)
                shellsLayoutMap[vehicleInvID] = {(vDesc.turret.compactDescr, vDesc.gun.compactDescr): [defaultAmmo]}
                equipmentLayoutMap[vehicleInvID] = [[]]
                optDevicesLayoutMap[vehicleInvID] = [[]]
                battleBoostersLayoutMap[vehicleInvID] = [[]]
                eqsMap[vehicleInvID] = []
                lockMap[vehicleInvID] = (0, 0)
                settingsMap[vehicleInvID] = 0
                repairMap[vehicleInvID] = (0, 0)
                customizationExpiryMap[vehicleInvID] = {}
                postProgressionMap[vehicleInvID] = []
                vehicleStateMap[vehicleInvID] = 0
                layoutIndexesMap[vehicleInvID] = {}
                crewCDs = _generateCrewForVehicle(value[0], value[1], vType)
                crewIDs = []
                for cd in crewCDs:
                    tmanInvID = len(tankmanCompDescr)
                    tankmanCompDescr[tmanInvID] = cd
                    tankmanVehicle[tmanInvID] = vehicleInvID
                    crewIDs.append(tmanInvID)
                crewMap[vehicleInvID] = crewIDs
        except Exception as e:
            LOG_DEBUG('Skipped vehicle id:', value, e)
            continue
    data[GUI_ITEM_TYPE.VEHICLE] = {
        'repair': repairMap,
        'crew': crewMap,
        'settings': settingsMap,
        'compDescr': compDescr,
        'eqs': eqsMap,
        'shells': shellsMap,
        'customizationExpiryTime': customizationExpiryMap,
        'lock': lockMap,
        TankSetupLayouts.SHELLS: shellsLayoutMap,  
        'vehicle': vehicleStateMap,
        'postProgression': postProgressionMap,
        'layoutIndexes': layoutIndexesMap,
        TankSetupLayouts.EQUIPMENT: equipmentLayoutMap,
        TankSetupLayouts.OPTIONAL_DEVICES: optDevicesLayoutMap,
        TankSetupLayouts.BATTLE_BOOSTERS: battleBoostersLayoutMap,
    }
    _apply_inventory_overlay(data)

    try:
        vehData = data.get(GUI_ITEM_TYPE.VEHICLE, {})

        plainShells = vehData.get('shells', {})
        for invID, ammo in plainShells.items():
            if ammo:
                _vehicleShellsByInvID[invID] = list(ammo)

        shellsLayouts = vehData.get(TankSetupLayouts.SHELLS, {})
        for invID, layouts in shellsLayouts.items():
            try:
                for layoutKey, ammoLists in layouts.items():
                    if ammoLists:
                        if isinstance(ammoLists, (list, tuple)):
                            first = ammoLists[0]
                            if isinstance(first, (list, tuple)):
                                _vehicleShellsByInvID[invID] = list(first)
                            else:
                                _vehicleShellsByInvID[invID] = list(ammoLists)
                            break
            except Exception:
                pass
    except Exception:
        pass

    data[GUI_ITEM_TYPE.TANKMAN] = {
        'compDescr': tankmanCompDescr,
        'vehicle': tankmanVehicle,
        'dismissedAt': {},
    }
    data[GUI_ITEM_TYPE.CREW_SKINS] = {
        SkinInvData.OUTFITS: {},
    }
    data[GUI_ITEM_TYPE.CUSTOMIZATION] = getOfflineCustomization()
    _offlineInventoryCache = {'inventory': data}   
    return _offlineInventoryCache


def getOfflineShop():
    shopItems = {}
    items.init(True, shopItems)

    shopItems.setdefault('itemPrices', {})
    shopItems.setdefault('vehiclesRentPrices', {})
    shopItems.setdefault('vehicleSellPriceFactors', {})
    shopItems.setdefault('vehiclesToSellForGold', {})
    shopItems.setdefault('customization', {})
    shopItems.setdefault('outfits', {})
    shopItems.setdefault('crewBooks', {})
    shopItems.setdefault('consumables', {})
    shopItems.setdefault('optionalDevices', {})
    shopItems.setdefault('shells', {})
    shopItems.setdefault('equipment', {})
    shopItems.setdefault('goods', {})
    shopItems.setdefault('tokens', {})
    shopItems.setdefault('lootBoxes', {})

    return {
        'rev': 1,
        'crystalExchangeRate': 200,
        'camouflageCost': {0: (250, True), 30: (100000, False), 7: (25000, False)},
        'goodies': {'prices': {}, 'notInShop': set(), 'goodies': {}},
        'berthsPrices': (16, 16, [300]),
        'femalePassportChangeCost': 50,
        'freeXPConversion': (100000, 0.1),
        'dropSkillsCost': {
            0: {'xpReuseFraction': 0.5, 'gold': 0, 'credits': 0},
            1: {'xpReuseFraction': 0.75, 'gold': 0, 'credits': 20000},
            2: {'xpReuseFraction': 1.0, 'gold': 10, 'credits': 1000},
        },
        'refSystem': {'maxNumberOfReferrals': 50, 'posByXPinTeam': 10, 'maxReferralXPPool': 350000, 'periods': [(24, 3.0), (168, 2.0), (876000, 1.5)]},
        'playerEmblemCost': {0: (15, True), 30: (6000, False), 7: (1500, False)},
        'premiumCost': {1: 1, 3: 1, 7: 1, 360: 1, 180: 1, 30: 1},
        'winXPFactorMode': 0,
        'sellPriceModif': 0.75,
        'passportChangeCost': 50,
        'exchangeRateForShellsAndEqs': 400,
        'exchangeRate': 400,
        'tankmanCost': (
            {'isPremium': False, 'baseRoleLoss': 0.2, 'gold': 0, 'credits': 0, 'classChangeRoleLoss': 0.2, 'roleLevel': 50},
            {'isPremium': False, 'baseRoleLoss': 0.1, 'gold': 0, 'credits': 20000, 'classChangeRoleLoss': 0.1, 'roleLevel': 75},
            {'isPremium': True, 'baseRoleLoss': 0.0, 'gold': 200, 'credits': 0, 'classChangeRoleLoss': 0.0, 'roleLevel': 100},
        ),
        'paidRemovalCost': {Currency.GOLD: 10},
        'dailyXPFactor': 100,
        'changeRoleCost': 500,
        'isEnabledBuyingGoldShellsForCredits': False,
        'items': shopItems,
        'slotsPrices': (9, ([Currency.CREDITS, 300],)),
        'freeXPToTManXPRate': 10,
        'defaults': {'items': shopItems, 'freeXPToTManXPRate': 0, 'goodies': {'prices': {}}},
        'sellPriceFactor': 0.5,
        'isEnabledBuyingGoldEqsForCredits': False,
        'playerInscriptionCost': {0: (15, True), 7: (1500, False), 30: (6000, False), 'nations': {}},

        'customization': {},
        'outfits': {},
        'crewBooks': {},
        'consumables': {},
        'optionalDevices': {},
        'shells': {},
        'equipment': {},
        'goods': {},
    }

def getOfflineStats():
    unlocksSet = set()
    vehiclesSet = set()
    for nationID in nations.INDICES.values():
        unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleChassis', nationID, i) for i in g_cache.chassis(nationID).keys()}
        unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleEngine', nationID, i) for i in g_cache.engines(nationID).keys()}
        unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleFuelTank', nationID, i) for i in g_cache.fuelTanks(nationID).keys()}
        unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleRadio', nationID, i) for i in g_cache.radios(nationID).keys()}
        unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleTurret', nationID, i) for i in g_cache.turrets(nationID).keys()}
        unlocksSet |= {vehicles.makeIntCompactDescrByID('vehicleGun', nationID, i) for i in g_cache.guns(nationID).keys()}
        unlocksSet |= {vehicles.makeIntCompactDescrByID('shell', nationID, i) for i in g_cache.shells(nationID).keys()}
        vData = {vehicles.makeIntCompactDescrByID('vehicle', nationID, i) for i in g_list.getList(nationID).keys()}
        unlocksSet |= vData
        vehiclesSet |= vData
    attrs = 0
    for field in dir(ACCOUNT_ATTR):
        value = getattr(ACCOUNT_ATTR, field, None)
        if isinstance(value, int) and not isinstance(value, bool): attrs |= value
    vehTypeXP = {i: 0 for i in vehiclesSet}
    return {
        'stats': {
            'crystalExchangeRate': 200, 'berths': 40000, 'accOnline': 0, 'gold': 10000000, 'crystal': 10000000,
            'finPswdAttemptsLeft': 0, 'denunciationsLeft': 0, 'freeVehiclesLeft': 0, 'refSystem': {'referrals': {}},
            'slots': 2000, 'battlesTillCaptcha': 0, 'hasFinPassword': True, 'clanInfo': (None, None, 0, 0, 0),
            'unlocks': unlocksSet, 'freeTMenLeft': 0, 'vehicleSellsLeft': 9999, 'SPA': {'/common/goldfish_bonus_applied/': '1'},
            'vehTypeXP': vehTypeXP, 'globalVehicleLocks': {}, 'freeXP': 10000000, 'captchaTriesLeft': 0, 'fortResource': 0,
            'tkillIsSuspected': False, 'credits': 100000000, 'vehTypeLocks': {}, 'dailyPlayHours': [0], 'restrictions': {},
            'accOffline': 0, 'dossier': '', 'multipliedXPVehs': {}, 'tutorialsCompleted': 33553532, 'eliteVehicles': vehiclesSet,
            'playLimits': ((99999, ''), (99999, '')),
        },
        'account': {'clanDBID': 0, 'attrs': attrs, 'premiumExpiryTime': 8000, 'autoBanTime': 0, 'globalRating': 0},
        'cache': {'isFinPswdVerified': True, 'mayConsumeWalletResources': True, 'unitAcceptDeadline': 0, 'oldVehInvIDs': ()},
    }

def getOfflineQuestsProgress():
    return {
        'tokens': {},
        'pmQuestsStates': {},
        'cache': {'pmQuestsStates': {}},
        'personalMissionQuests': {
            'regular': {'selected': [], 'slots': 0, 'lastIDs': {}},
            'pm2': {'selected': [], 'slots': 0, 'lastIDs': {}},
            'pm3': {'selected': [], 'slots': 0, 'lastIDs': {}},
        },
        'pm_progress': {},
        'potapovQuests': {
            'compDescr': '',
            'regular': {'tiles': set(), 'rewards': {}, 'compDescr': '', 'selected': {1, 17, 31, 46, 61}, 'lastIDs': {}, 'slots': 2},
            'fallout': {'tiles': set(), 'rewards': {}, 'compDescr': '', 'selected': {301, 401}, 'lastIDs': {}, 'slots': 2},
        },
        'quests': {},
    }

def _apply_inventory_overlay(data):
    cache = load_cache()
    vehCache = cache.get('vehicles', {})
    if not vehCache:
        return
    vehData = data.get(GUI_ITEM_TYPE.VEHICLE, {})
    for vehInvID, overlay in vehCache.iteritems():
        for key, value in overlay.iteritems():
            vehData.setdefault(key, {})[vehInvID] = value