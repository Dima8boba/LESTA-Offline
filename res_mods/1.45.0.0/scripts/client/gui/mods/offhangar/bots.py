import random
import math
import os
import sys
import json
import codecs
import BigWorld
import Math
from constants import IGR_TYPE
from items import vehicles as items_vehicles
from debug_utils import LOG_CURRENT_EXCEPTION
from gui.mods.offhangar.logging import LOG_DEBUG, LOG_NOTE
import sys

offhangar_battle = sys.modules.get('gui.mods.offhangar.battle')
if offhangar_battle is None:
    import gui.mods.offhangar.battle as offhangar_battle

try:
    import glob
except Exception:
    glob = None

_botVehicleIDs = []
_botCounter = [0]
_vehicleLevelCache = {}
_allowedVehicleNamesCache = {}
_battleLevels = None
_physicsStarted = [False]


def _getLevelFromDescriptor(descr):
    if descr is None:
        return 0

    try:
        vType = getattr(descr, 'type', None)
        for attr in ('level', 'vehicleLevel'):
            value = getattr(vType, attr, None)
            if value:
                return int(value)
    except Exception:
        pass

    for attr in ('level', 'vehicleLevel'):
        try:
            value = getattr(descr, attr, None)
            if value:
                return int(value)
        except Exception:
            pass

    return 0


def _getVehicleLevel(typeName):
    cached = _vehicleLevelCache.get(typeName)
    if cached is not None:
        return cached

    level = 0

    try:
        nationID, vehicleTypeID = items_vehicles.g_list.getIDsByName(typeName)
        vType = items_vehicles.g_cache.vehicle(nationID, vehicleTypeID)

        for attr in ('level', 'vehicleLevel'):
            value = getattr(vType, attr, None)
            if value:
                level = int(value)
                break
    except Exception:
        level = 0

    if level <= 0:
        try:
            descr = items_vehicles.VehicleDescr(typeName=typeName)
            level = _getLevelFromDescriptor(descr)
        except Exception:
            level = 0

    if level < 0:
        level = 0

    if level > 10:
        level = 10

    _vehicleLevelCache[typeName] = level

    return level


def _getPlayerVehicleLevel():
    try:
        vehID = getattr(offhangar_battle, '_vehicleID', 0)
        if vehID:
            veh = BigWorld.entity(vehID)
            level = _getLevelFromDescriptor(getattr(veh, 'typeDescriptor', None))
            if level > 0:
                return level
    except Exception:
        pass

    try:
        avatar = BigWorld.player()
        vehID = getattr(avatar, 'playerVehicleID', 0)
        if vehID:
            veh = BigWorld.entity(vehID)
            level = _getLevelFromDescriptor(getattr(veh, 'typeDescriptor', None))
            if level > 0:
                return level
    except Exception:
        pass

    try:
        from CurrentVehicle import g_currentVehicle
        item = getattr(g_currentVehicle, 'item', None)
        descriptor = getattr(item, 'descriptor', None)
        level = _getLevelFromDescriptor(descriptor)
        if level > 0:
            return level
    except Exception:
        pass

    return 0


def _pickBattleLevels(playerLevel):
    try:
        level = int(playerLevel)
    except Exception:
        return ()

    if level <= 0:
        return ()

    if level > 10:
        level = 10

    sets = [(level,)]

    if level - 1 >= 1:
        sets.append((level - 1, level))

    if level - 2 >= 1:
        sets.append((level - 2, level - 1, level))

    if level + 1 <= 10:
        sets.append((level, level + 1))

    if level + 2 <= 10:
        sets.append((level, level + 1, level + 2))

    if not sets:
        return ()

    return random.choice(sets)


def _getAllowedVehicleNames(allowedLevels):
    if not allowedLevels:
        key = ()
    else:
        levels = []
        for level in allowedLevels:
            try:
                levels.append(int(level))
            except Exception:
                pass

        key = tuple(sorted(set(levels)))

    cached = _allowedVehicleNamesCache.get(key)
    if cached is not None:
        return cached

    ids = getattr(items_vehicles.g_list, '_VehicleList__ids', {})

    if not ids:
        _allowedVehicleNamesCache[key] = []
        return []

    names = list(ids.keys())

    if key:
        filtered = []

        for name in names:
            if _getVehicleLevel(name) in key:
                filtered.append(name)

        if filtered:
            names = filtered

    _allowedVehicleNamesCache[key] = names

    return names

def _getPossibleResModRoots():
    roots = []
    seen = set()
    starts = []

    try:
        starts.append(os.getcwd())
    except Exception:
        pass

    try:
        starts.append(os.path.dirname(os.path.abspath(sys.executable)))
    except Exception:
        pass

    for start in starts:
        current = start
        for _ in range(8):
            try:
                if os.path.isdir(os.path.join(current, 'res_mods')):
                    if current not in seen:
                        seen.add(current)
                        roots.append(current)
            except Exception:
                pass

            try:
                parent = os.path.dirname(current)
            except Exception:
                break

            if parent == current:
                break

            current = parent

    return roots


def _loadBotsConfig():
    defaultConfig = {
        "team1Bots": 15,
        "team2Bots": 15,
        "spawnDelay": 0.15,
        "maxOffsetRadius": 50.0,
        "names": [],
        "team1Names": [],
        "team2Names": []
    }

    paths = []

    paths.append(os.path.join('res_mods', 'configs', 'bots_config.json'))

    for root in _getPossibleResModRoots():
        paths.append(os.path.join(root, 'res_mods', 'configs', 'bots_config.json'))

        if glob is not None:
            try:
                for path in sorted(glob.glob(os.path.join(root, 'res_mods', '*', 'configs', 'bots_config.json'))):
                    paths.append(path)
            except Exception:
                pass

    try:
        baseDir = os.path.dirname(os.path.abspath(__file__))
        paths.append(os.path.abspath(os.path.join(baseDir, '..', '..', '..', 'configs', 'bots_config.json')))
        paths.append(os.path.abspath(os.path.join(baseDir, '..', '..', '..', '..', 'configs', 'bots_config.json')))
    except Exception:
        pass

    paths.append('bots_config.json')

    seen = set()

    for path in paths:
        try:
            absPath = os.path.abspath(path)
        except Exception:
            absPath = path

        if absPath in seen:
            continue

        seen.add(absPath)

        try:
            with codecs.open(absPath, 'r', 'utf-8-sig') as f:
                cfg = json.load(f)

            if isinstance(cfg, dict):
                return cfg
        except Exception:
            pass

    return defaultConfig


bots_config = _loadBotsConfig()
_usedBotNames = set()


def _getConfigInt(key, default):
    try:
        return int(bots_config.get(key, default))
    except Exception:
        return default


def _getConfigFloat(key, default):
    try:
        return float(bots_config.get(key, default))
    except Exception:
        return default


def _getTeamNamePool(team):
    try:
        teamNames = bots_config.get('team%dNames' % team, [])
        if isinstance(teamNames, (list, tuple)) and teamNames:
            return list(teamNames)
    except Exception:
        pass

    try:
        names = bots_config.get('names', [])
        if isinstance(names, (list, tuple)) and names:
            return list(names)
    except Exception:
        pass

    return []


def _asBotName(name):
    try:
        if isinstance(name, unicode):
            return name.encode('utf-8')
    except Exception:
        pass

    try:
        return str(name)
    except Exception:
        return 'Bot'


def _pickBotName(team):
    pool = _getTeamNamePool(team)

    if not pool:
        return 'Bot %d' % _botCounter[0]

    available = [name for name in pool if name not in _usedBotNames]

    if not available:
        available = pool

    name = random.choice(available)
    _usedBotNames.add(name)

    return _asBotName(name)


def _pickRandomVehicleTypeName(allowedLevels=None):
    names = _getAllowedVehicleNames(allowedLevels)

    if not names:
        ids = getattr(items_vehicles.g_list, '_VehicleList__ids', {})
        if not ids:
            return None

        names = list(ids.keys())

    return random.choice(names)


def _makeRandomCompactDescr(vehicleTypeName):
    stock = items_vehicles.VehicleDescr(typeName=vehicleTypeName)

    try:
        nationID, vehicleTypeID = items_vehicles.g_list.getIDsByName(vehicleTypeName)
        vType = items_vehicles.g_cache.vehicle(nationID, vehicleTypeID)

        if vType.chassis:
            c_desc = random.choice(vType.chassis)
            stock.installComponent(c_desc.compactDescr)

        if vType.engines:
            e_desc = random.choice(vType.engines)
            stock.installComponent(e_desc.compactDescr)

        if vType.fuelTanks:
            f_desc = random.choice(vType.fuelTanks)
            stock.installComponent(f_desc.compactDescr)

        if vType.radios:
            r_desc = random.choice(vType.radios)
            stock.installComponent(r_desc.compactDescr)

        if vType.turrets:
            turretGroup = random.choice(vType.turrets)
            t_desc = turretGroup[0]

            if t_desc.guns:
                g_desc = random.choice(t_desc.guns)
                stock.installTurret(t_desc.compactDescr, g_desc.compactDescr)

    except Exception:
        LOG_CURRENT_EXCEPTION()
        LOG_DEBUG('bots: random configuration failed, falling back to stock', vehicleTypeName)

    return stock.makeCompactDescr()


def _getTeamSpawnPoint(avatar, team):
    try:
        arena = getattr(avatar, 'arena', None)
        arenaType = getattr(arena, 'arenaType', None)

        if arenaType is None:
            return None

        teamIndex = int(team) - 1

        if teamIndex < 0:
            teamIndex = 0

        tsp = getattr(arenaType, 'teamSpawnPoints', None)

        if tsp and teamIndex < len(tsp) and tsp[teamIndex]:
            points = tsp[teamIndex]

            if points:
                spawn = points[0]

                try:
                    if hasattr(spawn, 'x') and hasattr(spawn, 'y'):
                        return (float(spawn.x), 10.0, float(spawn.y))
                except Exception:
                    pass

                try:
                    if len(spawn) >= 2:
                        return (float(spawn[0]), 10.0, float(spawn[1]))
                except Exception:
                    pass

        tbp = getattr(arenaType, 'teamBasePositions', None)

        if tbp and teamIndex < len(tbp) and tbp[teamIndex]:
            bases = tbp[teamIndex]

            if bases:
                base = None

                try:
                    if isinstance(bases, dict):
                        values = bases.values()
                        if values:
                            base = values[0]
                    elif bases:
                        base = bases[0]
                except Exception:
                    base = None

                if base is not None:
                    try:
                        if hasattr(base, 'x') and hasattr(base, 'y'):
                            return (float(base.x), 10.0, float(base.y))
                    except Exception:
                        pass

                    try:
                        if len(base) >= 2:
                            return (float(base[0]), 10.0, float(base[1]))
                    except Exception:
                        pass

        bp = getattr(arenaType, 'botPoints', None)

        if bp:
            try:
                bpItems = bp.items()
            except Exception:
                bpItems = []

            for idx, pos in bpItems:
                try:
                    if hasattr(pos, 'x') and hasattr(pos, 'y') and hasattr(pos, 'z'):
                        return (float(pos.x), float(pos.y), float(pos.z))
                except Exception:
                    pass

                try:
                    if len(pos) >= 3:
                        return (float(pos[0]), float(pos[1]), float(pos[2]))
                except Exception:
                    pass

        import ResMgr

        path = 'spaces/%s/space.settings' % arenaType.geometryName
        root = ResMgr.openSection(path)

        if root is not None:
            tspSec = None

            try:
                tspSec = root['teamSpawnPoints']
            except Exception:
                tspSec = None

            if tspSec is None:
                try:
                    tspSec = root['spawnPoints']
                except Exception:
                    tspSec = None

            if tspSec is not None:
                teamSec = None

                try:
                    teamSec = tspSec['team%d' % team]
                except Exception:
                    teamSec = None

                if teamSec is None:
                    try:
                        teamSec = tspSec['team%s' % team]
                    except Exception:
                        teamSec = None

                if teamSec is not None:
                    try:
                        teamItems = teamSec.items()
                    except Exception:
                        teamItems = []

                    for key, val in teamItems:
                        try:
                            v2 = val.asVector2
                            if v2:
                                return (float(v2[0]), 10.0, float(v2[1]))
                        except Exception:
                            pass

                        try:
                            v3 = val.asVector3
                            if v3:
                                return (float(v3[0]), float(v3[1]), float(v3[2]))
                        except Exception:
                            pass

            bpSec = None

            try:
                bpSec = root['botPoints']
            except Exception:
                bpSec = None

            if bpSec is not None:
                try:
                    bpItems = bpSec.items()
                except Exception:
                    bpItems = []

                for key, val in bpItems:
                    try:
                        v3 = val['position'].asVector3
                        if v3:
                            return (float(v3[0]), float(v3[1]), float(v3[2]))
                    except Exception:
                        pass

    except Exception:
        LOG_CURRENT_EXCEPTION()

    return None


def _ensurePhysicsRunning():
    if _physicsStarted[0]:
        return

    try:
        import gui.mods.offhangar.physics as offhangar_physics
        offhangar_physics.start()
        _physicsStarted[0] = True
    except Exception:
        LOG_CURRENT_EXCEPTION()

def _getBotBadgesSafe():
    try:
        import random
        from gui.doc_loaders import badges_loader
        
        available = badges_loader.getAvailableBadges()
        if not available:
            return ((), ())
        ids = available.keys()
        prefix = (random.choice(ids),) if random.random() < 0.7 else ()
        suffix = (random.choice(ids),) if random.random() < 0.3 else ()
        res = (prefix, suffix)
        from gui.mods.offhangar.logging import LOG_DEBUG
        LOG_DEBUG('bots.py: bot badges = {}'.format(res))
        return res
    except Exception:
        from debug_utils import LOG_CURRENT_EXCEPTION
        LOG_CURRENT_EXCEPTION()
        return ((), ())

_BOT_TRACK_PERIOD = 0.033
_botTrackTickActive = False
_botTrackCache = {}
_botPrevMotion = {}

def _startBotVisual(vehID):
    veh = BigWorld.entity(vehID)
    if veh is None:
        return
    try:
        if not getattr(veh, 'isStarted', False):
            veh.startVisual()
    except Exception:
        pass
    try:
        from helpers import dependency
        from skeletons.gui.battle_session import IBattleSessionProvider
        sp = dependency.instance(IBattleSessionProvider)
        if sp is not None:
            sp.startVehicleVisual(veh, False)
    except Exception:
        pass
    try:
        appearance = getattr(veh, 'appearance', None)
        if appearance is not None:
            flt = getattr(appearance, 'filter', None)
            tsc = getattr(appearance, 'trackScrollController', None)
            if tsc is not None and flt is not None:
                tsc.activate()
                tsc.setData(flt)
    except Exception:
        pass

def _botDriveWheels(vehicle, appearance, wheels, cache, left, right, rotationSpeed):
    try:
        if not wheels:
            return False
        maxAngle = 0.5
        gain = 0.9
        angle = rotationSpeed * gain
        if (left + right) * 0.5 < 0.0:
            angle = -angle
        if angle > maxAngle:
            angle = maxAngle
        elif angle < -maxAngle:
            angle = -maxAngle
        if cache.get('linked') is not wheels:
            cache['linked'] = wheels
            cache['wheelVals'] = None
            steerCount = len(getattr(vehicle, 'wheelsSteeringFilters', None) or ())
            if not steerCount:
                cfg = getattr(getattr(appearance.typeDescriptor, 'chassis', None), 'generalWheelsAnimatorConfig', None)
                try:
                    steerCount = cfg.getSteerableWheelsCount() if cfg is not None else 0
                except Exception:
                    steerCount = 0
            cache['steerCount'] = steerCount
        if cache.get('wheelVals') != (left, right, angle):
            cache['wheelVals'] = (left, right, angle)
            def getWheelScrollLeft():
                return left
            def getWheelScrollRight():
                return right
            wheels.overrideScrollDataLink(getWheelScrollLeft, getWheelScrollRight)
            steerCount = cache.get('steerCount') or 0
            if steerCount and hasattr(wheels, 'overrideSteeringDataLink'):
                def getWheelAngle():
                    return angle
                wheels.overrideSteeringDataLink([getWheelAngle] * steerCount)
        return True
    except Exception:
        return False

def _botTrackScroll(vehicle, speed, rotationSpeed, halfWidth):
    appearance = getattr(vehicle, 'appearance', None)
    if appearance is None:
        return False
    turn = rotationSpeed * halfWidth
    left = speed - turn
    right = speed + turn
    if abs(turn) > abs(speed) * 0.5:
        direction = 4 if rotationSpeed > 0 else 8
    elif speed > 0:
        direction = 1
    elif speed < 0:
        direction = 2
    else:
        direction = 0
    moving = abs(speed) > 0.01 or abs(rotationSpeed) > 0.01
    mode = (2 if moving else 1, direction)
    cache = _botTrackCache.get(vehicle.id)
    if cache is None:
        cache = _botTrackCache[vehicle.id] = {
            'vals': None,
            'mode': None,
            'linked': None,
            'tscReady': False,
        }
    try:
        wheels = None
        try:
            if getattr(appearance.typeDescriptor, 'isWheeledVehicle', False):
                wheels = getattr(appearance, 'wheelsAnimator', None)
        except Exception:
            wheels = None
        if wheels is not None:
            _botDriveWheels(vehicle, appearance, wheels, cache, left, right, rotationSpeed)
        else:
            tsc = getattr(appearance, 'trackScrollController', None)
            if tsc is not None:
                if not cache.get('tscReady', False):
                    tsc.activate()
                    flt = getattr(appearance, 'filter', None)
                    if flt is not None:
                        tsc.setData(flt)
                    cache['tscReady'] = True
                if cache['vals'] != (left, right):
                    tsc.setExternal(left, right)
                    cache['vals'] = (left, right)
            else:
                update = getattr(appearance, 'updateTracksScroll', None)
                if update is not None and cache['vals'] != (left, right):
                    update(left, right)
                    cache['vals'] = (left, right)
        try:
            if cache['mode'] != mode:
                appearance.changeEngineMode(mode)
                cache['mode'] = mode
        except Exception:
            pass
        return True
    except Exception:
        _botTrackCache.pop(vehicle.id, None)
        return False

def _ensureBotTrackTick():
    global _botTrackTickActive
    if _botTrackTickActive:
        return
    _botTrackTickActive = True
    BigWorld.callback(_BOT_TRACK_PERIOD, _botTrackTick)

def _botTrackTick():
    global _botTrackTickActive
    if not _botTrackTickActive:
        return
    if not _botVehicleIDs:
        _botTrackTickActive = False
        return
    try:
        import gui.mods.offhangar.physics as offhangar_physics
    except Exception:
        offhangar_physics = None
    for vehID in list(_botVehicleIDs):
        veh = BigWorld.entity(vehID)
        if veh is None:
            _botPrevMotion.pop(vehID, None)
            continue
        if getattr(veh, 'appearance', None) is None:
            _startBotVisual(vehID)
        speed = 0.0
        rotSpeed = 0.0
        halfTrackBase = 1.6
        if offhangar_physics is not None:
            body = offhangar_physics.world.get_body(vehID)
            if body is not None:
                speed = getattr(body, 'currentSpeed', 0.0)
                rotSpeed = getattr(body, 'currentRotationSpeed', 0.0)
                halfTrackBase = getattr(body, 'halfTrackBase', 1.6)
        try:
            m = Math.Matrix(veh.matrix)
            pos = m.translation
            yaw = m.yaw
            prev = _botPrevMotion.get(vehID)
            if prev is not None:
                prevPos, prevYaw = prev
                dx = pos.x - prevPos.x
                dz = pos.z - prevPos.z
                distSq = dx * dx + dz * dz
                if distSq > 0.000001:
                    dist = math.sqrt(distSq)
                    fwdX = math.sin(prevYaw)
                    fwdZ = math.cos(prevYaw)
                    signed = (dx * fwdX + dz * fwdZ) / dist
                    fallbackSpeed = signed * dist / _BOT_TRACK_PERIOD
                    if abs(speed) < 0.01:
                        speed = fallbackSpeed
                yawDelta = (yaw - prevYaw + math.pi) % (2.0 * math.pi) - math.pi
                fallbackRot = yawDelta / _BOT_TRACK_PERIOD
                if abs(rotSpeed) < 0.01:
                    rotSpeed = fallbackRot
            _botPrevMotion[vehID] = (pos, yaw)
        except Exception:
            pass
        _botTrackScroll(veh, speed, rotSpeed, halfTrackBase)
    BigWorld.callback(_BOT_TRACK_PERIOD, _botTrackTick)

def spawnRandomBot(team=2, offset=None, maxOffsetRadius=None):
    if not offhangar_battle.IS_IN_BATTLE or offhangar_battle._spaceID is None:
        LOG_DEBUG('spawnRandomBot: not in battle')
        return None
    global _battleLevels
    if maxOffsetRadius is None:
        maxOffsetRadius = _getConfigFloat('maxOffsetRadius', 25.0)

    if maxOffsetRadius < 10.0:
        maxOffsetRadius = 10.0

    avatar = BigWorld.player()

    if avatar is None:
        return None

    if _battleLevels is None:
        _battleLevels = _pickBattleLevels(_getPlayerVehicleLevel())

    vehicleTypeName = _pickRandomVehicleTypeName(_battleLevels)

    if vehicleTypeName is None:
        LOG_DEBUG('spawnRandomBot: no vehicle types available')
        return None

    try:
        compactDescr = _makeRandomCompactDescr(vehicleTypeName)
        descr = items_vehicles.VehicleDescr(compactDescr=compactDescr)
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return None

    maxHealth = offhangar_battle._getMaxHealth(descr)

    _botCounter[0] += 1
    botName = _pickBotName(team)

    spawnPos = None

    if offset is None:
        spawnPos = _getTeamSpawnPoint(avatar, team)

    if spawnPos is not None:
        pos = spawnPos
    else:
        try:
            basePos = avatar.position
        except Exception:
            basePos = (100.0, 10.0, 100.0)

        if offset is None:
            angle = random.uniform(0.0, 6.28318)
            radius = random.uniform(10.0, maxOffsetRadius)
            offset = (math.sin(angle) * radius, 0.0, math.cos(angle) * radius)

        pos = (basePos[0] + offset[0], basePos[1] + offset[1], basePos[2] + offset[2])

    spawnYaw = random.uniform(0.0, 2.0 * math.pi)

    publicInfo = {
        'compDescr': compactDescr,
        'team': team,
        'outfit': 0,
        'maxHealth': maxHealth,
        'accountDBID': 0,
        'name': botName,
        'clanDBID': 0,
        'clanAbbrev': '',
        'prebattleID': 0,
        'isTeamKiller': False,
        'squadType': 0,
        'vehicleRank': 0,
        'index': 0,
        'marksOnGun': 0,
        'crewGroups': [],
        'commanderSkinID': 0,
    }

    vehID = BigWorld.createEntity('Vehicle', offhangar_battle._spaceID, 0, pos, (0, 0, 0), {
        'publicInfo': publicInfo,
        'compDescr': compactDescr,
        'health': maxHealth,
        'isCrewActive': True,
        'avatarID': 0,
        'isHidden': False,
        'engineMode': (0, 0),
        'siegeState': 0,
        'stunInfo': {'stunFinishTime': 0.0, 'stunType': ''},
        'publicStateModifiers': [],
        'damageStickers': [],
        'gunAnglesPacked': 0,
        'wheelsState': 0,
        'wheelsScroll': [],
        'steeringAngles': [],
        'burnoutLevel': 0.0,
        'dotEffect': 0,
        'thermalVisionFinishTime': 0.0,
        'isSpeedCapturing': False,
        'isBlockingCapture': False,
        'isStrafing': False,
        'quickShellChangerFactor': 1.0,
        'perks': [],
        'perksRibbonNotify': 0,
        'crewCompactDescrs': [],
        'customRoleSlotTypeId': 0,
        'enhancements': {},
        'onRespawnReloadTimeFactor': 1.0,
        'setups': [],
        'setupsIndexes': [],
        'disabledSwitches': [],
        'vehPostProgression': [],
        'selectedComp7Skill': 0,
    })

    veh = BigWorld.entity(vehID)

    if veh is not None:
        try:
            veh.isOffline = True
        except Exception:
            pass

        try:
            import gui.mods.offhangar.physics as offhangar_physics
            if offhangar_physics.world.get_body(vehID) is None:
                try:
                    botMProv = Math.AdaptiveMatrixProvider()
                except Exception:
                    botMProv = None
                offhangar_physics.add_vehicle(
                    vehID,
                    entity_id=vehID,
                    position=pos,
                    yaw=spawnYaw,
                    mProv=botMProv,
                    becomeControlled=False
                )
            _ensurePhysicsRunning()
        except Exception:
            LOG_CURRENT_EXCEPTION()
        try:
            BigWorld.callback(0.0, lambda vid=vehID: _startBotVisual(vid))
        except Exception:
            _startBotVisual(vehID)
        _ensureBotTrackTick()
    arena = getattr(avatar, 'arena', None)

    if arena is not None:
        vehInfo = {
            'vehicleType': descr,
            'name': botName,
            'team': team,
            'isAlive': True,
            'isAvatarReady': True,
            'isTeamKiller': False,
            'accountDBID': 0,
            'clanAbbrev': '',
            'clanDBID': 0,
            'prebattleID': 0,
            'isPrebattleCreator': False,
            'forbidInBattleInvitations': False,
            'events': {},
            'igrType': IGR_TYPE.NONE,
            'personalMissionIDs': [],
            'personalMissionInfo': {},
            'ranked': None,
            'outfitCD': 0,
            'avatarSessionID': '',
            'wtr': 0,
            'fakeName': '',
            'badges': _getBotBadgesSafe(),
            'overriddenBadge': None,
            'maxHealth': maxHealth,
            'vehPostProgression': [],
            'customRoleSlotTypeId': 0,
            'botDisplayStatus': 0,
            'statTrackFrags': 0,
            'selectedComp7Skill': 0,
            'invID': 0,
            'crewGroups': [],
        }

        try:
            arena.vehicles[vehID] = vehInfo

            if hasattr(arena, 'onVehicleAdded'):
                arena.onVehicleAdded(vehID)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    try:
        from skeletons.gui.battle_session import IBattleSessionProvider
        from helpers import dependency

        sp = dependency.instance(IBattleSessionProvider)

        if sp is not None:
            arenaDP = sp.getArenaDP()

            if arenaDP is not None:
                arenaDP.addVehicleInfo(vehID, vehInfo)

            if hasattr(sp, 'onVehicleAdded'):
                sp.onVehicleAdded(vehID)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    _botVehicleIDs.append(vehID)

    try:
        import gui.mods.offhangar.ai as offhangar_ai
        offhangar_ai.register_brain(vehID, team, descr) 
    except Exception:
        pass

    try:
        import gui.mods.offhangar.shooting as offhangar_shooting
        offhangar_shooting.registerBot(vehID, team)
    except Exception:
        pass

    LOG_NOTE('spawnRandomBot: spawned %s %s id=%s team=%s' % (botName, vehicleTypeName, vehID, team))

    return vehID


def spawnBotWave(team1Count=None, team2Count=None, maxOffsetRadius=None, spawnDelay=None, team1AtSpawn=False, team2AtSpawn=True):
    global _battleLevels
    if team1Count is None:
        team1Count = _getConfigInt('team1Bots', 6)
    if team2Count is None:
        team2Count = _getConfigInt('team2Bots', 7)
    if maxOffsetRadius is None:
        maxOffsetRadius = _getConfigFloat('maxOffsetRadius', 50.0)
    if spawnDelay is None:
        spawnDelay = _getConfigFloat('spawnDelay', 0.15)
    if team1Count < 0:
        team1Count = 0
    if team2Count < 0:
        team2Count = 0
    if maxOffsetRadius < 15.0:
        maxOffsetRadius = 15.0
    if spawnDelay < 0.0:
        spawnDelay = 0.0
    _battleLevels = _pickBattleLevels(_getPlayerVehicleLevel())
    _spawnState = {
        'team1_remaining': team1Count,
        'team2_remaining': team2Count,
        'index': 0,
        'spawned_positions': [],
    }
    MIN_BOT_DISTANCE = 15.0

    def _findValidOffset(team, basePos, maxRadius):
        for _ in range(30):
            angle = random.uniform(0.0, 2.0 * math.pi)
            radius = random.uniform(15.0, maxRadius)
            offsetX = math.sin(angle) * radius
            offsetZ = math.cos(angle) * radius
            candidate = (basePos[0] + offsetX, basePos[1], basePos[2] + offsetZ)
            valid = True
            for existing in _spawnState['spawned_positions']:
                dx = candidate[0] - existing[0]
                dz = candidate[2] - existing[2]
                dist = math.sqrt(dx * dx + dz * dz)
                if dist < MIN_BOT_DISTANCE:
                    valid = False
                    break
            if valid:
                return (offsetX, 0.0, offsetZ), candidate
        # Fallback если не нашли свободное место
        angle = random.uniform(0.0, 2.0 * math.pi)
        radius = maxRadius + random.uniform(0.0, 20.0)
        offsetX = math.sin(angle) * radius
        offsetZ = math.cos(angle) * radius
        candidate = (basePos[0] + offsetX, basePos[1], basePos[2] + offsetZ)
        return (offsetX, 0.0, offsetZ), candidate

    def _spawnNext():
        if _spawnState['team1_remaining'] <= 0 and _spawnState['team2_remaining'] <= 0:
            LOG_NOTE('spawnBotWave: all bots spawned (%d team1, %d team2)' % (team1Count, team2Count))
            return
        if _spawnState['index'] % 2 == 0 and _spawnState['team1_remaining'] > 0:
            team = 1
            _spawnState['team1_remaining'] -= 1
        elif _spawnState['team2_remaining'] > 0:
            team = 2
            _spawnState['team2_remaining'] -= 1
        elif _spawnState['team1_remaining'] > 0:
            team = 1
            _spawnState['team1_remaining'] -= 1
        else:
            return
        _spawnState['index'] += 1
        if (team == 1 and team1AtSpawn) or (team == 2 and team2AtSpawn):
            offset = None
            spawnPos = None
        else:
            avatar = BigWorld.player()
            try:
                basePos = avatar.position
            except Exception:
                basePos = (100.0, 10.0, 100.0)
            offset, spawnPos = _findValidOffset(team, basePos, maxOffsetRadius)
        if spawnPos is not None:
            _spawnState['spawned_positions'].append(spawnPos)
        try:
            spawnRandomBot(team=team, offset=offset, maxOffsetRadius=maxOffsetRadius)
        except Exception:
            LOG_CURRENT_EXCEPTION()
        BigWorld.callback(spawnDelay, _spawnNext)

    BigWorld.callback(0.0, _spawnNext)

def clearBots():
    try:
        import gui.mods.offhangar.ai as offhangar_ai
        offhangar_ai.clear_brains()
    except Exception:
        pass
    global _battleLevels, _botTrackTickActive
    _botTrackTickActive = False
    _botTrackCache.clear()
    _botPrevMotion.clear()
    try:
        import gui.mods.offhangar.physics as offhangar_physics
        for vehID in _botVehicleIDs:
            offhangar_physics.remove_body(vehID)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    del _botVehicleIDs[:]

    _battleLevels = None

    try:
        _usedBotNames.clear()
    except Exception:
        pass