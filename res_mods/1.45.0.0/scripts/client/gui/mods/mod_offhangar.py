import os
import signal
import Keys
import BigWorld
import constants
import Account
import game
import zlib
import pickle
from debug_utils import LOG_CURRENT_EXCEPTION
from predefined_hosts import g_preDefinedHosts
from connection_mgr import LOGIN_STATUS, ConnectionManager
from skeletons.connection_mgr import IConnectionManager
from skeletons.gui.app_loader import IAppLoader
from helpers import dependency
from gui.Scaleform.Waiting import Waiting
from gui.shared.gui_items.Vehicle import Vehicle
from gui.Scaleform.daapi.view.login.LoginView import LoginView
from gui.impl.lobby.achievements.notifications_utils import NotificationsRuleProcessor
from paragons_common import BaseParagonsStorage
from dog_tags_common.dog_tags_storage import Storage
import preferred_maps
import time
from gui.shared.gui_items.badge import Badge
from gui.mods.offhangar.logging import LOG_DEBUG, LOG_NOTE
from gui.mods.offhangar._constants import (
    IS_REQUEST_CATCHING,
    OFFLINE_SERVER_ADDRES,
    OFFLINE_NICKNAME,
    OFFLINE_LOGIN,
    OFFLINE_PWD,
    OFFLINE_GUI_CTX,
    OFFLINE_SERVER_SETTINGS,
)
from gui.mods.offhangar.server import FakeServer
from gui.mods.offhangar.utils import override
from gui.mods.offhangar.battle import enterOfflineBattle, leaveOfflineBattle
import gui.mods.offhangar.battle as offhangar_battle
from account_helpers.settings_core.IntUserSettings import IntUserSettings
import gui.mods.offhangar.requests
import AccountCommands
from notification.listeners import RecertificationFormStateListener
from constants import SwitchState
import gui.mods.offhangar.physics as offhangar_physics
import gui.mods.offhangar.bots as offhangar_bots
offhangar_physics.install()
import random
_offhangar_enterOfflineBattle = enterOfflineBattle
_offhangar_leaveOfflineBattle = leaveOfflineBattle

def enterOfflineBattle(vehInvID=0, mapName=None):
    result = _offhangar_enterOfflineBattle(vehInvID=vehInvID, mapName=mapName)
    offhangar_physics.start()
    return result

def leaveOfflineBattle():
    offhangar_physics.clear_bodies()
    result = _offhangar_leaveOfflineBattle()
    offhangar_physics.clear_bodies()
    return result

offhangar_battle.enterOfflineBattle = enterOfflineBattle
offhangar_battle.leaveOfflineBattle = leaveOfflineBattle
Account.LOG_DEBUG = LOG_DEBUG
Account.LOG_NOTE = LOG_NOTE

g_loginView = None
IS_OFFLINE_MODE = False

def fini():
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        LOG_CURRENT_EXCEPTION()

if not any(host.url == OFFLINE_SERVER_ADDRES for host in g_preDefinedHosts._hosts):
    g_preDefinedHosts._hosts.append(
        g_preDefinedHosts._makeHostItem(OFFLINE_SERVER_ADDRES, OFFLINE_SERVER_ADDRES, OFFLINE_SERVER_ADDRES)
    )

@override(NotificationsRuleProcessor, 'process')
def NotificationsRuleProcessor_process(baseFunc, baseSelf):
    if getattr(BigWorld.player(), 'isOffline', False):
        return
    return baseFunc(baseSelf)

@override(BaseParagonsStorage, '__init__')
def BaseParagonsStorage_init(baseFunc, baseSelf, data):
    if data is None:
        data = {}
    for key, value in BaseParagonsStorage.makeDefaultStorage().items():
        data.setdefault(key, value)
    return baseFunc(baseSelf, data)

import items as _items_module
try:
    from items import vehicles as _vehicles_module
except Exception:
    _vehicles_module = None

def _normalizeIntCompactDescr(compactDescr):
    if isinstance(compactDescr, (int, long)):
        return int(compactDescr)
    if isinstance(compactDescr, basestring):
        try:
            return int(compactDescr)
        except Exception:
            pass
        try:
            return long(compactDescr)
        except Exception:
            pass
        try:
            import struct
            raw = compactDescr[:8]
            if len(raw) < 8:
                raw = raw + '\x00' * (8 - len(raw))
            return struct.unpack('<Q', raw)[0]
        except Exception:
            return 0
    try:
        return int(compactDescr)
    except Exception:
        return 0

_origParseIntCompactDescr = _items_module.parseIntCompactDescr

def _safeParseIntCompactDescr(compactDescr):
    return _origParseIntCompactDescr(_normalizeIntCompactDescr(compactDescr))

_items_module.parseIntCompactDescr = _safeParseIntCompactDescr
if _vehicles_module is not None and hasattr(_vehicles_module, 'parseIntCompactDescr'):
    _vehicles_module.parseIntCompactDescr = _safeParseIntCompactDescr

def _patchAccountValidator(*_):
    try:
        try:
            from account_helpers.account_validator import InventoryOutfitValidator
        except Exception:
            from account_validator import InventoryOutfitValidator
        import th_async
        import constants
        from gui.shared.gui_items import GUI_ITEM_TYPE
        from items import vehicles

        if hasattr(vehicles, 'parseIntCompactDescr'):
            vehicles.parseIntCompactDescr = _safeParseIntCompactDescr

        @th_async.th_async
        def _safeValidateInventoryOutfit(self):
            try:
                c11nData = self.itemsCache.items.inventory.getCacheValue(GUI_ITEM_TYPE.CUSTOMIZATION, {})
            except Exception:
                c11nData = {}

            def validateOutfitsAsync():
                customizationInvData = getattr(constants, 'CustomizationInvData', None)
                outfitsKey = getattr(customizationInvData, 'OUTFITS', None)
                if outfitsKey is None:
                    return
                outfits = c11nData.get(outfitsKey, {})
                if not isinstance(outfits, dict):
                    return
                for vehKey, outfitsData in outfits.items():
                    if BigWorld.player() is None:
                        return
                    vehIntCD = _normalizeIntCompactDescr(vehKey)
                    if not vehIntCD:
                        continue
                    if not isinstance(outfitsData, dict):
                        continue
                    vehicleData = None
                    try:
                        vehicleData = self.itemsCache.items.inventory.getItemData(vehIntCD)
                    except Exception:
                        vehicleData = None
                    if vehicleData is not None:
                        if isinstance(vehicleData, dict):
                            vehicleCD = vehicleData.get('compDescr')
                        else:
                            vehicleCD = getattr(vehicleData, 'compDescr', None)
                        if vehicleCD is None:
                            continue
                    else:
                        try:
                            _, nationID, vehicleTypeID = vehicles.parseIntCompactDescr(vehIntCD)
                            vehicleDesc = vehicles.VehicleDescr(typeID=(nationID, vehicleTypeID))
                            vehicleCD = vehicleDesc.makeCompactDescr()
                        except Exception:
                            continue
                    for outfitCD in outfitsData.values():
                        if BigWorld.player() is None:
                            return
                        if not outfitCD:
                            continue
                        try:
                            yield self.itemsFactory.createOutfit(strCompactDescr=outfitCD, vehicleCD=vehicleCD)
                        except Exception:
                            continue
                return

            yield th_async.distributeLoopOverTicks(validateOutfitsAsync(), minPerTick=10, maxPerTick=100, logID='validateOutfitsAsync', tickLength=0.0)

        InventoryOutfitValidator._InventoryOutfitValidator__validateInventoryOutfit = _safeValidateInventoryOutfit
    except Exception:
        LOG_CURRENT_EXCEPTION()

BigWorld.callback(0.0, _patchAccountValidator)

@override(Storage, '__init__')
def DogTagsStorage_init(baseFunc, baseSelf, data):
    if data is None:
        data = {}
    if baseSelf.key not in data:
        data[baseSelf.key] = baseSelf.default()
    return baseFunc(baseSelf, data)

@override(preferred_maps, 'getConfiguredSlotLayout')
def preferred_maps_getConfiguredSlotLayout(baseFunc, config):
    if not isinstance(config, dict) or 'slots' not in config:
        config = dict(config) if isinstance(config, dict) else {}
    config['slots'] = {}
    return baseFunc(config)

@override(Vehicle, 'canSell')
def Vehicle_canSell(baseFunc, baseSelf):
    return getattr(BigWorld.player(), 'isOffline', False) or baseFunc(baseSelf)

@override(LoginView, '_populate')
def LoginView_populate(baseFunc, baseSelf, *args, **kwargs):
    global g_loginView
    baseFunc(baseSelf, *args, **kwargs)
    g_loginView = baseSelf
    if not IS_REQUEST_CATCHING and not IS_OFFLINE_MODE:
        def autoLogin():
            LOG_DEBUG('Auto-login triggered')
            try:
                params = {'login': OFFLINE_LOGIN, 'auth_method': 'login', 'session': '', 'token2': ''}
                dependency.instance(IConnectionManager).initiateConnection(params, OFFLINE_PWD, OFFLINE_SERVER_ADDRES)
            except Exception:
                LOG_CURRENT_EXCEPTION()
        BigWorld.callback(0.5, autoLogin)

@override(IntUserSettings, 'getCache')
def IntUserSettings_getCache(baseFunc, baseSelf, callback=None):
    player = BigWorld.player()
    if getattr(player, 'isOffline', False):
        if callback is not None:
            callback(AccountCommands.RES_SUCCESS, {})
        return
    return baseFunc(baseSelf, callback)

@override(IntUserSettings, 'get')
def IntUserSettings_get(baseFunc, baseSelf, key, callback=None):
    player = BigWorld.player()
    if getattr(player, 'isOffline', False):
        if callback is not None:
            callback(AccountCommands.RES_SUCCESS, None)
        return
    return baseFunc(baseSelf, key, callback)

@override(LoginView, '_dispose')
def LoginView_dispose(baseFunc, baseSelf, *args, **kwargs):
    global g_loginView
    g_loginView = None
    try:
        return baseFunc(baseSelf, *args, **kwargs)
    except ValueError as e:
        LOG_DEBUG('LoginView_dispose: suppressed cancelCallback error on shutdown:', e)
        return None

@override(ConnectionManager, 'initiateConnection')
def ConnectionManager_initiateConnection(baseFunc, baseSelf, params, password, serverName):
    global IS_OFFLINE_MODE
    IS_OFFLINE_MODE = True
    LOG_DEBUG('Intercepted login request, forcing offline server')
    params = {'login': OFFLINE_LOGIN, 'auth_method': 'login', 'session': '', 'token2': ''}
    baseFunc(baseSelf, params, OFFLINE_PWD, OFFLINE_SERVER_ADDRES)

@override(Account.PlayerAccount, '__init__')
def Account_init(baseFunc, baseSelf):
    baseSelf.isOffline = IS_OFFLINE_MODE
    if baseSelf.isOffline:
        constants.IS_SHOW_SERVER_STATS = True
        constants.DEVELOPMENT_INFO.ENABLE_SENDING_VEH_ATTRS_TO_CLIENT = True
        constants.CURRENT_REALM = 'ZZ'
        constants.ENABLE_DEBUG_DYNAMICS_INFO = True
        constants.IS_DEVELOPMENT = True
        constants.IS_RENTALS_ENABLED = True
        constants.IS_SHOW_INGAME_HELP_FIRST_TIME = False
        constants.IS_TUTORIAL_ENABLED = False
        constants.ACCOUNT_ATTR.ADMIN = 256
        baseSelf.fakeServer = FakeServer()
        clientServerVersion = getattr(Account, '_CLIENT_SERVER_VERSION', None)
        if clientServerVersion is not None:
            setattr(baseSelf, *clientServerVersion)
        baseSelf.name = OFFLINE_NICKNAME
        try:
            server_settings = pickle.loads(zlib.decompress(OFFLINE_SERVER_SETTINGS))
            if not isinstance(server_settings, dict):
                server_settings = {}
        except Exception:
            server_settings = {}
        server_settings.setdefault('vehicle_post_progression_config', {})
        server_settings.setdefault('craft_machine_config', {})
        server_settings.setdefault('event_progression_config', {})
        baseSelf.initialServerSettings = zlib.compress(pickle.dumps(server_settings, protocol=2))
    baseFunc(baseSelf)
    if baseSelf.isOffline:
        BigWorld.player(baseSelf)

@override(Account.PlayerAccount, '__getattribute__')
def Account_getattribute(baseFunc, baseSelf, name):
    if name in ('cell', 'base', 'server'):
        try:
            isOffline = baseFunc(baseSelf, 'isOffline')
        except Exception:
            isOffline = False
        if isOffline:
            name = 'fakeServer'
        try:
            return baseFunc(baseSelf, name)
        except AttributeError:
            if name == 'getVehicleAttached':
                return lambda *a, **kw: None
            raise
    try:
        return baseFunc(baseSelf, name)
    except AttributeError:
        if not getattr(baseSelf, 'isOffline', False):
            raise
        if name == 'isObserver':
            return lambda: False
        if name == 'isObserverFPV':
            return False
        if name == 'isGunLocked':
            return False
        if name == 'isOnArena':
            return False
        if name == 'isVehicleAlive':
            return False
        if name == 'isWaitingForShot':
            return False
        if name == 'isForcedGuiControlMode':
            return lambda: False
        if name == 'getVehicleAttached':
            return lambda *a, **kw: None
        if name == 'getOwnVehicleMatrix':
            return lambda *a, **kw: Math.Matrix()
        if name == 'getOwnVehiclePosition':
            return lambda: Math.Vector3(0, 0, 0)
        if name == 'getOwnVehicleTurretMatrix':
            return lambda *a, **kw: Math.Matrix()
        if name == 'getOwnVehicleStabilisedMatrix':
            return lambda *a, **kw: Math.Matrix()
        if name == 'getOwnVehicleShotDispersionAngle':
            return lambda *a, **kw: [0.0, 0.0, 0.0, 0.0]
        if name == 'playerVehicleID':
            return 0
        if name == 'arena':
            return None
        if name == 'arenaBonusType':
            return 0
        if name == 'inputHandler':
            return None
        if name == 'gunRotator':
            return None
        if name == 'consistentMatrices':
            return None
        if name == 'positionControl':
            return None
        if name == 'vehicleTypeDescriptor':
            return None
        if name == 'observerSeesAll':
            return lambda: False
        if name == 'isFPVModeSwitching':
            return False
        if name == 'magneticAutoAimTags':
            return frozenset()
        if name == 'team':
            return 0
        if name == 'moveVehicle':
            return lambda *a, **kw: None
        if name == 'moveVehicleByCurrentKeys':
            return lambda *a, **kw: None
        if name == 'makeVehicleMovementCommandByKeys':
            return lambda *a, **kw: 0
        if name == 'enableOwnVehicleAutorotation':
            return lambda *a, **kw: None
        if name == 'autoAim':
            return lambda *a, **kw: None
        if name == 'shoot':
            return lambda *a, **kw: None
        if name == 'showVehicleError':
            return lambda *a, **kw: None
        if name == 'guiSessionProvider':
            return None
        if name == 'soundNotifications':
            return None
        if name == 'complexSoundNotifications':
            return None
        raise
    
@override(Account.PlayerAccount, 'onBecomePlayer')
def Account_onBecomePlayer(baseFunc, baseSelf):
    baseFunc(baseSelf)
    if getattr(baseSelf, 'isOffline', False):
        try:
            Waiting.hide('login')
            Waiting.close()
        except Exception:
            LOG_CURRENT_EXCEPTION()
        baseSelf.showGUI(OFFLINE_GUI_CTX)

@override(BigWorld, 'clearEntitiesAndSpaces')
def BigWorld_clearEntitiesAndSpaces(baseFunc, *args):
    if getattr(BigWorld.player(), 'isOffline', False) and not getattr(offhangar_battle, 'ALLOW_CLEAR', False):
        return
    return baseFunc(*args)

@override(BigWorld, 'connect')
def BigWorld_connect(baseFunc, server, loginParams, progressFn):
    if server == OFFLINE_SERVER_ADDRES:
        LOG_DEBUG('BigWorld.connect -> offline')
        dummy_response = '{"token2": "offline_dummy_token", "session_id": "offline_session"}'
        progressFn(1, LOGIN_STATUS.LOGGED_ON, dummy_response)
        BigWorld.createEntity('Account', BigWorld.createSpace(), 0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), {})
    else:
        baseFunc(server, loginParams, progressFn)

@override(RecertificationFormStateListener, '_getState')
def RecertificationFormStateListener_getState(baseFunc, baseSelf):
    try:
        return baseFunc(baseSelf)
    except Exception:
        return SwitchState.DISABLED.value

@override(game, 'handleKeyEvent')
def game_handleKeyEvent(baseFunc, event):
    isOffline = getattr(BigWorld.player(), 'isOffline', False)
    if event.isKeyDown() and not event.isRepeatedEvent():
        if isOffline:
            if event.isCtrlDown():
                if event.key == Keys.KEY_V:
                    appLoader = dependency.instance(IAppLoader)
                    app = appLoader.getApp() if appLoader else None
                    if app is not None:
                        component = getattr(app, 'component', None)
                        if component is not None:
                            component.visible = not component.visible
                            graphicsOptimizationManager = getattr(app, 'graphicsOptimizationManager', None)
                            if graphicsOptimizationManager is not None and component is not None:
                                graphicsOptimizationManager.switchOptimizationEnabled(component.visible)
                    return True
                if event.key == Keys.KEY_W:
                    try:
                        if Waiting is not None and Waiting.isActive('login'):
                            Waiting.close()
                            return True
                    except Exception:
                        pass
                if event.key == Keys.KEY_L and not event.isCtrlDown():
                    if offhangar_battle.IS_IN_BATTLE:
                        LOG_DEBUG('Hotkey: spawn random bot')
                        offhangar_bots.spawnRandomBot()
                    return True
        elif not IS_REQUEST_CATCHING:
            if event.key == Keys.KEY_RBRACKET:
                LOG_DEBUG('Manual login via ConnectionManager')
                try:
                    params = {'login': OFFLINE_LOGIN, 'auth_method': 'login', 'session': '', 'token2': ''}
                    dependency.instance(IConnectionManager).initiateConnection(params, OFFLINE_PWD, OFFLINE_SERVER_ADDRES)
                except Exception:
                    LOG_CURRENT_EXCEPTION()
                return True
    return baseFunc(event)

@override(Badge, '__init__')
def Badge_init(baseFunc, baseSelf, data, proxy=None):
    baseFunc(baseSelf, data, proxy)
    if getattr(BigWorld.player(), 'isOffline', False):
        baseSelf.isAchieved = True
        if baseSelf.achievedAt is None:
            baseSelf.achievedAt = int(time.time())

def _pickBestBadges():
    prefixID = 0
    suffixID = 0
    prefixWeight = None
    suffixWeight = None
    for badgeID, descr in badges_loader.getAvailableBadges().iteritems():
        weight = descr.get('weight', -1.0)
        if descr.get('layout', BadgeLayouts.PREFIX) == BadgeLayouts.SUFFIX:
            if suffixWeight is None or weight > suffixWeight:
                suffixWeight = weight
                suffixID = badgeID
        elif prefixWeight is None or weight > prefixWeight:
            prefixWeight = weight
            prefixID = badgeID
    return (prefixID, suffixID)

def getOfflineBadges():
    try:
        prefixID, suffixID = _pickBestBadges()
        return ((prefixID,) if prefixID else (), (suffixID,) if suffixID else ())
    except Exception:
        return ((), ())

def getRandomBotBadges():
    try:
        available = badges_loader.getAvailableBadges()
        if not available:
            return ((), ())
        ids = available.keys()
        prefix = (random.choice(ids),) if random.random() < 0.7 else ()
        suffix = (random.choice(ids),) if random.random() < 0.3 else ()
        return (prefix, suffix)
    except Exception:
        return ((), ())

try:
    from gui.Scaleform.daapi.view.battle.shared.minimap.plugins import ArenaVehiclesPlugin
    from gui.Scaleform.daapi.view.battle.shared.minimap.component import MinimapComponent
    from gui.mods.offhangar.utils import override

    @override(ArenaVehiclesPlugin, '_ArenaVehiclesPlugin__handleShowExtendedInfo')
    def ArenaVehiclesPlugin_handleShowExtendedInfo(baseFunc, baseSelf, event):
        try:
            return baseFunc(baseSelf, event)
        except ReferenceError:
            return
        except Exception:
            return

    @override(MinimapComponent, 'isModalViewShown')
    def MinimapComponent_isModalViewShown(baseFunc, baseSelf):
        try:
            return baseFunc(baseSelf)
        except ReferenceError:
            return False
        except Exception:
            return False
except Exception:
    pass

try:
    from gui.Scaleform.daapi.view.meta.FragCorrelationBarMeta import FragCorrelationBarMeta
    from gui.mods.offhangar.utils import override
    from helpers import dependency
    from skeletons.gui.app_loader import IAppLoader
    import BigWorld

    def _isAtlasMgrReady():
        try:
            appLoader = dependency.instance(IAppLoader)
            app = appLoader.getApp() if appLoader else None
            if app is None:
                return False
            # В разных версиях клиента atlasMgr может быть свойством или вызываемым методом
            atlasMgr = getattr(app, 'atlasMgr', None)
            if callable(atlasMgr):
                atlasMgr = atlasMgr()
            return atlasMgr is not None
        except Exception:
            return False

    @override(FragCorrelationBarMeta, 'as_updateViewSettingS')
    def FragCorrelationBarMeta_as_updateViewSettingS(baseFunc, baseSelf, setting):
        if not _isAtlasMgrReady():
            # UI еще не инициализировал atlasMgr, откладываем вызов до готовности
            BigWorld.callback(0.2, lambda: baseFunc(baseSelf, setting))
            return None
        return baseFunc(baseSelf, setting)

    @override(FragCorrelationBarMeta, 'as_updateHPS')
    def FragCorrelationBarMeta_as_updateHPS(baseFunc, baseSelf, *args, **kwargs):
        if not _isAtlasMgrReady():
            BigWorld.callback(0.2, lambda: baseFunc(baseSelf, *args, **kwargs))
            return None
        return baseFunc(baseSelf, *args, **kwargs)
        
except Exception:
    import traceback
    traceback.print_exc()

try:
    from gui.Scaleform.daapi.view.battle.shared.base_stats import StatsBase
    from gui.mods.offhangar.utils import override
    import BigWorld

    def _offhangar_stats_base_delayed_cursor(baseFunc, baseSelf, event):
        def _call():
            try:
                player = BigWorld.player()
                if player is not None and getattr(player, 'isOffline', False):
                    return
                baseFunc(baseSelf, event)
            except Exception:
                pass
        BigWorld.callback(0.0, _call)

    @override(StatsBase, '_StatsBase__handleShowCursor')
    def StatsBase_handleShowCursor(baseFunc, baseSelf, event):
        _offhangar_stats_base_delayed_cursor(baseFunc, baseSelf, event)

    @override(StatsBase, '_StatsBase__handleHideCursor')
    def StatsBase_handleHideCursor(baseFunc, baseSelf, event):
        _offhangar_stats_base_delayed_cursor(baseFunc, baseSelf, event)
except Exception:
    pass

try:
    from gui.Scaleform.daapi.view.meta.StatsBaseMeta import StatsBaseMeta
    from gui.mods.offhangar.utils import override
    import BigWorld

    @override(StatsBaseMeta, 'as_setIsInteractiveS')
    def StatsBaseMeta_as_setIsInteractiveS(baseFunc, baseSelf, value):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                return None
            if not baseSelf._isDAAPIInited():
                return None
            flashObject = getattr(baseSelf, 'flashObject', None)
            if flashObject is None:
                return None
            return flashObject.as_setIsInteractive(value)
        except Exception:
            return None
except Exception:
    pass

try:
    from cosmic_event.gui.game_control.progression_controller import CosmicProgressionController
    from gui.mods.offhangar.utils import override

    @override(CosmicProgressionController, 'isCosmicProgressionQuest')
    def CosmicProgressionController_isCosmicProgressionQuest(baseFunc, baseSelf, questID):
        try:
            questionPrefix = baseSelf.cosmicBattleController.getProgressionQuestPrefix()
        except Exception:
            return False
        if not questionPrefix:
            return False
        if not isinstance(questID, basestring):
            return False
        return questID.startswith(questionPrefix)
except Exception:
    pass

try:
    import sys
    import items.customizations as _customizations_module
    from items.customizations import parseOutfitDescr as _offhangarParseOutfitDescr
    from items.components.c11n_constants import SeasonType as _offhangarSeasonType

    try:
        _OffhangarCustomizationOutfit = _customizations_module.CustomizationOutfit
    except Exception:
        from serializable_types.customizations import CustomizationOutfit as _OffhangarCustomizationOutfit

    def _offhangarBattleVehicleIntCD(vehType):
        from items import vehicles as _offhangarVehicles
        try:
            if isinstance(vehType, tuple) and len(vehType) == 2:
                return _offhangarVehicles.makeIntCompactDescrByID('vehicle', vehType[0], vehType[1])
        except Exception:
            pass
        try:
            return _offhangarVehicles.makeIntCompactDescrByID('vehicle', vehType.id[0], vehType.id[1])
        except Exception:
            pass
        candidates = []
        try:
            candidates.append(vehType.compactDescr)
        except Exception:
            pass
        try:
            candidates.append(vehType.type.compactDescr)
        except Exception:
            pass
        try:
            candidates.append(vehType)
        except Exception:
            pass
        try:
            candidates.append(vehType.makeCompactDescr())
        except Exception:
            pass
        for cd in candidates:
            if isinstance(cd, (int, long)):
                try:
                    nationID, vehicleTypeID = _offhangarVehicles.parseVehicleCompactDescr(cd)
                    return _offhangarVehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
                except Exception:
                    pass
                try:
                    itemTypeID, nationID, vehicleTypeID = _offhangarVehicles.parseIntCompactDescr(cd)
                    if itemTypeID == 1:
                        return _offhangarVehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
                except Exception:
                    pass
                try:
                    return int(cd)
                except Exception:
                    pass
            elif isinstance(cd, basestring):
                try:
                    nationID, vehicleTypeID = _offhangarVehicles.parseVehicleCompactDescr(cd)
                    return _offhangarVehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
                except Exception:
                    pass
        return 0

    def _offhangarNormalizeVehicleKey(key):
        from items import vehicles as _offhangarVehicles
        if isinstance(key, (int, long)):
            try:
                nationID, vehicleTypeID = _offhangarVehicles.parseVehicleCompactDescr(key)
                return _offhangarVehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
            except Exception:
                pass
            try:
                itemTypeID, nationID, vehicleTypeID = _offhangarVehicles.parseIntCompactDescr(key)
                if itemTypeID == 1:
                    return _offhangarVehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
            except Exception:
                pass
            try:
                return int(key)
            except Exception:
                return None
        if isinstance(key, basestring):
            try:
                nationID, vehicleTypeID = _offhangarVehicles.parseVehicleCompactDescr(key)
                return _offhangarVehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
            except Exception:
                return None
        return None

    def _offhangarFindSeasonsInMapping(mapping, vehIntCD):
        try:
            seasons = mapping.get(vehIntCD)
            if seasons is not None:
                return seasons
        except Exception:
            pass
        try:
            for key, value in mapping.iteritems():
                keyInt = _offhangarNormalizeVehicleKey(key)
                if keyInt is not None and keyInt == vehIntCD:
                    return value
        except Exception:
            pass
        return None

    def _offhangarGetOutfitSources():
        sources = []
        try:
            from gui.mods.offhangar.data import getAppliedOutfitsCache
            sources.append(getAppliedOutfitsCache())
        except Exception:
            pass
        try:
            from helpers import dependency
            from skeletons.gui.shared import IItemsCache
            from constants import CustomizationInvData
            from gui.shared.gui_items import GUI_ITEM_TYPE
            itemsCache = dependency.instance(IItemsCache)
            if itemsCache is not None:
                invData = itemsCache.items.inventory.getCacheValue(GUI_ITEM_TYPE.CUSTOMIZATION, {})
                sources.append(invData.get(CustomizationInvData.OUTFITS, {}))
        except Exception:
            pass
        return sources

    def _offhangarFindAppliedSeasons(vehIntCD):
        for source in _offhangarGetOutfitSources():
            if not isinstance(source, dict):
                continue
            seasons = _offhangarFindSeasonsInMapping(source, vehIntCD)
            if seasons:
                return seasons
        return {}

    _origGetBattleOutfit = _customizations_module.getBattleOutfit

    def _offhangarGetBattleOutfit(getter, vehType, arenaKind, bonusType):
        result = None
        try:
            result = _origGetBattleOutfit(getter, vehType, arenaKind, bonusType)
        except Exception:
            result = None
        if result:
            return result
        try:
            vehIntCD = _offhangarBattleVehicleIntCD(vehType)
            if not vehIntCD:
                return _OffhangarCustomizationOutfit()
            seasons = _offhangarFindAppliedSeasons(vehIntCD)
            if not seasons:
                return _OffhangarCustomizationOutfit()
            season = _offhangarSeasonType.fromArenaKind(arenaKind)
            outfitDescr = seasons.get(season)
            if not outfitDescr:
                outfitDescr = seasons.get(_offhangarSeasonType.ALL)
            if not outfitDescr and season not in seasons and _offhangarSeasonType.ALL not in seasons:
                for s in _offhangarSeasonType.SEASONS:
                    outfitDescr = seasons.get(s)
                    if outfitDescr:
                        break
            if outfitDescr:
                return _offhangarParseOutfitDescr(outfitDescr)
        except Exception:
            pass
        if result is not None:
            return result
        return _OffhangarCustomizationOutfit()

    _origGetVehicleOutfit = _customizations_module.getVehicleOutfit

    def _offhangarGetVehicleOutfit(outfits, vehTypeDescr, outfitType):
        result = ''
        try:
            result = _origGetVehicleOutfit(outfits, vehTypeDescr, outfitType)
            if result:
                return result
        except Exception:
            result = ''
        try:
            vehIntCD = _offhangarBattleVehicleIntCD(vehTypeDescr)
            if not vehIntCD or not isinstance(outfits, dict):
                return result
            seasons = _offhangarFindSeasonsInMapping(outfits, vehIntCD)
            if seasons:
                return seasons.get(outfitType, '')
        except Exception:
            pass
        return result

    _customizations_module.getBattleOutfit = _offhangarGetBattleOutfit
    _customizations_module.getVehicleOutfit = _offhangarGetVehicleOutfit

    for _offhangarModule in sys.modules.values():
        try:
            if _offhangarModule is None:
                continue
            if getattr(_offhangarModule, 'getBattleOutfit', None) is _origGetBattleOutfit:
                _offhangarModule.getBattleOutfit = _offhangarGetBattleOutfit
        except Exception:
            pass
        try:
            if getattr(_offhangarModule, 'getVehicleOutfit', None) is _origGetVehicleOutfit:
                _offhangarModule.getVehicleOutfit = _offhangarGetVehicleOutfit
        except Exception:
            pass
except Exception:
    LOG_CURRENT_EXCEPTION()

LOG_DEBUG('mod_offhangar: all overrides applied successfully')

