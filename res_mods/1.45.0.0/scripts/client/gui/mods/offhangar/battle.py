import os
import sys
import time
import random
import math
import Math
import ResMgr
import ArenaType
import Avatar
import BigWorld
import Vehicle as VehicleModule
import AvatarInputHandler
from constants import ARENA_BONUS_TYPE, ARENA_GUI_TYPE, IGR_TYPE
from items import vehicles as items_vehicles
from CurrentVehicle import g_currentVehicle
from gui.Scaleform.daapi.view.lobby.header.LobbyHeader import LobbyHeader
from gui.mods.offhangar.logging import LOG_DEBUG, LOG_NOTE
from gui.mods.offhangar.server import FakeServer
from gui.mods.offhangar.utils import override
from debug_utils import LOG_CURRENT_EXCEPTION
from constants import ATTACK_REASON_INDICES, ATTACK_REASON
try:
    import VehicleGunRotator as VehicleGunRotatorModule
except Exception:
    VehicleGunRotatorModule = None

def _crash_log(msg):
    try:
        msg_str = '[CRASH_TRACE] ' + str(msg)
        print(msg_str)
        try:
            root_dir = os.path.dirname(os.path.dirname(sys.executable))
            log_path = os.path.join(root_dir, 'crash_trace.txt')
            with open(log_path, 'a') as f:
                f.write('[{:.3f}] {}\n'.format(time.time(), msg_str))
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            with open('crash_trace.txt', 'a') as f:
                f.write('[{:.3f}] {}\n'.format(time.time(), msg_str))
                f.flush()
                os.fsync(f.fileno())
    except Exception:
        pass

try:
    from helpers import i18n
except Exception:
    i18n = None

try:
    import gui.mods.offhangar.data as offhangar_data
except Exception:
    offhangar_data = None

try:
    from gui.mods.offhangar.data import getVehicleIntCDByInvID
except Exception:
    getVehicleIntCDByInvID = None

try:
    from gui.shared.gui_items.Vehicle import Vehicle as GuiVehicle
except Exception:
    GuiVehicle = None

try:
    from gui.Scaleform.Waiting import Waiting
except Exception:
    Waiting = None

IS_IN_BATTLE = False
ALLOW_CLEAR = False
_spaceID = None
_avatarID = None
_vehicleID = None
_PLAYER_BADGES = ((), ())
_ARENA_UNIQUE_ID = 1
_PLAYER_VEHICLE_ENTITY_ID = 1
_OFFLINE_AVATAR_SESSION_ID = 'offline_session'
_OFFLINE_AVATAR_FALLBACK = {}
_OFFLINE_FALLBACK_NAMES = (
    'arenaUniqueID', 'arenaBonusType', 'arenaTypeID', 'arenaGuiType', 'arenaExtraData',
    'playLimits', 'team', 'playerVehicleID', 'databaseID', 'clanDBID',
    'clanAbbrev', 'tkillIsSuspected', 'denunciationsLeft', 'weatherPresetID',
    'paragons', 'getUnpackedEventsData', 'goodiesSnapshot', 'ownVehicleAuxPhysicsData',
    'avatarSessionID', 'ownVehicleGear', 'isGunLocked', 'isOnArena', 'invRotationOnBackMovement',
    'isObserver', 'isVehicleAlive', 'isWaitingForShot', 'autoAimVehicle', 'aimingInfo',
    'deviceStates', 'vehicles', 'consistentMatrices', 'vehicleOverturnLevel', 'isVehicleOverturned',
    'isVehicleDrowning', 'isOwnBarrelUnderWater', 'inCharge', 'isDisableRespawnMode',
    'canMakeDualShot', 'magneticAutoAimTags', 'followTeamID'
)

def _createFakeServer(name):
    try:
        return FakeServer(name=name, isMuted=True)
    except Exception:
        pass
    try:
        server = FakeServer()
        try:
            server.init(name=name, isMuted=True)
        except Exception:
            pass
        return server
    except Exception:
        return FakeServer()

def _force_load_destructibles_chunks(spaceID, centerPos):
    try:
        import AreaDestructibles
        import DestructiblesCache
        manager = getattr(AreaDestructibles, 'g_destructiblesManager', None)
        if manager is None:
            return

        minX, minZ = -500.0, -500.0
        maxX, maxZ = 500.0, 500.0

        try:
            bounds = BigWorld.getSpaceBounds()
            if bounds is not None:
                try:
                    minX = float(bounds[0][0]) if hasattr(bounds[0], '__getitem__') else float(getattr(bounds[0], 'x', -500.0))
                    minZ = float(bounds[0][1]) if hasattr(bounds[0], '__getitem__') else float(getattr(bounds[0], 'z', -500.0))
                    maxX = float(bounds[1][0]) if hasattr(bounds[1], '__getitem__') else float(getattr(bounds[1], 'x', 500.0))
                    maxZ = float(bounds[1][1]) if hasattr(bounds[1], '__getitem__') else float(getattr(bounds[1], 'z', 500.0))
                except Exception:
                    minX, minZ = -500.0, -500.0
                    maxX, maxZ = 500.0, 500.0
        except Exception:
            pass

        minChunkX = int(math.floor(minX * 0.01)) - 1
        minChunkZ = int(math.floor(minZ * 0.01)) - 1
        maxChunkX = int(math.floor(maxX * 0.01)) + 1
        maxChunkZ = int(math.floor(maxZ * 0.01)) + 1

        loadedChunks = getattr(manager, '_DestructiblesManager__loadedChunkIDs', None)
        if loadedChunks is None:
            loadedChunks = getattr(manager, 'loadedChunkIDs', None)

        for cx in range(minChunkX, maxChunkX + 1):
            for cz in range(minChunkZ, maxChunkZ + 1):
                try:
                    chunkID = DestructiblesCache.chunkIDFromChunkIndexes(cx, cz)
                except Exception:
                    continue
                if loadedChunks is not None and chunkID in loadedChunks:
                    continue
                try:
                    manager.onChunkLoad(chunkID, 1024)
                except Exception:
                    pass
        _crash_log('_force_load_destructibles_chunks: registered chunks from ({},{}) to ({},{})'.format(
            minChunkX, minChunkZ, maxChunkX, maxChunkZ))
    except Exception:
        LOG_CURRENT_EXCEPTION()

def _ensureTagsAreFrozenset(obj):
    if obj is None:
        return
    for attr in ('typeDescriptor', 'vehicleTypeDescriptor'):
        td = getattr(obj, attr, None)
        if td is not None:
            vType = getattr(td, 'type', None)
            if vType is not None:
                tags = getattr(vType, 'tags', None)
                if isinstance(tags, (list, tuple)):
                    try:
                        vType.tags = frozenset(tags)
                    except Exception:
                        pass

if VehicleGunRotatorModule is not None:
    try:
        @override(VehicleGunRotatorModule.VehicleGunRotator, '_VehicleGunRotator__shotPointSourceFunctor_Default')
        def VehicleGunRotator_shotPointSourceFunctor_Default(baseFunc, baseSelf):
            player = BigWorld.player()
            if player is None or not getattr(player, 'isOffline', False):
                return baseFunc(baseSelf)
            try:
                point = baseFunc(baseSelf)
                if point is not None:
                    return point
            except Exception:
                pass
            try:
                inputHandler = getattr(player, 'inputHandler', None)
                ctrl = getattr(inputHandler, 'ctrl', None)
                cam = getattr(ctrl, 'camera', None)
                aimingSystem = getattr(cam, 'aimingSystem', None)
                if aimingSystem is not None:
                    point = aimingSystem.getDesiredShotPoint()
                    if point is not None:
                        return point
            except Exception:
                pass
            try:
                cam = BigWorld.camera()
                if cam is not None:
                    direction = Math.Vector3(cam.direction)
                    return Math.Vector3(cam.position) + direction.scale(100.0)
            except Exception:
                pass
            return None
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        @override(VehicleGunRotatorModule.VehicleGunRotator, '_VehicleGunRotator__updateGunMarker')
        def VehicleGunRotator_updateGunMarker(baseFunc, baseSelf, forceRelaxTime=None):
            player = BigWorld.player()
            if player is None or not getattr(player, 'isOffline', False):
                return baseFunc(baseSelf, forceRelaxTime)
            try:
                return baseFunc(baseSelf, forceRelaxTime)
            except Exception:
                return None
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        @override(VehicleGunRotatorModule.VehicleGunRotator, '_VehicleGunRotator__onTick')
        def VehicleGunRotator_onTick(baseFunc, baseSelf):
            player = BigWorld.player()
            if player is None or not getattr(player, 'isOffline', False):
                return baseFunc(baseSelf)
            try:
                tickLength = getattr(baseSelf, '_VehicleGunRotator__ROTATION_TICK_LENGTH', 0.1)
                tickCallback = getattr(baseSelf, '_VehicleGunRotator__onTick', None)
                if tickCallback is not None:
                    try:
                        setattr(baseSelf, '_VehicleGunRotator__timerID', BigWorld.callback(tickLength, tickCallback))
                    except Exception:
                        pass
                shotPoint = None
                try:
                    shotFunctor = getattr(baseSelf, '_VehicleGunRotator__shotPointSourceFunctor', None)
                    if shotFunctor is not None:
                        shotPoint = shotFunctor()
                except Exception:
                    shotPoint = None

                # Сначала пытаемся не терять текущее наведение: если functor
                # не вернул валидную точку, берём последнюю известную точку
                # прицела вместо того, чтобы сразу прыгать на направление камеры.
                if shotPoint is None:
                    lastPoint = getattr(baseSelf, '_VehicleGunRotator__lastShotPoint', None)
                    if lastPoint is not None:
                        shotPoint = lastPoint

                # И только если валидной точки не было вообще никогда —
                # грубый фолбэк на направление камеры.
                if shotPoint is None:
                    try:
                        cam = BigWorld.camera()
                        if cam is not None:
                            direction = Math.Vector3(cam.direction)
                            shotPoint = Math.Vector3(cam.position) + direction.scale(100.0)
                    except Exception:
                        shotPoint = None

                currentTime = BigWorld.time()
                prevTime = getattr(baseSelf, '_VehicleGunRotator__time', currentTime)
                timeDiff = currentTime - prevTime
                if timeDiff < 0.02:
                    return
                if timeDiff > 0.2:
                    timeDiff = 0.2
                setattr(baseSelf, '_VehicleGunRotator__time', currentTime)
                try:
                    baseSelf.updateRotationAndGunMarker(shotPoint, timeDiff)
                except Exception:
                    try:
                        baseSelf._VehicleGunRotator__rotate(shotPoint, timeDiff)
                    except Exception:
                        pass
                return
            except Exception:
                return
    except Exception:
        LOG_CURRENT_EXCEPTION() 

@override(AvatarInputHandler.AvatarInputHandler, '_AvatarInputHandler__identifyVehicleType')
def AvatarInputHandler_identifyVehicleType(baseFunc, baseSelf):
    try:
        avatar = BigWorld.player()
        if avatar is None:
            return
        magnetAimTags = getattr(avatar, 'magneticAutoAimTags', frozenset())
        if not isinstance(magnetAimTags, (set, frozenset)):
            try:
                magnetAimTags = frozenset(magnetAimTags)
            except Exception:
                magnetAimTags = frozenset()
        veh = BigWorld.entity(getattr(avatar, 'playerVehicleID', 0))
        if veh is None:
            return
        td = getattr(veh, 'typeDescriptor', None)
        if td is None:
            return
        vType = getattr(td, 'type', None)
        if vType is None:
            return
        tags = getattr(vType, 'tags', [])
        if not isinstance(tags, (set, frozenset)):
            try:
                tags = frozenset(tags)
            except Exception:
                tags = frozenset()
        baseSelf._AvatarInputHandler__isSPG = 'SPG' in tags
        baseSelf._AvatarInputHandler__isATSPG = 'AT-SPG' in tags
        baseSelf._AvatarInputHandler__isDualGun = getattr(td, 'isDualgunVehicle', False)
        baseSelf._AvatarInputHandler__isFlamethrower = getattr(td, 'isFlamethrower', False)
        baseSelf._AvatarInputHandler__isAssaultSPG = getattr(td, 'isAssaultSPG', False)
        baseSelf._AvatarInputHandler__isMagnetAimEnabled = bool(magnetAimTags & tags)
        baseSelf._AvatarInputHandler__isOnlyArty = 'spgOnlyArtyMode' in tags
        return
    except Exception:
        LOG_CURRENT_EXCEPTION()

@override(Avatar.PlayerAvatar, '__init__')
def PlayerAvatar_init(baseFunc, baseSelf, *args, **kwargs):
    _crash_log('PlayerAvatar.init START')
    prevPlayer = BigWorld.player()
    baseSelf.isOffline = getattr(prevPlayer, 'isOffline', False)
    if baseSelf.isOffline:
        baseSelf.fakeCell = _createFakeServer('AvatarCell')
        baseSelf.fakeBase = _createFakeServer('AvatarBase')
    res = baseFunc(baseSelf, *args, **kwargs)
    _crash_log('PlayerAvatar.init END')
    return res

@override(Avatar.PlayerAvatar, '__getattribute__')
def PlayerAvatar_getattribute(baseFunc, baseSelf, name):
    if name in ('cell', 'base'):
        try:
            isOffline = baseFunc(baseSelf, 'isOffline')
        except Exception:
            isOffline = False
        if isOffline:
            name = 'fakeCell' if name == 'cell' else 'fakeBase'
    try:
        return baseFunc(baseSelf, name)
    except AttributeError:
        if getattr(baseSelf, 'isOffline', False):
            if name in _OFFLINE_AVATAR_FALLBACK:
                return _OFFLINE_AVATAR_FALLBACK[name]
            if name == 'ownVehicleGear':
                return 0
            if name == 'isGunLocked':
                return False
            if name == 'isOnArena':
                return True
            if name == 'invRotationOnBackMovement':
                return False
            if name == 'deviceStates':
                return {}
            if name == 'isVehicleAlive':
                vehID = 0
                try:
                    vehID = baseFunc(baseSelf, 'playerVehicleID')
                except Exception:
                    vehID = 0

                veh = BigWorld.entity(vehID) if vehID else None
                if veh is None:
                    return False

                return getattr(veh, 'health', 0) > 0 and getattr(veh, 'isCrewActive', False)
            if name == 'isWaitingForShot':
                return False
            if name in _OFFLINE_FALLBACK_NAMES and name in _OFFLINE_AVATAR_FALLBACK:
                return _OFFLINE_AVATAR_FALLBACK[name]
        raise

@override(Avatar.PlayerAvatar, 'onSpaceLoaded')
def PlayerAvatar_onSpaceLoaded(baseFunc, baseSelf, *args, **kwargs):
    _crash_log('PlayerAvatar.onSpaceLoaded START')
    if getattr(baseSelf, 'isOffline', False):
        try:
            _ensureTagsAreFrozenset(BigWorld.entity(getattr(baseSelf, 'playerVehicleID', 0)))
            _ensureTagsAreFrozenset(baseSelf)
            res = baseFunc(baseSelf, *args, **kwargs)
            _crash_log('PlayerAvatar.onSpaceLoaded END')
            return res
        except Exception:
            LOG_CURRENT_EXCEPTION()
            _crash_log('PlayerAvatar.onSpaceLoaded EXCEPTION')
            return None
    return baseFunc(baseSelf, *args, **kwargs)

try:
    import gui.mods.offhangar.physics as offhangar_physics
except Exception:
    offhangar_physics = None

@override(Avatar.PlayerAvatar, 'moveVehicle')
def PlayerAvatar_moveVehicle(baseFunc, baseSelf, flags, isKeyDown, handbrakeFired=False):
    if getattr(baseSelf, 'isOffline', False):
        veh = BigWorld.entity(getattr(baseSelf, 'playerVehicleID', 0))
        if veh is not None:
            try:
                if not veh.isAlive():
                    return
            except Exception:
                if getattr(veh, 'health', 0) <= 0:
                    return
        if offhangar_physics is not None:
            forward = 0
            if flags & 1:
                forward = 1
            elif flags & 2:
                forward = -1

            rotation = 0
            if flags & 4:
                rotation = -1
            elif flags & 8:
                rotation = 1

            try:
                offhangar_physics.set_control(getattr(baseSelf, 'playerVehicleID', 0), forward, rotation)
            except Exception:
                LOG_CURRENT_EXCEPTION()
        return

    return baseFunc(baseSelf, flags, isKeyDown, handbrakeFired)

@override(Avatar.PlayerAvatar, 'getOwnVehicleMatrix')
def PlayerAvatar_getOwnVehicleMatrix(baseFunc, baseSelf, default=None):
    if getattr(baseSelf, 'isOffline', False):
        mProv = getattr(baseSelf, '_PlayerAvatar__ownVehicleMProv', None)
        vehID = getattr(baseSelf, 'playerVehicleID', 0)
        physicsOwnsBody = False
        if offhangar_physics is not None:
            try:
                body = offhangar_physics.world.get_body(vehID)
                physicsOwnsBody = body is not None and offhangar_physics.world.controlled_body_id == vehID
            except Exception:
                physicsOwnsBody = False
        if physicsOwnsBody and mProv is not None:
            return mProv
        pos = None
        veh = BigWorld.entity(vehID) if vehID else None
        if veh is not None and hasattr(veh, 'matrix'):
            try:
                m = Math.Matrix(veh.matrix)
                if m.translation != Math.Matrix().translation:
                    pos = m.translation
            except Exception:
                pass
        if pos is None:
            try:
                apos = getattr(baseSelf, 'position', None)
                if apos and (apos[0] != 0 or apos[1] != 0 or apos[2] != 0):
                    pos = apos
            except Exception:
                pass
        if pos is None or (pos[0] == 0 and pos[1] == 0 and pos[2] == 0):
            pos = Math.Vector3(100.0, 10.0, 100.0)
        validMatrix = Math.Matrix()
        validMatrix.setTranslate(pos)
        if mProv is not None:
            try:
                mProv.setStaticTransform(validMatrix)
            except Exception:
                pass
            return mProv
        return validMatrix
    return baseFunc(baseSelf, default)

@override(Avatar.PlayerAvatar, 'getOwnVehiclePosition')
def PlayerAvatar_getOwnVehiclePosition(baseFunc, baseSelf):
    if getattr(baseSelf, 'isOffline', False):
        m = baseSelf.getOwnVehicleMatrix()
        if m is not None:
            try:
                return Math.Matrix(m).translation
            except Exception:
                pass
        return Math.Vector3(100.0, 10.0, 100.0)
    return baseFunc(baseSelf)

@override(Avatar.PlayerAvatar, 'getObservedVehicleMatrix')
def PlayerAvatar_getObservedVehicleMatrix(baseFunc, baseSelf):
    if getattr(baseSelf, 'isOffline', False):
        return None
    return baseFunc(baseSelf)

@override(Avatar.PlayerAvatar, 'getOwnVehicleStabilisedMatrix')
def PlayerAvatar_getOwnVehicleStabilisedMatrix(baseFunc, baseSelf):
    if getattr(baseSelf, 'isOffline', False):
        stabProv = getattr(baseSelf, '_PlayerAvatar__ownVehicleStabMProv', None)
        if stabProv is not None:
            try:
                m = Math.Matrix(stabProv)
                if m.translation == Math.Matrix().translation:
                    safeMatrix = Math.Matrix()
                    safeMatrix.setTranslate(Math.Vector3(100.0, 10.0, 100.0))
                    stabProv.setStaticTransform(safeMatrix)
            except Exception:
                pass
            return stabProv
        safeMatrix = Math.Matrix()
        safeMatrix.setTranslate(Math.Vector3(100.0, 10.0, 100.0))
        return safeMatrix
    return baseFunc(baseSelf)

def _getOfflineBadgesSafe():
    return _PLAYER_BADGES

@override(Avatar.PlayerAvatar, 'getOwnVehicleTurretMatrix')
def PlayerAvatar_getOwnVehicleTurretMatrix(baseFunc, baseSelf):
    if getattr(baseSelf, 'isOffline', False):
        turretProv = getattr(baseSelf, '_PlayerAvatar__ownVehicleTurretMProv', None)
        if turretProv is not None:
            try:
                m = Math.Matrix(turretProv)
                if m.translation == Math.Matrix().translation:
                    safeMatrix = Math.Matrix()
                    safeMatrix.setTranslate(Math.Vector3(100.0, 10.0, 100.0))
                    turretProv.setStaticTransform(safeMatrix)
            except Exception:
                pass
            return turretProv
        safeMatrix = Math.Matrix()
        safeMatrix.setTranslate(Math.Vector3(100.0, 10.0, 100.0))
        return safeMatrix
    return baseFunc(baseSelf)

@override(Avatar.PlayerAvatar, 'getOwnVehicleShotDispersionAngle')
def PlayerAvatar_getOwnVehicleShotDispersionAngle(baseFunc, baseSelf, turretRotationSpeed, withShot=0):
    if getattr(baseSelf, 'isOffline', False):
        try:
            return baseFunc(baseSelf, turretRotationSpeed, withShot)
        except Exception:
            return [0.0, 0.0, 0.0, 0.0]
    return baseFunc(baseSelf, turretRotationSpeed, withShot)

@override(Avatar.PlayerAvatar, 'vehicle_onAppearanceReady')
def PlayerAvatar_vehicle_onAppearanceReady(baseFunc, baseSelf, vehicle):
    _crash_log('vehicle_onAppearanceReady START vehID={}'.format(vehicle.id))
    if getattr(baseSelf, 'isOffline', False):
        try:
            _ensureTagsAreFrozenset(vehicle)
            baseSelf._PlayerAvatar__vehicles.add(vehicle)
            if vehicle.id == baseSelf.playerVehicleID:
                _crash_log('vehicle_onAppearanceReady is player vehicle')
                vehicle.isPlayerVehicle = True
                baseSelf.vehicleTypeDescriptor = vehicle.typeDescriptor
                baseSelf._PlayerAvatar__isVehicleAlive = True
                m = Math.Matrix()
                tm = Math.Matrix()
                try:
                    if hasattr(vehicle, 'filter') and vehicle.filter is not None and hasattr(vehicle.filter, 'bodyMatrix'):
                        m = Math.Matrix(vehicle.filter.bodyMatrix)
                        tm = Math.Matrix(vehicle.filter.turretMatrix)
                    elif hasattr(vehicle, 'appearance') and vehicle.appearance and hasattr(vehicle.appearance, 'turretMatrix'):
                        m = Math.Matrix(vehicle.matrix)
                        tm = Math.Matrix(vehicle.appearance.turretMatrix)
                    else:
                        m = Math.Matrix(vehicle.matrix)
                        tm = m
                except Exception:
                    _crash_log('vehicle_onAppearanceReady failed to get vehicle matrices')
                if m.translation == Math.Matrix().translation:
                    _crash_log('vehicle_onAppearanceReady ZERO matrix detected, applying fallback')
                    pos = getattr(baseSelf, 'position', (100.0, 10.0, 100.0))
                    if not pos or (pos[0] == 0 and pos[1] == 0 and pos[2] == 0):
                        pos = (100.0, 10.0, 100.0)
                    m.setTranslate(pos)
                    tm.setTranslate(pos)
                baseSelf._PlayerAvatar__ownVehicleMProv.setStaticTransform(m)
                baseSelf._PlayerAvatar__ownVehicleTurretMProv.setStaticTransform(tm)
                baseSelf._PlayerAvatar__ownVehicleStabMProv.setStaticTransform(m)
                if offhangar_physics is not None:
                    try:
                        offhangar_physics.add_vehicle(
                            vehicle.id,
                            position=m.translation,
                            yaw=m.yaw,
                            mProv=baseSelf._PlayerAvatar__ownVehicleMProv
                        )
                        _crash_log('vehicle_onAppearanceReady physics body registered')
                    except Exception:
                        LOG_CURRENT_EXCEPTION()
                        _crash_log('vehicle_onAppearanceReady physics registration failed')
            baseSelf._PlayerAvatar__initProgress |= 8
            baseSelf._PlayerAvatar__onInitStepCompleted()
            if baseSelf._PlayerAvatar__initProgress & 16 and not vehicle.isStarted:
                baseSelf._PlayerAvatar__startVehicleVisual(vehicle, resetControllers=True)
            else:
                baseSelf.consistentMatrices.notifyVehicleLoaded(baseSelf, vehicle)
        except Exception:
            LOG_CURRENT_EXCEPTION()
            _crash_log('vehicle_onAppearanceReady EXCEPTION')
            return
        _crash_log('vehicle_onAppearanceReady END (offline branch)')
        return
    return baseFunc(baseSelf, vehicle)

@override(Avatar.PlayerAvatar, 'onBecomePlayer')
def PlayerAvatar_onBecomePlayer(baseFunc, baseSelf):
    _crash_log('PlayerAvatar.onBecomePlayer START')
    if getattr(baseSelf, 'isOffline', False):
        try:
            res = baseFunc(baseSelf)
            _crash_log('PlayerAvatar.onBecomePlayer END')
            return res
        except Exception:
            LOG_CURRENT_EXCEPTION()
            _crash_log('PlayerAvatar.onBecomePlayer EXCEPTION')
            return None
    return baseFunc(baseSelf)

@override(Avatar.PlayerAvatar, 'onEnterWorld')
def PlayerAvatar_onEnterWorld(baseFunc, baseSelf, *args, **kwargs):
    _crash_log('PlayerAvatar.onEnterWorld START')
    if getattr(baseSelf, 'isOffline', False):
        try:
            res = baseFunc(baseSelf, *args, **kwargs)
            _crash_log('PlayerAvatar.onEnterWorld END')
            return res
        except Exception:
            LOG_CURRENT_EXCEPTION()
            _crash_log('PlayerAvatar.onEnterWorld EXCEPTION')
            return None
    return baseFunc(baseSelf, *args, **kwargs)

@override(Avatar.PlayerAvatar, '_PlayerAvatar__startVehicleVisual')
def PlayerAvatar_startVehicleVisual(baseFunc, baseSelf, vehicle, resetControllers=False):
    _crash_log('PlayerAvatar.__startVehicleVisual START vehID={}'.format(getattr(vehicle, 'id', 0)))
    if getattr(baseSelf, 'isOffline', False):
        try:
            if not getattr(vehicle, 'isStarted', False):
                vehicle.startVisual()
            try:
                baseSelf.onVehicleEnterWorld(vehicle)
            except Exception:
                LOG_CURRENT_EXCEPTION()
            try:
                baseSelf.consistentMatrices.notifyVehicleLoaded(baseSelf, vehicle)
            except Exception:
                LOG_CURRENT_EXCEPTION()
            if getattr(vehicle, 'id', 0) == getattr(baseSelf, 'playerVehicleID', 0):
                try:
                    baseSelf.guiSessionProvider.setPlayerVehicle(baseSelf.playerVehicleID, baseSelf.vehicleTypeDescriptor)
                except Exception:
                    LOG_CURRENT_EXCEPTION()
            _crash_log('PlayerAvatar.__startVehicleVisual END (offline safe branch)')
            return
        except Exception:
            LOG_CURRENT_EXCEPTION()
            _crash_log('PlayerAvatar.__startVehicleVisual EXCEPTION')
            return
    return baseFunc(baseSelf, vehicle, resetControllers)

@override(Avatar.PlayerAvatar, '_PlayerAvatar__onSetOwnVehicleAuxPhysicsData')
def PlayerAvatar_onSetOwnVehicleAuxPhysicsData(baseFunc, baseSelf, prev=None):
    if getattr(baseSelf, 'isOffline', False):
        return
    return baseFunc(baseSelf, prev)

@override(Avatar.PlayerAvatar, 'setClientReady')
def PlayerAvatar_setClientReady(baseFunc, baseSelf, *args, **kwargs):
    _crash_log('PlayerAvatar.setClientReady START')
    if getattr(baseSelf, 'isOffline', False):
        try:
            baseSelf._PlayerAvatar__initProgress |= 32
            _crash_log('setClientReady: initProgress set to {}'.format(baseSelf._PlayerAvatar__initProgress))
            try:
                baseSelf.inputHandler.setForcedGuiControlMode(baseSelf._PlayerAvatar__forcedGuiCtrlModeFlags)
            except Exception:
                LOG_CURRENT_EXCEPTION()
            for v in BigWorld.entities.values():
                if getattr(v, 'inWorld', False) and isinstance(v, VehicleModule.Vehicle) and not getattr(v, 'isStarted', False):
                    try:
                        baseSelf._PlayerAvatar__startVehicleVisual(v)
                    except Exception:
                        LOG_CURRENT_EXCEPTION()
            try:
                baseSelf._PlayerAvatar__setIsOnArena(True)
                _crash_log('setClientReady: __setIsOnArena(True) called')
            except Exception:
                LOG_CURRENT_EXCEPTION()
            try:
                arena = getattr(baseSelf, 'arena', None)
                if arena is not None:
                    callback = getattr(baseSelf, '_PlayerAvatar__onArenaVehicleKilled', None)
                    if callback is not None:
                        arena.onVehicleKilled += callback
            except Exception:
                pass
            try:
                from constants import ARENA_PERIOD
                period = ARENA_PERIOD.BATTLE
                isBattle = True
                endTime = BigWorld.serverTime() + 900.0
                length = 900.0
                addInfo = {}
                try:
                    setattr(baseSelf.arena, '_ClientArena__periodInfo', (period, endTime, length, addInfo))
                except Exception:
                    pass
                try:
                    baseSelf.arena.onPeriodChange += baseSelf._PlayerAvatar__onArenaPeriodChange
                except Exception:
                    pass
                try:
                    baseSelf._PlayerAvatar__onArenaPeriodChange(period, endTime, length, addInfo)
                except Exception:
                    LOG_CURRENT_EXCEPTION()
                from PlayerEvents import g_playerEvents
                g_playerEvents.onArenaStateChange(isBattle, period)
                g_playerEvents.onArenaPeriodChange(period, endTime, length, addInfo)
                try:
                    baseSelf.arena.onPeriodChange(period, endTime, length, addInfo)
                except Exception:
                    LOG_CURRENT_EXCEPTION()
                _crash_log('setClientReady: forced period to BATTLE (3)')
            except Exception:
                LOG_CURRENT_EXCEPTION()
            try:
                vehicle = BigWorld.entity(baseSelf.playerVehicleID)
                if vehicle is not None:
                    vehicle.resetProperties()
                    _crash_log('setClientReady: vehicle.resetProperties() called')
            except Exception:
                LOG_CURRENT_EXCEPTION()
            try:
                from PlayerEvents import g_playerEvents
                g_playerEvents.onAvatarReady()
            except Exception:
                LOG_CURRENT_EXCEPTION()
            _crash_log('setClientReady: isOnArena={}'.format(getattr(baseSelf, '_PlayerAvatar__isOnArena', 'MISSING')))
            _crash_log('PlayerAvatar.setClientReady END (offline safe branch)')
            return
        except Exception:
            LOG_CURRENT_EXCEPTION()
            return
    return baseFunc(baseSelf, *args, **kwargs)

@override(VehicleModule.Vehicle, '__init__')
def Vehicle_init(baseFunc, baseSelf, *args, **kwargs):
    _crash_log('Vehicle.init START')
    prevPlayer = BigWorld.player()
    baseSelf.isOffline = getattr(prevPlayer, 'isOffline', False)
    if baseSelf.isOffline:
        baseSelf.fakeCell = _createFakeServer('VehicleCell')
        baseSelf.fakeBase = _createFakeServer('VehicleBase')
    res = baseFunc(baseSelf, *args, **kwargs)
    _crash_log('Vehicle.init END')
    return res

@override(VehicleModule.Vehicle, '__getattribute__')
def Vehicle_getattribute(baseFunc, baseSelf, name):
    if name in ('cell', 'base'):
        try:
            isOffline = baseFunc(baseSelf, 'isOffline')
        except Exception:
            isOffline = False
        if isOffline:
            name = 'fakeCell' if name == 'cell' else 'fakeBase'
    return baseFunc(baseSelf, name)

try:
    from vehicle_systems import model_assembler
except Exception:
    model_assembler = None

@override(VehicleModule.Vehicle, 'onEnterWorld')
def Vehicle_onEnterWorld(baseFunc, baseSelf, *args, **kwargs):
    _crash_log('Vehicle.onEnterWorld START id={}'.format(baseSelf.id))
    if getattr(baseSelf, 'isOffline', False):
        try:
            if model_assembler is not None and getattr(baseSelf, 'filter', None) is None:
                td = getattr(baseSelf, 'typeDescriptor', None)
                if td is not None:
                    try:
                        vf = model_assembler.createVehicleFilter(td)
                        baseSelf.filter = vf
                        _crash_log('Vehicle.onEnterWorld: pre-created VehicleFilter (id={})'.format(baseSelf.id))
                    except Exception:
                        LOG_CURRENT_EXCEPTION()
                else:
                    _crash_log('Vehicle.onEnterWorld: typeDescriptor not yet available, filter NOT created')
        except Exception:
            LOG_CURRENT_EXCEPTION()
        try:
            res = baseFunc(baseSelf, *args, **kwargs)
            _crash_log('Vehicle.onEnterWorld END')
            return res
        except Exception:
            LOG_CURRENT_EXCEPTION()
            _crash_log('Vehicle.onEnterWorld EXCEPTION')
            return None
    return baseFunc(baseSelf, *args, **kwargs)

def _offhangar_gr_as_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _offhangar_gr_get_field(obj, name, default=None):
    if obj is None:
        return default
    getter = getattr(obj, 'get', None)
    if callable(getter):
        try:
            return getter(name, default)
        except Exception:
            pass
    return getattr(obj, name, default)


def _offhangar_gr_get_path(obj, path, default=None):
    cur = obj
    for part in path.split('.'):
        cur = _offhangar_gr_get_field(cur, part, None)
        if cur is None:
            return default
    if cur is None:
        return default
    return cur


def _offhangar_gr_first_path(obj, paths):
    """Возвращает (значение, путь) для первого пути, где нашлось не-None значение."""
    for path in paths:
        value = _offhangar_gr_get_path(obj, path, None)
        if value is not None:
            return value, path
    return None, None


def _offhangar_normalize_rotation_speed(value):
    """
    В XML-конфигах World of Tanks скорость поворота башни/орудия обычно
    задаётся в градусах/сек. VehicleGunRotator работает в радианах/сек.
    Если число уже похоже на радианы (<= ~3.2 рад ~ 183°/сек), не трогаем его,
    иначе конвертируем градусы -> радианы.
    """
    v = abs(_offhangar_gr_as_float(value, 0.0))
    if v <= 0.0:
        return 0.0
    if v > 3.2:
        return math.radians(v)
    return v


def _get_offline_gun_rotator_speeds(vehicle):
    """
    Скорость поворота башни (yaw) и скорость наведения орудия по вертикали (pitch)
    берутся из typeDescriptor конкретной машины (т.е. из её XML-конфига),
    а не из захардкоженных значений. При отсутствии данных используется
    осторожный дефолт ~24 град/с, и факт фолбэка пишется в crash_trace.txt,
    чтобы баг с рассинхроном башни/прицела был диагностируем.
    """
    DEFAULT_SPEED = math.radians(24.0)  # ~24 град/с - типичное значение для среднего танка

    turretSpeed = DEFAULT_SPEED
    gunSpeed = DEFAULT_SPEED

    td = getattr(vehicle, 'typeDescriptor', None)
    if td is None:
        _crash_log('_get_offline_gun_rotator_speeds: no typeDescriptor, using default {:.3f} rad/s'.format(DEFAULT_SPEED))
        return turretSpeed, gunSpeed

    rawTurret, turretPath = _offhangar_gr_first_path(td, (
        'turret.rotationSpeed',
        'turret.rotationSpeedLimit',
        'type.turret.rotationSpeed',
        'chassis.rotationSpeed',  # для машин без поворотной башни (некоторые ПТ-САУ)
    ))
    if rawTurret is not None:
        normalized = _offhangar_normalize_rotation_speed(rawTurret)
        if normalized > 0.0:
            turretSpeed = normalized
        else:
            _crash_log('_get_offline_gun_rotator_speeds: turret path "{}" gave {!r}, using default'.format(turretPath, rawTurret))
    else:
        _crash_log('_get_offline_gun_rotator_speeds: turret.rotationSpeed not found in typeDescriptor for vehicle id={}, using default {:.3f} rad/s'.format(
            getattr(vehicle, 'id', '?'), DEFAULT_SPEED))

    rawGun, gunPath = _offhangar_gr_first_path(td, (
        'gun.rotationSpeed',
        'gun.pitchLimits.rotationSpeed',
        'type.gun.rotationSpeed',
    ))
    if rawGun is not None:
        normalized = _offhangar_normalize_rotation_speed(rawGun)
        if normalized > 0.0:
            gunSpeed = normalized
        else:
            _crash_log('_get_offline_gun_rotator_speeds: gun path "{}" gave {!r}, using turret speed as fallback'.format(gunPath, rawGun))
            gunSpeed = turretSpeed
    else:
        # У орудия часто нет отдельного поля вертикальной скорости наведения в XML —
        # разумное приближение: взять скорость поворота башни.
        gunSpeed = turretSpeed

    _crash_log('_get_offline_gun_rotator_speeds: vehicle id={} turretSpeed={:.3f} rad/s ({:.1f} deg/s) [{}], gunSpeed={:.3f} rad/s [{}]'.format(
        getattr(vehicle, 'id', '?'), turretSpeed, math.degrees(turretSpeed), turretPath, gunSpeed, gunPath))

    return turretSpeed, gunSpeed

def _ensure_offline_gun_rotator(avatar, vehicle):
    if avatar is None:
        return
    try:
        if getattr(avatar, 'gunRotator', None) is None:
            if VehicleGunRotatorModule is not None:
                avatar.gunRotator = VehicleGunRotatorModule.VehicleGunRotator(avatar)
            else:
                from VehicleGunRotator import VehicleGunRotator
                avatar.gunRotator = VehicleGunRotator(avatar)
        turretSpeed, gunSpeed = _get_offline_gun_rotator_speeds(vehicle)
        turretYaw = 0.0
        gunPitch = 0.0
        try:
            turretYaw, gunPitch = vehicle.getAimParams()
            turretYaw = float(turretYaw)
            gunPitch = float(gunPitch)
        except Exception:
            turretYaw = 0.0
            gunPitch = 0.0
        try:
            avatar.gunRotator.clientMode = True
        except Exception:
            pass
        started = False
        try:
            started = bool(getattr(avatar.gunRotator, '_VehicleGunRotator__isStarted', False))
        except Exception:
            started = False
        if not started:
            try:
                avatar.gunRotator.update(turretYaw, gunPitch, turretSpeed, gunSpeed)
            except Exception:
                LOG_CURRENT_EXCEPTION()
        try:
            if not getattr(avatar.gunRotator, '_VehicleGunRotator__isStarted', False):
                setattr(avatar.gunRotator, '_VehicleGunRotator__speedsInitialized', True)
                setattr(avatar.gunRotator, '_VehicleGunRotator__maxTurretRotationSpeed', turretSpeed)
                setattr(avatar.gunRotator, '_VehicleGunRotator__maxGunRotationSpeed', gunSpeed)
                setattr(avatar.gunRotator, '_VehicleGunRotator__isStarted', True)
                setattr(avatar.gunRotator, '_VehicleGunRotator__time', BigWorld.time())
                tickLength = getattr(avatar.gunRotator, '_VehicleGunRotator__ROTATION_TICK_LENGTH', 0.1)
                tickCallback = getattr(avatar.gunRotator, '_VehicleGunRotator__onTick', None)
                if tickCallback is not None:
                    setattr(avatar.gunRotator, '_VehicleGunRotator__timerID', BigWorld.callback(tickLength, tickCallback))
        except Exception:
            LOG_CURRENT_EXCEPTION()
    except Exception:
        LOG_CURRENT_EXCEPTION()

@override(VehicleModule.Vehicle, 'startVisual')
def Vehicle_startVisual(baseFunc, baseSelf, *args, **kwargs):
    _crash_log('Vehicle.startVisual START id={}'.format(baseSelf.id))
    if getattr(baseSelf, 'isOffline', False):
        original_startPhysics = None
        original_stopPhysics = None
        try:
            avatar = BigWorld.player()
            if avatar is not None:
                _crash_log('Vehicle.startVisual: avatar found')
                _ensure_offline_gun_rotator(avatar, baseSelf)
            _crash_log('Vehicle.startVisual: disabling internal C++ physics to prevent crash')
            original_startPhysics = getattr(baseSelf, '_Vehicle__startPhysics', None)
            baseSelf._Vehicle__startPhysics = lambda: None
            original_stopPhysics = getattr(baseSelf, '_Vehicle__stopPhysics', None)
            baseSelf._Vehicle__stopPhysics = lambda: None
            original_filter = getattr(baseSelf, 'filter', None)
            if original_filter is not None and hasattr(original_filter, 'setVehiclePhysics'):
                original_filter.setVehiclePhysics = lambda *a, **kw: None
            _crash_log('Vehicle.startVisual: calling baseFunc')
            res = baseFunc(baseSelf, *args, **kwargs)
            try:
                if avatar is not None and baseSelf.isPlayerVehicle and baseSelf.isAlive():
                    appearance = getattr(baseSelf, 'appearance', None)
                    gunRotator = getattr(avatar, 'gunRotator', None)
                    if appearance is not None and gunRotator is not None and hasattr(appearance, 'setupGunMatrixTargets'):
                        appearance.setupGunMatrixTargets(gunRotator)
            except Exception:
                LOG_CURRENT_EXCEPTION()
            _crash_log('Vehicle.startVisual END')
            return res
        except Exception:
            LOG_CURRENT_EXCEPTION()
            _crash_log('Vehicle.startVisual EXCEPTION')
            return None
        finally:
            if original_startPhysics is not None:
                baseSelf._Vehicle__startPhysics = original_startPhysics
            if original_stopPhysics is not None:
                baseSelf._Vehicle__stopPhysics = original_stopPhysics
            try:
                appearance = getattr(baseSelf, 'appearance', None)
                if appearance is not None:
                    if getattr(appearance, 'filter', None) is None:
                        flt = getattr(appearance, '_CommonTankAppearance__filter', None)
                        if flt is not None:
                            appearance.filter = flt
                    tsc = getattr(appearance, 'trackScrollController', None)
                    if tsc is not None:
                        flt = getattr(appearance, 'filter', None)
                        if flt is not None:
                            tsc.activate()
                            tsc.setData(flt)
            except Exception:
                LOG_CURRENT_EXCEPTION()
    return baseFunc(baseSelf, *args, **kwargs)

@override(VehicleModule.Vehicle, 'resetProperties')
def Vehicle_resetProperties(baseFunc, baseSelf, *args, **kwargs):
    if getattr(baseSelf, 'isOffline', False):
        return
    return baseFunc(baseSelf, *args, **kwargs)

@override(VehicleModule.Vehicle, 'startGUIVisual')
def Vehicle_startGUIVisual(baseFunc, baseSelf, *args, **kwargs):
    try:
        return baseFunc(baseSelf, *args, **kwargs)
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return None


@override(VehicleModule.Vehicle, 'stopGUIVisual')
def Vehicle_stopGUIVisual(baseFunc, baseSelf, *args, **kwargs):
    try:
        return baseFunc(baseSelf, *args, **kwargs)
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return None

@override(VehicleModule.Vehicle, 'stopGUIVisual')
def Vehicle_stopGUIVisual(baseFunc, baseSelf, *args, **kwargs):
    if getattr(baseSelf, 'isOffline', False):
        return
    return baseFunc(baseSelf, *args, **kwargs)

def _makeFullCompactDescr(compactDescr):
    try:
        descr = items_vehicles.VehicleDescr(compactDescr=compactDescr)
        return descr.makeCompactDescr()
    except Exception:
        pass
    try:
        vType = items_vehicles.getVehicleType(compactDescr)
        descr = items_vehicles.VehicleDescr(typeID=vType.id)
        return descr.makeCompactDescr()
    except Exception:
        return compactDescr

def _getSelectedVehicleCompactDescr():
    item = getattr(g_currentVehicle, 'item', None)
    if item is None:
        return None
    descriptor = getattr(item, 'descriptor', None)
    if descriptor is not None:
        try:
            return descriptor.makeCompactDescr()
        except Exception:
            pass
    for attr in ('intCD', 'typeCompDescr', 'compactDescr'):
        value = getattr(item, attr, None)
        if value:
            return _makeFullCompactDescr(value)
    itemType = getattr(item, 'type', None)
    if itemType is not None:
        for attr in ('intCD', 'compactDescr'):
            value = getattr(itemType, attr, None)
            if value:
                return _makeFullCompactDescr(value)
    return None

def _ensureInventory():
    if offhangar_data is None:
        return
    try:
        if not getattr(offhangar_data, '_invID_to_intCD', {}):
            offhangar_data.getOfflineInventory()
    except Exception:
        pass

def _getDefaultVehicleCompactDescr():
    try:
        ids = getattr(items_vehicles.g_list, '_VehicleList__ids', {})
        for value in list(ids.values()):
            try:
                typeCD = items_vehicles.makeIntCompactDescrByID('vehicle', value[0], value[1])
                return _makeFullCompactDescr(typeCD)
            except Exception:
                continue
    except Exception:
        pass
    return None

def _normalizeBattleVehicleIntCD(value):
    if value is None:
        return 0
    try:
        if isinstance(value, (int, long)):
            cd = int(value)
        else:
            cd = value
        nationID, vehicleTypeID = items_vehicles.parseVehicleCompactDescr(cd)
        return items_vehicles.makeIntCompactDescrByID('vehicle', nationID, vehicleTypeID)
    except Exception:
        try:
            return int(value)
        except Exception:
            return 0

def _ensureBattleOutfitDescr(descr):
    if isinstance(descr, basestring):
        return descr
    if isinstance(descr, (int, long)):
        try:
            from items import parseIntCompactDescr
            from items.components.c11n_constants import CustomizationType, ApplyArea
            from serializable_types.customizations import CustomizationOutfit, CamouflageComponent
            itemTypeID, cType, itemId = parseIntCompactDescr(descr)
            if itemTypeID == 12:
                if cType == CustomizationType.STYLE:
                    return CustomizationOutfit(styleId=itemId).makeCompDescr()
                if cType == CustomizationType.CAMOUFLAGE:
                    regions = []
                    for name in ('HULL_CAMOUFLAGE_REGIONS', 'TURRET_CAMOUFLAGE_REGIONS', 'GUN_CAMOUFLAGE_REGIONS'):
                        regions.extend(getattr(ApplyArea, name, ()))
                    appliedTo = reduce(int.__or__, regions, 0)
                    return CustomizationOutfit(camouflages=[CamouflageComponent(id=itemId, appliedTo=appliedTo)]).makeCompDescr()
        except Exception:
            pass
    try:
        return descr.makeCompDescr() or ''
    except Exception:
        return ''

def _getGuiVehicleOutfitDescr(vehInvID):
    item = getattr(g_currentVehicle, 'item', None)
    if item is None:
        return ''
    if vehInvID and getattr(item, 'invID', None) != vehInvID:
        return ''
    try:
        from items.components.c11n_constants import SeasonType
        try:
            styleOutfitData = item.itemsCache.items.inventory.getOutfitData(item.intCD, SeasonType.ALL)
            if styleOutfitData:
                return _ensureBattleOutfitDescr(styleOutfitData)
        except Exception:
            pass
        for season in SeasonType.SEASONS:
            try:
                component = item.getOutfitComponent(season)
                if component:
                    descr = _ensureBattleOutfitDescr(component)
                    if descr:
                        return descr
            except Exception:
                continue
        try:
            outfits = getattr(item, 'outfits', None)
            if outfits:
                for component in outfits.itervalues():
                    descr = _ensureBattleOutfitDescr(component)
                    if descr:
                        return descr
        except Exception:
            pass
    except Exception:
        pass
    return ''

def _getOfflineBattleOutfitDescr(vehInvID, vehicleCompactDescr):
    vehIntCD = _normalizeBattleVehicleIntCD(vehicleCompactDescr)
    if offhangar_data is not None:
        try:
            cache = offhangar_data.getAppliedOutfitsCache()
            seasons = cache.get(vehIntCD)
            if seasons is None:
                for key, value in cache.iteritems():
                    keyInt = _normalizeBattleVehicleIntCD(key)
                    if keyInt == vehIntCD:
                        seasons = value
                        break
            if seasons:
                from items.components.c11n_constants import SeasonType
                descr = seasons.get(SeasonType.ALL)
                if descr:
                    return _ensureBattleOutfitDescr(descr)
                for season in SeasonType.SEASONS:
                    descr = seasons.get(season)
                    if descr:
                        return _ensureBattleOutfitDescr(descr)
                for descr in seasons.itervalues():
                    if descr:
                        return _ensureBattleOutfitDescr(descr)
        except Exception:
            pass
    return _getGuiVehicleOutfitDescr(vehInvID)

def _resolveVehicleCompactDescr(vehInvID=0, vehicleCompactDescr=None):
    if vehicleCompactDescr:
        return _makeFullCompactDescr(vehicleCompactDescr)
    _ensureInventory()
    invMap = getattr(offhangar_data, '_invID_to_intCD', {}) if offhangar_data is not None else {}
    if vehInvID is not None and vehInvID in invMap:
        return _makeFullCompactDescr(invMap[vehInvID])
    if getVehicleIntCDByInvID is not None:
        try:
            intCD = getVehicleIntCDByInvID(vehInvID)
            if intCD:
                return _makeFullCompactDescr(intCD)
        except Exception:
            pass
    selected = _getSelectedVehicleCompactDescr()
    if selected:
        return selected
    if invMap:
        return _makeFullCompactDescr(next(iter(invMap.values())))
    default = _getDefaultVehicleCompactDescr()
    if default:
        return default
    return None

def _findArenaTypeID(mapName=None, gameplayName=None):
    candidates = []
    for arenaTypeId, arenaType in ArenaType.g_cache.iteritems():
        if getattr(arenaType, 'isDevelopment', False):
            continue
        if getattr(arenaType, 'explicitRequestOnly', False):
            continue
        if getattr(arenaType, 'bonusType', ARENA_BONUS_TYPE.REGULAR) != ARENA_BONUS_TYPE.REGULAR:
            continue
        if getattr(arenaType, 'guiType', ARENA_GUI_TYPE.RANDOM) != ARENA_GUI_TYPE.RANDOM:
            continue
        geometryName = arenaType.geometryName
        if not geometryName:
            continue
        if mapName and geometryName != mapName:
            continue
        spacePath = 'spaces/' + geometryName + '/space.settings'
        try:
            section = ResMgr.openSection(spacePath)
            if section is None:
                continue
        except Exception:
            continue
        if gameplayName and arenaType.gameplayName != gameplayName:
            continue
        candidates.append(arenaTypeId)
    if not candidates:
        for arenaTypeId, arenaType in ArenaType.g_cache.iteritems():
            if getattr(arenaType, 'isDevelopment', False):
                continue
            if getattr(arenaType, 'explicitRequestOnly', False):
                continue
            geometryName = arenaType.geometryName
            if not geometryName:
                continue
            if mapName and geometryName != mapName:
                continue
            spacePath = 'spaces/' + geometryName + '/space.settings'
            try:
                section = ResMgr.openSection(spacePath)
                if section is None:
                    continue
            except Exception:
                continue
            candidates.append(arenaTypeId)
    if not candidates:
        for arenaTypeId, arenaType in ArenaType.g_cache.iteritems():
            geometryName = arenaType.geometryName
            if not geometryName:
                continue
            if mapName and geometryName != mapName:
                continue
            candidates.append(arenaTypeId)
    if not candidates:
        raise ValueError('No valid arena found: mapName=%r' % mapName)
    seen = {}
    unique = []
    for tid in candidates:
        gn = ArenaType.g_cache[tid].geometryName
        if gn not in seen:
            seen[gn] = True
            unique.append(tid)
    return random.choice(unique)

def _getMaxHealth(descr):
    for attrPath in ('maxHealth', 'type.maxHealth', 'hull.maxHealth'):
        obj = descr
        try:
            for part in attrPath.split('.'):
                obj = getattr(obj, part)
            if obj:
                return obj
        except Exception:
            continue
    return 1000

def _spawnPointToPos(spawn):
    try:
        if spawn is None:
            return None

        pos = getattr(spawn, 'position', None)
        if pos is not None:
            return (float(pos[0]), float(pos[1]), float(pos[2]))

        x = getattr(spawn, 'x', None)
        y = getattr(spawn, 'y', None)
        z = getattr(spawn, 'z', None)
        if x is not None and z is not None:
            if y is None:
                y = 10.0
            return (float(x), float(y), float(z))

        seq = tuple(spawn)
        if len(seq) >= 3:
            return (float(seq[0]), float(seq[1]), float(seq[2]))
        if len(seq) >= 2:
            return (float(seq[0]), 10.0, float(seq[1]))
    except Exception:
        LOG_CURRENT_EXCEPTION()

    return None


def _getPointsFromTeamSpawnPoints(teamSpawnPoints, team):
    try:
        if not teamSpawnPoints:
            return None

        teamIndex = int(team) - 1
        if teamIndex < 0:
            teamIndex = 0

        getter = getattr(teamSpawnPoints, 'get', None)
        if callable(getter):
            points = getter(team, None)
            if not points:
                points = getter(teamIndex, None)
            if not points:
                points = getter(str(team), None)
            return points

        if teamIndex < len(teamSpawnPoints):
            return teamSpawnPoints[teamIndex]

        if len(teamSpawnPoints) == 1:
            return teamSpawnPoints[0]
    except Exception:
        LOG_CURRENT_EXCEPTION()

    return None


def _spawnPointsToPositions(points):
    result = []

    try:
        if not points:
            return result

        for spawn in list(points):
            pos = _spawnPointToPos(spawn)
            if pos is not None:
                result.append(pos)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    return result


def _getTeamSpawnPositions(avatar, team):
    positions = []

    try:
        visitor = getattr(getattr(avatar, 'guiSessionProvider', None), 'arenaVisitor', None)
        if visitor is not None:
            method = getattr(visitor, 'getTeamSpawnPoints', None)
            if not callable(method):
                method = getattr(visitor, 'getTeamSpawnPointsIterator', None)

            if callable(method):
                positions = _spawnPointsToPositions(method(team))
                if positions:
                    return positions
    except Exception:
        pass

    try:
        arena = getattr(avatar, 'arena', None)
        arenaType = getattr(arena, 'arenaType', None)
        points = _getPointsFromTeamSpawnPoints(getattr(arenaType, 'teamSpawnPoints', None), team)
        positions = _spawnPointsToPositions(points)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    return positions


def _getTeamSpawnPoint(avatar, team):
    try:
        positions = offhangar_battle.getTeamSpawnPositionsFromSpaceSettings(team)
        if positions:
            return random.choice(positions)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        visitor = getattr(getattr(avatar, 'guiSessionProvider', None), 'arenaVisitor', None)
        if visitor is not None:
            method = getattr(visitor, 'getTeamSpawnPoints', None)
            if not callable(method):
                method = getattr(visitor, 'getTeamSpawnPointsIterator', None)

            if callable(method):
                rawPoints = list(method(team) or [])
                positions = []

                for p in rawPoints:
                    pos = offhangar_battle._parseSpawnPointValue(p)
                    if pos is not None:
                        positions.append(pos)

                if positions:
                    return random.choice(positions)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        arena = getattr(avatar, 'arena', None)
        arenaType = getattr(arena, 'arenaType', None)
        points = getattr(arenaType, 'teamSpawnPoints', None)

        if points:
            teamIndex = int(team) - 1
            if teamIndex >= 0 and teamIndex < len(points):
                rawPoints = list(points[teamIndex])
                positions = []

                for p in rawPoints:
                    pos = offhangar_battle._parseSpawnPointValue(p)
                    if pos is not None:
                        positions.append(pos)

                if positions:
                    return random.choice(positions)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    return None


def _getPointsFromTeamSpawnPoints(teamSpawnPoints, team):
    try:
        if not teamSpawnPoints:
            return None

        teamIndex = int(team) - 1
        if teamIndex < 0:
            teamIndex = 0

        getter = getattr(teamSpawnPoints, 'get', None)
        if callable(getter):
            points = getter(team, None)
            if not points:
                points = getter(teamIndex, None)
            if not points:
                points = getter(str(team), None)
            return points

        if teamIndex < len(teamSpawnPoints):
            return teamSpawnPoints[teamIndex]

        if len(teamSpawnPoints) == 1:
            return teamSpawnPoints[0]
    except Exception:
        LOG_CURRENT_EXCEPTION()

    return None


def _spawnPointsToPositions(points):
    result = []

    try:
        if not points:
            return result

        for spawn in list(points):
            pos = _spawnPointToPos(spawn)
            if pos is not None:
                result.append(pos)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    return result


def _getArenaSpawnPos(arenaType, team, fallback=(100.0, 10.0, 100.0)):
    try:
        points = _getPointsFromTeamSpawnPoints(getattr(arenaType, 'teamSpawnPoints', None), team)
        positions = _spawnPointsToPositions(points)
        if positions:
            return positions[0]
    except Exception:
        LOG_CURRENT_EXCEPTION()

    return fallback

def _iterResMgrSectionItems(section):
    try:
        for item in section.items():
            yield item
        return
    except Exception:
        pass

    try:
        keys = getattr(section, 'keys', None)
        if keys is None:
            return
        if callable(keys):
            keyList = keys()
        else:
            keyList = keys
        for key in keyList:
            try:
                yield key, section[key]
            except Exception:
                pass
    except Exception:
        pass


def _extractNumbersFromText(text):
    cleaned = str(text)
    for ch in ('(', ')', '[', ']', '{', '}', ',', ';', ':', '<', '>', '=', '\n', '\r', '\t', '|', '/'):
        cleaned = cleaned.replace(ch, ' ')

    result = []
    for part in cleaned.split():
        try:
            result.append(float(part))
        except Exception:
            pass

    return result


def _parseSpawnPointValue(value):
    if value is None:
        return None

    try:
        v = value.asVector3
        if v is not None:
            return (float(v[0]), float(v[1]), float(v[2]))
    except Exception:
        pass

    try:
        v = value.asVector2
        if v is not None:
            return (float(v[0]), 10.0, float(v[1]))
    except Exception:
        pass

    try:
        xSec = value['x']
        zSec = value['z']
        if xSec is not None and zSec is not None:
            yVal = 10.0
            try:
                ySec = value['y']
                if ySec is not None:
                    yVal = float(ySec.asString)
            except Exception:
                pass
            return (float(xSec.asString), yVal, float(zSec.asString))
    except Exception:
        pass

    try:
        s = value.asString
        if s:
            nums = _extractNumbersFromText(s)
            if len(nums) >= 3:
                return (float(nums[0]), float(nums[1]), float(nums[2]))
            if len(nums) >= 2:
                return (float(nums[0]), 10.0, float(nums[1]))
    except Exception:
        pass

    try:
        if hasattr(value, '__len__'):
            seq = tuple(value)
            if len(seq) >= 3:
                return (float(seq[0]), float(seq[1]), float(seq[2]))
            if len(seq) >= 2:
                return (float(seq[0]), 10.0, float(seq[1]))
    except Exception:
        pass

    try:
        x = getattr(value, 'x', None)
        y = getattr(value, 'y', None)
        z = getattr(value, 'z', None)
        if x is not None and z is not None:
            if y is None:
                y = 10.0
            return (float(x), float(y), float(z))
    except Exception:
        pass

    try:
        s = str(value)
        nums = _extractNumbersFromText(s)
        if len(nums) >= 3:
            return (float(nums[0]), float(nums[1]), float(nums[2]))
        if len(nums) >= 2:
            return (float(nums[0]), 10.0, float(nums[1]))
    except Exception:
        pass

    return None


def _collectSpawnPositions(section, depth=0, visited=None):
    positions = []

    if section is None or depth > 10:
        return positions

    if visited is None:
        visited = set()

    sid = id(section)
    if sid in visited:
        return positions

    visited.add(sid)

    pos = _parseSpawnPointValue(section)
    if pos is not None:
        positions.append(pos)

    for key, child in _iterResMgrSectionItems(section):
        positions.extend(_collectSpawnPositions(child, depth + 1, visited))

    return positions


def _findTeamSpawnSections(section, team, depth=0, visited=None, insideSpawn=False):
    found = []

    if section is None or depth > 10:
        return found

    if visited is None:
        visited = set()

    sid = id(section)
    if sid in visited:
        return found

    visited.add(sid)

    teamStr = str(team)
    normalizedTeamNames = (
        teamStr,
        'team' + teamStr,
        'team_' + teamStr,
        'team-' + teamStr,
    )

    for key, child in _iterResMgrSectionItems(section):
        keyLower = str(key).lower().replace(' ', '').replace('-', '_')

        isSpawn = 'spawn' in keyLower
        isTeam = keyLower in normalizedTeamNames

        if not isTeam and 'team' in keyLower and keyLower.endswith(teamStr):
            isTeam = True

        if isSpawn and isTeam:
            found.append(child)

        if isSpawn:
            found.extend(_findTeamSpawnSections(child, team, depth + 1, visited, True))
        elif insideSpawn and isTeam:
            found.append(child)
            found.extend(_findTeamSpawnSections(child, team, depth + 1, visited, True))
        else:
            found.extend(_findTeamSpawnSections(child, team, depth + 1, visited, insideSpawn))

    return found


def getTeamSpawnPositionsFromSpaceSettings(team, arenaType=None):
    positions = []

    try:
        if arenaType is None:
            avatar = BigWorld.player()
            arena = getattr(avatar, 'arena', None)
            arenaType = getattr(arena, 'arenaType', None)

        if arenaType is None:
            return positions

        path = 'spaces/%s/space.settings' % arenaType.geometryName
        root = ResMgr.openSection(path)

        if root is None:
            return positions

        sections = _findTeamSpawnSections(root, team)

        seen = set()
        for sec in sections:
            for pos in _collectSpawnPositions(sec):
                key = (round(pos[0], 2), round(pos[1], 2), round(pos[2], 2))
                if key not in seen:
                    seen.add(key)
                    positions.append(pos)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    return positions

try:
    from items.components.c11n_constants import ApplyArea as _OffhangarApplyArea
    from serializable_types.customizations import CustomizationOutfit as _OffhangarCustomizationOutfit
    from serializable_types.customizations import CamouflageComponent as _OffhangarCamouflageComponent
except Exception:
    _OffhangarApplyArea = None
    _OffhangarCustomizationOutfit = None
    _OffhangarCamouflageComponent = None

def getOfflineBotOutfitDescr(vehicleCompactDescr):
    if random.random() >= 0.75:
        return ''
    if _OffhangarCustomizationOutfit is None or _OffhangarCamouflageComponent is None or _OffhangarApplyArea is None:
        return ''
    try:
        cache = items_vehicles.g_cache.customization20()
        camouflages = getattr(cache, 'camouflages', None) or {}
        camoIds = []
        for camoId, camo in camouflages.iteritems():
            if camoId <= 0:
                continue
            if getattr(camo, 'isStyleOnly', False):
                continue
            camoIds.append(camoId)
        if not camoIds:
            return ''
        camoId = random.choice(camoIds)
        regions = []
        for name in ('HULL_CAMOUFLAGE_REGIONS', 'TURRET_CAMOUFLAGE_REGIONS', 'GUN_CAMOUFLAGE_REGIONS'):
            regions.extend(getattr(_OffhangarApplyArea, name, ()))
        appliedTo = reduce(int.__or__, regions, 0)
        if not appliedTo:
            appliedTo = _OffhangarApplyArea.HULL
        try:
            component = _OffhangarCamouflageComponent(id=camoId, appliedTo=appliedTo, palette=0)
        except Exception:
            component = _OffhangarCamouflageComponent(id=camoId, appliedTo=appliedTo)
        outfit = _OffhangarCustomizationOutfit(camouflages=[component])
        return outfit.makeCompDescr() or ''
    except Exception:
        return ''

if not getattr(BigWorld, '_offhangar_createEntity_patched', False):
    _offhangar_origCreateEntity = BigWorld.createEntity

    def _offhangar_createEntity(entityType, spaceID, scriptID, position, direction, props):
        outfitToSet = ''
        try:
            if getattr(BigWorld.player(), 'isOffline', False) and entityType == 'Vehicle':
                props = dict(props or {})
                try:
                    publicInfo = dict(props.get('publicInfo') or {})
                except Exception:
                    publicInfo = {}
                if not publicInfo.get('outfit'):
                    if props.get('avatarID') != _avatarID:
                        compDescr = props.get('compDescr') or publicInfo.get('compDescr')
                        if compDescr:
                            outfitToSet = getOfflineBotOutfitDescr(compDescr)
                            if outfitToSet:
                                publicInfo['outfit'] = outfitToSet
                                props['publicInfo'] = publicInfo
        except Exception:
            pass

        entityID = _offhangar_origCreateEntity(entityType, spaceID, scriptID, position, direction, props)

        try:
            if outfitToSet and entityID:
                player = BigWorld.player()
                arena = getattr(player, 'arena', None)
                if arena is not None and entityID in getattr(arena, 'vehicles', {}):
                    arena.vehicles[entityID]['outfitCD'] = outfitToSet
        except Exception:
            pass

        return entityID

    BigWorld.createEntity = _offhangar_createEntity
    BigWorld._offhangar_createEntity_patched = True

_CHUNK_FOLLOW_INTERVAL = 0.8
_CHUNK_DESTR_RADIUS = 600.0
_chunkFollowID = None
_lastChunkCenter = None

def _get_player_world_pos():
    player = BigWorld.player()
    if player is None:
        return None
    vehID = getattr(player, 'playerVehicleID', 0)
    veh = BigWorld.entity(vehID) if vehID else None
    if veh is not None:
        try:
            p = veh.position
            if p is not None and (p[0] != 0 or p[1] != 0 or p[2] != 0):
                return Math.Vector3(p)
        except Exception:
            pass
    try:
        p = player.position
        if p is not None and (p[0] != 0 or p[1] != 0 or p[2] != 0):
            return Math.Vector3(p)
    except Exception:
        pass
    return None

def _load_destructibles_around(centerPos, radius):
    try:
        import AreaDestructibles
        import DestructiblesCache
        manager = getattr(AreaDestructibles, 'g_destructiblesManager', None)
        if manager is None:
            return 0
        minX = centerPos[0] - radius
        maxX = centerPos[0] + radius
        minZ = centerPos[2] - radius
        maxZ = centerPos[2] + radius
        minCX = int(math.floor(minX * 0.01)) - 1
        minCZ = int(math.floor(minZ * 0.01)) - 1
        maxCX = int(math.floor(maxX * 0.01)) + 1
        maxCZ = int(math.floor(maxZ * 0.01)) + 1
        loaded = getattr(manager, '_DestructiblesManager__loadedChunkIDs', None)
        if loaded is None:
            loaded = getattr(manager, 'loadedChunkIDs', None)
        count = 0
        for cx in range(minCX, maxCX + 1):
            for cz in range(minCZ, maxCZ + 1):
                try:
                    cid = DestructiblesCache.chunkIDFromChunkIndexes(cx, cz)
                except Exception:
                    continue
                if loaded is not None and cid in loaded:
                    continue
                try:
                    manager.onChunkLoad(cid, 1024)
                    count += 1
                except Exception:
                    pass
        return count
    except Exception:
        return 0

def _try_force_terrain_chunks(spaceID, centerPos, radius):
    try:
        minCX = int(math.floor((centerPos[0] - radius) * 0.01))
        minCZ = int(math.floor((centerPos[2] - radius) * 0.01))
        maxCX = int(math.floor((centerPos[0] + radius) * 0.01))
        maxCZ = int(math.floor((centerPos[2] + radius) * 0.01))
        for cx in range(minCX, maxCX + 1):
            for cz in range(minCZ, maxCZ + 1):
                try:
                    BigWorld.loadChunk(spaceID, cx, cz)
                except Exception:
                    pass
    except Exception:
        pass
    try:
        cam = BigWorld.camera()
        if cam is not None and hasattr(cam, 'lodDistance'):
            cam.lodDistance = max(getattr(cam, 'lodDistance', 0), 1500.0)
    except Exception:
        pass
    try:
        if hasattr(BigWorld, 'setGlobalLOD'):
            BigWorld.setGlobalLOD(1.0)
    except Exception:
        pass

def _chunk_follow_tick():
    global _chunkFollowID, _lastChunkCenter
    try:
        player = BigWorld.player()
        if player is None or not getattr(player, 'isOffline', False):
            return
        pos = _get_player_world_pos()
        if pos is not None:
            needUpdate = False
            if _lastChunkCenter is None:
                needUpdate = True
            else:
                dx = pos[0] - _lastChunkCenter[0]
                dz = pos[2] - _lastChunkCenter[2]
                if dx * dx + dz * dz > 50.0 * 50.0:
                    needUpdate = True
            if needUpdate:
                _lastChunkCenter = Math.Vector3(pos)
                spaceID = getattr(player, 'spaceID', None)
                if spaceID is None:
                    spaceID = _spaceID
                if spaceID is not None:
                    _try_force_terrain_chunks(spaceID, pos, _CHUNK_DESTR_RADIUS)
                _load_destructibles_around(pos, _CHUNK_DESTR_RADIUS)
    except Exception:
        pass
    _chunkFollowID = BigWorld.callback(_CHUNK_FOLLOW_INTERVAL, _chunk_follow_tick)

def start_chunk_follower():
    global _chunkFollowID, _lastChunkCenter
    stop_chunk_follower()
    _lastChunkCenter = None
    _chunkFollowID = BigWorld.callback(0.1, _chunk_follow_tick)

def stop_chunk_follower():
    global _chunkFollowID, _lastChunkCenter
    if _chunkFollowID is not None:
        try:
            BigWorld.cancelCallback(_chunkFollowID)
        except Exception:
            pass
        _chunkFollowID = None
    _lastChunkCenter = None

def enterOfflineBattle(vehInvID=0, mapName=None):
    global IS_IN_BATTLE, _spaceID, _avatarID, _vehicleID, ALLOW_CLEAR

    def _iterResMgrSectionItems(section):
        itemsOk = False

        try:
            for item in section.items():
                yield item
            itemsOk = True
        except Exception:
            itemsOk = False

        if not itemsOk:
            try:
                keys = getattr(section, 'keys', None)
                if keys is not None:
                    if callable(keys):
                        keyList = keys()
                    else:
                        keyList = keys

                    for key in keyList:
                        try:
                            yield key, section[key]
                        except Exception:
                            pass
            except Exception:
                pass

    def _extractNumbersFromText(text):
        cleaned = str(text)

        for ch in ('(', ')', '[', ']', '{', '}', ',', ';', ':', '<', '>', '=', '\n', '\r', '\t', '|', '/'):
            cleaned = cleaned.replace(ch, ' ')

        result = []

        for part in cleaned.split():
            try:
                result.append(float(part))
            except Exception:
                pass

        return result

    def _parseSpawnPointValue(value):
        if value is None:
            return None

        try:
            v = value.asVector3
            if v is not None:
                return (float(v[0]), float(v[1]), float(v[2]))
        except Exception:
            pass

        try:
            v = value.asVector2
            if v is not None:
                return (float(v[0]), 10.0, float(v[1]))
        except Exception:
            pass

        try:
            xSec = value['x']
            zSec = value['z']

            if xSec is not None and zSec is not None:
                yVal = 10.0

                try:
                    ySec = value['y']
                    if ySec is not None:
                        yVal = float(ySec.asString)
                except Exception:
                    pass

                return (float(xSec.asString), yVal, float(zSec.asString))
        except Exception:
            pass

        try:
            s = value.asString
            if s:
                nums = _extractNumbersFromText(s)

                if len(nums) >= 3:
                    return (float(nums[0]), float(nums[1]), float(nums[2]))

                if len(nums) >= 2:
                    return (float(nums[0]), 10.0, float(nums[1]))
        except Exception:
            pass

        try:
            if hasattr(value, '__len__'):
                seq = tuple(value)

                if len(seq) >= 3:
                    return (float(seq[0]), float(seq[1]), float(seq[2]))

                if len(seq) >= 2:
                    return (float(seq[0]), 10.0, float(seq[1]))
        except Exception:
            pass

        try:
            x = getattr(value, 'x', None)
            y = getattr(value, 'y', None)
            z = getattr(value, 'z', None)

            if x is not None and z is not None:
                if y is None:
                    y = 10.0

                return (float(x), float(y), float(z))
        except Exception:
            pass

        try:
            s = str(value)
            nums = _extractNumbersFromText(s)

            if len(nums) >= 3:
                return (float(nums[0]), float(nums[1]), float(nums[2]))

            if len(nums) >= 2:
                return (float(nums[0]), 10.0, float(nums[1]))
        except Exception:
            pass

        return None

    def _collectSpawnPositions(section, depth=0, visited=None):
        positions = []

        if section is None or depth > 10:
            return positions

        if visited is None:
            visited = set()

        sid = id(section)
        if sid in visited:
            return positions

        visited.add(sid)

        pos = _parseSpawnPointValue(section)
        if pos is not None:
            positions.append(pos)

        for key, child in _iterResMgrSectionItems(section):
            positions.extend(_collectSpawnPositions(child, depth + 1, visited))

        return positions

    def _findTeamSpawnSections(section, team, depth=0, visited=None, insideSpawn=False):
        found = []

        if section is None or depth > 10:
            return found

        if visited is None:
            visited = set()

        sid = id(section)
        if sid in visited:
            return found

        visited.add(sid)

        teamStr = str(team)
        normalizedTeamNames = (
            teamStr,
            'team' + teamStr,
            'team_' + teamStr,
            'team-' + teamStr,
        )

        for key, child in _iterResMgrSectionItems(section):
            keyLower = str(key).lower().replace(' ', '').replace('-', '_')

            isSpawn = 'spawn' in keyLower
            isTeam = keyLower in normalizedTeamNames

            if not isTeam and 'team' in keyLower and keyLower.endswith(teamStr):
                isTeam = True

            if isSpawn and isTeam:
                found.append(child)

            if isSpawn:
                found.extend(_findTeamSpawnSections(child, team, depth + 1, visited, True))
            elif insideSpawn and isTeam:
                found.append(child)
                found.extend(_findTeamSpawnSections(child, team, depth + 1, visited, True))
            else:
                found.extend(_findTeamSpawnSections(child, team, depth + 1, visited, insideSpawn))

        return found

    def _getTeamSpawnPositionsFromSpaceSettings(team, arenaType):
        positions = []

        try:
            if arenaType is None:
                return positions

            path = 'spaces/%s/space.settings' % arenaType.geometryName
            root = ResMgr.openSection(path)

            if root is None:
                return positions

            sections = _findTeamSpawnSections(root, team)

            seen = set()

            for sec in sections:
                for pos in _collectSpawnPositions(sec):
                    key = (round(pos[0], 2), round(pos[1], 2), round(pos[2], 2))
                    if key not in seen:
                        seen.add(key)
                        positions.append(pos)
        except Exception:
            LOG_CURRENT_EXCEPTION()

        return positions

    _crash_log('enterOfflineBattle START')

    account = BigWorld.player()
    if account is None or not getattr(account, 'isOffline', False):
        LOG_DEBUG('enterOfflineBattle: offline only')
        return

    if IS_IN_BATTLE:
        LOG_DEBUG('enterOfflineBattle: already in battle')
        return

    vehicleCompactDescr = _resolveVehicleCompactDescr(vehInvID)
    if vehicleCompactDescr is None:
        LOG_DEBUG('enterOfflineBattle: no vehicleCompactDescr for invID', vehInvID)
        return

    try:
        descr = items_vehicles.VehicleDescr(compactDescr=vehicleCompactDescr)
    except Exception:
        try:
            vType = items_vehicles.getVehicleType(vehicleCompactDescr)
            descr = items_vehicles.VehicleDescr(typeID=vType.id)
        except Exception as e:
            LOG_DEBUG('enterOfflineBattle: VehicleDescr failed', e)
            return

    vehicleCompactDescr = descr.makeCompactDescr()
    
    global _PLAYER_BADGES
    _PLAYER_BADGES = ((), ())
    try:
        from helpers import dependency
        from skeletons.gui.game_control import IBadgesController
        badgesCtrl = dependency.instance(IBadgesController)
        if badgesCtrl is not None:
            prefix = badgesCtrl.getPrefix()
            suffix = badgesCtrl.getSuffix()
            prefixID = prefix.badgeID if prefix else 0
            suffixID = suffix.badgeID if suffix else 0
            _PLAYER_BADGES = ((prefixID,) if prefixID else (), (suffixID,) if suffixID else ())
            _crash_log('enterOfflineBattle: saved player badges = {}'.format(_PLAYER_BADGES))
    except Exception:
        LOG_CURRENT_EXCEPTION()
        
    if not _PLAYER_BADGES[0] and not _PLAYER_BADGES[1]:
        try:
            from helpers import dependency
            from skeletons.gui.shared import IItemsCache
            itemsCache = dependency.instance(IItemsCache)
            if itemsCache is not None:
                prefixID = 0
                suffixID = 0
                for badge in itemsCache.items.getBadges().itervalues():
                    if getattr(badge, 'isSelected', False):
                        if getattr(badge, 'isPrefixLayout', lambda: False)() and getattr(badge, 'isAchieved', False):
                            prefixID = badge.badgeID
                        elif getattr(badge, 'isSuffixLayout', lambda: False)():
                            suffixID = badge.badgeID
                _PLAYER_BADGES = ((prefixID,) if prefixID else (), (suffixID,) if suffixID else ())
                _crash_log('enterOfflineBattle: fallback saved player badges = {}'.format(_PLAYER_BADGES))
        except Exception:
            LOG_CURRENT_EXCEPTION()

    try:
        arenaTypeID = _findArenaTypeID(mapName)
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return

    arenaType = ArenaType.g_cache[arenaTypeID]

    _crash_log('enterOfflineBattle creating space')

    try:
        spaceID = BigWorld.createSpace()
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return

    _spaceID = spaceID

    pos = (100.0, 10.0, 100.0)
    teamIndex = 0 # team 1
    
    try:
        # 1. teamSpawnPoints
        tsp = getattr(arenaType, 'teamSpawnPoints', None)
        if tsp and teamIndex < len(tsp) and tsp[teamIndex]:
            spawn = tsp[teamIndex][0]
            if hasattr(spawn, 'x') and hasattr(spawn, 'y'):
                pos = (float(spawn.x), 10.0, float(spawn.y))
            elif len(spawn) >= 2:
                pos = (float(spawn[0]), 10.0, float(spawn[1]))
                
        # 2. teamBasePositions
        if pos == (100.0, 10.0, 100.0):
            tbp = getattr(arenaType, 'teamBasePositions', None)
            if tbp and teamIndex < len(tbp) and tbp[teamIndex]:
                bases = tbp[teamIndex]
                if bases:
                    base = bases.values()[0] if isinstance(bases, dict) else bases[0]
                    if hasattr(base, 'x') and hasattr(base, 'y'):
                        pos = (float(base.x), 10.0, float(base.y))
                    elif len(base) >= 2:
                        pos = (float(base[0]), 10.0, float(base[1]))
                        
        # 3. botPoints
        if pos == (100.0, 10.0, 100.0):
            bp = getattr(arenaType, 'botPoints', None)
            if bp:
                for idx, p in bp.items():
                    if hasattr(p, 'x') and hasattr(p, 'y') and hasattr(p, 'z'):
                        pos = (float(p.x), float(p.y), float(p.z))
                        break
                        
        # Diagnostic log
        if pos == (100.0, 10.0, 100.0):
            _crash_log('SPAWNS NOT FOUND! teamSpawnPoints=%r, teamBasePositions=%r, botPoints=%r' % (
                getattr(arenaType, 'teamSpawnPoints', None),
                getattr(arenaType, 'teamBasePositions', None),
                getattr(arenaType, 'botPoints', None)
            ))
    except Exception:
        LOG_CURRENT_EXCEPTION()

    playerName = getattr(account, 'name', 'offline')
    if isinstance(playerName, str):
        pass
    else:
        try:
            playerName = playerName.encode('utf-8')
        except Exception:
            playerName = 'offline'

    maxHealth = _getMaxHealth(descr)

    _OFFLINE_AVATAR_FALLBACK.clear()
    _OFFLINE_AVATAR_FALLBACK.update({
        'arenaUniqueID': _ARENA_UNIQUE_ID,
        'arenaBonusType': ARENA_BONUS_TYPE.REGULAR,
        'arenaTypeID': arenaTypeID,
        'arenaGuiType': ARENA_GUI_TYPE.RANDOM,
        'arenaExtraData': {},
        'playLimits': {'curfew': -1, 'weeklyPlayLimit': -1, 'dailyPlayLimit': -1, 'sessionLimit': -1},
        'getUnpackedEventsData': lambda *a, **kw: {},
        'team': 1,
        'playerVehicleID': 0,
        'databaseID': 1,
        'clanDBID': 0,
        'clanAbbrev': '',
        'tkillIsSuspected': 0,
        'denunciationsLeft': 0,
        'weatherPresetID': 0,
        'paragons': None,
        'goodiesSnapshot': {},
        'ownVehicleAuxPhysicsData': 0,
        'avatarSessionID': _OFFLINE_AVATAR_SESSION_ID,
        'ownVehicleGear': 0,
        'isGunLocked': False,
        'isOnArena': True,
        'invRotationOnBackMovement': False,
    })

    avatarProps = {
        'arenaUniqueID': _ARENA_UNIQUE_ID,
        'arenaTypeID': arenaTypeID,
        'arenaBonusType': ARENA_BONUS_TYPE.REGULAR,
        'arenaGuiType': ARENA_GUI_TYPE.RANDOM,
        'arenaExtraData': {},
        'playerVehicleID': 0,
        'playLimits': {'curfew': -1, 'weeklyPlayLimit': -1, 'dailyPlayLimit': -1, 'sessionLimit': -1},
        'team': 1,
        'name': playerName,
        'databaseID': 1,
        'clanDBID': 0,
        'clanAbbrev': '',
        'tkillIsSuspected': 0,
        'denunciationsLeft': 0,
        'weatherPresetID': 0,
        'ownVehicleAuxPhysicsData': 0,
    }

    _crash_log('enterOfflineBattle creating Avatar')

    try:
        avatarID = BigWorld.createEntity('Avatar', spaceID, 0, pos, (0, 0, 0), avatarProps)
    except Exception:
        LOG_CURRENT_EXCEPTION()
        try:
            BigWorld.releaseSpace(spaceID)
        except Exception:
            pass
        _spaceID = None
        _OFFLINE_AVATAR_FALLBACK.clear()
        return

    _avatarID = avatarID
    avatar = BigWorld.entities.get(avatarID)

    if avatar is None:
        try:
            BigWorld.releaseSpace(spaceID)
        except Exception:
            pass
        _spaceID = None
        _avatarID = None
        _OFFLINE_AVATAR_FALLBACK.clear()
        return

    try:
        avatar.isOffline = True
    except Exception:
        pass

    try:
        avatar.name = playerName
    except Exception:
        pass

    try:
        avatar.arenaUniqueID = _ARENA_UNIQUE_ID
        avatar.arenaTypeID = arenaTypeID
        avatar.arenaBonusType = ARENA_BONUS_TYPE.REGULAR
        avatar.arenaGuiType = ARENA_GUI_TYPE.RANDOM
        avatar.arenaExtraData = {}
        avatar.weatherPresetID = 0
        avatar.playerVehicleID = 0
        avatar.team = 1
        avatar.name = playerName
        avatar.databaseID = 1
        avatar.clanDBID = 0
        avatar.clanAbbrev = ''
        avatar.tkillIsSuspected = 0
        avatar.denunciationsLeft = 0
        avatar.ownVehicleAuxPhysicsData = 0
        avatar.avatarSessionID = _OFFLINE_AVATAR_SESSION_ID
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        BigWorld.player(avatar)
    except Exception:
        LOG_CURRENT_EXCEPTION()
        try:
            BigWorld.releaseSpace(spaceID)
        except Exception:
            pass
        _spaceID = None
        _avatarID = None
        _OFFLINE_AVATAR_FALLBACK.clear()
        return

    try:
        import AreaDestructibles
        if AreaDestructibles.g_cache is None:
            AreaDestructibles.init()
        if AreaDestructibles.g_destructiblesManager is not None:
            if AreaDestructibles.g_destructiblesManager.getSpaceID() != spaceID:
                AreaDestructibles.g_destructiblesManager.startSpace(spaceID)
    except Exception:
        pass

    try:
        BigWorld.addSpaceGeometryMapping(spaceID, None, 'spaces/' + arenaType.geometryName)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    _force_load_destructibles_chunks(spaceID, pos)

    try:
        visitor = getattr(avatar.guiSessionProvider, 'arenaVisitor', None)
        if visitor is not None:
            method = getattr(visitor, 'getTeamSpawnPoints', None)
            if not callable(method):
                method = getattr(visitor, 'getTeamSpawnPointsIterator', None)

            if callable(method):
                rawPoints = list(method(1) or [])
                visitorPositions = []

                for p in rawPoints:
                    parsed = _parseSpawnPointValue(p)
                    if parsed is not None:
                        visitorPositions.append(parsed)

                if visitorPositions:
                    pos = visitorPositions[0]
                    try:
                        avatar.position = Math.Vector3(pos[0], pos[1], pos[2])
                    except Exception:
                        pass
    except Exception:
        LOG_CURRENT_EXCEPTION()
    start_chunk_follower()
    IS_IN_BATTLE = True

    try:
        validMatrix = Math.Matrix()
        validMatrix.setTranslate(pos)

        cm = getattr(avatar, '_PlayerAvatar__consistentMatrices', None)
        if cm is not None:
            mProv = getattr(cm, '_ConsistentMatrices__ownVehicleMProv', None)
            if mProv is not None:
                mProv.setStaticTransform(validMatrix)

            turretProv = getattr(cm, '_ConsistentMatrices__ownVehicleTurretMProv', None)
            if turretProv is not None:
                turretProv.setStaticTransform(validMatrix)

            attachedProv = getattr(cm, '_ConsistentMatrices__attachedVehicleMatrix', None)
            if attachedProv is not None:
                attachedProv.setStaticTransform(validMatrix)

        stabProv = getattr(avatar, '_PlayerAvatar__ownVehicleStabMProv', None)
        if stabProv is not None:
            stabProv.setStaticTransform(validMatrix)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    arena = getattr(avatar, 'arena', None)

    def _spawnVehicle():
        global _vehicleID
        _crash_log('_spawnVehicle START')
        try:
            outfitDescr = _getOfflineBattleOutfitDescr(vehInvID, vehicleCompactDescr)
        except Exception:
            outfitDescr = ''
        publicInfo = {
            'compDescr': vehicleCompactDescr,
            'team': 1,
            'outfit': outfitDescr,
            'maxHealth': maxHealth,
            'accountDBID': 1,
            'name': playerName,
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

        vehID = BigWorld.createEntity('Vehicle', spaceID, 0, pos, (0, 0, 0), {
            'publicInfo': publicInfo,
            'compDescr': vehicleCompactDescr,
            'health': maxHealth,
            'isCrewActive': True,
            'avatarID': avatarID,
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

        _crash_log('_spawnVehicle Vehicle created ID={}'.format(vehID))

        _vehicleID = vehID
        veh = BigWorld.entity(vehID)

        if veh is not None:
            try:
                veh.isOffline = True
            except Exception:
                pass

        if arena is not None:
            vehInfo = {
                'vehicleType': descr,
                'name': playerName,
                'team': 1,
                'isAlive': True,
                'isAvatarReady': True,
                'isTeamKiller': False,
                'accountDBID': 1,
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
                'outfitCD': outfitDescr,
                'avatarSessionID': _OFFLINE_AVATAR_SESSION_ID,
                'wtr': 0,
                'fakeName': '',
                'badges': _getOfflineBadgesSafe(),
                'overriddenBadge': None,
                'maxHealth': maxHealth,
                'vehPostProgression': [],
                'customRoleSlotTypeId': 0,
                'botDisplayStatus': 0,
                'statTrackFrags': 0,
                'selectedComp7Skill': 0,
                'invID': vehInvID,
                'crewGroups': [],
            }

            try:
                arena.vehicles[vehID] = vehInfo
                if hasattr(arena, 'onVehicleAdded'):
                    arena.onVehicleAdded(vehID)
            except Exception:
                LOG_CURRENT_EXCEPTION()

            try:
                sp = getattr(avatar, 'guiSessionProvider', None)
                if sp is not None:
                    arenaDP = sp.getArenaDP()
                    if arenaDP is not None:
                        arenaDP.addVehicleInfo(vehID, vehInfo)
            except Exception:
                LOG_CURRENT_EXCEPTION()

            try:
                stats = getattr(arena, 'statistics', None)
                if stats is None:
                    stats = {}
                    arena.statistics = stats
                if vehID not in stats:
                    stats[vehID] = {}
            except Exception:
                LOG_CURRENT_EXCEPTION()

        try:
            avatar.playerVehicleID = vehID
        except Exception:
            LOG_CURRENT_EXCEPTION()

        _OFFLINE_AVATAR_FALLBACK['playerVehicleID'] = vehID

        attempts = [30]

        def _ensurePlayerVehicleSet():
            if attempts[0] <= 0:
                return

            attempts[0] -= 1
            veh = BigWorld.entity(vehID)

            if veh is not None and getattr(veh, 'inWorld', False):
                try:
                    avatar.set_playerVehicleID()
                except Exception:
                    LOG_CURRENT_EXCEPTION()
                return

            BigWorld.callback(0.1, _ensurePlayerVehicleSet)

        BigWorld.callback(0.0, _ensurePlayerVehicleSet)

    try:
        _spawnVehicle()
    except Exception:
        LOG_CURRENT_EXCEPTION()
        try:
            BigWorld.releaseSpace(spaceID)
        except Exception:
            pass
        _spaceID = None
        _avatarID = None
        _vehicleID = None
        IS_IN_BATTLE = False
        return

    def _finishEntering():
        if Waiting is not None:
            try:
                Waiting.close()
            except Exception:
                pass

        _crash_log('enterOfflineBattle END')

        try:
            import gui.mods.offhangar.bots as offhangar_bots
            _crash_log('Auto-spawn bot scheduled in 2.0s')
            BigWorld.callback(2.0, lambda: offhangar_bots.spawnBotWave())
        except Exception:
            LOG_CURRENT_EXCEPTION()

        try:
            import gui.mods.offhangar.ai as offhangar_ai
            offhangar_ai.start()
        except Exception:
            pass

        LOG_NOTE('enterOfflineBattle: start on map', arenaType.geometryName)

    BigWorld.callback(0.0, _finishEntering)

def leaveOfflineBattle():
    global IS_IN_BATTLE, _spaceID, _avatarID, _vehicleID, ALLOW_CLEAR
    if not IS_IN_BATTLE:
        return
    stop_chunk_follower()
    try:
        import gui.mods.offhangar.bots as offhangar_bots
        offhangar_bots.clearBots()
    except Exception:
        pass

    try:
        import gui.mods.offhangar.ai as offhangar_ai
        offhangar_ai.stop()
    except Exception:
        pass

    IS_IN_BATTLE = False
    ALLOW_CLEAR = True
    try:
        import AreaDestructibles
        if AreaDestructibles.g_destructiblesManager is not None:
            AreaDestructibles.clear()
    except Exception:
        pass
    try:
        BigWorld.clearEntitiesAndSpaces()
    except Exception:
        LOG_CURRENT_EXCEPTION()
    finally:
        ALLOW_CLEAR = False
    if _spaceID:
        try:
            BigWorld.clearSpace(_spaceID)
            BigWorld.releaseSpace(_spaceID)
        except Exception:
            pass
    _spaceID = None
    _avatarID = None
    _vehicleID = None
    _OFFLINE_AVATAR_FALLBACK.clear()
    LOG_DEBUG('leaveOfflineBattle: space cleared')

def _makeGuiVehicleOverride(value):
    def hook(baseFunc, baseSelf, *args, **kwargs):
        if getattr(BigWorld.player(), 'isOffline', False):
            return value
        if baseFunc is None:
            return value
        return baseFunc(baseSelf, *args, **kwargs)
    return hook

if GuiVehicle is not None:
    for propName, propValue in (
        ('canBattle', True),
        ('isBattleReady', True),
        ('isUnsuitableToQueue', False),
        ('isDisabledInRent', False),
        ('isLocked', False),
        ('isInBattle', False),
    ):
        if hasattr(GuiVehicle, propName):
            try:
                override(GuiVehicle, propName, _makeGuiVehicleOverride(propValue))
            except Exception:
                pass

try:
    from gui.battle_control import matrix_factory
except Exception:
    matrix_factory = None

if matrix_factory is not None:
    try:
        _original_makeAttachedVehicleMatrix = matrix_factory.makeAttachedVehicleMatrix
    except Exception:
        _original_makeAttachedVehicleMatrix = None

    def _offhangar_makeAttachedVehicleMatrix():
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            mProv = getattr(player, '_PlayerAvatar__ownVehicleMProv', None)
            if mProv is not None:
                return mProv
            try:
                return player.getOwnVehicleMatrix()
            except Exception:
                pass
        if _original_makeAttachedVehicleMatrix is not None:
            return _original_makeAttachedVehicleMatrix()
        return None

    try:
        matrix_factory.makeAttachedVehicleMatrix = _offhangar_makeAttachedVehicleMatrix
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        _original_makeOwnVehicleMatrix = matrix_factory.makeOwnVehicleMatrix
    except Exception:
        _original_makeOwnVehicleMatrix = None

    def _offhangar_makeOwnVehicleMatrix():
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            mProv = getattr(player, '_PlayerAvatar__ownVehicleMProv', None)
            if mProv is not None:
                return mProv
            try:
                return player.getOwnVehicleMatrix()
            except Exception:
                pass
        if _original_makeOwnVehicleMatrix is not None:
            return _original_makeOwnVehicleMatrix()
        return None

    try:
        matrix_factory.makeOwnVehicleMatrix = _offhangar_makeOwnVehicleMatrix
    except Exception:
        LOG_CURRENT_EXCEPTION()

def _getFightLabel():
    if i18n is not None:
        try:
            return i18n.makeString('#menu:headerButtons/battle')
        except Exception:
            pass
    return 'Battle'

def _forceFightButtonEnabled(header):
    try:
        header.as_disableFightButtonS(False)
    except Exception:
        pass
    try:
        header.as_setFightButtonS(_getFightLabel())
    except Exception:
        pass
    try:
        header.as_setFightBtnTooltipS('', False)
    except Exception:
        pass

@override(LobbyHeader, '_checkFightButtonDisabled')
def LobbyHeader_checkFightButtonDisabled(baseFunc, baseSelf, canDo, isLocked):
    if getattr(BigWorld.player(), 'isOffline', False):
        return False
    return baseFunc(baseSelf, canDo, isLocked)

@override(LobbyHeader, '_populate')
def LobbyHeader_populate(baseFunc, baseSelf, *args, **kwargs):
    isOffline = getattr(BigWorld.player(), 'isOffline', False)
    if isOffline:
        try:
            result = baseFunc(baseSelf, *args, **kwargs)
        except Exception:
            LOG_DEBUG('LobbyHeader._populate offline exception')
            result = None
        _forceFightButtonEnabled(baseSelf)
        return result
    return baseFunc(baseSelf, *args, **kwargs)

@override(LobbyHeader, '_updatePrebattleControls')
def LobbyHeader_updatePrebattleControls(baseFunc, baseSelf, *args, **kwargs):
    isOffline = getattr(BigWorld.player(), 'isOffline', False)
    if isOffline:
        try:
            result = baseFunc(baseSelf, *args, **kwargs)
        except Exception:
            LOG_DEBUG('LobbyHeader._updatePrebattleControls offline exception')
            result = None
        _forceFightButtonEnabled(baseSelf)
        return result
    return baseFunc(baseSelf, *args, **kwargs)

try:
    from AvatarInputHandler.DynamicCameras import ArcadeCamera
except Exception:
    ArcadeCamera = None

if ArcadeCamera is not None:
    @override(ArcadeCamera.ArcadeCamera, 'getTargetMProv')
    def ArcadeCamera_getTargetMProv(baseFunc, baseSelf):
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            mProv = getattr(player, '_PlayerAvatar__ownVehicleMProv', None)
            if mProv is not None:
                return mProv
        return baseFunc(baseSelf)

    @override(ArcadeCamera.ArcadeCamera, 'enable')
    def ArcadeCamera_enable(baseFunc, baseSelf, *args, **kwargs):
        result = baseFunc(baseSelf, *args, **kwargs)
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            ownMProv = getattr(player, '_PlayerAvatar__ownVehicleMProv', None)
            if ownMProv is not None:
                try:
                    baseSelf.vehicleMProv = ownMProv
                    _crash_log('ArcadeCamera.enable: vehicleMProv relinked to ownMProv')
                except Exception:
                    LOG_CURRENT_EXCEPTION()
        return result

try:
    import math_utils
except Exception:
    math_utils = None

try:
    from AvatarInputHandler.AimingSystems.steady_vehicle_matrix import SteadyVehicleMatrixCalculator
except Exception:
    SteadyVehicleMatrixCalculator = None


def _offhangar_identity_matrix():
    try:
        return math_utils.createIdentityMatrix()
    except Exception:
        m = Math.Matrix()
        try:
            m.setIdentity()
        except Exception:
            pass
        return m


if SteadyVehicleMatrixCalculator is not None:
    @override(SteadyVehicleMatrixCalculator, 'relinkSources')
    def SteadyVehicleMatrixCalculator_relinkSources(baseFunc, baseSelf):
        player = BigWorld.player()
        if player is None or not getattr(player, 'isOffline', False):
            return baseFunc(baseSelf)
        output = getattr(baseSelf, '_SteadyVehicleMatrixCalculator__outputMProv', None)
        stabilised = getattr(baseSelf, '_SteadyVehicleMatrixCalculator__stabilisedMProv', None)
        if output is None or stabilised is None:
            return baseFunc(baseSelf)
        try:
            vehicle = player.getVehicleAttached()
        except Exception:
            vehicle = None
        if vehicle is None or getattr(vehicle, 'isHidden', False):
            identity = _offhangar_identity_matrix()
            output.rotationSrc = identity
            output.translationSrc = identity
            stabilised.target = identity
            return
        try:
            ownMatrix = player.getOwnVehicleMatrix()
        except Exception:
            ownMatrix = None
        try:
            stabMatrix = player.getOwnVehicleStabilisedMatrix()
        except Exception:
            stabMatrix = None
        if ownMatrix is None:
            return baseFunc(baseSelf)
        if stabMatrix is None:
            stabMatrix = ownMatrix
        typeDescriptor = getattr(vehicle, 'typeDescriptor', None)
        pitchHull = False
        if typeDescriptor is not None:
            pitchHull = bool(getattr(typeDescriptor, 'isPitchHullAimingAvailable', False))
        if pitchHull:
            output.rotationSrc = stabMatrix
            output.translationSrc = ownMatrix
        else:
            output.rotationSrc = ownMatrix
            output.translationSrc = output.rotationSrc
        stabilised.target = stabMatrix

try:
    from vehicle_systems.common_tank_appearance import CommonTankAppearance
except Exception:
    CommonTankAppearance = None

if CommonTankAppearance is not None:
    @override(CommonTankAppearance, 'construct')
    def CommonTankAppearance_construct(baseFunc, baseSelf, isPlayer, resourceRefs):
        result = baseFunc(baseSelf, isPlayer, resourceRefs)
        try:
            if getattr(baseSelf, 'filter', None) is None:
                flt = getattr(baseSelf, '_CommonTankAppearance__filter', None)
                if flt is not None:
                    baseSelf.filter = flt
        except Exception:
            pass
        return result

try:
    from vehicle_systems.CompoundAppearance import CompoundAppearance
except Exception:
    CompoundAppearance = None

if CommonTankAppearance is not None:
    @override(CommonTankAppearance, '_periodicUpdate')
    def CommonTankAppearance_periodicUpdate(baseFunc, baseSelf):
        baseFunc(baseSelf)
        try:
            player = BigWorld.player()
            if player is None or not getattr(player, 'isOffline', False):
                return
            veh = baseSelf._vehicle
            if veh is None or not veh.isAlive():
                return
            flt = getattr(baseSelf, 'filter', None)
            if flt is None:
                return
            speed = 0.0
            try:
                speed = flt.averageSpeed
            except Exception:
                pass
            swinging = getattr(baseSelf, 'swingingAnimator', None)
            if swinging is not None and hasattr(swinging, 'maxMovementSpeed'):
                try:
                    swinging.maxMovementSpeed = abs(speed)
                except Exception:
                    pass
        except Exception:
            pass

@override(AvatarInputHandler.AvatarInputHandler, 'start')
def AvatarInputHandler_start(baseFunc, baseSelf, *args, **kwargs):
    result = baseFunc(baseSelf, *args, **kwargs)
    try:
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            calc = getattr(baseSelf, 'steadyVehicleMatrixCalculator', None)
            if calc is not None:
                calc.relinkSources()
    except Exception:
        pass
    return result

@override(LobbyHeader, 'fightClick')
def LobbyHeader_fightClick(baseFunc, baseSelf, mmData, actionName):
    if getattr(BigWorld.player(), 'isOffline', False):
        vehInvID = getattr(g_currentVehicle.item, 'invID', 0) if g_currentVehicle.item is not None else 0
        LOG_NOTE('LobbyHeader.fightClick intercepted offline, vehInvID=', vehInvID)
        BigWorld.callback(0, lambda: enterOfflineBattle(vehInvID))
        return
    return baseFunc(baseSelf, mmData, actionName)

try:
    from vehicle_systems.CompoundAppearance import CompoundAppearance
except Exception:
    CompoundAppearance = None

@override(VehicleModule.Vehicle, 'startVisual')
def Vehicle_startVisual_engineSoundHook(baseFunc, baseSelf, *args, **kwargs):
    result = baseFunc(baseSelf, *args, **kwargs)
    try:
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            appearance = getattr(baseSelf, 'appearance', None)
            if appearance is not None:
                if hasattr(appearance, '_onEngineStart'):
                    try:
                        appearance._onEngineStart()
                    except Exception:
                        pass
                
                from vehicle_systems.components import engine_state
                detailedEngineState = getattr(appearance, 'detailedEngineState', None)
                if detailedEngineState is not None:
                    try:
                        engine_state.checkEngineStart(detailedEngineState, 3)
                    except Exception:
                        pass
    except Exception:
        LOG_CURRENT_EXCEPTION()
    return result

import gui.mods.offhangar.shooting

def _normalizeShellLayout(shells):
    if not shells:
        return []
    if isinstance(shells, dict):
        result = []
        for k, v in shells.items():
            result.append((k, v))
        return result
    try:
        shells = tuple(shells)
    except Exception:
        return []
    if not shells:
        return []
    first = shells[0]
    if isinstance(first, (list, tuple)) and len(first) == 2:
        result = []
        for item in shells:
            result.append((item[0], item[1]))
        return result
    result = []
    for idx in xrange(0, len(shells), 2):
        result.append((shells[idx], shells[idx + 1]))
    return result


def _getHangarShellLayout(vDesc=None):
    try:
        item = getattr(g_currentVehicle, 'item', None)
        if item is not None:
            installed = getattr(getattr(item, 'shells', None), 'installed', None)
            if installed is not None:
                shells = installed.getItems()
                if shells:
                    return _normalizeShellLayout(shells)
            invID = getattr(item, 'invID', 0)
            if offhangar_data is not None:
                stored = getattr(offhangar_data, '_vehicleShellsByInvID', {}).get(invID, [])
                if stored:
                    return _normalizeShellLayout(stored)
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
                    return _normalizeShellLayout(stored)
    except Exception:
        LOG_CURRENT_EXCEPTION()

    if vDesc is not None:
        try:
            return _normalizeShellLayout(items_vehicles.getDefaultAmmoForGun(vDesc.gun))
        except Exception:
            LOG_CURRENT_EXCEPTION()

    return []


def _applyShellLayout(ammoCtrl, gun, shells):
    items = _normalizeShellLayout(shells)
    if not items:
        return False

    try:
        ammoCtrl.updateForNewSetup(gun, items)
        firstCD = items[0][0]
        currentCD = None
        for intCD, count in items:
            try:
                count = int(count)
            except Exception:
                count = 0
            if count > 0:
                currentCD = intCD
                break
        if currentCD is None:
            currentCD = firstCD
        try:
            ammoCtrl.setCurrentShellCD(currentCD)
        except Exception:
            pass
        try:
            ammoCtrl._offhangar_shellsVehicleID = getattr(BigWorld.player(), 'playerVehicleID', 0)
        except Exception:
            pass
        return True
    except Exception:
        pass

    try:
        ammoCtrl.setGunSettings(gun)
    except Exception:
        return False

    clipSize = gun.clip[0] if hasattr(gun, 'clip') and gun.clip else 1
    firstCD = None
    currentCD = None

    for intCD, count in items:
        try:
            count = int(count)
        except Exception:
            count = 0
        if count < 0:
            count = 0
        try:
            ammoCtrl.setShells(intCD, count, min(count, clipSize))
        except Exception:
            pass
        if firstCD is None:
            firstCD = intCD
        if currentCD is None and count > 0:
            currentCD = intCD

    if currentCD is None:
        currentCD = firstCD

    if currentCD is not None:
        try:
            ammoCtrl.setCurrentShellCD(currentCD)
        except Exception:
            pass

    try:
        ammoCtrl._offhangar_shellsVehicleID = getattr(BigWorld.player(), 'playerVehicleID', 0)
    except Exception:
        pass

    return True

@override(VehicleModule.Vehicle, 'showShooting')
def Vehicle_showShooting(baseFunc, baseSelf, burstCount, currentGuns, isPredictedShot=False):
    return baseFunc(baseSelf, burstCount, currentGuns, isPredictedShot)

@override(Avatar.PlayerAvatar, '_PlayerAvatar__startVehicleVisual')
def PlayerAvatar_initAmmoController(baseFunc, baseSelf, vehicle, resetControllers=False):
    if getattr(baseSelf, 'isOffline', False):
        try:
            return baseFunc(baseSelf, vehicle, resetControllers)
        except Exception:
            LOG_CURRENT_EXCEPTION()
            return None
    return baseFunc(baseSelf, vehicle, resetControllers)

try:
    from gui.Scaleform.daapi.view.battle.shared.consumables_panel import ConsumablesPanel
    from gui.mods.offhangar.utils import override

    def _consumablesPanelEnsureShell(baseSelf, intCD):
        try:
            if intCD in baseSelf._cds:
                return True
            ammoCtrl = baseSelf.sessionProvider.shared.ammo
            layout = ammoCtrl.getOrderedShellsLayout()
            for shellIntCD, descriptor, quantity, quantityInClip, gunSettings in layout:
                if shellIntCD == intCD:
                    baseSelf._onShellsAdded(shellIntCD, descriptor, quantity, quantityInClip, gunSettings)
                    return intCD in baseSelf._cds
            shots = ammoCtrl.getGunSettings().shots
            data = shots.get(intCD)
            if data is not None:
                descriptor = data[3]
                quantity, quantityInClip = ammoCtrl.getShells(intCD)
                baseSelf._onShellsAdded(intCD, descriptor, quantity, quantityInClip, None)
                return intCD in baseSelf._cds
        except Exception:
            LOG_CURRENT_EXCEPTION()
        return intCD in baseSelf._cds

    @override(ConsumablesPanel, '_onShellsAdded')
    def ConsumablesPanel_onShellsAdded(baseFunc, baseSelf, intCD, descriptor, quantity, quantityInClip, gunSettings):
        try:
            baseFunc(baseSelf, intCD, descriptor, quantity, quantityInClip, gunSettings)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    @override(ConsumablesPanel, '_onShellsUpdated')
    def ConsumablesPanel_onShellsUpdated(baseFunc, baseSelf, intCD, quantity, *args):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                if intCD not in baseSelf._cds:
                    _consumablesPanelEnsureShell(baseSelf, intCD)
            if intCD in baseSelf._cds:
                baseFunc(baseSelf, intCD, quantity, *args)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    @override(ConsumablesPanel, '_onNextShellChanged')
    def ConsumablesPanel_onNextShellChanged(baseFunc, baseSelf, intCD):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                if intCD not in baseSelf._cds:
                    _consumablesPanelEnsureShell(baseSelf, intCD)
            if intCD in baseSelf._cds:
                baseFunc(baseSelf, intCD)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    @override(ConsumablesPanel, '_onCurrentShellChanged')
    def ConsumablesPanel_onCurrentShellChanged(baseFunc, baseSelf, intCD):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                if intCD not in baseSelf._cds:
                    _consumablesPanelEnsureShell(baseSelf, intCD)
            if intCD in baseSelf._cds:
                baseFunc(baseSelf, intCD)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    @override(ConsumablesPanel, '_onGunReloadTimeSet')
    def ConsumablesPanel_onGunReloadTimeSet(baseFunc, baseSelf, currShellCD, state, skipAutoLoader):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                if currShellCD not in baseSelf._cds:
                    _consumablesPanelEnsureShell(baseSelf, currShellCD)
            if currShellCD in baseSelf._cds:
                baseFunc(baseSelf, currShellCD, state, skipAutoLoader)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    @override(ConsumablesPanel, '_populate')
    def ConsumablesPanel_populate(baseFunc, baseSelf, *args, **kwargs):
        baseFunc(baseSelf, *args, **kwargs)
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                ammoCtrl = baseSelf.sessionProvider.shared.ammo
                if ammoCtrl is not None:
                    layout = ammoCtrl.getOrderedShellsLayout()
                    if not layout:
                        vehicleID = getattr(player, 'playerVehicleID', 0)
                        vehicle = BigWorld.entity(vehicleID)
                        td = getattr(vehicle, 'typeDescriptor', None)
                        if td is not None:
                            gun = td.gun
                            ammoCtrl.setGunSettings(gun)
                            defaultAmmo = items_vehicles.getDefaultAmmoForGun(gun)
                            if defaultAmmo:
                                clipSize = gun.clip[0] if hasattr(gun, 'clip') and gun.clip else 1
                                for i in xrange(0, len(defaultAmmo), 2):
                                    intCD = defaultAmmo[i]
                                    count = defaultAmmo[i+1]
                                    if count <= 0:
                                        count = 10
                                    ammoCtrl.setShells(intCD, count, min(count, clipSize))
                                ammoCtrl.setCurrentShellCD(defaultAmmo[0])
                                if len(defaultAmmo) > 2:
                                    ammoCtrl.setNextShellCD(defaultAmmo[2])
                                layout = ammoCtrl.getOrderedShellsLayout()
                    if layout:
                        for intCD, descriptor, quantity, quantityInClip, gunSettings in layout:
                            if intCD not in baseSelf._cds:
                                baseSelf._onShellsAdded(intCD, descriptor, quantity, quantityInClip, gunSettings)
                            else:
                                baseSelf._onShellsUpdated(intCD, quantity, quantityInClip)
                    currCD = ammoCtrl.getCurrentShellCD()
                    if currCD is not None:
                        if currCD not in baseSelf._cds:
                            _consumablesPanelEnsureShell(baseSelf, currCD)
                        if currCD in baseSelf._cds:
                            baseSelf._onCurrentShellChanged(currCD)
                    nextCD = ammoCtrl.getNextShellCD()
                    if nextCD is not None:
                        if nextCD not in baseSelf._cds:
                            _consumablesPanelEnsureShell(baseSelf, nextCD)
                        if nextCD in baseSelf._cds:
                            baseSelf._onNextShellChanged(nextCD)
        except Exception:
            LOG_CURRENT_EXCEPTION()
except Exception:
    pass

try:
    from gui.battle_control.battle_session import BattleSessionProvider
except Exception:
    BattleSessionProvider = None

if BattleSessionProvider is not None:
    @override(BattleSessionProvider, 'setPlayerVehicle')
    def BattleSessionProvider_setPlayerVehicle(baseFunc, baseSelf, vID, vDesc):
        result = baseFunc(baseSelf, vID, vDesc)
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                ammoCtrl = baseSelf.shared.ammo
                if ammoCtrl is not None and vDesc is not None:
                    shells = _getHangarShellLayout(vDesc)
                    _applyShellLayout(ammoCtrl, vDesc.gun, shells)
        except Exception:
            LOG_CURRENT_EXCEPTION()
        return result
try:
    from gui.battle_control.controllers.consumables.ammo_ctrl import AmmoController

    def _getConsumablesPanel():
        try:
            from helpers import dependency
            from skeletons.gui.battle_session import IBattleSessionProvider
            sp = dependency.instance(IBattleSessionProvider)
            if sp is None:
                return None
            panel = getattr(sp, '_BattleSessionProvider__consumablesPanel', None)
            if panel is None:
                panel = getattr(sp, '_shared__consumablesPanel', None)
            return panel
        except Exception:
            return None

    @override(AmmoController, 'setCurrentShellCD')
    def AmmoController_setCurrentShellCD(baseFunc, baseSelf, *args, **kwargs):
        result = baseFunc(baseSelf, *args, **kwargs)
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                intCD = args[0] if args else kwargs.get('intCD', None)
                panel = _getConsumablesPanel()
                if panel is not None and intCD in getattr(panel, '_cds', {}):
                    panel._onCurrentShellChanged(intCD)
        except Exception:
            LOG_CURRENT_EXCEPTION()
        return result

    @override(AmmoController, 'setShells')
    def AmmoController_setShells(baseFunc, baseSelf, *args, **kwargs):
        result = baseFunc(baseSelf, *args, **kwargs)
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                intCD = args[0] if len(args) > 0 else kwargs.get('intCD', None)
                quantity = args[1] if len(args) > 1 else kwargs.get('quantity', None)
                quantityInClip = args[2] if len(args) > 2 else kwargs.get('quantityInClip', 0)
                panel = _getConsumablesPanel()
                if panel is not None and intCD in getattr(panel, '_cds', {}):
                    panel._onShellsUpdated(intCD, quantity, quantityInClip)
        except Exception:
            LOG_CURRENT_EXCEPTION()
        return result

    @override(AmmoController, 'setGunReloadTime')
    def AmmoController_setGunReloadTime(baseFunc, baseSelf, *args, **kwargs):
        result = baseFunc(baseSelf, *args, **kwargs)
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                currShellCD = args[0] if len(args) > 0 else kwargs.get('currShellCD', None)
                state = args[1] if len(args) > 1 else kwargs.get('state', 0.0)
                skipAutoLoader = args[2] if len(args) > 2 else kwargs.get('skipAutoLoader', False)
                panel = _getConsumablesPanel()
                if panel is not None and currShellCD in getattr(panel, '_cds', {}):
                    panel._onGunReloadTimeSet(currShellCD, state, skipAutoLoader)
        except Exception:
            LOG_CURRENT_EXCEPTION()
        return result

except Exception:
    LOG_CURRENT_EXCEPTION()

try:
    from vehicle_systems.CompoundAppearance import CompoundAppearance
except Exception:
    CompoundAppearance = None

if CompoundAppearance is not None:
    @override(CompoundAppearance, 'onVehicleHealthChanged')
    def CompoundAppearance_onVehicleHealthChanged_offlineSafe(baseFunc, baseSelf, showEffects=True):
        player = BigWorld.player()
        if player is None or not getattr(player, 'isOffline', False):
            return baseFunc(baseSelf, showEffects)

        vehicle = baseSelf._vehicle
        if vehicle is None:
            return

        try:
            if not vehicle.isAlive() and vehicle.health > 0:
                baseSelf.changeEngineMode((0, 0))
        except Exception:
            LOG_CURRENT_EXCEPTION()

        currentState = baseSelf.damageState

        try:
            isUnderWater = baseSelf.waterSensor.isUnderWater
        except Exception:
            isUnderWater = False

        currentState.update(vehicle.health, vehicle.isCrewActive, isUnderWater)

        if vehicle.health <= 0 and vehicle.id == getattr(player, 'playerVehicleID', 0):
            if not getattr(vehicle, '_offhangar_deathHandled', False):
                try:
                    vehicle._offhangar_deathHandled = True
                    player._PlayerAvatar__isVehicleAlive = False
                except Exception:
                    pass

                try:
                    inputHandler = getattr(player, 'inputHandler', None)
                    if inputHandler is not None:
                        inputHandler.onVehicleDeath(vehicle, currentState.state == 'ammoBayExplosion')
                except Exception:
                    LOG_CURRENT_EXCEPTION()

        return

try:
    from gui.battle_control.battle_constants import VEHICLE_VIEW_STATE
except Exception:
    VEHICLE_VIEW_STATE = None

if BattleSessionProvider is not None and VEHICLE_VIEW_STATE is not None:
    @override(BattleSessionProvider, 'setVehicleHealth')
    def BattleSessionProvider_setVehicleHealth(baseFunc, baseSelf, isPlayerVehicle, vehicleID, newHealth, attackerID, attackReasonID):
        result = baseFunc(baseSelf, isPlayerVehicle, vehicleID, newHealth, attackerID, attackReasonID)
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                if isPlayerVehicle:
                    baseSelf.invalidateVehicleState(VEHICLE_VIEW_STATE.HEALTH, newHealth, vehicleID)
        except Exception:
            pass
        return result

try:
    from gui.Scaleform.daapi.view.battle.shared.consumables_panel import ConsumablesPanel
    from gui.battle_control.controllers.consumables.ammo_ctrl import AmmoController

    @override(ConsumablesPanel, '_addListeners')
    def ConsumablesPanel_addListeners_autoReload(baseFunc, baseSelf):
        baseFunc(baseSelf)
        ammoCtrl = baseSelf.sessionProvider.shared.ammo
        if ammoCtrl is not None:
            ammoCtrl.onGunAutoReloadTimeSet += baseSelf._onGunAutoReloadTimeSet

    def _consumables_panel_onGunAutoReloadTimeSet(baseSelf, currShellCD, state, isSlowed):
        if currShellCD not in baseSelf._cds:
            return
        shellIndex = baseSelf._cds.index(currShellCD)
        if baseSelf._ConsumablesPanel__delayedReload > 0:
            baseSelf.delayCallback(
                baseSelf._ConsumablesPanel__delayedReload,
                baseSelf._ConsumablesPanel__startReloadDelayed,
                shellIndex, state
            )
            baseSelf.as_setCoolDownPosAsPercentS(shellIndex, 0)
        else:
            baseSelf._ConsumablesPanel__startReload(shellIndex, state)

    if not hasattr(ConsumablesPanel, '_onGunAutoReloadTimeSet'):
        ConsumablesPanel._onGunAutoReloadTimeSet = _consumables_panel_onGunAutoReloadTimeSet

    @override(AmmoController, 'setGunAutoReloadTime')
    def AmmoController_setGunAutoReloadTime_offline(baseFunc, baseSelf, timeLeft, baseTime, firstClipBaseTime, isSlowed, isBoostApplicable):
        result = baseFunc(baseSelf, timeLeft, baseTime, firstClipBaseTime, isSlowed, isBoostApplicable)
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                from helpers import dependency
                from skeletons.gui.battle_session import IBattleSessionProvider
                sp = dependency.instance(IBattleSessionProvider)
                if sp is not None:
                    panel = getattr(sp, '_BattleSessionProvider__consumablesPanel', None)
                    if panel is None:
                        panel = getattr(sp, '_shared__consumablesPanel', None)
                    if panel is not None:
                        currShellCD = baseSelf.getCurrentShellCD()
                        if currShellCD in getattr(panel, '_cds', {}):
                            panel._onGunAutoReloadTimeSet(currShellCD, baseSelf._autoReloadingState.getSnapshot(), isSlowed)
        except Exception:
            pass
        return result

except Exception:
    LOG_CURRENT_EXCEPTION()

try:
    from gui.Scaleform.Waiting import Waiting
except Exception:
    Waiting = None

def _returnToOfflineHangar():
    _crash_log('_returnToOfflineHangar START')

    try:
        leaveOfflineBattle()
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        if Waiting is not None:
            Waiting.close()
    except Exception:
        pass

    try:
        spaceID = BigWorld.createSpace()
        BigWorld.createEntity('Account', spaceID, 0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), {})
        _crash_log('_returnToOfflineHangar: new offline Account entity created')
    except Exception:
        LOG_CURRENT_EXCEPTION()
        _crash_log('_returnToOfflineHangar: FAILED to create Account entity')


@override(Avatar.PlayerAvatar, 'leaveArena')
def PlayerAvatar_leaveArena(baseFunc, baseSelf):
    if getattr(baseSelf, 'isOffline', False):
        _crash_log('PlayerAvatar.leaveArena OFFLINE intercepted')
        BigWorld.callback(0.0, _returnToOfflineHangar)
        return
    return baseFunc(baseSelf)

try:
    from gui.Scaleform.daapi.view.battle.shared.consumables_panel import ConsumablesPanel
    from gui.battle_control.controllers.consumables.ammo_ctrl import AmmoController

    def _consumables_panel_onGunAutoReloadTimeSet(baseSelf, currShellCD, state, isSlowed):
        if currShellCD not in baseSelf._cds:
            return
        shellIndex = baseSelf._cds.index(currShellCD)
        if baseSelf._ConsumablesPanel__delayedReload > 0:
            baseSelf.delayCallback(
                baseSelf._ConsumablesPanel__delayedReload,
                baseSelf._ConsumablesPanel__startReloadDelayed,
                shellIndex, state
            )
            baseSelf.as_setCoolDownPosAsPercentS(shellIndex, 0)
        else:
            baseSelf._ConsumablesPanel__startReload(shellIndex, state)

    if not hasattr(ConsumablesPanel, '_onGunAutoReloadTimeSet'):
        ConsumablesPanel._onGunAutoReloadTimeSet = _consumables_panel_onGunAutoReloadTimeSet

    if hasattr(ConsumablesPanel, '_addListeners'):
        @override(ConsumablesPanel, '_addListeners')
        def ConsumablesPanel_addListeners_autoReload(baseFunc, baseSelf):
            baseFunc(baseSelf)
            ammoCtrl = baseSelf.sessionProvider.shared.ammo
            if ammoCtrl is not None:
                ammoCtrl.onGunAutoReloadTimeSet += baseSelf._onGunAutoReloadTimeSet
    else:
        LOG_DEBUG('ConsumablesPanel._addListeners отсутствует в этой версии клиента, пропускаю autoreload-хук')

    @override(AmmoController, 'setGunAutoReloadTime')
    def AmmoController_setGunAutoReloadTime_offline(baseFunc, baseSelf, timeLeft, baseTime, firstClipBaseTime, isSlowed, isBoostApplicable):
        result = baseFunc(baseSelf, timeLeft, baseTime, firstClipBaseTime, isSlowed, isBoostApplicable)
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                from helpers import dependency
                from skeletons.gui.battle_session import IBattleSessionProvider
                sp = dependency.instance(IBattleSessionProvider)
                if sp is not None:
                    panel = getattr(sp, '_BattleSessionProvider__consumablesPanel', None)
                    if panel is None:
                        panel = getattr(sp, '_shared__consumablesPanel', None)
                    if panel is not None:
                        currShellCD = baseSelf.getCurrentShellCD()
                        if currShellCD in getattr(panel, '_cds', {}):
                            panel._onGunAutoReloadTimeSet(currShellCD, baseSelf._autoReloadingState.getSnapshot(), isSlowed)
        except Exception:
            pass
        return result

except Exception:
    LOG_CURRENT_EXCEPTION()

try:
    from AvatarInputHandler.control_modes import PostMortemControlMode
    import gui.mods.offhangar.physics as offhangar_physics

    @override(PostMortemControlMode, 'enable')
    def PostMortemControlMode_enable_offline(baseFunc, baseSelf, **args):
        result = baseFunc(baseSelf, **args)
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                newVehicle = args.get('newVehicleID', None)
                inputHandler = getattr(player, 'inputHandler', None)
                killerID = None
                if inputHandler is not None:
                    killerID = getattr(inputHandler, '_AvatarInputHandler__killerVehicleID', None)
                targetID = newVehicle if newVehicle is not None else killerID
                if targetID is not None:
                    body = offhangar_physics.world.get_body(targetID)
                    if body is not None and body.mProv is not None:
                        cam = getattr(baseSelf, '_PostMortemControlMode__cam', None)
                        if cam is not None:
                            cam.vehicleMProv = body.mProv
        except Exception:
            pass
        return result

    @override(PostMortemControlMode, '_PostMortemControlMode__switch')
    def PostMortemControlMode_switch_offline(baseFunc, baseSelf, isNext=True):
        try:
            return baseFunc(baseSelf, isNext)
        except Exception:
            pass
        return

    @override(PostMortemControlMode, '_PostMortemControlMode__switchToVehicle')
    def PostMortemControlMode_switchToVehicle_offline(baseFunc, baseSelf, toId=None):
        try:
            return baseFunc(baseSelf, toId)
        except Exception:
            pass
        return

except Exception:
    pass

try:
    import AvatarInputHandler as _AvatarInputHandlerModule

    @override(_AvatarInputHandlerModule.AvatarInputHandler, 'getDesiredShotPoint')
    def AvatarInputHandler_getDesiredShotPoint(baseFunc, baseSelf, ignoreAimingMode=False, ignoreDetached=False):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                arena = getattr(player, 'arena', None)
                if arena is None:
                    cam = BigWorld.camera()
                    if cam is not None:
                        direction = Math.Vector3(cam.direction)
                        return Math.Vector3(cam.position) + direction.scale(100.0)
                    return Math.Vector3(100.0, 10.0, 100.0)
                vehicle = player.getVehicleAttached()
                if vehicle is None or getattr(vehicle, 'typeDescriptor', None) is None:
                    cam = BigWorld.camera()
                    if cam is not None:
                        direction = Math.Vector3(cam.direction)
                        return Math.Vector3(cam.position) + direction.scale(100.0)
                    return Math.Vector3(100.0, 10.0, 100.0)
        except Exception:
            pass
        return baseFunc(baseSelf, ignoreAimingMode, ignoreDetached)

    @override(_AvatarInputHandlerModule.AvatarInputHandler, 'getMarkerPoint')
    def AvatarInputHandler_getMarkerPoint(baseFunc, baseSelf):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                arena = getattr(player, 'arena', None)
                if arena is None:
                    return None
                vehicle = player.getVehicleAttached()
                if vehicle is None or getattr(vehicle, 'typeDescriptor', None) is None:
                    return None
        except Exception:
            pass
        return baseFunc(baseSelf)

    @override(_AvatarInputHandlerModule.AvatarInputHandler, '_AvatarInputHandler__constructComponents')
    def AvatarInputHandler_constructComponents(baseFunc, baseSelf):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                vehicle = player.getVehicleAttached()
                if vehicle is None or getattr(vehicle, 'typeDescriptor', None) is None:
                    return
                arena = getattr(player, 'arena', None)
                if arena is None:
                    return
        except Exception:
            pass
        return baseFunc(baseSelf)

    @override(_AvatarInputHandlerModule.AvatarInputHandler, 'onVehicleControlModeChanged')
    def AvatarInputHandler_onVehicleControlModeChanged(baseFunc, baseSelf, eMode):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                arena = getattr(player, 'arena', None)
                if arena is None:
                    return
        except Exception:
            pass
        return baseFunc(baseSelf, eMode)

    @override(_AvatarInputHandlerModule.AvatarInputHandler, 'onControlModeChanged')
    def AvatarInputHandler_onControlModeChanged(baseFunc, baseSelf, eMode, **args):
        try:
            player = BigWorld.player()
            if player is not None and getattr(player, 'isOffline', False):
                vehicle = player.getVehicleAttached()
                if vehicle is None or getattr(vehicle, 'typeDescriptor', None) is None:
                    return
        except Exception:
            pass
        return baseFunc(baseSelf, eMode, **args)

except Exception:
    LOG_CURRENT_EXCEPTION()

if matrix_factory is not None:
    try:
        _original_makeVehicleMatrix = getattr(matrix_factory, 'makeVehicleMatrix', None)
    except Exception:
        _original_makeVehicleMatrix = None

    def _offhangar_makeVehicleMatrix(vehicleID, *args, **kwargs):
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            try:
                import gui.mods.offhangar.physics as offhangar_physics
                body = offhangar_physics.world.get_body(vehicleID)
                if body is not None and body.mProv is not None:
                    return body.mProv
            except Exception:
                pass
        if _original_makeVehicleMatrix is not None:
            return _original_makeVehicleMatrix(vehicleID, *args, **kwargs)
        return None

    try:
        matrix_factory.makeVehicleMatrix = _offhangar_makeVehicleMatrix
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        _original_getVehicleMPAndLocation = getattr(matrix_factory, 'getVehicleMPAndLocation', None)
    except Exception:
        _original_getVehicleMPAndLocation = None

    def _offhangar_getVehicleMPAndLocation(vehicleID, positions=None, *args, **kwargs):
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            try:
                import gui.mods.offhangar.physics as offhangar_physics
                body = offhangar_physics.world.get_body(vehicleID)
                if body is not None and body.mProv is not None:
                    location = None
                    if _original_getVehicleMPAndLocation is not None:
                        try:
                            _, location = _original_getVehicleMPAndLocation(vehicleID, positions, *args, **kwargs)
                        except Exception:
                            location = None
                    return (body.mProv, location)
            except Exception:
                pass
        if _original_getVehicleMPAndLocation is not None:
            try:
                return _original_getVehicleMPAndLocation(vehicleID, positions, *args, **kwargs)
            except Exception:
                try:
                    return _original_getVehicleMPAndLocation(vehicleID)
                except Exception:
                    return (None, None)
        return (None, None)

    try:
        _original_getVehicleMPAndLocation = matrix_factory.getVehicleMPAndLocation
    except Exception:
        _original_getVehicleMPAndLocation = None

    def _offhangar_getVehicleMPAndLocation(vehicleID, positions):
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            try:
                import gui.mods.offhangar.physics as offhangar_physics
                body = offhangar_physics.world.get_body(vehicleID)
                if body is not None and body.mProv is not None:
                    from gui.battle_control.battle_constants import VEHICLE_LOCATION
                    mProv = Math.TranslationOnlyMP()
                    mProv.source = body.mProv
                    return (mProv, VEHICLE_LOCATION.AOI)
            except Exception:
                pass
        if _original_getVehicleMPAndLocation is not None:
            return _original_getVehicleMPAndLocation(vehicleID, positions)
        return (None, None)

    try:
        matrix_factory.getVehicleMPAndLocation = _offhangar_getVehicleMPAndLocation
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        _original_makeVehicleMPByLocation = matrix_factory.makeVehicleMPByLocation
    except Exception:
        _original_makeVehicleMPByLocation = None

    def _offhangar_makeVehicleMPByLocation(vehicleID, location, positions):
        player = BigWorld.player()
        if player is not None and getattr(player, 'isOffline', False):
            try:
                import gui.mods.offhangar.physics as offhangar_physics
                body = offhangar_physics.world.get_body(vehicleID)
                if body is not None and body.mProv is not None:
                    mProv = Math.TranslationOnlyMP()
                    mProv.source = body.mProv
                    return mProv
            except Exception:
                pass
        if _original_makeVehicleMPByLocation is not None:
            return _original_makeVehicleMPByLocation(vehicleID, location, positions)
        return None

    try:
        matrix_factory.makeVehicleMPByLocation = _offhangar_makeVehicleMPByLocation
    except Exception:
        LOG_CURRENT_EXCEPTION()

    try:
        matrix_factory.getVehicleMPAndLocation = _offhangar_getVehicleMPAndLocation
    except Exception:
        LOG_CURRENT_EXCEPTION()