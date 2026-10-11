import math
import weakref

try:
    import BigWorld
    import Math
except Exception:
    BigWorld = None
    Math = None

try:
    import Vehicle as VehicleModule
    from gui.mods.offhangar.utils import override
except Exception:
    VehicleModule = None
    override = None

try:
    import AreaDestructibles
    import DestructiblesCache
except Exception:
    AreaDestructibles = None
    DestructiblesCache = None

_TICK_PERIOD = 0.033

_FORWARD_SPEED_DEFAULT = 12.0
_BACKWARD_SPEED_DEFAULT = 6.0
_ROTATION_SPEED_DEFAULT = 2.0

_HALF_LENGTH_DEFAULT = 3.3
_HALF_WIDTH_DEFAULT = 1.8
_HALF_TRACK_BASE_DEFAULT = 1.6

_HEIGHT_SMOOTH_RATE = 35.0
_HEIGHT_DOWN_SMOOTH_RATE = 35.0
_TILT_SMOOTH_RATE = 25.0
_TILT_SNAP_DISTANCE = 0.45
_MAX_TILT_ANGLE = 1.25

_COLLISION_HEIGHT_OFFSET = 2.5
_COLLISION_SKIN = 0.15
_COLLISION_SIDE_FACTOR = 0.9

_TRACK_SCROLL_SCALE = 1.0
_TRACK_SCROLL_DIRECTION = 1.0
_TRACK_SCROLL_WRAP = 1000.0

_GROUND_OFFSET = 0.03
_SUSPENSION_MAX_LIFT = 1.2
_SUSPENSION_MAX_DROP = 0.8
_GROUND_SNAP_DISTANCE = 0.35

# Ray steps used to find the ground height under/around the vehicle.
# NOTE: the "raise" (first) value is how far ABOVE the current reference
# height each ray starts. It used to start very high (18/55/140m), which
# meant that when the tank was standing under a bridge/overpass the ray
# could hit the underside of the bridge deck first and the physics would
# treat the bridge as "ground", lifting the tank into it or refusing to
# let it pass underneath. Keeping the raise small on the first (most
# common) attempts fixes driving under bridges, while the larger fallback
# tiers still exist for genuine large drops (falling off a cliff, etc.).
_GROUND_RAY_STEPS = (
    (2.5, 25.0),
    (6.0, 60.0),
    (12.0, 150.0),
)

# Maximum slope (from horizontal) the tank is allowed to climb by driving
# forward/backward. Anything steeper than this (walls, cliffs, vertical or
# overhanging objects) is treated like a solid obstacle: the tank is
# stopped instead of being snapped/lifted up onto it.
_MAX_CLIMB_ANGLE = math.radians(60.0)
_MAX_CLIMB_ANGLE_MIN_HEIGHT = 0.05

_FORWARD_ACCEL = 8.0
_FORWARD_DECEL = 14.0
_BACKWARD_ACCEL = 6.0
_ROTATION_ACCEL = 6.0

_ENGINE_IDLE_RPM_REL = 0.18
_ENGINE_MAX_RPM_REL = 1.0
_ENGINE_RPM_SMOOTH_RATE = 3.0
_ENGINE_ROTATION_RPM_BOOST = 0.35

_DIAG_PERIOD_TICKS = 30
_diag_counter = 0

_RAM_DESTRUCTIBLE_CHECK_INTERVAL = 0.1
_RAM_MIN_SPEED = 1.0
_RAM_OBJECT_RADIUS = 2.0

_ram_broken = set()

_GRAVITY = 22.0
_MAX_FALL_SPEED = 40.0
_GROUND_SNAP_UP_TOLERANCE = 0.5

_BUSH_FILENAME_MARKERS = ('shrubs', 'bush')


class _SpeedValueWrapper(object):
    __slots__ = ('value',)

    def __init__(self, vec4):
        self.value = vec4


def _crash_log(msg):
    text = 'offhangar_physics: {}'.format(msg)
    try:
        BigWorld.LOG_ERROR(text)
        return
    except Exception:
        pass
    try:
        BigWorld.logInfo(text)
        return
    except Exception:
        pass
    try:
        import logging
        logging.getLogger('offhangar.physics').error(text)
        return
    except Exception:
        pass
    try:
        print(text)
    except Exception:
        pass


_tickCallbackID = None


class _FakeDataLink(object):
    __slots__ = ('_getter',)

    def __init__(self, getter):
        self._getter = getter

    def __call__(self):
        return self._getter()

    def get(self):
        return self._getter()

    @property
    def value(self):
        return self._getter()


class Body(object):
    def __init__(self, body_id, position, yaw, mProv, vehicleRef,
                 halfLength, halfWidth, halfTrackBase,
                 fwdSpeed, bckwdSpeed, rotationSpeed):
        self.id = body_id
        self.x, self.y, self.z = float(position[0]), float(position[1]), float(position[2])
        self.yaw = float(yaw)
        self.pitch = 0.0
        self.roll = 0.0
        self.halfLength = float(halfLength)
        self.halfWidth = float(halfWidth)
        self.halfTrackBase = float(halfTrackBase)
        self.fwdSpeed = float(fwdSpeed)
        self.bckwdSpeed = float(bckwdSpeed)
        self.rotationSpeed = float(rotationSpeed)
        self.scrollLeft = 0.0
        self.scrollRight = 0.0
        self.mProv = mProv
        self.vehicleRef = vehicleRef
        self.forward = 0
        self.rotation = 0
        self.trackControllerActivated = False
        self.groundY = float(position[1])
        self.cornerHeights = [float(position[1])] * 4
        self.centerHeight = float(position[1])
        self.currentSpeed = 0.0
        self.currentRotationSpeed = 0.0
        self.currentRpmRel = _ENGINE_IDLE_RPM_REL
        self.engineStarted = False
        self._diagCapabilitiesLogged = False
        self._diagEngineLogged = False
        self.mass = 30000.0
        self.ramDestructibleCheckTime = 0.0
        self.vy = 0.0
        self.isGrounded = True

class _World(object):
    def __init__(self):
        self.bodies = {}
        self.controlled_body_id = 0

    def get_body(self, body_id):
        return self.bodies.get(body_id)

world = _World()
_installed = False


def install():
    global _installed
    if _installed:
        return
    _installed = True

    if VehicleModule is None or override is None:
        return

    try:
        @override(VehicleModule.Vehicle, 'notifyInputKeysDown')
        def physics_Vehicle_notifyInputKeysDown(baseFunc, baseSelf, movementDir, rotationDir, handbrakeFired=False):
            try:
                player = BigWorld.player() if BigWorld is not None else None
                if player is not None and getattr(player, 'isOffline', False):
                    if baseSelf.id == getattr(player, 'playerVehicleID', 0) and baseSelf.isAlive():
                        set_control(baseSelf.id, forward=movementDir, rotation=rotationDir)
                        try:
                            appearance = getattr(baseSelf, 'appearance', None)
                            engineState = getattr(appearance, 'detailedEngineState', None) if appearance is not None else None
                            if engineState is not None:
                                engineState.throttle = movementDir or rotationDir
                        except Exception:
                            pass
                        return
            except Exception:
                pass
            return baseFunc(baseSelf, movementDir, rotationDir, handbrakeFired)
    except Exception:
        pass


def start():
    global _tickCallbackID
    stop()
    _ram_broken.clear()
    _tick()


def stop():
    global _tickCallbackID
    if _tickCallbackID is not None and BigWorld is not None:
        try:
            BigWorld.cancelCallback(_tickCallbackID)
        except Exception:
            pass
    _tickCallbackID = None


def clear_bodies():
    stop()
    world.bodies.clear()
    world.controlled_body_id = 0
    _ram_broken.clear()


def set_height_getter(callback):
    pass


def _clamp(value, lo, hi):
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


try:
    _OFFHANGAR_STRING_TYPES = (str, unicode)
except Exception:
    _OFFHANGAR_STRING_TYPES = (str,)


def _offhangar_as_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def _offhangar_get_field(obj, name, default=None):
    if obj is None:
        return default
    getter = getattr(obj, 'get', None)
    if callable(getter):
        try:
            return getter(name, default)
        except Exception:
            pass
    return getattr(obj, name, default)


def _offhangar_get_path(obj, path, default=None):
    cur = obj
    for part in path.split('.'):
        cur = _offhangar_get_field(cur, part, None)
        if cur is None:
            return default
    if cur is None:
        return default
    return cur


def _offhangar_first_path(obj, paths, default=None):
    for path in paths:
        value = _offhangar_get_path(obj, path, None)
        if value is not None:
            return value
    return default


def _offhangar_to_sequence(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return value
    if isinstance(value, _OFFHANGAR_STRING_TYPES):
        return value.replace(',', ' ').split()
    if isinstance(value, dict):
        return (value,)
    try:
        return tuple(value)
    except Exception:
        return (value,)


def _offhangar_norm_rotation(value):
    seq = _offhangar_to_sequence(value)
    if seq is not None:
        if not len(seq):
            return 0.0
        value = seq[0]
    v = abs(_offhangar_as_float(value, 0.0))
    if v > 3.2:
        v = math.radians(v)
    return v


def _read_vehicle_config(veh):
    fwd = _FORWARD_SPEED_DEFAULT
    bckwd = _BACKWARD_SPEED_DEFAULT
    rot = _ROTATION_SPEED_DEFAULT
    halfLength = _HALF_LENGTH_DEFAULT
    halfWidth = _HALF_WIDTH_DEFAULT
    halfTrackBase = _HALF_TRACK_BASE_DEFAULT
    mass = 30000.0

    td = getattr(veh, 'typeDescriptor', None) if veh is not None else None
    if td is None:
        return {
            'fwdSpeed': fwd,
            'bckwdSpeed': bckwd,
            'rotationSpeed': rot,
            'halfLength': halfLength,
            'halfWidth': halfWidth,
            'halfTrackBase': halfTrackBase,
            'mass': mass,
        }

    speedLimits = _offhangar_first_path(td, (
        'physics.speedLimits',
        'type.physics.speedLimits',
        'vehiclePhysics.speedLimits',
        'speedLimits',
        'type.speedLimits',
    ), None)
    speedSeq = _offhangar_to_sequence(speedLimits)
    if speedSeq is not None and len(speedSeq) > 0:
        rawFwd = abs(_offhangar_as_float(speedSeq[0], 0.0))
        rawBckwd = rawFwd * 0.5
        if len(speedSeq) >= 2:
            rawBckwd = abs(_offhangar_as_float(speedSeq[1], 0.0))
        if rawFwd > 24.0 or rawBckwd > 12.0:
            rawFwd /= 3.6
            rawBckwd /= 3.6
        fwd = rawFwd
        bckwd = rawBckwd

    rawRot = _offhangar_first_path(td, (
        'chassis.rotationSpeed',
        'chassis.rotationSpeedLimit',
        'physics.rotationSpeed',
        'physics.rotationSpeedLimit',
        'type.chassis.rotationSpeed',
        'type.chassis.rotationSpeedLimit',
        'type.physics.rotationSpeed',
        'type.physics.rotationSpeedLimit',
        'rotationSpeed',
        'rotationSpeedLimit',
    ), None)
    if rawRot is not None:
        rot = _offhangar_norm_rotation(rawRot)

    rawMass = _offhangar_first_path(td, (
        'physics.weight',
        'type.physics.weight',
        'chassis.weight',
        'type.chassis.weight',
        'weight',
    ), None)
    if rawMass is not None:
        mass = abs(_offhangar_as_float(rawMass, mass))

    point = _offhangar_first_path(td, (
        'chassis.topRightCarryingPoint',
        'type.chassis.topRightCarryingPoint',
    ), None)
    if point is not None:
        try:
            pointSeq = _offhangar_to_sequence(point)
            if pointSeq is not None and len(pointSeq) > 0:
                halfTrackBase = abs(_offhangar_as_float(pointSeq[0], halfTrackBase))
        except Exception:
            pass

    for attrPath in (
        'collisionBoundingBox',
        'hull.collisionBoundingBox',
        'hull.boundingBox',
    ):
        box = _offhangar_first_path(td, (
            attrPath,
            'type.' + attrPath,
        ), None)
        if box is None:
            continue
        try:
            boxSeq = _offhangar_to_sequence(box)
            if boxSeq is None or len(boxSeq) < 2:
                continue
            minV, maxV = boxSeq[0], boxSeq[1]
            minSeq = _offhangar_to_sequence(minV)
            maxSeq = _offhangar_to_sequence(maxV)
            if minSeq is None or maxSeq is None or len(minSeq) < 3 or len(maxSeq) < 3:
                continue
            halfLength = abs(_offhangar_as_float(maxSeq[2], 0.0) - _offhangar_as_float(minSeq[2], 0.0)) * 0.5
            halfWidth = abs(_offhangar_as_float(maxSeq[0], 0.0) - _offhangar_as_float(minSeq[0], 0.0)) * 0.5
            if halfLength > 0.1 and halfWidth > 0.1:
                break
        except Exception:
            continue

    if fwd <= 0.01:
        fwd = _FORWARD_SPEED_DEFAULT
    if bckwd <= 0.01:
        bckwd = _BACKWARD_SPEED_DEFAULT
    if rot <= 0.01:
        rot = _ROTATION_SPEED_DEFAULT
    if halfLength <= 0.1:
        halfLength = _HALF_LENGTH_DEFAULT
    if halfWidth <= 0.1:
        halfWidth = _HALF_WIDTH_DEFAULT
    if halfTrackBase <= 0.1:
        halfTrackBase = halfWidth * 0.85 if halfWidth > 0.1 else _HALF_TRACK_BASE_DEFAULT
    if mass <= 0.01:
        mass = 30000.0

    return {
        'fwdSpeed': fwd,
        'bckwdSpeed': bckwd,
        'rotationSpeed': rot,
        'halfLength': halfLength,
        'halfWidth': halfWidth,
        'halfTrackBase': halfTrackBase,
        'mass': mass,
    }

def add_vehicle(body_id, entity_id=0, position=(0.0, 10.0, 0.0), yaw=0.0, mProv=None,
                halfLength=None, halfWidth=None, halfTrackBase=None,
                fwdSpeed=None, bckwdSpeed=None, rotationSpeed=None,
                becomeControlled=True, **kwargs):
    vehicleRef = None
    veh = None
    if BigWorld is not None:
        try:
            veh = BigWorld.entity(body_id)
            if veh is not None:
                vehicleRef = weakref.ref(veh)
        except Exception:
            vehicleRef = None
            veh = None

    # --- НАЧАЛО БЛОКА КОРРЕКТИРОВКИ ВЫСОТЫ СПАВНА ---
    corrected_position = position
    if BigWorld is not None and Math is not None:
        try:
            player = BigWorld.player()
            spaceID = getattr(player, 'spaceID', None)
            if spaceID is not None:
                x = float(position[0])
                y = float(position[1])
                z = float(position[2])
                
                hit = None
                # Ищем землю в широком диапазоне относительно переданного Y
                for raise_val, depth_val in ((20.0, 100.0), (200.0, 500.0), (1500.0, 2500.0)):
                    top = Math.Vector3(x, y + raise_val, z)
                    bottom = Math.Vector3(x, y - depth_val, z)
                    try:
                        hit = BigWorld.collideDynamicStatic(spaceID, top, bottom, 1, body_id, -1, 0)
                    except Exception:
                        hit = None
                    if hit is not None:
                        break
                
                # Абсолютный fallback с огромной высоты
                if hit is None:
                    top = Math.Vector3(x, 3000.0, z)
                    bottom = Math.Vector3(x, -3000.0, z)
                    try:
                        hit = BigWorld.collideDynamicStatic(spaceID, top, bottom, 1, body_id, -1, 0)
                    except Exception:
                        hit = None
                
                if hit is not None:
                    ground_y = float(hit[0].y)
                    # Если разница между переданным Y и найденной землей больше 2 метров,
                    # значит спавн произошел в небе или под землей. Корректируем.
                    if abs(y - ground_y) > 2.0:
                        new_y = ground_y + 1.2 # Чуть выше земли, чтобы не застрять в текстурах
                        corrected_position = (x, new_y, z)
                        try:
                            # Обновляем позицию самого энтити и аватара, если это игрок
                            if veh is not None:
                                veh.position = Math.Vector3(x, new_y, z)
                            if player is not None and getattr(player, 'playerVehicleID', 0) == body_id:
                                player.position = Math.Vector3(x, new_y, z)
                        except Exception:
                            pass
                        _crash_log('add_vehicle: corrected Y from {:.2f} to {:.2f} for body {}'.format(y, new_y, body_id))
        except Exception:
            pass
    # --- КОНЕЦ БЛОКА КОРРЕКТИРОВКИ ВЫСОТЫ ---

    cfg = _read_vehicle_config(veh)
    if halfLength is None:
        halfLength = cfg['halfLength']
    if halfWidth is None:
        halfWidth = cfg['halfWidth']
    if halfTrackBase is None:
        halfTrackBase = cfg['halfTrackBase']
    if fwdSpeed is None:
        fwdSpeed = cfg['fwdSpeed']
    if bckwdSpeed is None:
        bckwdSpeed = cfg['bckwdSpeed']
    if rotationSpeed is None:
        rotationSpeed = cfg['rotationSpeed']
        
    # Используем исправленную позицию
    body = Body(
        body_id, corrected_position, yaw, mProv, vehicleRef,
        halfLength, halfWidth, halfTrackBase,
        fwdSpeed, bckwdSpeed, rotationSpeed
    )
    body.engineStarted = True
    body.mass = cfg.get('mass', 30000.0)
    world.bodies[body_id] = body
    if becomeControlled:
        world.controlled_body_id = body_id
        
    if BigWorld is not None:
        try:
            player = BigWorld.player()
            isOfflineControlled = (
                becomeControlled
                and player is not None
                and getattr(player, 'isOffline', False)
                and getattr(player, 'playerVehicleID', 0) == body_id
            )
            if isOfflineControlled:
                if getattr(player, 'filter', None) is not None:
                    player.filter.ignoreInputs = True
                if veh is not None:
                    if getattr(veh, 'filter', None) is not None:
                        veh.filter.ignoreInputs = True
                if mProv is not None:
                    try:
                        mProv.target = None
                        initMatrix = Math.Matrix()
                        try:
                            initMatrix.setRotateYPR((float(yaw), 0.0, 0.0))
                        except Exception:
                            pass
                        # Применяем исправленную позицию к матрице провайдера
                        initMatrix.translation = Math.Vector3(float(corrected_position[0]), float(corrected_position[1]), float(corrected_position[2]))
                        mProv.setStaticTransform(initMatrix)
                    except Exception:
                        pass
                try:
                    model = getattr(veh, 'model', None)
                    if model is not None:
                        model.matrix = mProv
                except Exception:
                    pass
                try:
                    appearance_obj = getattr(veh, 'appearance', None)
                    compoundModel = getattr(appearance_obj, 'compoundModel', None) if appearance_obj is not None else None
                    if compoundModel is not None:
                        compoundModel.matrix = mProv
                except Exception:
                    pass
                inputHandler = getattr(player, 'inputHandler', None)
                ctrl = getattr(inputHandler, 'ctrl', None) if inputHandler is not None else None
                cam = getattr(ctrl, 'camera', None) if ctrl is not None else None
                ownMProv = getattr(player, '_PlayerAvatar__ownVehicleMProv', None)
                if cam is not None and ownMProv is not None and hasattr(cam, 'vehicleMProv'):
                    try:
                        ownMProv.target = None
                        cam.vehicleMProv = ownMProv
                    except Exception:
                        pass
            elif veh is not None:
                try:
                    if getattr(veh, 'filter', None) is not None:
                        veh.filter.ignoreInputs = True
                except Exception:
                    pass
                if mProv is not None:
                    try:
                        mProv.target = None
                        initMatrix = Math.Matrix()
                        try:
                            initMatrix.setRotateYPR((float(yaw), 0.0, 0.0))
                        except Exception:
                            pass
                        initMatrix.translation = Math.Vector3(float(corrected_position[0]), float(corrected_position[1]), float(corrected_position[2]))
                        mProv.setStaticTransform(initMatrix)
                    except Exception:
                        pass
        except Exception:
            pass
    return body_id


def remove_body(body_id):
    world.bodies.pop(body_id, None)
    if world.controlled_body_id == body_id:
        world.controlled_body_id = 0


def set_control(body_id, forward=0, rotation=0, **kwargs):
    body = world.bodies.get(body_id)
    if body is None and world.controlled_body_id:
        body = world.bodies.get(world.controlled_body_id)
    if body is None:
        return
    body.forward = forward
    body.rotation = rotation


def get_body_matrix(body_id):
    body = world.bodies.get(body_id)
    if body is None or Math is None:
        return None
    m = Math.Matrix()
    try:
        m.setRotateYPR((body.yaw, body.pitch, body.roll))
    except Exception:
        pass
    m.translation = Math.Vector3(body.x, body.y, body.z)
    return m

_TRACK_VISUAL_MAX_STEER_ANGLE = 0.5
_TRACK_VISUAL_STEER_GAIN = 0.9


def _drive_wheels_visual(vehicle, appearance, wheels, cache, left, right, rotationSpeed):
    try:
        if not wheels:
            return False
        angle = rotationSpeed * _TRACK_VISUAL_STEER_GAIN
        if (left + right) * 0.5 < 0.0:
            angle = -angle
        if angle > _TRACK_VISUAL_MAX_STEER_ANGLE:
            angle = _TRACK_VISUAL_MAX_STEER_ANGLE
        elif angle < -_TRACK_VISUAL_MAX_STEER_ANGLE:
            angle = -_TRACK_VISUAL_MAX_STEER_ANGLE
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


def _drive_track_visuals(body, vehicle, appearance, speed, rotationSpeed, halfTrackBase):
    """
    Общая анимация гусениц/колёс — та же логика, что и для ботов
    (см. gui/mods/offhangar/bots.py:_botTrackScroll), но теперь применяется
    и к машине игрока. Раньше игрок анимировался напрямую через
    flt.leftTrackScroll/rightTrackScroll без активации
    trackScrollController и без changeEngineMode, из-за чего гусеницы
    визуально либо не крутились, либо крутились некорректно по сравнению
    с ботами.
    """
    if appearance is None:
        return False

    turn = rotationSpeed * halfTrackBase
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

    cache = getattr(body, '_trackVisualCache', None)
    if cache is None:
        cache = {
            'vals': None,
            'mode': None,
            'linked': None,
            'tscReady': False,
        }
        body._trackVisualCache = cache

    try:
        wheels = None
        try:
            if getattr(appearance.typeDescriptor, 'isWheeledVehicle', False):
                wheels = getattr(appearance, 'wheelsAnimator', None)
        except Exception:
            wheels = None

        if wheels is not None:
            _drive_wheels_visual(vehicle, appearance, wheels, cache, left, right, rotationSpeed)
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
        body._trackVisualCache = None
        return False

def _corner_offsets(yaw, halfLength, halfWidth):
    sy = math.sin(yaw)
    cy = math.cos(yaw)
    corners = []
    for f in (halfLength, -halfLength):
        for r in (halfWidth, -halfWidth):
            dx = f * sy + r * cy
            dz = f * cy - r * sy
            corners.append((dx, dz))
    return corners


def _get_ground_height(spaceID, x, z, fallbackY, excludeId):
    if BigWorld is None or Math is None:
        return None
    try:
        base = float(fallbackY)
        for raiseValue, depthValue in _GROUND_RAY_STEPS:
            top = Math.Vector3(x, base + raiseValue, z)
            bottom = Math.Vector3(x, base - depthValue, z)
            hit = BigWorld.collideDynamicStatic(spaceID, top, bottom, 1, excludeId, -1, 0)
            if hit is not None:
                return float(hit[0].y)

        top = Math.Vector3(x, base + 500.0, z)
        bottom = Math.Vector3(x, base - 2000.0, z)
        hit = BigWorld.collideDynamicStatic(spaceID, top, bottom, 1, excludeId, -1, 0)
        if hit is not None:
            return float(hit[0].y)

        top = Math.Vector3(x, 3000.0, z)
        bottom = Math.Vector3(x, -500.0, z)
        hit = BigWorld.collideDynamicStatic(spaceID, top, bottom, 1, excludeId, -1, 0)
        if hit is not None:
            return float(hit[0].y)
    except Exception:
        pass
    return None

def _sample_corners_and_tilt(spaceID, body, dt):
    corners = _corner_offsets(body.yaw, body.halfLength, body.halfWidth)
    localCorners = (
        (body.halfWidth, body.halfLength),
        (-body.halfWidth, body.halfLength),
        (body.halfWidth, -body.halfLength),
        (-body.halfWidth, -body.halfLength),
    )
    prevHeights = getattr(body, 'cornerHeights', None)
    if not isinstance(prevHeights, list) or len(prevHeights) != 4:
        prevHeights = [float(body.y)] * 4

    topHint = getattr(body, 'groundY', body.y)
    heights = []
    for i, corner in enumerate(corners):
        dx, dz = corner
        h = _get_ground_height(spaceID, body.x + dx, body.z + dz, topHint, body.id)
        if h is None:
            h = prevHeights[i]
        heights.append(float(h))

    body.cornerHeights = heights

    frHeight, flHeight, brHeight, blHeight = heights
    avgHeight = sum(heights) * 0.25

    prevCenter = getattr(body, 'centerHeight', avgHeight)
    centerHeight = _get_ground_height(spaceID, body.x, body.z, topHint, body.id)
    if centerHeight is None:
        centerHeight = prevCenter
    centerHeight = float(centerHeight)
    body.centerHeight = centerHeight

    frontHeight = (frHeight + flHeight) * 0.5
    backHeight = (brHeight + blHeight) * 0.5
    rightHeight = (frHeight + brHeight) * 0.5
    leftHeight = (flHeight + blHeight) * 0.5

    targetPitch = math.atan2(backHeight - frontHeight, 2.0 * body.halfLength)
    targetRoll = math.atan2(rightHeight - leftHeight, 2.0 * body.halfWidth)

    targetPitch = _clamp(targetPitch, -_MAX_TILT_ANGLE, _MAX_TILT_ANGLE)
    targetRoll = _clamp(targetRoll, -_MAX_TILT_ANGLE, _MAX_TILT_ANGLE)

    tiltStep = min(1.0, dt * _TILT_SMOOTH_RATE)
    supportPitch = body.pitch + (targetPitch - body.pitch) * tiltStep
    supportRoll = body.roll + (targetRoll - body.roll) * tiltStep

    if abs(targetPitch - body.pitch) > _TILT_SNAP_DISTANCE:
        supportPitch = targetPitch
    if abs(targetRoll - body.roll) > _TILT_SNAP_DISTANCE:
        supportRoll = targetRoll

    tp = math.tan(supportPitch)
    tr = math.tan(supportRoll)

    required = []
    for i, h in enumerate(heights):
        lx, lz = localCorners[i]
        required.append(h - (-lz * tp + lx * tr))

    maxRequired = max(required)
    lift = _clamp(maxRequired - avgHeight, -_SUSPENSION_MAX_DROP, _SUSPENSION_MAX_LIFT)
    targetY = avgHeight + lift + _GROUND_OFFSET

    centerLimit = centerHeight + _GROUND_OFFSET
    maxCenterLimit = avgHeight + _SUSPENSION_MAX_LIFT + _GROUND_OFFSET
    if centerLimit > maxCenterLimit:
        centerLimit = maxCenterLimit
    if centerLimit > targetY:
        targetY = centerLimit

    return targetY, targetPitch, targetRoll


def _resolve_horizontal_collision(spaceID, body, dx, dz):
    """
    4-point hull collision: casts one ray from each of the tank's four hull
    corners (front-left/right, back-left/right - via _corner_offsets, so it
    correctly follows the vehicle's current yaw) along the movement vector.
    The shortest allowed distance among the four corners is used, so the
    tank stops as soon as ANY corner would clip through a wall/object, not
    just its centerline or two side points like before.
    """
    if spaceID is None or BigWorld is None or Math is None:
        return dx, dz

    moveLen = math.sqrt(dx * dx + dz * dz)
    if moveLen < 1e-6:
        return dx, dz

    baseY = getattr(body, 'groundY', body.y)
    testHeight = baseY + _COLLISION_HEIGHT_OFFSET

    corners = _corner_offsets(body.yaw, body.halfLength * _COLLISION_SIDE_FACTOR, body.halfWidth * _COLLISION_SIDE_FACTOR)

    minAllowed = moveLen
    for cornerDx, cornerDz in corners:
        startX = body.x + cornerDx
        startZ = body.z + cornerDz
        fromPos = Math.Vector3(startX, testHeight, startZ)
        toPos = Math.Vector3(startX + dx, testHeight, startZ + dz)
        try:
            hit = BigWorld.collideDynamicStatic(spaceID, fromPos, toPos, 1, body.id, -1, 0)
        except Exception:
            hit = None
        if hit is not None:
            hitPoint = hit[0]
            hitDx = hitPoint.x - startX
            hitDz = hitPoint.z - startZ
            hitDist = math.sqrt(hitDx * hitDx + hitDz * hitDz)
            allowed = max(0.0, hitDist - _COLLISION_SKIN)
            if allowed < minAllowed:
                minAllowed = allowed

    if minAllowed >= moveLen:
        return dx, dz

    scale = minAllowed / moveLen
    return dx * scale, dz * scale


def _limit_climb_angle(body, dx, dz, targetY):
    """
    Prevent the tank from driving up (being snapped/lifted onto) surfaces
    that are steeper than _MAX_CLIMB_ANGLE (e.g. vertical walls, cliffs,
    or anything a tracked vehicle realistically could not climb).

    Compares how much the ground height rose (targetY vs. the ground
    height we were on before this tick's move, body.groundY) against how
    far the vehicle actually travelled horizontally this tick. If the
    implied slope angle exceeds the limit, the horizontal move is
    reverted and the vehicle is treated as if it hit a wall.

    Returns (dx, dz, blocked) where dx/dz are the (possibly reverted)
    deltas already applied to body.x/body.z, and blocked is True if the
    climb was rejected.
    """
    moveDist = math.sqrt(dx * dx + dz * dz)
    if moveDist <= 1e-4:
        return dx, dz, False

    prevGroundY = getattr(body, 'groundY', body.y)
    climbHeight = targetY - prevGroundY
    if climbHeight <= _MAX_CLIMB_ANGLE_MIN_HEIGHT:
        return dx, dz, False

    climbAngle = math.atan2(climbHeight, moveDist)
    if climbAngle <= _MAX_CLIMB_ANGLE:
        return dx, dz, False

    # Too steep to climb - revert this tick's horizontal movement and
    # stop the vehicle, as if it had run into a solid wall.
    body.x -= dx
    body.z -= dz
    body.currentSpeed = 0.0
    return 0.0, 0.0, True


def _update_speed_smoothing(body, dt):
    if body.forward > 0:
        targetSpeed = body.fwdSpeed
    elif body.forward < 0:
        targetSpeed = -body.bckwdSpeed
    else:
        targetSpeed = 0.0

    cur = body.currentSpeed
    accelerating = (
        (targetSpeed >= 0.0 and cur >= 0.0 and targetSpeed >= cur) or
        (targetSpeed <= 0.0 and cur <= 0.0 and targetSpeed <= cur)
    )
    if accelerating:
        rate = _FORWARD_ACCEL if targetSpeed >= 0.0 else _BACKWARD_ACCEL
    else:
        rate = _FORWARD_DECEL

    step = rate * dt
    if targetSpeed > cur:
        body.currentSpeed = min(targetSpeed, cur + step)
    elif targetSpeed < cur:
        body.currentSpeed = max(targetSpeed, cur - step)

    if _ROTATION_ACCEL <= 0.0:
        body.currentRotationSpeed = body.rotation * body.rotationSpeed
    else:
        targetRotSpeed = body.rotation * body.rotationSpeed
        curRot = body.currentRotationSpeed
        rotStep = _ROTATION_ACCEL * dt
        if targetRotSpeed > curRot:
            body.currentRotationSpeed = min(targetRotSpeed, curRot + rotStep)
        elif targetRotSpeed < curRot:
            body.currentRotationSpeed = max(targetRotSpeed, curRot - rotStep)


def _update_track_scroll(body, dt):
    linearSpeed = body.currentSpeed
    angularSpeed = body.currentRotationSpeed
    vLeft = linearSpeed + angularSpeed * body.halfTrackBase
    vRight = linearSpeed - angularSpeed * body.halfTrackBase

    body.scrollLeft += vLeft * dt * _TRACK_SCROLL_SCALE * _TRACK_SCROLL_DIRECTION
    body.scrollRight += vRight * dt * _TRACK_SCROLL_SCALE * _TRACK_SCROLL_DIRECTION

    wrap = _TRACK_SCROLL_WRAP
    if wrap > 0.0:
        body.scrollLeft = math.fmod(body.scrollLeft, wrap)
        body.scrollRight = math.fmod(body.scrollRight, wrap)


def _get_body_mass(body):
    mass = getattr(body, 'mass', 0.0)
    if mass > 0.0:
        return mass

    mass = 30000.0
    if body.vehicleRef is not None:
        try:
            veh = body.vehicleRef()
        except Exception:
            veh = None
        if veh is not None:
            td = getattr(veh, 'typeDescriptor', None)
            if td is not None:
                try:
                    mass = abs(float(td.physics['weight']))
                except Exception:
                    mass = 30000.0
    body.mass = mass
    return mass


def _is_destructible_broken(chunkID, destrIndex, matKind, destrType):
    if AreaDestructibles is None:
        return False
    key = (chunkID, destrIndex, matKind, destrType)
    if key in _ram_broken:
        return True
    manager = getattr(AreaDestructibles, 'g_destructiblesManager', None)
    if manager is not None:
        try:
            ctrl = manager.getController(chunkID)
            if ctrl is not None and ctrl.isDestructibleBroken(destrIndex, matKind, destrType):
                _ram_broken.add(key)
                return True
        except Exception:
            pass
    return False


def _order_destructible_destroy(manager, spaceID, chunkID, destrIndex, destrType, matKind, fallYaw, speed):
    if DestructiblesCache is None:
        return
    key = (chunkID, destrIndex, matKind, destrType)
    if key in _ram_broken:
        return

    try:
        fallSpeed = int(min(3, max(0, abs(speed) / 5.0)))
    except Exception:
        fallSpeed = 0

    try:
        if destrType == DestructiblesCache.DESTR_TYPE_TREE:
            pitchConstr = math.pi / 2.0
            try:
                res = BigWorld.getDestructibleFallPitchConstr(spaceID, chunkID, destrIndex, fallYaw)
                if res is not None:
                    pitchConstr = float(res[0])
            except Exception:
                pass
            data = DestructiblesCache.encodeFallenTree(destrIndex, fallYaw, pitchConstr, fallSpeed)
            manager.orderDestructibleDestroy(chunkID, destrType, data, True, False)
        elif destrType == DestructiblesCache.DESTR_TYPE_FALLING_ATOM:
            data = DestructiblesCache.encodeFallenColumn(destrIndex, fallYaw, fallSpeed)
            manager.orderDestructibleDestroy(chunkID, destrType, data, True, False)
        elif destrType == DestructiblesCache.DESTR_TYPE_FRAGILE:
            data = DestructiblesCache.encodeFragile(destrIndex, False)
            manager.orderDestructibleDestroy(chunkID, destrType, data, True, False)
        elif destrType == DestructiblesCache.DESTR_TYPE_STRUCTURE:
            data = DestructiblesCache.encodeDestructibleModule(destrIndex, matKind, False)
            manager.orderDestructibleDestroy(chunkID, destrType, data, True, False)
        else:
            data = DestructiblesCache.encodeFragile(destrIndex, False)
            manager.orderDestructibleDestroy(chunkID, destrType, data, True, False)
        _ram_broken.add(key)
        _ram_broken.add(key)
    except Exception:
        pass


def _isBushFilename(filename):
    if not filename:
        return False
    try:
        name = str(filename).lower()
    except Exception:
        try:
            name = unicode(filename).lower()
        except Exception:
            return False
    for marker in _BUSH_FILENAME_MARKERS:
        if marker in name:
            return True
    return False

def _update_destructible_ramming(body, spaceID, dt, dx, dz):
    if BigWorld is None or AreaDestructibles is None or DestructiblesCache is None:
        return

    manager = getattr(AreaDestructibles, 'g_destructiblesManager', None)
    cache = getattr(AreaDestructibles, 'g_cache', None)
    if manager is None or cache is None:
        return

    speed = abs(body.currentSpeed)
    if speed < _RAM_MIN_SPEED:
        return

    now = BigWorld.time()
    nextCheck = getattr(body, 'ramDestructibleCheckTime', 0.0)
    if now < nextCheck:
        return
    body.ramDestructibleCheckTime = now + _RAM_DESTRUCTIBLE_CHECK_INTERVAL

    try:
        gridX, gridZ = DestructiblesCache.chunkIndexesFromPosition((body.x, body.y, body.z))
    except Exception:
        return

    if dx != 0.0 or dz != 0.0:
        moveYaw = math.atan2(dx, dz)
    else:
        moveYaw = body.yaw

    mass = _get_body_mass(body)
    if mass <= 0.0:
        return

    instantDamage = 0.5 * mass * speed * speed * 0.00015
    if instantDamage <= 0.0:
        return

    unitMass = getattr(cache, 'unitVehicleMass', 0.0)
    if unitMass <= 0.0:
        unitMass = 30000.0

    radius = max(body.halfLength, body.halfWidth) + _RAM_OBJECT_RADIUS
    radiusSq = radius * radius

    offsets = set([(0, 0)])
    try:
        localX = body.x - gridX * 100.0
        localZ = body.z - gridZ * 100.0
        border = radius + 5.0

        needNegX = localX < border
        needPosX = localX > 100.0 - border
        needNegZ = localZ < border
        needPosZ = localZ > 100.0 - border

        if needNegX:
            offsets.add((-1, 0))
        if needPosX:
            offsets.add((1, 0))
        if needNegZ:
            offsets.add((0, -1))
        if needPosZ:
            offsets.add((0, 1))

        if needNegX and needNegZ:
            offsets.add((-1, -1))
        if needNegX and needPosZ:
            offsets.add((-1, 1))
        if needPosX and needNegZ:
            offsets.add((1, -1))
        if needPosX and needPosZ:
            offsets.add((1, 1))
    except Exception:
        offsets = set([(0, 0)])

    if not getattr(body, '_chunksRegistered', False):
        try:
            loadedChunks = getattr(manager, '_DestructiblesManager__loadedChunkIDs', None)
            if loadedChunks is None:
                loadedChunks = getattr(manager, 'loadedChunkIDs', None)

            if loadedChunks is not None:
                for offX, offZ in offsets:
                    try:
                        chunkID = DestructiblesCache.chunkIDFromChunkIndexes(gridX + offX, gridZ + offZ)
                    except Exception:
                        continue
                    if chunkID not in loadedChunks:
                        try:
                            manager.onChunkLoad(chunkID, 1024)
                        except Exception:
                            pass

            body._chunksRegistered = True
        except Exception:
            pass

    loadedChunks = getattr(manager, '_DestructiblesManager__loadedChunkIDs', None)
    if loadedChunks is None:
        loadedChunks = getattr(manager, 'loadedChunkIDs', None)

    if not loadedChunks:
        return

    chunkMatrixCache = {}

    for offX, offZ in offsets:
        try:
            chunkID = DestructiblesCache.chunkIDFromChunkIndexes(gridX + offX, gridZ + offZ)
        except Exception:
            continue

        numDestructibles = loadedChunks.get(chunkID)
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

        for destrIndex in range(numDestructibles):
            try:
                filename = BigWorld.getDestructibleFilename(spaceID, chunkID, destrIndex)
            except Exception:
                continue

            if not filename:
                continue

            if _isBushFilename(filename):
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
            distSq = (pos.x - body.x) * (pos.x - body.x) + (pos.z - body.z) * (pos.z - body.z)
            if distSq > radiusSq:
                continue

            try:
                itemScale = destrMatrix.applyVector((0.0, 1.0, 0.0)).length
            except Exception:
                itemScale = 1.0

            if itemScale <= 0.0:
                itemScale = 1.0

            if destrType == DestructiblesCache.DESTR_TYPE_STRUCTURE:
                modules = desc.get('modules', {})
                for matKind, moduleDesc in modules.items():
                    if _is_destructible_broken(chunkID, destrIndex, matKind, destrType):
                        continue

                    refHealth = moduleDesc.get('health', 0)
                    if refHealth <= 0:
                        continue

                    if DestructiblesCache.scaledDestructibleHealth(itemScale, refHealth) >= instantDamage:
                        continue

                    _order_destructible_destroy(manager, spaceID, chunkID, destrIndex, destrType, matKind, moveYaw, speed)
            else:
                if _is_destructible_broken(chunkID, destrIndex, 0, destrType):
                    continue

                refHealth = desc.get('health', 0)
                if refHealth <= 0:
                    continue

                damage = instantDamage
                corr = desc.get('kineticDamageCorrection', 0.0)
                if corr:
                    try:
                        damage *= math.pow(mass / unitMass, corr)
                    except Exception:
                        pass

                if DestructiblesCache.scaledDestructibleHealth(itemScale, refHealth) >= damage:
                    continue

                _order_destructible_destroy(manager, spaceID, chunkID, destrIndex, destrType, 0, moveYaw, speed)

_scroll = {}

def driveWheels(vehicle, appearance, wheels, cache, left, right, rotationSpeed):
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

def trackScroll(vehicle, speed, rotationSpeed, halfWidth):
    appearance = getattr(vehicle, 'appearance', None)
    if appearance is None:
        return False
    update = getattr(appearance, 'updateTracksScroll', None)
    if update is None:
        return False
    turn = rotationSpeed * halfWidth
    left, right = speed - turn, speed + turn
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
    cache = _scroll.get(vehicle.id)
    if cache is None:
        cache = _scroll[vehicle.id] = {
            'vals': None,
            'mode': None,
            'linked': None,
        }
    try:
        wheels = None
        try:
            if getattr(appearance.typeDescriptor, 'isWheeledVehicle', False):
                wheels = getattr(appearance, 'wheelsAnimator', None)
        except Exception:
            wheels = None
        if wheels is not None:
            driveWheels(vehicle, appearance, wheels, cache, left, right, rotationSpeed)
        elif cache['vals'] != (left, right):
            update(left, right)
            cache['vals'] = (left, right)
        if cache['mode'] != mode:
            appearance.changeEngineMode(mode)
            cache['mode'] = mode
        return True
    except Exception:
        _scroll.pop(vehicle.id, None)
        return False

def _apply(body):
    if Math is None:
        return
    if body.vehicleRef is not None:
        veh = body.vehicleRef()
        if veh is None or not getattr(veh, 'isStarted', False):
            return
        try:
            if not veh.isAlive():
                m = Math.Matrix()
                try:
                    m.setRotateYPR((body.yaw, body.pitch, body.roll))
                except Exception:
                    pass
                m.translation = Math.Vector3(body.x, body.y, body.z)
                if body.mProv is not None:
                    try:
                        body.mProv.target = None
                        body.mProv.setStaticTransform(m)
                    except Exception:
                        pass
                return
        except Exception:
            return

    m = Math.Matrix()
    try:
        m.setRotateYPR((body.yaw, body.pitch, body.roll))
    except Exception:
        pass
    m.translation = Math.Vector3(body.x, body.y, body.z)

    if body.mProv is not None:
        try:
            body.mProv.target = None
            body.mProv.setStaticTransform(m)
        except Exception:
            pass

    player = BigWorld.player() if BigWorld is not None else None
    if player is not None and getattr(player, 'playerVehicleID', 0) == body.id:
        try:
            if getattr(player, 'filter', None) is not None and not getattr(player.filter, 'ignoreInputs', False):
                player.filter.ignoreInputs = True
        except Exception:
            pass
        try:
            player.position = Math.Vector3(body.x, body.y, body.z)
            player.direction = Math.Vector3(math.sin(body.yaw), 0.0, math.cos(body.yaw))
        except Exception:
            pass
        try:
            import BWReplay
            BWReplay.injectNonVolatileUpdate(
                player.id,
                body.id,
                Math.Vector3(body.x, body.y, body.z),
                (body.yaw, 0.0, 0.0)
            )
        except Exception:
            pass
        for attr in ('_PlayerAvatar__ownVehicleStabMProv', '_PlayerAvatar__ownVehicleTurretMProv', '_PlayerAvatar__ownVehicleMProv'):
            prov = getattr(player, attr, None)
            if prov is not None:
                try:
                    prov.target = None
                    prov.setStaticTransform(m)
                except Exception:
                    pass
        cm = getattr(player, '_PlayerAvatar__consistentMatrices', None)
        if cm is not None:
            attachedProv = getattr(cm, '_ConsistentMatrices__attachedVehicleMatrix', None)
            if attachedProv is None:
                attachedProv = getattr(cm, 'attachedVehicleMatrix', None)
            if attachedProv is not None:
                try:
                    attachedProv.target = None
                    attachedProv.setStaticTransform(m)
                except Exception:
                    pass

    if body.vehicleRef is not None:
        veh = body.vehicleRef()
        if veh is not None:
            vDir = Math.Vector3(math.sin(body.yaw), 0.0, math.cos(body.yaw))
            try:
                veh.position = pos
            except Exception:
                pass
            try:
                veh.direction = vDir
            except Exception:
                pass
            try:
                if body.mProv is not None:
                    veh.matrix = body.mProv
                else:
                    veh.matrix = m
            except Exception:
                pass
            vFlt = getattr(veh, 'filter', None)
            if vFlt is not None:
                try:
                    vFlt.position = pos
                    vFlt.direction = vDir
                except Exception:
                    pass
                try:
                    vFlt.setPosDir(pos, vDir, 0.0)
                except Exception:
                    pass
                try:
                    vFlt.bodyMatrix = m
                except Exception:
                    pass
            appearance_obj = getattr(veh, 'appearance', None)
            if appearance_obj is not None:
                compoundModel = getattr(appearance_obj, 'compoundModel', None)
                if compoundModel is not None:
                    try:
                        if body.mProv is not None:
                            compoundModel.matrix = body.mProv
                        else:
                            compoundModel.matrix = m
                    except Exception:
                        pass
                aFlt = getattr(appearance_obj, 'filter', None)
                if aFlt is not None:
                    try:
                        aFlt.position = pos
                        aFlt.direction = vDir
                    except Exception:
                        pass
                    try:
                        aFlt.bodyMatrix = m
                    except Exception:
                        pass
                speed = float(body.currentSpeed)
                rotSpeed = float(body.currentRotationSpeed)
                trackScroll(veh, speed, rotSpeed, body.halfTrackBase)
                engineState = getattr(appearance_obj, 'detailedEngineState', None)
                if engineState is not None:
                    try:
                        engineState.throttle = 1.0 if (body.forward or body.rotation) else 0.0
                    except Exception:
                        pass

            appearance_obj = getattr(veh, 'appearance', None)
            model = getattr(veh, 'model', None)
            if model is not None:
                try:
                    model.matrix = m
                except Exception:
                    try:
                        model.matrix(m)
                    except Exception:
                        pass

            if appearance_obj is not None:
                compoundModel = getattr(appearance_obj, 'compoundModel', None)
                if compoundModel is not None:
                    try:
                        compoundModel.matrix = m
                    except Exception:
                        try:
                            compoundModel.matrix(m)
                        except Exception:
                            pass

                moving = body.forward != 0 or body.rotation != 0
                speed = float(body.currentSpeed)
                rotSpeed = float(body.currentRotationSpeed)
                if body.fwdSpeed > 0.01:
                    speedRatio = min(1.0, abs(speed) / body.fwdSpeed)
                else:
                    speedRatio = 0.0
                targetRpmRel = 0.18 + speedRatio * 0.82
                if body.rotation and abs(speed) < 0.5:
                    targetRpmRel = min(1.0, targetRpmRel + 0.35)
                rpm = targetRpmRel * 100.0

                leftScroll = float(body.scrollLeft)
                rightScroll = float(body.scrollRight)

                flt = getattr(appearance_obj, 'filter', None)
                if flt is not None:
                    # leftTrackScroll/rightTrackScroll сюда больше не пишем напрямую -
                    # этим теперь занимается _drive_track_visuals ниже (тот же путь,
                    # что и у ботов: trackScrollController.setExternal/changeEngineMode).
                    for attrName, value in (
                        ('averageSpeed', speed),
                        ('averageRotationSpeed', rotSpeed),
                        ('angularSpeed', rotSpeed),
                        ('strafeSpeed', 0.0),
                        ('velocity', Math.Vector3(math.sin(body.yaw) * speed, 0.0, math.cos(body.yaw) * speed)),
                    ):
                        try:
                            setattr(flt, attrName, value)
                        except Exception:
                            pass

                detailedEngineState = getattr(appearance_obj, 'detailedEngineState', None)
                if detailedEngineState is not None:
                    try:
                        detailedEngineState.vehicleSpeedLink = lambda: speed
                        detailedEngineState.rotationSpeedLink = lambda: rotSpeed
                    except Exception:
                        pass
                    try:
                        detailedEngineState.physicRPMLink = lambda: rpm
                        detailedEngineState.physicGearLink = lambda: 1 if moving else 0
                    except Exception:
                        pass
                    try:
                        detailedEngineState.throttle = 1.0 if moving else 0.0
                        detailedEngineState.engineStarted = True
                        detailedEngineState.mode = body.forward
                    except Exception:
                        pass

                engineAudition = getattr(appearance_obj, 'engineAudition', None)
                if engineAudition is not None:
                    try:
                        engineAudition.setSpeedInfo(lambda: rotSpeed, lambda: 0.0)
                        engineAudition.setTracksInfo(lambda: leftScroll, lambda: 0.0, lambda: 0.0, lambda: False)
                    except Exception:
                        pass

                # Единая анимация гусениц/колёс - та же логика, что и у ботов
                # (activate/setData/setExternal + changeEngineMode), теперь
                # применяется и к машине игрока.
                _drive_track_visuals(body, veh, appearance_obj, speed, rotSpeed, body.halfTrackBase)

                updateTracksScroll = getattr(appearance_obj, 'updateTracksScroll', None)
                if updateTracksScroll is not None and getattr(appearance_obj, 'trackScrollController', None) is None:
                    # Фолбэк на случай, если trackScrollController недоступен и
                    # _drive_track_visuals ушла по ветке updateTracksScroll -
                    # оставлено для совместимости со старыми путями анимации.
                    try:
                        updateTracksScroll(leftScroll, rightScroll)
                    except Exception:
                        pass

_last_chunk_check = [0.0]

def _tick():
    global _tickCallbackID
    dt = _TICK_PERIOD
    try:
        player = BigWorld.player() if BigWorld is not None else None
        spaceID = getattr(player, 'spaceID', None) if player is not None else None

        if player is not None and getattr(player, 'isOffline', False) and world.controlled_body_id:
            controlled = world.bodies.get(world.controlled_body_id)
            if controlled is not None:
                forward = 0
                rotation = 0
                try:
                    import CommandMapping
                    cmdMap = CommandMapping.g_instance
                    fwdSpec = getattr(CommandMapping, 'CMD_MOVE_FORWARD_SPEC', CommandMapping.CMD_MOVE_FORWARD)
                    if cmdMap.isActive(CommandMapping.CMD_MOVE_FORWARD) or cmdMap.isActive(fwdSpec):
                        forward = 1
                    elif cmdMap.isActive(CommandMapping.CMD_MOVE_BACKWARD):
                        forward = -1
                    if cmdMap.isActive(CommandMapping.CMD_ROTATE_LEFT):
                        rotation = -1
                    elif cmdMap.isActive(CommandMapping.CMD_ROTATE_RIGHT):
                        rotation = 1
                except Exception:
                    pass

                if forward == 0 and rotation == 0:
                    try:
                        import Keys
                        if BigWorld.isKeyDown(Keys.KEY_W):
                            forward += 1
                        if BigWorld.isKeyDown(Keys.KEY_S):
                            forward -= 1
                        if BigWorld.isKeyDown(Keys.KEY_A):
                            rotation -= 1
                        if BigWorld.isKeyDown(Keys.KEY_D):
                            rotation += 1
                        if forward > 1:
                            forward = 1
                        if forward < -1:
                            forward = -1
                        if rotation > 1:
                            rotation = 1
                        if rotation < -1:
                            rotation = -1
                    except Exception:
                        pass

                controlled.forward = forward
                controlled.rotation = rotation

        for body in list(world.bodies.values()):
            isDead = False
            if body.vehicleRef is not None:
                veh = body.vehicleRef()
                if veh is None:
                    world.bodies.pop(body.id, None)
                    continue
                try:
                    if getattr(veh, 'isStarted', False) and not veh.isAlive():
                        isDead = True
                except Exception:
                    isDead = False

            if isDead:
                body.forward = 0
                body.rotation = 0
                body.currentSpeed = 0.0
                body.currentRotationSpeed = 0.0
                if spaceID is not None:
                    fallbackY = getattr(body, 'groundY', body.y)
                    groundY = _get_ground_height(spaceID, body.x, body.z, fallbackY, body.id)
                    if groundY is None:
                        groundY = fallbackY
                    if body.y > groundY + _GROUND_SNAP_UP_TOLERANCE:
                        body.isGrounded = False
                        body.vy -= _GRAVITY * dt
                        if body.vy < -_MAX_FALL_SPEED:
                            body.vy = -_MAX_FALL_SPEED
                        body.y += body.vy * dt
                        if body.y <= groundY:
                            body.y = groundY
                            body.vy = 0.0
                            body.isGrounded = True
                    else:
                        body.isGrounded = True
                        body.vy = 0.0
                        body.y = groundY
                    body.groundY = groundY
                _apply(body)
                continue

            _update_speed_smoothing(body, dt)

            if body.currentRotationSpeed:
                body.yaw += body.currentRotationSpeed * dt

            dx = 0.0
            dz = 0.0
            if abs(body.currentSpeed) > 1e-4:
                dx = math.sin(body.yaw) * body.currentSpeed * dt
                dz = math.cos(body.yaw) * body.currentSpeed * dt
                if spaceID is not None:
                    dx, dz = _resolve_horizontal_collision(spaceID, body, dx, dz)
                body.x += dx
                body.z += dz

            if spaceID is not None:
                targetY, targetPitch, targetRoll = _sample_corners_and_tilt(spaceID, body, dt)
                if not hasattr(body, 'groundY'):
                    body.groundY = targetY

                dx, dz, climbBlocked = _limit_climb_angle(body, dx, dz, targetY)
                if climbBlocked:
                    targetY, targetPitch, targetRoll = _sample_corners_and_tilt(spaceID, body, dt)

                _update_destructible_ramming(body, spaceID, dt, dx, dz)

                if body.y > targetY + _GROUND_SNAP_UP_TOLERANCE:
                    body.isGrounded = False
                    body.vy -= _GRAVITY * dt
                    if body.vy < -_MAX_FALL_SPEED:
                        body.vy = -_MAX_FALL_SPEED
                    body.y += body.vy * dt
                    if body.y <= targetY:
                        body.y = targetY
                        body.vy = 0.0
                        body.isGrounded = True
                else:
                    body.isGrounded = True
                    body.vy = 0.0
                    heightError = targetY - body.y
                    if abs(heightError) > _GROUND_SNAP_DISTANCE:
                        body.y = targetY
                    else:
                        rate = _HEIGHT_SMOOTH_RATE if heightError >= 0.0 else _HEIGHT_DOWN_SMOOTH_RATE
                        body.y += heightError * min(1.0, dt * rate)

                pitchError = targetPitch - body.pitch
                rollError = targetRoll - body.roll
                if abs(pitchError) > _TILT_SNAP_DISTANCE:
                    body.pitch = targetPitch
                else:
                    body.pitch += pitchError * min(1.0, dt * _TILT_SMOOTH_RATE)

                if abs(rollError) > _TILT_SNAP_DISTANCE:
                    body.roll = targetRoll
                else:
                    body.roll += rollError * min(1.0, dt * _TILT_SMOOTH_RATE)

                body.groundY = targetY

            _update_track_scroll(body, dt)
            _apply(body)

    except Exception:
        _crash_log('tick OUTER FAILED')
        import traceback
        _crash_log(traceback.format_exc())

    if BigWorld is not None:
        try:
            _tickCallbackID = BigWorld.callback(dt, _tick)
        except Exception:
            _tickCallbackID = None