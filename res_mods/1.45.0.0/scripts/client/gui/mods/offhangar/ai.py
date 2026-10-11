import math
import random
import BigWorld
import Math
import gui.mods.offhangar.physics as offhangar_physics
import gui.mods.offhangar.shooting as offhangar_shooting
from vehicle_systems.tankStructure import TankPartNames

_brains = {}
_tick_id = None
_ai_dt = 0.25
_DEFAULT_DAMAGE = 250.0
_DEFAULT_RELOAD = 3.5
_DEFAULT_TURRET_SPEED = 0.35
_DEFAULT_GUN_SPEED = 0.35
_DEFAULT_PITCH_LIMITS = (-0.10, 0.35)
_DEFAULT_MAX_RANGE = 600.0
_STUCK_CHECK_INTERVAL = 1.5
_STUCK_MOVE_THRESHOLD = 1.0
_FRONT_PROBE_DIST = 10.0
_SIDE_PROBE_DIST = 6.0
_SIDE_PROBE_ANGLE = math.pi / 2.0
_TARGET_CHECK_INTERVAL = 0.5
_AIM_TOLERANCE = 0.08
try:
    import gui.mods.offhangar.armour as offhangar_armour
except Exception:
    offhangar_armour = None

def _getShellFromIntCD_safe(vehicle):
    try:
        td = getattr(vehicle, 'typeDescriptor', None)
        if td is not None:
            return getattr(td, 'shot', None) and td.shot.shell
    except Exception:
        pass
    return None

def _getShellShot_safe(vehicle):
    try:
        td = getattr(vehicle, 'typeDescriptor', None)
        if td is not None:
            return getattr(td, 'shot', None)
    except Exception:
        pass
    return None

def _get_static_hit_distance(spaceID, start, end, excludeId):
    if BigWorld is None or Math is None or spaceID is None:
        return None
    staticFunc = getattr(BigWorld, 'collideStatic', None)
    if callable(staticFunc):
        for args in ((spaceID, start, end, 1, excludeId), (spaceID, start, end, 1), (spaceID, start, end)):
            try:
                hit = staticFunc(*args)
            except Exception:
                hit = None
            if hit is not None:
                try:
                    p = Math.Vector3(hit[0])
                except Exception:
                    continue
                d = (p - start).length
                if d > 0.01:
                    return d
    try:
        hit = BigWorld.collideDynamicStatic(spaceID, start, end, 1, excludeId, -1, 0)
    except Exception:
        hit = None
    if hit is None:
        return None
    try:
        p = Math.Vector3(hit[0])
    except Exception:
        return None
    d = (p - start).length
    if d <= 0.01:
        return None
    return d


def _get_sphere_hit_distance(start, end, pos, radius):
    try:
        ray = end - start
        rayLen = ray.length
        if rayLen < 0.1:
            return None
        ray.normalise()
        to = pos - start
        proj = to.x * ray.x + to.y * ray.y + to.z * ray.z
        if proj < 0.0 or proj > rayLen:
            return None
        closest = start + ray.scale(proj)
        distToRay = (closest - pos).length
        if distToRay > radius:
            return None
        offset = math.sqrt(max(0.0, radius * radius - distToRay * distToRay))
        return max(0.0, proj - offset)
    except Exception:
        return None


def _get_entity_hit_distance(entity, start, end):
    if entity is None:
        return None
    try:
        hits = entity.collideSegmentExt(start, end)
    except Exception:
        hits = None
    if hits:
        best = None
        try:
            for hit in hits:
                d = getattr(hit, 'dist', None)
                if d is None:
                    try:
                        d = (Math.Vector3(hit[0]) - start).length
                    except Exception:
                        continue
                else:
                    try:
                        d = float(d)
                    except Exception:
                        d = None
                if d is None:
                    continue
                if best is None or d < best:
                    best = d
        except Exception:
            best = None
        if best is not None:
            return best
    try:
        pos = None
        try:
            pos = Math.Matrix(entity.matrix).translation
        except Exception:
            pos = None
        if pos is None or pos.length < 0.1:
            try:
                pos = Math.Vector3(entity.position)
            except Exception:
                pos = None
        if pos is None or pos.length < 0.1:
            return None
        radius = 3.0
        try:
            body = offhangar_physics.world.get_body(getattr(entity, 'id', 0))
            if body is not None:
                radius = max(float(getattr(body, 'halfLength', 3.0)), float(getattr(body, 'halfWidth', 2.0))) + 0.8
        except Exception:
            radius = 3.0
        return _get_sphere_hit_distance(start, end, pos, radius)
    except Exception:
        return None


def _collide_static_only(spaceID, start, end, excludeId):
    if BigWorld is None or Math is None or spaceID is None:
        return None
    staticFunc = getattr(BigWorld, 'collideStatic', None)
    if callable(staticFunc):
        for args in ((spaceID, start, end, 1, excludeId), (spaceID, start, end, 1), (spaceID, start, end)):
            try:
                hit = staticFunc(*args)
            except Exception:
                hit = None
            if hit is not None:
                return hit
    try:
        return BigWorld.collideDynamicStatic(spaceID, start, end, 1, excludeId, -1, 0)
    except Exception:
        return None


def _get_arena():
    player = BigWorld.player()
    if not player:
        return None
    return getattr(player, 'arena', None)


def _get_arena_vehicle_info(entity_id):
    arena = _get_arena()
    if arena is None:
        return None
    try:
        return getattr(arena, 'vehicles', {}).get(entity_id)
    except Exception:
        return None


def _entity_health(entity):
    try:
        return float(getattr(entity, 'health', 0.0))
    except Exception:
        return 0.0


def _is_entity_alive(entity_id):
    veh = BigWorld.entity(entity_id)
    if veh is None:
        return False
    vinfo = _get_arena_vehicle_info(entity_id)
    if vinfo is not None:
        try:
            return bool(vinfo.get('isAlive', True))
        except Exception:
            return True
    health = getattr(veh, 'health', None)
    if health is not None:
        try:
            return float(health) > 0.0
        except Exception:
            pass
    return getattr(veh, 'isStarted', False) or hasattr(veh, 'typeDescriptor')


def _readVehicleStats(descr):
    stats = {
        'damage': _DEFAULT_DAMAGE,
        'reload_time': _DEFAULT_RELOAD,
        'turret_speed': _DEFAULT_TURRET_SPEED,
        'gun_speed': _DEFAULT_GUN_SPEED,
        'pitch_limits': _DEFAULT_PITCH_LIMITS,
        'yaw_limits': None,
        'max_range': _DEFAULT_MAX_RANGE,
    }
    if descr is None:
        return stats
    gun = getattr(descr, 'gun', None)
    turret = getattr(descr, 'turret', None)
    for owner, attr in ((gun, 'reloadTime'), (gun, 'reloadTimeSecs'), (descr, 'reloadTime')):
        try:
            v = getattr(owner, attr, None)
            if v:
                stats['reload_time'] = max(0.5, float(v))
                break
        except Exception:
            pass
    try:
        shots = getattr(gun, 'shots', None) or getattr(gun, 'defaultShots', None)
        if shots:
            shot = shots[0]
            shell = getattr(shot, 'shell', shot)
            dmg = getattr(shell, 'damage', None)
            if dmg is not None:
                if isinstance(dmg, dict):
                    stats['damage'] = float(dmg.get('armor', dmg.get('vehicleDamage', _DEFAULT_DAMAGE)))
                elif isinstance(dmg, (tuple, list)):
                    vals = [float(v) for v in list(dmg)[:2]]
                    if vals:
                        stats['damage'] = sum(vals) / len(vals)
                elif hasattr(dmg, '__getitem__'):
                    try:
                        vals = [float(v) for v in list(dmg)[:2]]
                        if vals:
                            stats['damage'] = sum(vals) / len(vals)
                    except Exception:
                        pass
                else:
                    stats['damage'] = float(dmg)
    except Exception:
        pass
    for owner in (turret, gun):
        try:
            raw = getattr(owner, 'rotationSpeed', None)
            if raw:
                raw = float(raw)
                stats['turret_speed'] = math.radians(raw) if raw > 3.5 else raw
                break
        except Exception:
            pass
    try:
        rawGunSpeed = getattr(gun, 'pitchRotationSpeed', None) or getattr(gun, 'verticalRotationSpeed', None)
        if rawGunSpeed:
            rawGunSpeed = float(rawGunSpeed)
            stats['gun_speed'] = math.radians(rawGunSpeed) if rawGunSpeed > 3.5 else rawGunSpeed
    except Exception:
        pass
    try:
        pitchLimits = getattr(gun, 'pitchLimits', None)
        if pitchLimits:
            seq = pitchLimits
            if isinstance(pitchLimits, dict):
                seq = pitchLimits.get('absolute') or pitchLimits.get('default')
                if seq is None:
                    vals = list(pitchLimits.values())
                    seq = vals[0] if vals else _DEFAULT_PITCH_LIMITS
            lo, hi = float(seq[0]), float(seq[-1])
            if abs(lo) > 3.5 or abs(hi) > 3.5:
                lo, hi = math.radians(lo), math.radians(hi)
            stats['pitch_limits'] = (-abs(lo), abs(hi))
    except Exception:
        pass
    try:
        is360 = getattr(turret, 'rotationIsAround', True)
        yawLimits = getattr(turret, 'yawLimits', None) or getattr(gun, 'turretYawLimits', None)
        if not is360 and yawLimits:
            lo, hi = float(yawLimits[0]), float(yawLimits[-1])
            if abs(lo) > 3.5 or abs(hi) > 3.5:
                lo, hi = math.radians(lo), math.radians(hi)
            stats['yaw_limits'] = (lo, hi)
    except Exception:
        pass
    try:
        cvr = getattr(turret, 'circularVisionRadius', None) or getattr(descr, 'maxLodDist', None)
        if cvr:
            stats['max_range'] = min(float(cvr), 650.0)
    except Exception:
        pass
    return stats


def _get_body_pos(entity_id):
    body = offhangar_physics.world.get_body(entity_id)
    if body is not None:
        return Math.Vector3(body.x, body.y, body.z)
    veh = BigWorld.entity(entity_id)
    if veh is not None:
        try:
            p = Math.Vector3(veh.position)
            if p.length > 0.1:
                return p
        except Exception:
            pass
        try:
            m = Math.Matrix(veh.matrix)
            if m.translation.length > 0.1:
                return m.translation
        except Exception:
            pass
    return None


def _get_body_pos_yaw(entity_id):
    body = offhangar_physics.world.get_body(entity_id)
    if body is not None:
        return Math.Vector3(body.x, body.y, body.z), body.yaw
    veh = BigWorld.entity(entity_id)
    if veh is not None:
        try:
            p = Math.Vector3(veh.position)
            if p.length > 0.1:
                return p, 0.0
        except Exception:
            pass
        try:
            m = Math.Matrix(veh.matrix)
            if m.translation.length > 0.1:
                return m.translation, m.yaw
        except Exception:
            pass
    return None, 0.0


class BotBrain(object):
    def __init__(self, bot_id, team, descr=None):
        self.bot_id = bot_id
        self.team = team
        self.target_id = None
        self.last_shot_time = 0.0
        self.descr = descr
        stats = _readVehicleStats(descr)
        self.damage = stats['damage']
        self.reload_time = stats['reload_time']
        self.turret_speed = stats['turret_speed']
        self.gun_speed = stats['gun_speed']
        self.pitch_limits = stats['pitch_limits']
        self.yaw_limits = stats['yaw_limits']
        self.max_range = stats['max_range']
        self.turret_yaw = 0.0
        self.gun_pitch = 0.0
        self._stuck_check_pos = None
        self._stuck_check_time = 0.0
        self._unstuck_until = 0.0
        self._unstuck_dir = 1
        self._next_target_check = 0.0
        self._last_target_pos = None

    def get_pos(self):
        return _get_body_pos_yaw(self.bot_id)

    @staticmethod
    def _angleDiff(a, b):
        d = b - a
        while d > math.pi:
            d -= 2.0 * math.pi
        while d < -math.pi:
            d += 2.0 * math.pi
        return d

    def _getPlayerVehicleID(self):
        player = BigWorld.player()
        if not player:
            return None
        return getattr(player, 'playerVehicleID', None)

    def find_target(self):
        my_pos, _ = self.get_pos()
        if not my_pos:
            return None
        candidates = set()
        arena = _get_arena()
        if arena is not None:
            try:
                vehicles = getattr(arena, 'vehicles', {})
                for vid, vinfo in vehicles.items():
                    if vid == self.bot_id:
                        continue
                    if not vinfo.get('isAlive', False):
                        continue
                    if vinfo.get('team', 0) == self.team:
                        continue
                    candidates.add(vid)
            except Exception:
                pass
        for bid, brain in _brains.items():
            if bid == self.bot_id:
                continue
            if getattr(brain, 'team', 0) == self.team:
                continue
            candidates.add(bid)
        pvid = self._getPlayerVehicleID()
        if pvid is not None and pvid != self.bot_id and pvid not in _brains:
            add_player = True
            if arena is not None:
                try:
                    vinfo = getattr(arena, 'vehicles', {}).get(pvid)
                    if vinfo is not None and vinfo.get('team', 0) == self.team:
                        add_player = False
                except Exception:
                    pass
            if add_player:
                candidates.add(pvid)
        if not candidates:
            try:
                for eid, ent in BigWorld.entities().items():
                    if eid == self.bot_id:
                        continue
                    health = _entity_health(ent)
                    if health <= 0.0 and not getattr(ent, 'isStarted', False):
                        continue
                    team = getattr(ent, 'team', None)
                    if team is not None and team == self.team:
                        continue
                    if arena is not None:
                        try:
                            vinfo = getattr(arena, 'vehicles', {}).get(eid)
                            if vinfo is not None:
                                if not vinfo.get('isAlive', False):
                                    continue
                                if vinfo.get('team', 0) == self.team:
                                    continue
                        except Exception:
                            pass
                    candidates.add(eid)
            except Exception:
                pass
        best_id = None
        best_dist = 99999.0
        for vid in candidates:
            if not _is_entity_alive(vid):
                continue
            t_pos = _get_body_pos(vid)
            if t_pos is None:
                veh = BigWorld.entity(vid)
                if veh is None:
                    continue
                try:
                    t_pos = Math.Matrix(veh.matrix).translation
                except Exception:
                    continue
            if t_pos.length <= 0.1:
                continue
            dist = (t_pos - my_pos).length
            if dist < best_dist:
                best_dist = dist
                best_id = vid
        return best_id

    def _retarget_if_needed(self, now):
        if self.target_id is not None and not self.is_target_alive():
            self.target_id = None
        if self.target_id is None or now >= self._next_target_check:
            self._next_target_check = now + _TARGET_CHECK_INTERVAL
            new_id = self.find_target()
            if new_id is not None:
                self.target_id = new_id

    def _applyGunAngles(self, veh):
        try:
            appearance = getattr(veh, 'appearance', None)
            if appearance is not None:
                turretProv = getattr(appearance, 'turretMatrix', None)
                if turretProv is not None:
                    m = Math.Matrix()
                    m.setRotateY(self.turret_yaw)
                    try:
                        turretProv.target = None
                        turretProv.setStaticTransform(m)
                    except Exception:
                        try:
                            turretProv.set(m)
                        except Exception:
                            pass
                gunProv = getattr(appearance, 'gunMatrix', None)
                if gunProv is not None:
                    m = Math.Matrix()
                    m.setRotateX(self.gun_pitch)
                    try:
                        gunProv.target = None
                        gunProv.setStaticTransform(m)
                    except Exception:
                        try:
                            gunProv.set(m)
                        except Exception:
                            pass
        except Exception:
            pass
        try:
            pitchLimits = (-0.3, 0.3)
            try:
                td_gun = getattr(veh.typeDescriptor, 'gun', None)
                raw = getattr(td_gun, 'pitchLimits', None)
                if raw:
                    if isinstance(raw, dict):
                        seq = raw.get('absolute') or raw.get('default')
                        if seq is None:
                            vals = list(raw.values())
                            seq = vals[0] if vals else pitchLimits
                    else:
                        seq = raw
                    pitchLimits = (float(seq[0]), float(seq[-1]))
            except Exception:
                pass
            import gun_rotation_shared
            packed = gun_rotation_shared.encodeGunAngles(self.turret_yaw, self.gun_pitch, pitchLimits)
            veh.gunAnglesPacked = packed
        except Exception:
            try:
                yaw10 = int(round((self.turret_yaw + math.pi) / (2.0 * math.pi) * 1024)) & 0x3FF
                p_min, p_max = self.pitch_limits
                if p_max > p_min:
                    t = (self.gun_pitch - p_min) / (p_max - p_min)
                    t = max(0.0, min(1.0, t))
                    pitch6 = int(round(63 * t)) & 0x3F
                else:
                    pitch6 = 0
                veh.gunAnglesPacked = (yaw10 << 6) | pitch6
            except Exception:
                pass

    def update(self, now):
        veh = BigWorld.entity(self.bot_id)
        if not veh or not _is_entity_alive(self.bot_id):
            return
        self._retarget_if_needed(now)
        if self.target_id is None:
            self._driveIdle(now)
            return
        target_veh = BigWorld.entity(self.target_id)
        if target_veh is None:
            self.target_id = None
            return
        t_pos = _get_body_pos(self.target_id)
        if t_pos is None:
            try:
                t_pos = Math.Matrix(target_veh.matrix).translation
            except Exception:
                if self._last_target_pos is not None:
                    t_pos = self._last_target_pos
                else:
                    return
        self._last_target_pos = t_pos
        my_pos, my_yaw = self.get_pos()
        if not my_pos:
            return
        dx = t_pos.x - my_pos.x
        dz = t_pos.z - my_pos.z
        dist = math.sqrt(dx * dx + dz * dz)
        if dist < 1.0:
            offhangar_physics.set_control(self.bot_id, forward=0, rotation=0)
            self._aimTurret(veh, my_pos, my_yaw, t_pos, max(1.0, dist))
            return
        angle_to_target = math.atan2(dx, dz)
        self._driveTowards(my_pos, my_yaw, angle_to_target, now, dist)
        self._aimTurret(veh, my_pos, my_yaw, t_pos, dist)
        turret_world_yaw = my_yaw + self.turret_yaw
        aim_diff = abs(self._angleDiff(turret_world_yaw, angle_to_target))
        if aim_diff < _AIM_TOLERANCE and dist <= self.max_range:
            if now - self.last_shot_time > self.reload_time:
                if self.has_line_of_sight(my_pos, t_pos, self.target_id):
                    self.shoot(target_veh)
                    self.last_shot_time = now

    def is_target_alive(self):
        return self.target_id is not None and _is_entity_alive(self.target_id)

    def _driveIdle(self, now):
        my_pos, my_yaw = self.get_pos()
        if self._checkStuck(my_pos, now):
            offhangar_physics.set_control(self.bot_id, forward=-1, rotation=self._unstuck_dir)
            return
        forward = 1
        rotation = 0
        if my_pos:
            scan = self._scanObstacles(my_pos, my_yaw)
            forward, rotation = self._steerFromScan(scan, 1)
        offhangar_physics.set_control(self.bot_id, forward=forward, rotation=rotation)

    def _driveTowards(self, my_pos, my_yaw, angle_to_target, now, dist):
        if self._checkStuck(my_pos, now):
            offhangar_physics.set_control(self.bot_id, forward=-1, rotation=self._unstuck_dir)
            return
        yaw_diff = self._angleDiff(my_yaw, angle_to_target)
        scan = self._scanObstacles(my_pos, my_yaw)
        preferred_rotation = 1 if yaw_diff >= 0 else -1
        forward, rotation = self._steerFromScan(scan, preferred_rotation)
        if not scan['front'] and not scan['left'] and not scan['right']:
            if abs(yaw_diff) > 0.12:
                rotation = 1 if yaw_diff > 0 else -1
                forward = 0 if abs(yaw_diff) > 1.35 else 1
            else:
                rotation = 0
                forward = 1
        if scan['front'] and abs(yaw_diff) > 1.8:
            forward = 0
        if dist < 12.0:
            forward = 0
        elif dist < 25.0 and scan['front']:
            forward = 0
        offhangar_physics.set_control(self.bot_id, forward=forward, rotation=rotation)

    def _checkStuck(self, my_pos, now):
        if my_pos is None:
            return False
        if now < self._unstuck_until:
            return True
        if self._stuck_check_pos is None:
            self._stuck_check_pos = my_pos
            self._stuck_check_time = now
            return False
        if now - self._stuck_check_time > _STUCK_CHECK_INTERVAL:
            moved = (my_pos - self._stuck_check_pos).length
            self._stuck_check_pos = my_pos
            self._stuck_check_time = now
            if moved < _STUCK_MOVE_THRESHOLD:
                self._unstuck_until = now + random.uniform(1.0, 2.0)
                self._unstuck_dir = 1 if random.random() > 0.5 else -1
                return True
        return False

    def _probeRay(self, my_pos, angle, dist):
        player = BigWorld.player()
        if not player:
            return False, dist
        spaceID = getattr(player, 'spaceID', 0)
        if spaceID is None:
            return False, dist
        try:
            dirX = math.sin(angle)
            dirZ = math.cos(angle)
            start = Math.Vector3(my_pos.x, my_pos.y + 1.0, my_pos.z)
            end = Math.Vector3(my_pos.x + dirX * dist, my_pos.y + 1.0, my_pos.z + dirZ * dist)
            hitDist = _get_static_hit_distance(spaceID, start, end, self.bot_id)
            if hitDist is not None and hitDist < dist - 0.35:
                return True, hitDist
        except Exception:
            pass
        return False, dist

    def _scanObstacles(self, my_pos, my_yaw):
        front_blocked, front_dist = self._probeRay(my_pos, my_yaw, _FRONT_PROBE_DIST)
        left_blocked, left_dist = self._probeRay(my_pos, my_yaw - _SIDE_PROBE_ANGLE, _SIDE_PROBE_DIST)
        right_blocked, right_dist = self._probeRay(my_pos, my_yaw + _SIDE_PROBE_ANGLE, _SIDE_PROBE_DIST)
        return {
            'front': front_blocked,
            'front_dist': front_dist,
            'left': left_blocked,
            'left_dist': left_dist,
            'right': right_blocked,
            'right_dist': right_dist,
        }

    def _steerFromScan(self, scan, preferred_rotation):
        forward = 1
        rotation = 0
        if scan['front']:
            if scan['left'] and not scan['right']:
                rotation = 1
            elif scan['right'] and not scan['left']:
                rotation = -1
            else:
                rotation = preferred_rotation
            forward = 0 if scan['front_dist'] < 5.0 else 1
        elif scan['left'] and not scan['right']:
            rotation = 1
        elif scan['right'] and not scan['left']:
            rotation = -1
        return forward, rotation

    def _aimTurret(self, veh, my_pos, my_yaw, t_pos, dist):
        angle_to_target = math.atan2(t_pos.x - my_pos.x, t_pos.z - my_pos.z)
        desired_local_yaw = self._angleDiff(my_yaw, angle_to_target)
        if self.yaw_limits is not None:
            lo, hi = self.yaw_limits
            desired_local_yaw = max(lo, min(hi, desired_local_yaw))
        yaw_step = max(0.001, self.turret_speed * _ai_dt)
        yaw_delta = self._angleDiff(self.turret_yaw, desired_local_yaw)
        if abs(yaw_delta) <= yaw_step:
            self.turret_yaw = desired_local_yaw
        else:
            self.turret_yaw += yaw_step if yaw_delta > 0 else -yaw_step
        dy = t_pos.y - (my_pos.y + 2.0)
        horiz = max(1.0, dist)
        desired_pitch = -math.atan2(dy, horiz)
        lo, hi = self.pitch_limits
        desired_pitch = max(lo, min(hi, desired_pitch))
        pitch_step = max(0.001, self.gun_speed * _ai_dt)
        pitch_delta = desired_pitch - self.gun_pitch
        if abs(pitch_delta) <= pitch_step:
            self.gun_pitch = desired_pitch
        else:
            self.gun_pitch += pitch_step if pitch_delta > 0 else -pitch_step
        self._applyGunAngles(veh)

    def has_line_of_sight(self, start, end, targetID=None):
        player = BigWorld.player()
        if not player:
            return False
        spaceID = getattr(player, 'spaceID', 0)
        if spaceID is None:
            return False
        try:
            start_ray = Math.Vector3(start.x, start.y + 1.7, start.z)
            end_ray = Math.Vector3(end.x, end.y + 1.4, end.z)
            ray = end_ray - start_ray
            rayLen = ray.length
            if rayLen < 0.1:
                return True
            targetDist = None
            if targetID is not None:
                target = BigWorld.entity(targetID)
                targetDist = _get_entity_hit_distance(target, start_ray, end_ray)
                if targetDist is None:
                    radius = 3.0
                    try:
                        body = offhangar_physics.world.get_body(targetID)
                        if body is not None:
                            radius = max(float(getattr(body, 'halfLength', 3.0)), float(getattr(body, 'halfWidth', 2.0))) + 0.8
                    except Exception:
                        radius = 3.0
                    targetDist = _get_sphere_hit_distance(start_ray, end_ray, Math.Vector3(end), radius)
            staticDist = _get_static_hit_distance(spaceID, start_ray, end_ray, self.bot_id)
            if staticDist is None:
                return True
            if targetDist is None:
                return staticDist >= rayLen - 2.0
            return staticDist >= targetDist - 0.75
        except Exception:
            return False

    def shoot(self, target_veh):
        if target_veh is None:
            return
        target_id = getattr(target_veh, 'id', None)
        if target_id is None:
            return
        my_pos, _ = self.get_pos()
        t_pos = _get_body_pos(target_id)
        if t_pos is None:
            try:
                t_pos = Math.Matrix(target_veh.matrix).translation
            except Exception:
                t_pos = None
        if my_pos is None or t_pos is None or t_pos.length <= 0.1:
            return
        if not self.has_line_of_sight(my_pos, t_pos, target_id):
            return
        bot = BigWorld.entity(self.bot_id)
        if bot is not None and getattr(bot, 'isStarted', False):
            try:
                bot.showShooting(1, [0], True)
            except Exception:
                pass
            try:
                appearance = getattr(bot, 'appearance', None)
                if appearance is not None:
                    effectsList = bot.typeDescriptor.type.effects.get('shot', None)
                    if effectsList:
                        keyPoints, effects, _ = effectsList[0]
                        appearance.boundEffects.addNewToNode(
                            TankPartNames.GUN,
                            None,
                            effects,
                            keyPoints,
                            isPlayerVehicle=False,
                            showShockWave=False,
                            showFlashBang=False,
                            entity_id=self.bot_id
                        )
            except Exception:
                pass
        try:
            offhangar_shooting._applyDamage(target_id, self.damage, self.bot_id)
        except Exception:
            pass


def register_brain(bot_id, team, descr=None):
    _brains[bot_id] = BotBrain(bot_id, team, descr)


def unregister_brain(bot_id):
    _brains.pop(bot_id, None)


def clear_brains():
    _brains.clear()


def _tick():
    global _tick_id
    now = BigWorld.time()
    for brain in list(_brains.values()):
        try:
            brain.update(now)
        except Exception:
            pass
    _tick_id = BigWorld.callback(_ai_dt, _tick)


def start():
    global _tick_id
    if _tick_id is None:
        _tick_id = BigWorld.callback(_ai_dt, _tick)


def stop():
    global _tick_id
    if _tick_id is not None:
        try:
            BigWorld.cancelCallback(_tick_id)
        except Exception:
            pass
    _tick_id = None