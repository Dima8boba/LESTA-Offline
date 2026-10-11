import sys
import math
import Math
import BigWorld
import CommandMapping
from items import vehicles as items_vehicles
from debug_utils import LOG_CURRENT_EXCEPTION
try:
    import gui.mods.offhangar.physics as offhangar_physics
except Exception:
    offhangar_physics = None
try:
    from CurrentVehicle import g_currentVehicle
except Exception:
    g_currentVehicle = None
try:
    import gui.mods.offhangar.data as offhangar_data
except Exception:
    offhangar_data = None
try:
    import AreaDestructibles
    import DestructiblesCache
    from constants import DESTRUCTIBLE_MATKIND
except Exception:
    AreaDestructibles = None
    DestructiblesCache = None
    DESTRUCTIBLE_MATKIND = None
import random 
try:
    import gui.mods.offhangar.armour as offhangar_armour
except Exception:
    offhangar_armour = None
_bots = {}
_ammo_ctrl = None
_player_vehicle_id = 0
_initialized_for_vehicle = 0
_tick_id = None
_offlineScore = {'damageDealt': 0, 'kills': 0, 'frags': 0}
_destr_broken = set()

_gunParams = {}
_reloadState = {
    'isReloading': False,
    'mode': 'none',
    'startTime': 0.0,
    'duration': 0.0,
    'isPartial': False,
    'partialCount': 0,
    'baseTime': 0.0,
}
_fireState = {
    'nextShotTime': 0.0,
    'fireTriggered': False,
    'burstRemaining': 0,
    'burstNextTime': 0.0,
}
_reloadKeyTriggered = False


def registerBot(vehID, team):
    _bots[vehID] = team


def unregisterBot(vehID):
    _bots.pop(vehID, None)


def clearBots():
    global _offlineScore
    _bots.clear()
    _offlineScore = {'damageDealt': 0, 'kills': 0, 'frags': 0}
    _destr_broken.clear()


def _processDelayer(ctrl, name):
    try:
        ctrl.processDelayer(name)
    except Exception:
        pass


def _normalizeAmmoLayout(layout):
    if not layout:
        return []
    if isinstance(layout, dict):
        return list(layout.items())
    try:
        layout = tuple(layout)
    except Exception:
        return []
    if not layout:
        return []
    first = layout[0]
    if isinstance(first, (list, tuple)) and len(first) == 2:
        return [(item[0], item[1]) for item in layout]
    result = []
    for idx in xrange(0, len(layout), 2):
        if idx + 1 < len(layout):
            result.append((layout[idx], layout[idx + 1]))
    return result

class _FakeMissing(object):
    def call(self, *args, **kwargs):
        return False

    def __call__(self, *args, **kwargs):  
        return False

    def __nonzero__(self):
        return False

    def __bool__(self):
        return False


class _FakeDamageExtra(object):
    def __init__(self, damage):
        self._damage = int(max(0, damage))

    def getDamage(self):
        return self._damage

    def isNone(self):
        return False

    def isSpawnedBotExplosion(self, primary=True):
        return False

    def isSpawnedBotRam(self, primary=True):
        return False

    def isFire(self):
        return False

    def isBerserker(self):
        return False

    def isMinefield(self):
        return False

    def isDamagingSmoke(self):
        return False

    def isCorrodingShot(self):
        return False

    def isFireCircle(self):
        return False

    def isThunderStrike(self):
        return False

    def isRam(self):
        return False

    def isShot(self):
        return True

    def isWorldCollision(self):
        return False

    def isDeathZone(self):
        return False

    def isStaticDeathZone(self):
        return False

    def isShellGold(self):
        return False

    def isProtectionZoneDamage(self, primary=True):
        return False

    def isArtilleryEqDamage(self, primary=True):
        return False

    def isBomberEqDamage(self, primary=True):
        return False

    def isBombersDamage(self, primary=True):
        return False

    def isMineFieldDamage(self, primary=True):
        return False

    def isFortArtilleryEqDamage(self, primary=True):
        return False

    def getShellType(self):
        return 0

    def isClingBrander(self):
        return False

    def isClingBranderRam(self):
        return False

    def __getattr__(self, name):
        return _FakeMissing()


class _FakeDamageFeedbackEvent(object):
    def __init__(self, eventType, targetID, extra, battleEventType=0):
        self._eventType = eventType
        self._targetID = targetID
        self._extra = extra
        self._battleEventType = battleEventType

    def getType(self):
        return self._eventType

    def getTargetID(self):
        return self._targetID

    def getExtra(self):
        return self._extra

    def getBattleEventType(self):
        return self._battleEventType

    def __getattr__(self, name):
        return _FakeMissing()


def _getShotAttackReason():
    try:
        from constants import ATTACK_REASON_INDICES
        return ATTACK_REASON_INDICES.get('SHOT', 0)
    except Exception:
        return 0


def _getVehicleTeam(vehicleID):
    player = BigWorld.player()
    if player is None:
        return 0
    arena = getattr(player, 'arena', None)
    if arena is not None:
        vehInfo = arena.vehicles.get(vehicleID)
        if vehInfo is not None:
            team = vehInfo.get('team', 0)
            if team:
                try:
                    return int(team)
                except Exception:
                    return 0
    team = _bots.get(vehicleID, 0)
    if team:
        try:
            return int(team)
        except Exception:
            return 0
    if vehicleID == getattr(player, 'playerVehicleID', 0):
        team = getattr(player, 'team', 0)
        if team:
            try:
                return int(team)
            except Exception:
                return 0
    return 0


def _pushDamageFeedback(targetID, damage, attackReason):
    player = BigWorld.player()
    if player is None:
        return
    try:
        damage = int(max(0, damage))
    except Exception:
        damage = 0
    if damage <= 0:
        return
    eventType = None
    try:
        from gui.battle_control.battle_constants import FEEDBACK_EVENT_ID
        eventType = getattr(FEEDBACK_EVENT_ID, 'PLAYER_DAMAGED_HP_ENEMY', None)
        if eventType is None:
            eventType = getattr(FEEDBACK_EVENT_ID, 'PLAYER_DAMAGED_ENEMY', None)
    except Exception:
        eventType = None
    if eventType is None:
        return
    sp = getattr(player, 'guiSessionProvider', None)
    if sp is None:
        return
    shared = getattr(sp, 'shared', None)
    if shared is None:
        return
    extra = _FakeDamageExtra(damage)
    event = _FakeDamageFeedbackEvent(eventType, targetID, extra, attackReason)
    feedback = getattr(shared, 'feedback', None)
    if feedback is not None and hasattr(feedback, 'onPlayerFeedbackReceived'):
        try:
            feedback.onPlayerFeedbackReceived([event])
            return
        except Exception:
            LOG_CURRENT_EXCEPTION()
    ctrl = getattr(shared, 'personalEfficiencyCtrl', None)
    if ctrl is not None and hasattr(ctrl, '_onPlayerFeedbackReceived'):
        try:
            ctrl._onPlayerFeedbackReceived([event])
        except Exception:
            LOG_CURRENT_EXCEPTION()


def _ensureArenaStatistics(player):
    arena = getattr(player, 'arena', None)
    if arena is None:
        return None
    stats = getattr(arena, 'statistics', None)
    if stats is None:
        stats = {}
        try:
            arena.statistics = stats
        except Exception:
            return None
    return stats


def _addVehicleStat(attackerID, statName, value):
    player = BigWorld.player()
    if player is None:
        return
    stats = _ensureArenaStatistics(player)
    if stats is None:
        return
    vStats = stats.get(attackerID)
    if vStats is None:
        vStats = {}
        stats[attackerID] = vStats
    try:
        current = int(vStats.get(statName, 0))
    except Exception:
        current = 0
    try:
        add = int(value)
    except Exception:
        add = 0
    if add == 0:
        return
    vStats[statName] = current + add
    arena = getattr(player, 'arena', None)
    notified = False
    if arena is not None and hasattr(arena, 'onVehicleStatisticsUpdate'):
        try:
            arena.onVehicleStatisticsUpdate(attackerID)
            notified = True
        except Exception:
            LOG_CURRENT_EXCEPTION()
    if not notified:
        try:
            sp = getattr(player, 'guiSessionProvider', None)
            if sp is not None:
                arenaDP = sp.getArenaDP()
                if arenaDP is not None:
                    arenaDP.updateVehicleStats(attackerID, {statName: vStats[statName]})
        except Exception:
            LOG_CURRENT_EXCEPTION()

def _isPlayerVehicle(vehicleID):
    player = BigWorld.player()
    if player is None:
        return False
    return vehicleID == getattr(player, 'playerVehicleID', 0)


def _applyDamageToPlayer(vehicleID, damage, attackerID):
    player = BigWorld.player()
    vehicle = BigWorld.entity(vehicleID)
    if player is None or vehicle is None:
        return

    oldHealth = getattr(vehicle, 'health', 0)
    if oldHealth <= 0:
        return

    try:
        damage = int(max(0, damage))
    except Exception:
        damage = 0

    newHealth = max(0, oldHealth - damage)
    actualDamage = max(0, oldHealth - newHealth)
    reason = _getShotAttackReason()

    if actualDamage > 0:
        _addVehicleStat(attackerID, 'damageDealt', actualDamage)

    try:
        vehicle.health = newHealth
    except Exception:
        pass

    try:
        vehicle.isCrewActive = newHealth > 0
    except Exception:
        pass

    arena = getattr(player, 'arena', None)
    if arena is not None:
        vehInfo = arena.vehicles.get(vehicleID)
        if vehInfo is not None:
            vehInfo['health'] = newHealth
            vehInfo['isAlive'] = newHealth > 0

    try:
        import gui.mods.offhangar.physics as _ph
        _ph.set_control(vehicleID, forward=0, rotation=0)
    except Exception:
        pass

    try:
        sp = getattr(player, 'guiSessionProvider', None)
        if sp is not None:
            sp.setVehicleHealth(True, vehicleID, newHealth, attackerID, reason)
    except Exception:
        pass

    try:
        vehicle.onHealthChanged(newHealth, oldHealth, attackerID, reason)
    except Exception:
        pass

    appearance = getattr(vehicle, 'appearance', None)
    if appearance is not None and hasattr(appearance, 'onVehicleHealthChanged'):
        try:
            appearance.onVehicleHealthChanged(True)
        except Exception:
            pass

    if newHealth <= 0:
        try:
            player._PlayerAvatar__isVehicleAlive = False
        except Exception:
            pass

        if not getattr(vehicle, '_offhangar_deathHandled', False):
            try:
                vehicle._offhangar_deathHandled = True
                inputHandler = getattr(player, 'inputHandler', None)
                if inputHandler is not None:
                    inputHandler.onVehicleDeath(vehicle, False)
            except Exception:
                pass

        _notifyArenaVehicleKilled(vehicleID, attackerID)

        attackerTeam = _getVehicleTeam(attackerID)
        targetTeam = _getVehicleTeam(vehicleID)
        isAlly = bool(attackerTeam and targetTeam and attackerTeam == targetTeam)
        fragDelta = -1 if isAlly else 1
        _addVehicleStat(attackerID, 'frags', fragDelta)

def _isPlayerVehicle(vehicleID):
    player = BigWorld.player()
    if player is None:
        return False
    return vehicleID == getattr(player, 'playerVehicleID', 0)


def _applyDamageToPlayer(vehicleID, damage, attackerID):
    player = BigWorld.player()
    vehicle = BigWorld.entity(vehicleID)
    if player is None or vehicle is None:
        return

    oldHealth = getattr(vehicle, 'health', 0)
    if oldHealth <= 0:
        return

    try:
        damage = int(max(0, damage))
    except Exception:
        damage = 0

    newHealth = max(0, oldHealth - damage)
    actualDamage = max(0, oldHealth - newHealth)
    if actualDamage <= 0:
        return

    reason = _getShotAttackReason()

    _addVehicleStat(attackerID, 'damageDealt', actualDamage)

    try:
        vehicle.health = newHealth
    except Exception:
        pass

    try:
        vehicle.isCrewActive = newHealth > 0
    except Exception:
        pass

    arena = getattr(player, 'arena', None)
    if arena is not None:
        vehInfo = arena.vehicles.get(vehicleID)
        if vehInfo is not None:
            vehInfo['health'] = newHealth
            vehInfo['isAlive'] = newHealth > 0
        try:
            arena.onVehicleHealthChanged(vehicleID, attackerID, actualDamage)
        except Exception:
            pass

    try:
        import gui.mods.offhangar.physics as _ph
        _ph.set_control(vehicleID, forward=0, rotation=0)
    except Exception:
        pass

    try:
        player._PlayerAvatar__initProgress |= 32
    except Exception:
        pass

    try:
        player.updateVehicleHealth(vehicleID, newHealth, reason, newHealth > 0, False)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        vehicle.onHealthChanged(newHealth, oldHealth, attackerID, reason)
    except Exception:
        pass

    appearance = getattr(vehicle, 'appearance', None)
    if appearance is not None and hasattr(appearance, 'onVehicleHealthChanged'):
        try:
            appearance.onVehicleHealthChanged(True)
        except Exception:
            pass

    if newHealth <= 0:
        try:
            player._PlayerAvatar__isVehicleAlive = False
        except Exception:
            pass

        try:
            vehicle._Vehicle__onVehicleDeath(True)
        except Exception:
            pass

        try:
            from gui.battle_control.battle_constants import VEHICLE_VIEW_STATE
            sp = getattr(player, 'guiSessionProvider', None)
            if sp is not None:
                sp.invalidateVehicleState(VEHICLE_VIEW_STATE.DESTROYED, reason, vehicleID)
                sp.switchToPostmortem(True, False)
        except Exception:
            pass

        try:
            inputHandler = getattr(player, 'inputHandler', None)
            if inputHandler is not None:
                inputHandler.setKillerVehicleID(attackerID)
                if getattr(inputHandler, 'ctrlModeName', None) != 'postMortem':
                    inputHandler.activatePostmortem(False)
        except Exception:
            pass

        try:
            player._PlayerAvatar__onArenaVehicleKilled(vehicleID, attackerID, 0, reason, 0)
        except Exception:
            pass

        if arena is not None:
            vehInfo = arena.vehicles.get(vehicleID)
            if vehInfo is not None:
                vehInfo['isAlive'] = False

        try:
            sp = getattr(player, 'guiSessionProvider', None)
            if sp is not None:
                arenaDP = sp.getArenaDP()
                if arenaDP is not None:
                    arenaDP.updateVehicleStatus(vehicleID, {'isAlive': False})
        except Exception:
            pass

        attackerTeam = _getVehicleTeam(attackerID)
        targetTeam = _getVehicleTeam(vehicleID)
        isAlly = bool(attackerTeam and targetTeam and attackerTeam == targetTeam)
        fragDelta = -1 if isAlly else 1
        _addVehicleStat(attackerID, 'frags', fragDelta)

def _applyDamage(botID, damage, attackerID):
    if _isPlayerVehicle(botID):
        _applyDamageToPlayer(botID, damage, attackerID)
        return

    bot = BigWorld.entity(botID)
    if bot is None:
        return
    oldHealth = getattr(bot, 'health', 0)
    if oldHealth <= 0:
        return
    try:
        damage = int(max(0, damage))
    except Exception:
        damage = 0
    newHealth = max(0, oldHealth - damage)
    actualDamage = max(0, oldHealth - newHealth)
    isDying = newHealth <= 0
    reason = _getShotAttackReason()
    if isDying:
        try:
            import gui.mods.offhangar.physics as _ph
            _ph.set_control(botID, forward=0, rotation=0)
            _ph.remove_body(botID)
        except Exception:
            LOG_CURRENT_EXCEPTION()
    try:
        bot.health = newHealth
    except Exception:
        pass
    try:
        bot.onHealthChanged(newHealth, oldHealth, attackerID, reason)
    except Exception:
        LOG_CURRENT_EXCEPTION()
    player = BigWorld.player()
    arena = getattr(player, 'arena', None)
    if arena is not None:
        vehInfo = arena.vehicles.get(botID)
        if vehInfo is not None:
            vehInfo['health'] = newHealth
            vehInfo['isAlive'] = newHealth > 0
    attackerTeam = _getVehicleTeam(attackerID)
    if not attackerTeam:
        try:
            attackerTeam = int(getattr(player, 'team', 0) or 0)
        except Exception:
            attackerTeam = 0
    targetTeam = _getVehicleTeam(botID)
    isAlly = bool(attackerTeam and targetTeam and attackerTeam == targetTeam)
    if actualDamage > 0:
        if attackerID == getattr(player, 'playerVehicleID', 0) and not isAlly:
            _pushDamageFeedback(botID, actualDamage, reason)
        if not isAlly:
            _addVehicleStat(attackerID, 'damageDealt', actualDamage)
    if isDying:
        try:
            if getattr(bot, 'isCrewActive', True):
                bot.isCrewActive = False
        except Exception:
            LOG_CURRENT_EXCEPTION()
        fragDelta = -1 if isAlly else 1
        _notifyArenaVehicleKilled(botID, attackerID)
        _addVehicleStat(attackerID, 'frags', fragDelta)
        unregisterBot(botID)
        try:
            import gui.mods.offhangar.physics as _ph
            _ph.remove_body(botID)
        except Exception:
            pass
        try:
            botsModule = sys.modules.get('gui.mods.offhangar.bots')
            if botsModule is not None:
                botList = getattr(botsModule, '_botVehicleIDs', None)
                if botList is not None and botID in botList:
                    botList.remove(botID)
        except Exception:
            pass


def _notifyArenaVehicleKilled(botID, attackerID):
    player = BigWorld.player()
    if player is None:
        return
    arena = getattr(player, 'arena', None)
    if arena is None:
        return
    reason = _getShotAttackReason()
    vehInfo = arena.vehicles.get(botID)
    if vehInfo is not None:
        vehInfo['isAlive'] = False
    try:
        arena.onVehicleKilled(botID, attackerID, 0, reason, 0)
    except Exception:
        LOG_CURRENT_EXCEPTION()
    try:
        sp = getattr(player, 'guiSessionProvider', None)
        if sp is not None:
            arenaDP = sp.getArenaDP()
            if arenaDP is not None:
                arenaDP.updateVehicleStatus(botID, {'isAlive': False})
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _getDestructiblesManagers():
    if AreaDestructibles is None:
        return None, None
    manager = getattr(AreaDestructibles, 'g_destructiblesManager', None)
    cache = getattr(AreaDestructibles, 'g_cache', None)
    if manager is None or cache is None:
        try:
            AreaDestructibles.init()
        except Exception:
            pass
        manager = getattr(AreaDestructibles, 'g_destructiblesManager', None)
        cache = getattr(AreaDestructibles, 'g_cache', None)
    return manager, cache


def _ensureChunkLoaded(manager, chunkID):
    loaded = getattr(manager, '_DestructiblesManager__loadedChunkIDs', None)
    if loaded is None:
        loaded = getattr(manager, 'loadedChunkIDs', None)
    if loaded is None:
        return
    if chunkID not in loaded:
        try:
            loaded[chunkID] = 1024
        except Exception:
            pass


def _isDestructibleShotBroken(manager, chunkID, destrIndex, matKind, destrType):
    key = (chunkID, destrIndex, matKind, destrType)
    if key in _destr_broken:
        return True
    try:
        ctrl = manager.getController(chunkID)
        if ctrl is not None and ctrl.isDestructibleBroken(destrIndex, matKind, destrType):
            _destr_broken.add(key)
            return True
    except Exception:
        pass
    return False


def _markDestructibleShotBroken(chunkID, destrIndex, matKind, destrType):
    _destr_broken.add((chunkID, destrIndex, matKind, destrType))


def _orderDestructibleShotDestroy(manager, spaceID, chunkID, destrIndex, destrType, matKind, directionYaw, damage):
    if DestructiblesCache is None:
        return
    try:
        fallSpeed = int(min(3, max(0, abs(damage) / 250.0)))
    except Exception:
        fallSpeed = 1
    try:
        if destrType == DestructiblesCache.DESTR_TYPE_TREE:
            pitchConstr = math.pi / 2.0
            try:
                res = BigWorld.getDestructibleFallPitchConstr(spaceID, chunkID, destrIndex, directionYaw)
                if res is not None:
                    pitchConstr = float(res[0])
            except Exception:
                pass
            data = DestructiblesCache.encodeFallenTree(destrIndex, directionYaw, pitchConstr, fallSpeed)
            manager.orderDestructibleDestroy(chunkID, destrType, data, True, False)
        elif destrType == DestructiblesCache.DESTR_TYPE_FALLING_ATOM:
            data = DestructiblesCache.encodeFallenColumn(destrIndex, directionYaw, fallSpeed)
            manager.orderDestructibleDestroy(chunkID, destrType, data, True, False)
        elif destrType == DestructiblesCache.DESTR_TYPE_FRAGILE:
            data = DestructiblesCache.encodeFragile(destrIndex, True)
            manager.orderDestructibleDestroy(chunkID, destrType, data, True, False)
        elif destrType == DestructiblesCache.DESTR_TYPE_STRUCTURE:
            data = DestructiblesCache.encodeDestructibleModule(destrIndex, matKind, True)
            manager.orderDestructibleDestroy(chunkID, destrType, data, True, False)
        else:
            return
        _markDestructibleShotBroken(chunkID, destrIndex, matKind, destrType)
    except Exception:
        pass


def _getHangarAmmoLayout(vehicle):
    try:
        item = getattr(g_currentVehicle, 'item', None)
        if item is not None:
            installed = getattr(getattr(item, 'shells', None), 'installed', None)
            if installed is not None:
                shells = installed.getItems()
                if shells:
                    return _normalizeAmmoLayout(shells)
            invID = getattr(item, 'invID', 0)
            if offhangar_data is not None:
                stored = getattr(offhangar_data, '_vehicleShellsByInvID', {}).get(invID, [])
                if stored:
                    return _normalizeAmmoLayout(stored)
    except Exception:
        LOG_CURRENT_EXCEPTION()
    try:
        player = BigWorld.player()
        arena = getattr(player, 'arena', None)
        vehID = getattr(player, 'playerVehicleID', 0)
        if arena is not None and vehID:
            vehInfo = arena.vehicles.get(vehID, {})
            invID = vehInfo.get('invID', 0)
            if offhangar_data is not None:
                stored = getattr(offhangar_data, '_vehicleShellsByInvID', {}).get(invID, [])
                if stored:
                    return _normalizeAmmoLayout(stored)
    except Exception:
        LOG_CURRENT_EXCEPTION()
    try:
        descriptor = getattr(vehicle, 'typeDescriptor', None)
        if descriptor is not None:
            return _normalizeAmmoLayout(items_vehicles.getDefaultAmmoForGun(descriptor.gun))
    except Exception:
        LOG_CURRENT_EXCEPTION()
    return []


def _updateConsumablesPanel(ctrl, intCD, quantity, quantityInClip):
    try:
        from helpers import dependency
        from skeletons.gui.battle_session import IBattleSessionProvider
        sp = dependency.instance(IBattleSessionProvider)
        if sp is None:
            return
        panel = getattr(sp, '_BattleSessionProvider__consumablesPanel', None)
        if panel is None:
            panel = getattr(sp, '_shared__consumablesPanel', None)
        if panel is None:
            return
        cds = getattr(panel, '_cds', {})
        if intCD not in cds:
            descriptor = None
            gunSettings = None
            try:
                gunSettings = ctrl.getGunSettings()
                data = gunSettings.shots.get(intCD)
                if data is not None:
                    descriptor = data[3]
            except Exception:
                descriptor = None
            if descriptor is not None:
                try:
                    panel._onShellsAdded(intCD, descriptor, quantity, quantityInClip, gunSettings)
                except Exception:
                    pass
        if intCD in getattr(panel, '_cds', {}):
            try:
                panel._onShellsUpdated(intCD, quantity, quantityInClip)
            except Exception:
                pass
            try:
                panel._onCurrentShellChanged(intCD)
            except Exception:
                pass
    except Exception:
        pass


def _readGunParams(gun, vehicle):
    clipSize = 1
    burstSize = 1
    burstInterval = 0.0
    reloadTime = 2.5
    isClipGun = False
    isBurst = False
    isAutoReload = False
    autoReloadTimes = ()
    isAutoShoot = False
    autoShootInterval = 0.1
    isDualGun = False
    try:
        clip = getattr(gun, 'clip', None)
        if clip is not None and len(clip) >= 2:
            clipSize = int(clip[0])
            burstInterval = float(clip[1])
            if clipSize > 1:
                isClipGun = True
    except Exception:
        pass
    try:
        burst = getattr(gun, 'burst', None)
        if burst is not None and len(burst) >= 2:
            burstSize = int(burst[0])
            if burstSize > 1:
                isBurst = True
    except Exception:
        pass
    try:
        rt = float(gun.reloadTime)
        if rt > 0.0:
            reloadTime = rt
    except Exception:
        pass
    try:
        td = getattr(vehicle, 'typeDescriptor', None)
        if td is not None:
            isAutoShoot = bool(getattr(td, 'isAutoShootGunVehicle', False))
            isDualGun = bool(getattr(td, 'isDualgunVehicle', False))
            isAutoReload = bool(getattr(td, 'isAutoReloadGun', False))
    except Exception:
        pass
    tags = getattr(gun, 'tags', set())
    if not isAutoReload:
        try:
            isAutoReload = 'autoreload' in tags
        except Exception:
            pass
    if isAutoReload:
        try:
            ar = getattr(gun, 'autoreload', None)
            if ar is not None:
                rt = getattr(ar, 'reloadTime', None)
                if rt is not None:
                    autoReloadTimes = tuple(rt)
        except Exception:
            pass
        if not autoReloadTimes:
            autoReloadTimes = tuple(reloadTime for _ in xrange(clipSize))
    if isAutoShoot:
        try:
            autoShoot = getattr(gun, 'autoShoot', None)
            if autoShoot is not None:
                interval = float(getattr(autoShoot, 'shotInterval', 0.1))
                if interval > 0.0:
                    autoShootInterval = interval
        except Exception:
            pass
    return {
        'clipSize': max(1, clipSize),
        'burstSize': max(1, burstSize),
        'burstInterval': burstInterval,
        'reloadTime': reloadTime,
        'isClipGun': isClipGun,
        'isBurst': isBurst,
        'isAutoReload': isAutoReload,
        'autoReloadTimes': autoReloadTimes,
        'isAutoShoot': isAutoShoot,
        'autoShootInterval': autoShootInterval,
        'isDualGun': isDualGun,
    }


def _getAutoReloadTime(qc, clipSize, times):
    if not times:
        return 2.5
    idx = clipSize - 1 - qc
    idx = max(0, min(idx, len(times) - 1))
    return times[idx]


def _getShellIntCD():
    if _ammo_ctrl is None:
        return None
    try:
        intCD = _ammo_ctrl.getCurrentShellCD()
        if intCD is not None:
            return intCD
    except Exception:
        pass
    try:
        for intCD in _ammo_ctrl.getShellsOrderIter():
            return intCD
    except Exception:
        pass
    return None


def _setPanelReload(timeLeft, baseTime):
    if _ammo_ctrl is None:
        return
    try:
        _ammo_ctrl.setGunReloadTime(timeLeft, baseTime)
    except Exception:
        pass


def _setPanelAutoReload(timeLeft, baseTime, firstTime):
    if _ammo_ctrl is None:
        return
    try:
        _ammo_ctrl.setGunAutoReloadTime(timeLeft, baseTime, firstTime, False, True)
    except Exception:
        pass


def _startClipReload(duration=None):
    global _reloadState
    if _reloadState['isReloading']:
        return
    if duration is None:
        duration = _gunParams.get('reloadTime', 2.5)
    if duration <= 0.0:
        return
    _reloadState = {
        'isReloading': True,
        'mode': 'clipFull',
        'startTime': BigWorld.time(),
        'duration': duration,
        'isPartial': False,
        'partialCount': 0,
        'baseTime': duration,
    }
    _setPanelReload(duration, duration)


def _startAutoReloadStep(intCD):
    global _reloadState
    if _reloadState['isReloading']:
        return
    try:
        q, qc = _ammo_ctrl.getShells(intCD)
    except Exception:
        return
    clipSize = _gunParams.get('clipSize', 1)
    times = _gunParams.get('autoReloadTimes', ())
    if qc >= clipSize or q <= qc:
        return
    t = _getAutoReloadTime(qc, clipSize, times)
    _reloadState = {
        'isReloading': True,
        'mode': 'autoReload',
        'startTime': BigWorld.time(),
        'duration': t,
        'isPartial': False,
        'partialCount': 0,
        'baseTime': t,
    }
    _setPanelAutoReload(t, t, t)


def _finishAutoReloadStep(intCD):
    global _reloadState
    try:
        q, qc = _ammo_ctrl.getShells(intCD)
    except Exception:
        _reloadState['isReloading'] = False
        return
    clipSize = _gunParams.get('clipSize', 1)
    if qc < clipSize and q > qc:
        qc += 1
        try:
            _ammo_ctrl.setShells(intCD, q, qc)
        except Exception:
            pass
        _updateConsumablesPanel(_ammo_ctrl, intCD, q, qc)
    _reloadState['isReloading'] = False
    if qc < clipSize and q > qc:
        _startAutoReloadStep(intCD)
    else:
        _setPanelAutoReload(0.0, 0.0, 0.0)


def _startPartialReload():
    global _reloadState
    if _reloadState['isReloading']:
        return
    if not _gunParams.get('isClipGun', False):
        return
    if _gunParams.get('isAutoReload', False):
        return
    intCD = _getShellIntCD()
    if intCD is None:
        return
    try:
        q, qc = _ammo_ctrl.getShells(intCD)
    except Exception:
        return
    clipSize = _gunParams.get('clipSize', 1)
    reserve = max(0, q - qc)
    missing = min(clipSize - qc, reserve)
    if missing <= 0:
        return
    reloadTime = _gunParams.get('reloadTime', 2.5)
    duration = reloadTime * float(missing) / float(clipSize)
    _reloadState = {
        'isReloading': True,
        'mode': 'partial',
        'startTime': BigWorld.time(),
        'duration': duration,
        'isPartial': True,
        'partialCount': missing,
        'baseTime': reloadTime,
    }
    _setPanelReload(duration, reloadTime)


def _finishReload():
    global _reloadState
    if not _reloadState['isReloading']:
        return
    mode = _reloadState['mode']
    _reloadState['isReloading'] = False
    intCD = _getShellIntCD()
    if intCD is None:
        return
    if mode == 'autoReload':
        _finishAutoReloadStep(intCD)
        return
    try:
        q, qc = _ammo_ctrl.getShells(intCD)
    except Exception:
        return
    clipSize = _gunParams.get('clipSize', 1)
    if mode == 'partial':
        if _gunParams.get('isClipGun', False):
            reserve = max(0, q - qc)
            add = min(_reloadState['partialCount'], reserve, max(0, clipSize - qc))
            if add > 0:
                qc += add
                try:
                    _ammo_ctrl.setShells(intCD, q, qc)
                except Exception:
                    pass
                _updateConsumablesPanel(_ammo_ctrl, intCD, q, qc)
    elif mode == 'clipFull':
        if _gunParams.get('isClipGun', False):
            qc = min(q, clipSize)
            try:
                _ammo_ctrl.setShells(intCD, q, qc)
            except Exception:
                pass
            _updateConsumablesPanel(_ammo_ctrl, intCD, q, qc)
    _reloadState['isPartial'] = False
    _reloadState['partialCount'] = 0
    _reloadState['mode'] = 'none'
    _setPanelReload(0.0, 0.0)


def _updateReloads():
    global _reloadState
    if not _reloadState['isReloading']:
        return
    now = BigWorld.time()
    elapsed = now - _reloadState['startTime']
    if elapsed >= _reloadState['duration']:
        _finishReload()


def _initAmmoController(player, vehicle):
    global _ammo_ctrl
    global _player_vehicle_id
    global _initialized_for_vehicle
    global _gunParams
    global _reloadState
    global _fireState
    descriptor = getattr(vehicle, 'typeDescriptor', None)
    if descriptor is None:
        descriptor = getattr(player, 'vehicleTypeDescriptor', None)
    if descriptor is None:
        return False
    gun = getattr(descriptor, 'gun', None)
    if gun is None:
        return False
    sp = getattr(player, 'guiSessionProvider', None)
    if sp is None:
        return False
    ctrl = getattr(sp.shared, 'ammo', None)
    if ctrl is None:
        return False
    try:
        ctrl.startControl()
    except Exception:
        pass
    try:
        ctrl.setGunSettings(gun)
    except Exception:
        return False
    _processDelayer(ctrl, 'setGunSettings')
    _gunParams = _readGunParams(gun, vehicle)
    _reloadState = {
        'isReloading': False,
        'mode': 'none',
        'startTime': 0.0,
        'duration': 0.0,
        'isPartial': False,
        'partialCount': 0,
        'baseTime': 0.0,
    }
    _fireState = {
        'nextShotTime': 0.0,
        'fireTriggered': False,
        'burstRemaining': 0,
        'burstNextTime': 0.0,
    }
    layout = _getHangarAmmoLayout(vehicle)
    if not layout:
        try:
            layout = _normalizeAmmoLayout(items_vehicles.getUniformAmmoForGun(gun))
        except Exception:
            layout = []
    clipSize = _gunParams['clipSize']
    firstCD = None
    currentCD = None
    for intCD, count in layout:
        try:
            count = int(count)
        except Exception:
            count = 0
        if count < 0:
            count = 0
        try:
            ctrl.setShells(intCD, count, min(count, clipSize))
        except Exception:
            pass
        if firstCD is None:
            firstCD = intCD
        if currentCD is None and count > 0:
            currentCD = intCD
    _processDelayer(ctrl, 'setShells')
    if currentCD is None:
        currentCD = firstCD
    if currentCD is not None:
        try:
            ctrl.setCurrentShellCD(currentCD)
        except Exception:
            pass
        _processDelayer(ctrl, 'setCurrentShellCD')
    try:
        ctrl.setGunReloadTime(0.0, 0.0)
    except Exception:
        pass
    _ammo_ctrl = ctrl
    _player_vehicle_id = vehicle.id
    _initialized_for_vehicle = vehicle.id
    if _gunParams['isAutoReload']:
        try:
            q, qc = ctrl.getShells(currentCD)
            _updateConsumablesPanel(ctrl, currentCD, q, qc)
            if qc < clipSize and q > qc:
                _startAutoReloadStep(currentCD)
        except Exception:
            pass
    else:
        try:
            q, qc = ctrl.getShells(currentCD)
            _updateConsumablesPanel(ctrl, currentCD, q, qc)
        except Exception:
            pass
    return True


def _clearAmmoController():
    global _ammo_ctrl
    global _player_vehicle_id
    global _initialized_for_vehicle
    global _gunParams
    global _reloadState
    global _fireState
    if _ammo_ctrl is not None:
        try:
            _ammo_ctrl.stopControl()
        except Exception:
            pass
    _ammo_ctrl = None
    _player_vehicle_id = 0
    _initialized_for_vehicle = 0
    _gunParams = {}
    _reloadState = {
        'isReloading': False,
        'mode': 'none',
        'startTime': 0.0,
        'duration': 0.0,
        'isPartial': False,
        'partialCount': 0,
        'baseTime': 0.0,
    }
    _fireState = {
        'nextShotTime': 0.0,
        'fireTriggered': False,
        'burstRemaining': 0,
        'burstNextTime': 0.0,
    }


def _getMuzzleAndTarget(player, vehicle):
    muzzle = None
    if offhangar_physics is not None:
        try:
            body = offhangar_physics.world.bodies.get(vehicle.id)
            if body is not None:
                fwd_x = math.sin(body.yaw) * 3.0
                fwd_z = math.cos(body.yaw) * 3.0
                muzzle = Math.Vector3(body.x + fwd_x, body.y + 2.0, body.z + fwd_z)
        except Exception:
            pass
    if muzzle is None or muzzle.length < 0.1:
        try:
            m = Math.Matrix(vehicle.matrix)
            if m.translation.length > 0.1:
                muzzle = m.translation + Math.Vector3(0.0, 2.0, 0.0)
        except Exception:
            pass
    if muzzle is None or muzzle.length < 0.1:
        try:
            pos = Math.Vector3(vehicle.position)
            if pos.length > 0.1:
                muzzle = pos + Math.Vector3(0.0, 2.0, 0.0)
        except Exception:
            pass
    if muzzle is None or muzzle.length < 0.1:
        try:
            pos = Math.Vector3(player.position)
            if pos.length > 0.1:
                muzzle = pos + Math.Vector3(0.0, 2.0, 0.0)
        except Exception:
            pass
    target = None
    gunRotator = getattr(player, 'gunRotator', None)
    if gunRotator is not None:
        try:
            t = getattr(gunRotator, '_VehicleGunRotator__lastShotPoint', None)
            if t is not None:
                t = Math.Vector3(t)
                if t.length > 0.1:
                    target = t
        except Exception:
            pass
        if target is None or target.length < 0.1:
            try:
                t = gunRotator.getDesiredShotPoint()
                if t is not None:
                    t = Math.Vector3(t)
                    if t.length > 0.1:
                        target = t
            except Exception:
                pass
    if target is None or target.length < 0.1:
        try:
            cam = BigWorld.camera()
            if cam is not None:
                target = Math.Vector3(cam.position) + Math.Vector3(cam.direction).scale(100.0)
        except Exception:
            pass
    if muzzle is None or target is None:
        return None, None
    if muzzle.length < 0.1 or target.length < 0.1:
        return None, None
    return muzzle, target

def _getShellDamage(intCD):
    global _ammo_ctrl
    baseDamage = 300
    try:
        shots = _ammo_ctrl.getGunSettings().shots
        data = shots.get(intCD)
        if data is not None:
            shellDescr = data[3]
            damage = getattr(shellDescr, 'damage', None)
            if damage:
                try:
                    baseDamage = float(damage[0])
                except Exception:
                    baseDamage = float(damage)
    except Exception:
        pass
    variance = random.uniform(0.75, 1.25)
    return baseDamage * variance

def _getShellFromIntCD(intCD):
    global _ammo_ctrl
    if _ammo_ctrl is None:
        return None
    try:
        shots = _ammo_ctrl.getGunSettings().shots
        data = shots.get(intCD)
        if data is not None:
            return data[3]
    except Exception:
        pass
    return None

def _getShellShot(intCD):
    global _ammo_ctrl
    if _ammo_ctrl is None:
        return None
    try:
        shots = _ammo_ctrl.getGunSettings().shots
        data = shots.get(intCD)
        if data is not None:
            return data[2]
    except Exception:
        pass
    return None


def _getShellExplosionRadius(intCD):
    global _ammo_ctrl
    if _ammo_ctrl is None:
        return 3.0
    try:
        shots = _ammo_ctrl.getGunSettings().shots
        data = shots.get(intCD)
        if data is not None:
            shellDescr = data[3]
            for attr in ('explosionRadius', 'splashRadius', 'radius'):
                value = getattr(shellDescr, attr, None)
                if value:
                    return max(1.0, float(value))
            params = getattr(shellDescr, 'params', None)
            if params is not None:
                for attr in ('explosionRadius', 'splashRadius', 'radius'):
                    value = getattr(params, attr, None)
                    if value:
                        return max(1.0, float(value))
    except Exception:
        pass
    return 3.0


def _getShotHit(player, start, end):
    spaceID = getattr(player, 'spaceID', 0)
    staticPoint = None
    staticDist = None
    excludeID = getattr(player, 'playerVehicleID', 0)
    try:
        hit = BigWorld.collideDynamicStatic(spaceID, start, end, 1, excludeID, -1, 0)
        if hit is not None:
            p = Math.Vector3(hit[0])
            d = (p - start).length
            if d > 1.0:
                staticPoint = p
                staticDist = d
    except Exception:
        pass
    bestID = None
    bestDist = None
    rayDir = end - start
    rayLen = rayDir.length
    if rayLen < 0.1:
        return bestID, bestDist, staticPoint, staticDist
    rayDir.normalise()
    for botID in tuple(_bots.keys()):
        bot = BigWorld.entity(botID)
        if bot is None:
            continue
        try:
            if getattr(bot, 'health', 1) <= 0:
                continue
        except Exception:
            continue
        botPos = None
        if offhangar_physics is not None:
            try:
                body = offhangar_physics.world.bodies.get(botID)
                if body is not None:
                    botPos = Math.Vector3(body.x, body.y, body.z)
            except Exception:
                botPos = None
        if botPos is None:
            try:
                botPos = Math.Vector3(bot.position)
                if botPos.length == 0.0:
                    botPos = None
            except Exception:
                botPos = None
        if botPos is None:
            try:
                botPos = Math.Matrix(bot.matrix).translation
                if botPos.length == 0.0:
                    botPos = None
            except Exception:
                continue
        if botPos is None:
            continue
        hitDist = None
        try:
            hits = bot.collideSegmentExt(start, end)
            if hits:
                for hit in hits:
                    d = getattr(hit, 'dist', None)
                    if d is None:
                        try:
                            d = (Math.Vector3(hit[0]) - start).length
                        except Exception:
                            continue
                    if hitDist is None or d < hitDist:
                        hitDist = d
        except Exception:
            hitDist = None
        if hitDist is None:
            try:
                toBot = botPos - start
                proj = toBot.x * rayDir.x + toBot.y * rayDir.y + toBot.z * rayDir.z
                if proj < 0.0 or proj > rayLen:
                    continue
                closest = start + rayDir.scale(proj)
                distToRay = (closest - botPos).length
                if distToRay <= 6.0:
                    hitDist = proj
            except Exception:
                continue
        if hitDist is None:
            continue
        if staticDist is not None and staticDist < hitDist - 0.5:
            continue
        if bestDist is None or hitDist < bestDist:
            bestDist = hitDist
            bestID = botID
    return bestID, bestDist, staticPoint, staticDist


def _applyDestructibleDamageAt(spaceID, point, damage, attackerID, direction, radius):
    manager, cache = _getDestructiblesManagers()
    if manager is None or cache is None or DestructiblesCache is None or BigWorld is None:
        return
    try:
        point = Math.Vector3(point)
    except Exception:
        return
    try:
        damage = float(damage)
    except Exception:
        return
    if damage <= 0.0 or radius <= 0.0:
        return
    try:
        if manager.getSpaceID() != spaceID:
            manager.startSpace(spaceID)
    except Exception:
        pass
    try:
        gridX, gridZ = DestructiblesCache.chunkIndexesFromPosition((point.x, point.y, point.z))
    except Exception:
        return
    directionYaw = 0.0
    try:
        if direction is not None:
            direction = Math.Vector3(direction)
            if direction.length > 0.001:
                directionYaw = math.atan2(direction.x, direction.z)
    except Exception:
        directionYaw = 0.0
    chunkSpan = int(math.floor(radius / 100.0)) + 1
    chunkMatrixCache = {}
    for offX in xrange(-chunkSpan, chunkSpan + 1):
        for offZ in xrange(-chunkSpan, chunkSpan + 1):
            try:
                chunkID = DestructiblesCache.chunkIDFromChunkIndexes(gridX + offX, gridZ + offZ)
            except Exception:
                continue
            _ensureChunkLoaded(manager, chunkID)
            loaded = getattr(manager, '_DestructiblesManager__loadedChunkIDs', None)
            if loaded is None:
                loaded = getattr(manager, 'loadedChunkIDs', None)
            if not loaded:
                continue
            numDestructibles = loaded.get(chunkID, 0)
            if not numDestructibles:
                continue
            chunkMatrix = chunkMatrixCache.get(chunkID)
            if chunkMatrix is None:
                try:
                    chunkMatrix = BigWorld.getChunkMatrix(spaceID, chunkID)
                except Exception:
                    chunkMatrix = None
                chunkMatrixCache[chunkID] = chunkMatrix
            if chunkMatrix is None:
                continue
            chunkPos = chunkMatrix.translation
            for destrIndex in xrange(numDestructibles):
                try:
                    filename = BigWorld.getDestructibleFilename(spaceID, chunkID, destrIndex)
                except Exception:
                    continue
                if not filename:
                    continue
                desc = cache.getDescByFilename(filename)
                if desc is None:
                    continue
                destrType = desc.get('type')
                if destrType is None:
                    continue
                try:
                    destrMatrix = BigWorld.getDestructibleMatrix(spaceID, chunkID, destrIndex)
                except Exception:
                    continue
                if destrMatrix is None:
                    continue
                pos = chunkPos + destrMatrix.translation
                try:
                    scale = destrMatrix.applyVector((0.0, 1.0, 0.0)).length
                except Exception:
                    scale = 1.0
                if scale <= 0.0:
                    scale = 1.0
                if destrType == DestructiblesCache.DESTR_TYPE_STRUCTURE:
                    modules = desc.get('modules', {})
                    try:
                        moduleItems = modules.items()
                    except Exception:
                        moduleItems = []
                    structureRadius = radius * 2.0
                    for matKind, moduleDesc in moduleItems:
                        if _isDestructibleShotBroken(manager, chunkID, destrIndex, matKind, destrType):
                            continue
                        try:
                            refHealth = int(moduleDesc.get('health', 0))
                        except Exception:
                            refHealth = 0
                        if refHealth <= 0:
                            continue
                        modulePos = pos
                        try:
                            hpMatrix = BigWorld.getNMHardPointMatrix(spaceID, chunkID, destrIndex, 0)
                            if hpMatrix is not None:
                                modulePos = hpMatrix.translation
                        except Exception:
                            modulePos = pos
                        dx = modulePos.x - point.x
                        dz = modulePos.z - point.z
                        dist = math.sqrt(dx * dx + dz * dz)
                        if dist > structureRadius:
                            continue
                        falloff = max(0.0, 1.0 - dist / max(structureRadius, 0.001))
                        dmg = damage * falloff
                        if dmg <= 0.0:
                            continue
                        if DestructiblesCache.scaledDestructibleHealth(scale, refHealth) > dmg:
                            continue
                        _orderDestructibleShotDestroy(manager, spaceID, chunkID, destrIndex, destrType, matKind, directionYaw, dmg)
                else:
                    if _isDestructibleShotBroken(manager, chunkID, destrIndex, 0, destrType):
                        continue
                    try:
                        refHealth = int(desc.get('health', 0))
                    except Exception:
                        refHealth = 0
                    if refHealth <= 0:
                        continue
                    dx = pos.x - point.x
                    dz = pos.z - point.z
                    dist = math.sqrt(dx * dx + dz * dz)
                    if dist > radius:
                        continue
                    falloff = max(0.0, 1.0 - dist / max(radius, 0.001))
                    dmg = damage * falloff
                    if dmg <= 0.0:
                        continue
                    if DestructiblesCache.scaledDestructibleHealth(scale, refHealth) > dmg:
                        continue
                    _orderDestructibleShotDestroy(manager, spaceID, chunkID, destrIndex, destrType, 0, directionYaw, dmg)


def _showShot(vehicle, guns=None):
    try:
        if guns is None:
            gunIndex = getattr(vehicle, 'activeGunIndex', 0)
            if gunIndex is None:
                gunIndex = 0
            guns = [gunIndex]
        vehicle.showShooting(1, guns, True)
    except Exception:
        pass


def _performShotEffects(player, vehicle, muzzle, target, damage, intCD, guns):
    direction = target - muzzle
    if direction.length < 0.1:
        return
    direction.normalise()
    end = muzzle + direction.scale(720.0)
    botID, botDist, staticPoint, staticDist = _getShotHit(player, muzzle, end)
    _showShot(vehicle, guns)
    attackerID = getattr(player, 'playerVehicleID', 0)
    if staticPoint is not None and (botID is None or botDist is None or staticDist <= botDist + 0.5):
        try:
            radius = max(3.0, _getShellExplosionRadius(intCD))
            _applyDestructibleDamageAt(getattr(player, 'spaceID', 0), staticPoint, damage, attackerID, direction, radius)
        except Exception:
            pass
    if botID is not None:
        if staticPoint is None or staticDist is None or botDist is None or botDist <= staticDist + 0.5:
            actualDamage = damage
            if offhangar_armour is not None:
                botEntity = BigWorld.entity(botID)
                if botEntity is not None:
                    shell = _getShellFromIntCD(intCD)
                    shot = _getShellShot(intCD)
                    if shell is not None and shot is not None:
                        distance = (muzzle - target).length if botDist is None else botDist
                        hit = offhangar_armour.resolve(botEntity, target, direction, shell, shot, distance)
                        if hit is not None:
                            if hit.pierced:
                                actualDamage = damage * hit.damageFactor
                            elif hit.nonPiercingFactor > 0.0:
                                actualDamage = damage * hit.nonPiercingFactor * (hit.damageFactor or 1.0)
                            elif hit.blocked:
                                actualDamage = 0.0
                            else:
                                actualDamage = 0.0
            if actualDamage > 0:
                _applyDamage(botID, actualDamage, attackerID)


def _switchToAvailableShell(ctrl):
    currentCD = ctrl.getCurrentShellCD()
    for intCD in ctrl.getShellsOrderIter():
        quantity, quantityInClip = ctrl.getShells(intCD)
        if quantity > 0 and intCD != currentCD:
            try:
                ctrl.setCurrentShellCD(intCD)
            except Exception:
                pass
            _processDelayer(ctrl, 'setCurrentShellCD')
            _updateConsumablesPanel(ctrl, intCD, quantity, quantityInClip)
            return


def _consumeShot(allowReload=True):
    intCD = _getShellIntCD()
    if intCD is None:
        return False
    try:
        q, qc = _ammo_ctrl.getShells(intCD)
    except Exception:
        return False
    clipSize = _gunParams.get('clipSize', 1)
    isAutoReload = _gunParams.get('isAutoReload', False)
    isClipGun = _gunParams.get('isClipGun', False)
    if isAutoReload and isClipGun:
        if qc <= 0:
            return False
        q = max(0, q - 1)
        qc -= 1
        try:
            _ammo_ctrl.setShells(intCD, q, qc)
        except Exception:
            pass
        _updateConsumablesPanel(_ammo_ctrl, intCD, q, qc)
        if allowReload:
            if _reloadState['isReloading'] and _reloadState['mode'] == 'autoReload':
                _reloadState['isReloading'] = False
                _reloadState['mode'] = 'none'
            if qc < clipSize and q > qc:
                _startAutoReloadStep(intCD)
            else:
                _setPanelAutoReload(0.0, 0.0, 0.0)
        return True
    if isClipGun:
        if qc <= 0:
            return False
        q = max(0, q - 1)
        qc -= 1
        try:
            _ammo_ctrl.setShells(intCD, q, qc)
        except Exception:
            pass
        _updateConsumablesPanel(_ammo_ctrl, intCD, q, qc)
        if allowReload and qc <= 0 and q > 0:
            _startClipReload()
        return True
    if q <= 0:
        return False
    q -= 1
    try:
        _ammo_ctrl.setShells(intCD, q, 0)
    except Exception:
        pass
    _updateConsumablesPanel(_ammo_ctrl, intCD, q, 0)
    if allowReload and q > 0:
        _startClipReload(_gunParams.get('reloadTime', 2.5))
    return True


def _fireSingleShot(player, vehicle, allowReload=True):
    intCD = _getShellIntCD()
    if intCD is None:
        return False
    muzzle, target = _getMuzzleAndTarget(player, vehicle)
    if muzzle is None or target is None:
        return False
    if not _consumeShot(allowReload=allowReload):
        return False
    damage = _getShellDamage(intCD)
    _performShotEffects(player, vehicle, muzzle, target, damage, intCD, None)
    return True


def _fireBurstShot(player, vehicle, isLast):
    intCD = _getShellIntCD()
    if intCD is None:
        return False
    muzzle, target = _getMuzzleAndTarget(player, vehicle)
    if muzzle is None or target is None:
        return False
    if not _consumeShot(allowReload=isLast):
        return False
    damage = _getShellDamage(intCD)
    _performShotEffects(player, vehicle, muzzle, target, damage, intCD, None)
    return True


def _startBurstIfPossible():
    global _fireState
    intCD = _getShellIntCD()
    if intCD is None:
        return False
    try:
        q, qc = _ammo_ctrl.getShells(intCD)
    except Exception:
        return False
    burstSize = _gunParams.get('burstSize', 1)
    if _gunParams.get('isClipGun', False):
        count = min(burstSize, qc, q)
    else:
        count = min(burstSize, q)
    if count > 1 and not (_reloadState['isReloading'] and _reloadState['mode'] in ('clipFull', 'partial')):
        _fireState['burstRemaining'] = count
        _fireState['burstNextTime'] = BigWorld.time()
        return True
    return False


def _isFireHeld():
    try:
        if BigWorld.isKeyDown(0):
            return True
    except Exception:
        pass
    try:
        cmd = getattr(CommandMapping, 'CMD_CM_SHOOT', None)
        if cmd is not None and CommandMapping.g_instance.isActive(cmd):
            return True
    except Exception:
        pass
    return False

import BigWorld
from constants import DUAL_GUN, DUALGUN_CHARGER_ACTION_TYPE, DUALGUN_CHARGER_STATUS

_pending = []

def _schedule(delay, fn):
    handle = [None, fn, BigWorld.time(), delay]
    def _fire():
        try:
            _pending.remove(handle)
        except ValueError:
            pass
        fn()
    handle[0] = BigWorld.callback(delay, _fire)
    _pending.append(handle)
    return handle

def _cancelPending():
    for handle in _pending[:]:
        try:
            BigWorld.cancelCallback(handle[0])
        except Exception:
            pass
    del _pending[:]


class _Cooldown(object):
    __slots__ = ('id', 'endTime', 'baseTime', 'leftTime')

    def __init__(self, cooldownID=0, leftTime=0.0, baseTime=0.0):
        self.id = cooldownID
        self.baseTime = float(baseTime)
        self.leftTime = float(leftTime)
        self.endTime = float(baseTime)

    def __getitem__(self, index):
        return (self.id, self.endTime, self.baseTime, self.leftTime)[index]


class _DualGun(object):
    def __init__(self, descriptor):
        params = descriptor.gun.dualGun
        times = tuple(float(t) for t in params.reloadTimes)
        self.reloadTimes = times if len(times) >= 2 else (times + times)[:2]
        self.reloadLockTime = float(getattr(params, 'reloadLockTime', 0.0))
        self.rateTime = float(params.rateTime)
        self.chargeTime = float(params.chargeTime)
        self.chargeCancelTime = float(getattr(params, 'chargeCancelTime', 0.2))
        self.chargeThreshold = float(getattr(params, 'chargeThreshold', 0.5))
        self.afterShotDelay = float(params.afterShotDelay)
        self.pendingStart = None
        self.active = DUAL_GUN.ACTIVE_GUN.LEFT
        self.states = [DUAL_GUN.GUN_STATE.READY, DUAL_GUN.GUN_STATE.READY]
        self.switchLeft = 0.0
        self.charging = False
        self.chargeHandle = None


_dualGun = [None]


def dualGunFor(descriptor):
    if not getattr(descriptor, 'isDualgunVehicle', False):
        return None
    if _dualGun[0] is None:
        try:
            _dualGun[0] = _DualGun(descriptor)
        except Exception:
            return None
    return _dualGun[0]


def _publishDualGun(avatar, vehicleID, dual, switchLeft=0.0, debuffLeft=0.0):
    cooldowns = [
        _Cooldown(DUAL_GUN.COOLDOWNS.LEFT,
                  dual.reloadTimes[0] if dual.states[0] == DUAL_GUN.GUN_STATE.RELOADING else 0.0,
                  dual.reloadTimes[0]),
        _Cooldown(DUAL_GUN.COOLDOWNS.RIGHT,
                  dual.reloadTimes[1] if dual.states[1] == DUAL_GUN.GUN_STATE.RELOADING else 0.0,
                  dual.reloadTimes[1]),
        _Cooldown(DUAL_GUN.COOLDOWNS.SWITCH, switchLeft, dual.rateTime),
        _Cooldown(DUAL_GUN.COOLDOWNS.DEBUFF, debuffLeft, dual.reloadLockTime),
    ]
    try:
        avatar.updateDualGunState(vehicleID, dual.active, list(dual.states), cooldowns)
        return True
    except Exception:
        return False


def _dualGunAfterShot(avatar, vehicle, dual, barrels):
    vehicleID = vehicle.id

    def _reloadBarrel(barrel):
        dual.states[barrel] = DUAL_GUN.GUN_STATE.RELOADING
        def _loaded(_barrel=barrel):
            later = BigWorld.player()
            if later is None or getattr(later, 'playerVehicleID', None) != vehicleID:
                return
            dual.states[_barrel] = DUAL_GUN.GUN_STATE.READY
            _publishDualGun(later, vehicleID, dual)
        _schedule(dual.reloadTimes[barrel], _loaded)

    if len(barrels) == 1:
        _reloadBarrel(barrels[0])
        dual.active = (DUAL_GUN.ACTIVE_GUN.RIGHT
                       if barrels[0] == DUAL_GUN.ACTIVE_GUN.LEFT
                       else DUAL_GUN.ACTIVE_GUN.LEFT)
        _publishDualGun(avatar, vehicleID, dual, switchLeft=dual.rateTime)
        def _switched():
            later = BigWorld.player()
            if later is None or getattr(later, 'playerVehicleID', None) != vehicleID:
                return
            _publishDualGun(later, vehicleID, dual)
        _schedule(dual.rateTime, _switched)
    else:
        for barrel in barrels:
            dual.states[barrel] = DUAL_GUN.GUN_STATE.EMPTY
        _publishDualGun(avatar, vehicleID, dual, debuffLeft=dual.reloadLockTime)
        def _lockOver():
            later = BigWorld.player()
            if later is None or getattr(later, 'playerVehicleID', None) != vehicleID:
                return
            for barrel in barrels:
                _reloadBarrel(barrel)
            _publishDualGun(later, vehicleID, dual)
        _schedule(dual.reloadLockTime, _lockOver)


def _cancelCharge(dual):
    dual.charging = False
    handle = dual.chargeHandle
    dual.chargeHandle = None
    if handle is None:
        return
    try:
        BigWorld.cancelCallback(handle[0])
    except Exception:
        pass
    try:
        _pending.remove(handle)
    except ValueError:
        pass


def handleDualGunCharger(avatar, vehicle, descriptor, action):
    dual = dualGunFor(descriptor)
    if dual is None:
        return

    vehicleID = vehicle.id

    if action == DUALGUN_CHARGER_ACTION_TYPE.CANCEL:
        pending = dual.pendingStart
        dual.pendingStart = None
        if pending is not None:
            try:
                BigWorld.cancelCallback(pending[0])
            except Exception:
                pass
            try:
                _pending.remove(pending)
            except ValueError:
                pass
            try:
                avatar.updateDualGunStatus(vehicleID, DUALGUN_CHARGER_STATUS.CANCELED, (0.0, 0.0))
            except Exception:
                pass
            return

        wasCharging = dual.charging
        _cancelCharge(dual)
        try:
            penalty = dual.chargeCancelTime if wasCharging else 0.0
            avatar.updateDualGunStatus(vehicleID, DUALGUN_CHARGER_STATUS.CANCELED, (penalty, 0.0))
        except Exception:
            pass
        return

    if dual.charging or dual.pendingStart is not None:
        return
    if not all(state == DUAL_GUN.GUN_STATE.READY for state in dual.states):
        return

    def _beginCharge():
        dual.pendingStart = None
        later = BigWorld.player()
        if later is None or dual.charging:
            return
        if not all(state == DUAL_GUN.GUN_STATE.READY for state in dual.states):
            return
        dual.charging = True
        try:
            later.updateDualGunStatus(vehicleID, DUALGUN_CHARGER_STATUS.PREPARING,
                                      (dual.chargeTime, dual.chargeTime))
        except Exception:
            dual.charging = False
            return
        dual.chargeHandle = _schedule(dual.chargeTime, _applied)

    def _applied():
        later = BigWorld.player()
        target = BigWorld.entity(getattr(later, 'playerVehicleID', 0)) if later else None
        wasCharging = dual.charging
        dual.charging = False
        dual.chargeHandle = None
        if not wasCharging:
            return
        if later is None or target is None or not getattr(target, 'isStarted', False):
            return
        try:
            later.updateDualGunStatus(vehicleID, DUALGUN_CHARGER_STATUS.APPLIED,
                                      (dual.chargeTime, 0.0))
        except Exception:
            pass
        _dualGunAfterShot(later, target, dual,
                          [DUAL_GUN.ACTIVE_GUN.LEFT, DUAL_GUN.ACTIVE_GUN.RIGHT])

    if action == DUALGUN_CHARGER_ACTION_TYPE.START_IMMEDIATELY:
        _beginCharge()
        return

    dual.pendingStart = _schedule(dual.chargeThreshold, _beginCharge)


def dualGunShotCycle(avatar, vehicle, descriptor, fireShell, afterShell, gunCycle):
    dual = dualGunFor(descriptor)
    if dual is None:
        return False

    barrel = dual.active
    fireShell(avatar, vehicle, descriptor, gunIndex=barrel)
    afterShell(avatar, vehicle, gunCycle, isLast=False)
    _dualGunAfterShot(avatar, vehicle, dual, [barrel])
    return True


def resetDualGun():
    _dualGun[0] = None
    _cancelPending()

def _isReloadKeyActive():
    global _reloadKeyTriggered
    isDown = False
    try:
        cmd = getattr(CommandMapping, 'CMD_RELOAD_PARTIAL_CLIP', None)
        if cmd is not None and CommandMapping.g_instance.isActive(cmd):
            isDown = True
    except Exception:
        pass
    if not isDown:
        try:
            isDown = BigWorld.isKeyDown(19)
        except Exception:
            pass
    if isDown and not _reloadKeyTriggered:
        _reloadKeyTriggered = True
        return True
    if not isDown:
        _reloadKeyTriggered = False
    return False


def _processFire(player, vehicle):
    global _fireState
    if _ammo_ctrl is None:
        return
    now = BigWorld.time()
    if _isReloadKeyActive():
        _startPartialReload()
    fireHeld = _isFireHeld()
    if not fireHeld:
        _fireState['fireTriggered'] = False
        return
    _fireState['fireTriggered'] = True
    isAutoReload = _gunParams.get('isAutoReload', False)
    reloadMode = _reloadState['mode']
    if not isAutoReload:
        if reloadMode in ('clipFull', 'partial'):
            return
    else:
        if reloadMode in ('clipFull', 'partial'):
            return
    if _gunParams.get('isAutoShoot', False):
        if now >= _fireState['nextShotTime']:
            if _fireSingleShot(player, vehicle):
                _fireState['nextShotTime'] = now + max(0.01, _gunParams.get('autoShootInterval', 0.1))
            else:
                _fireState['nextShotTime'] = now + 0.1
        return
    if _gunParams.get('isBurst', False) and _gunParams.get('isClipGun', False):
        if _fireState['burstRemaining'] > 0:
            if now >= _fireState['burstNextTime']:
                isLast = _fireState['burstRemaining'] == 1
                if _fireBurstShot(player, vehicle, isLast):
                    _fireState['burstRemaining'] -= 1
                    if _fireState['burstRemaining'] > 0:
                        _fireState['burstNextTime'] = now + max(0.05, _gunParams.get('burstInterval', 0.1))
                    else:
                        _fireState['nextShotTime'] = now + max(0.3, _gunParams.get('burstInterval', 0.3))
            return
        if now >= _fireState['nextShotTime']:
            if _startBurstIfPossible():
                return
    if now >= _fireState['nextShotTime']:
        if _fireSingleShot(player, vehicle):
            if _gunParams.get('isClipGun', False):
                _fireState['nextShotTime'] = now + max(0.05, _gunParams.get('burstInterval', 0.1))
            else:
                _fireState['nextShotTime'] = now + max(0.1, _gunParams.get('reloadTime', 2.5))
        else:
            _fireState['nextShotTime'] = now + 0.1


def _tick():
    global _tick_id
    player = BigWorld.player()
    if player is None or not getattr(player, 'isOffline', False):
        _clearAmmoController()
    else:
        vehicleID = getattr(player, 'playerVehicleID', 0)
        vehicle = BigWorld.entity(vehicleID) if vehicleID else None

        isVehicleAlive = False
        if vehicle is not None:
            try:
                isVehicleAlive = vehicle.isAlive()
            except Exception:
                isVehicleAlive = getattr(vehicle, 'health', 0) > 0

        if vehicle is None or not getattr(vehicle, 'isStarted', False) or not isVehicleAlive:
            _clearAmmoController()
        elif _ammo_ctrl is None or _player_vehicle_id != vehicleID:
            _clearAmmoController()
            _initAmmoController(player, vehicle)
        if _ammo_ctrl is not None:
            _updateReloads()
            _processFire(player, vehicle)
    _tick_id = BigWorld.callback(0.1, _tick)

def start():
    global _tick_id
    if _tick_id is None:
        _tick_id = BigWorld.callback(0.0, _tick)


def stop():
    global _tick_id
    if _tick_id is not None:
        try:
            BigWorld.cancelCallback(_tick_id)
        except Exception:
            pass
    _tick_id = None
    _clearAmmoController()


try:
    start()
except Exception:
    pass