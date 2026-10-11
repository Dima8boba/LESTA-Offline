import math
import random
import BigWorld
from debug_utils import LOG_CURRENT_EXCEPTION

_BACKWARD = 0.1
_FORWARD = 20.0
_MAX_HIT_ANGLE = math.pi / 2.0 - 1e-05
_MIN_COS = 1e-05

class Result(object):
    __slots__ = ('pierced', 'ricochet', 'damageFactor', 'nonPiercingFactor', 'armour', 'effectiveArmour', 'piercingPower', 'angle', 'componentIdx', 'hitEffectCode', 'critOnly', 'blocked', 'plates', 'reason', 'hitOffset', 'hitExtras')

    def __init__(self):
        self.pierced = False
        self.ricochet = False
        self.damageFactor = 0.0
        self.nonPiercingFactor = 0.0
        self.armour = 0.0
        self.effectiveArmour = 0.0
        self.piercingPower = 0.0
        self.angle = 0.0
        self.componentIdx = 0
        self.hitEffectCode = 3
        self.critOnly = False
        self.blocked = False
        self.plates = 0
        self.reason = ''
        self.hitOffset = 0.0
        self.hitExtras = []

    def __repr__(self):
        return 'armour.Result(%s, %.0fmm/%.0fmm eff at %.0fdeg vs %.0fmm pen, x%.2f)' % (self.reason,
         self.armour,
         self.effectiveArmour,
         self.angle,
         self.piercingPower,
         self.damageFactor)

def _hitEffect():
    from constants import VEHICLE_HIT_EFFECT
    return VEHICLE_HIT_EFFECT

_EXTRA_DATA = None

def _shellExtra(kind):
    global _EXTRA_DATA
    if _EXTRA_DATA is None:
        from constants import SHELL_TYPES
        _EXTRA_DATA = {SHELL_TYPES.ARMOR_PIERCING: (True, True, True, False),
         SHELL_TYPES.ARMOR_PIERCING_CR: (True, True, True, False),
         SHELL_TYPES.ARMOR_PIERCING_HE: (True, False, False, False),
         SHELL_TYPES.HOLLOW_CHARGE: (False, True, False, True),
         SHELL_TYPES.HIGH_EXPLOSIVE: (False, False, False, False)}
    return _EXTRA_DATA.get(kind, (True, True, True, False))

def piercingPowerAt(shot, distance, multiplier=1.0):
    try:
        from helpers_common import computePiercingPowerAtDist
        return computePiercingPowerAtDist(shot.piercingPower, distance) * multiplier
    except Exception:
        try:
            return float(shot.piercingPower[0]) * multiplier
        except Exception:
            return 0.0

def damageAt(shell, distance):
    try:
        from helpers_common import computeDamageAtDist
        return computeDamageAtDist(shell.armorDamage, distance)
    except Exception:
        try:
            return float(shell.armorDamage[0])
        except Exception:
            return 0.0

def rollPiercingPower(shell, nominal):
    spread = getattr(shell, 'piercingPowerRandomization', None)
    try:
        spread = float(spread)
    except (TypeError, ValueError):
        spread = 0.0
    if spread <= 0.0:
        return nominal
    return nominal * random.uniform(1.0 - spread, 1.0 + spread)

def _shouldRicochet(shell, hitAngleCos, matInfo):
    if not matInfo.mayRicochet:
        return False
    hasNorm, mayRicochet, checkCaliber, hasLoss = _shellExtra(shell.kind)
    if not mayRicochet:
        return False
    armour = matInfo.armor
    if not armour:
        return False
    if hitAngleCos <= shell.type.ricochetAngleCos:
        if not matInfo.checkCaliberForRicochet:
            return True
        if not checkCaliber:
            return True
        if armour * 3 >= shell.caliber:
            return True
    return False

def _penetrationArmour(shell, hitAngleCos, matInfo):
    armour = matInfo.armor
    if not matInfo.useHitAngle:
        return armour
    normalisation = 0.0
    hasNorm, mayRicochet, checkCaliber, hasLoss = _shellExtra(shell.kind)
    if hasNorm:
        normalisation = shell.type.normalizationAngle
    if normalisation > 0.0 and hitAngleCos < 1.0:
        if matInfo.checkCaliberForHitAngleNorm:
            if shell.caliber > armour * 2 > 0:
                normalisation *= 1.4 * shell.caliber / (armour * 2)
        hitAngle = math.acos(hitAngleCos) - normalisation
        if hitAngle < 0.0:
            hitAngleCos = 1.0
        elif hitAngle > _MAX_HIT_ANGLE:
            hitAngle = _MAX_HIT_ANGLE
            hitAngleCos = math.cos(hitAngle)
    if hitAngleCos < _MIN_COS:
        hitAngleCos = _MIN_COS
    return armour / hitAngleCos

def _record(result, detail, matInfo, hitAngleCos):
    result.componentIdx = detail.compName
    result.armour = float(matInfo.armor or 0.0)
    try:
        result.hitOffset = float(detail.dist) - _BACKWARD
    except Exception:
        result.hitOffset = 0.0
    try:
        result.angle = math.degrees(math.acos(max(-1.0, min(1.0, hitAngleCos))))
    except ValueError:
        result.angle = 0.0

def _collisionDetails(target, hitPoint, direction):
    try:
        start = hitPoint - direction * _BACKWARD
        end = hitPoint + direction * _FORWARD
        return target.collideSegmentExt(start, end)
    except Exception:
        LOG_CURRENT_EXCEPTION()
    return None

_heFormulaLogged = [False]

def _highExplosiveDamage(shell, effectiveArmour, nominalArmour):
    shellType = getattr(shell, 'type', None)
    factor = float(getattr(shellType, 'explosionDamageFactor', 0.0) or 0.0)
    absorption = float(getattr(shellType, 'explosionDamageAbsorptionFactor', 0.0) or 0.0)
    if factor <= 0.0 or absorption <= 0.0:
        try:
            from items import vehicles
            misc = vehicles.g_cache.commonConfig['miscParams']
            if factor <= 0.0:
                factor = float(misc.get('explosionDamageFactor', 0.5))
            if absorption <= 0.0:
                absorption = float(misc.get('explosionDamageAbsorptionFactor', 1.1))
        except Exception:
            factor = factor or 0.5
            absorption = absorption or 1.1
    if not _heFormulaLogged[0]:
        _heFormulaLogged[0] = True
    nominal = damageAt(shell, 0.0)
    if nominal <= 0.0:
        return 0.0
    absorbed = nominalArmour * absorption
    remaining = nominal * factor - absorbed
    if remaining <= 0.0:
        return 0.0
    return remaining / nominal

def _nonPiercingFactor(shell, effectiveArmour, nominalArmour):
    shellType = getattr(shell, 'type', None)
    direct = getattr(shellType, 'nonPiercingArmorDamage', 0.0)
    try:
        direct = float(direct)
    except (TypeError, ValueError):
        direct = 0.0
    if direct > 0.0:
        return direct
    from constants import SHELL_TYPES
    if shell.kind == SHELL_TYPES.HIGH_EXPLOSIVE:
        return _highExplosiveDamage(shell, effectiveArmour, nominalArmour)
    return 0.0

def resolve(target, hitPoint, direction, shell, shot, distance, piercingMultiplier=1.0):
    try:
        return _resolve(target, hitPoint, direction, shell, shot, distance, piercingMultiplier)
    except Exception:
        LOG_CURRENT_EXCEPTION()
        failed = Result()
        failed.reason = 'no-collision-model'
        return failed

def _resolve(target, hitPoint, direction, shell, shot, distance, piercingMultiplier=1.0):
    result = Result()
    HIT = _hitEffect()
    result.hitEffectCode = HIT.ARMOR_NOT_PIERCED
    nominalPower = piercingPowerAt(shot, distance, piercingMultiplier)
    result.piercingPower = rollPiercingPower(shell, nominalPower)
    details = _collisionDetails(target, hitPoint, direction)
    if not details:
        result.reason = 'no-collision-model'
        return result

    piercingPower = result.piercingPower
    isJet = False
    jetStart = None
    ignored = set()
    hasNorm, mayRicochet, checkCaliber, hasLoss = _shellExtra(shell.kind)
    first = True

    for detail in details:
        result.plates += 1
        matInfo = detail.matInfo
        if isJet and jetStart is not None:
            jetDistance = detail.dist - jetStart
            if jetDistance > 0.0:
                loss = float(getattr(shell.type, 'piercingPowerLossFactorByDistance', 0.0) or 0.0)
                piercingPower *= max(0.0, 1.0 - jetDistance * loss)
        if matInfo is None:
            result.critOnly = True
            continue
        key = (detail.compName, matInfo.kind)
        if key in ignored:
            continue
        if matInfo.armor is None:
            continue
        hitAngleCos = detail.hitAngleCos if matInfo.useHitAngle else 1.0
        if first:
            _record(result, detail, matInfo, hitAngleCos)
            first = False
        if not isJet and _shouldRicochet(shell, hitAngleCos, matInfo):
            _record(result, detail, matInfo, hitAngleCos)
            result.ricochet = True
            result.blocked = bool(matInfo.vehicleDamageFactor)
            result.effectiveArmour = float(matInfo.armor)
            result.hitEffectCode = HIT.FINAL_RICOCHET
            result.reason = 'ricochet'
            return result
        penetration = _penetrationArmour(shell, hitAngleCos, matInfo)
        pierced = piercingPower >= penetration
        piercingPower -= penetration
        if matInfo.extra and pierced:
            result.critOnly = True
            if matInfo.extra not in result.hitExtras:
                result.hitExtras.append(matInfo.extra)
        if matInfo.vehicleDamageFactor and not result.pierced:
            _record(result, detail, matInfo, hitAngleCos)
            result.effectiveArmour = penetration
            result.damageFactor = float(matInfo.vehicleDamageFactor)
            result.pierced = bool(pierced)
            result.blocked = not pierced
            if pierced:
                result.hitEffectCode = HIT.ARMOR_PIERCED
                result.reason = 'pierced'
            else:
                result.hitEffectCode = HIT.ARMOR_NOT_PIERCED
                result.reason = 'no-penetration'
                result.nonPiercingFactor = _nonPiercingFactor(shell, penetration, float(matInfo.armor))
            return result
        if matInfo.collideOnceOnly:
            ignored.add(key)
        if piercingPower <= 0.0:
            if not result.reason:
                _record(result, detail, matInfo, hitAngleCos)
                result.effectiveArmour = penetration
                result.hitEffectCode = HIT.ARMOR_NOT_PIERCED
                result.blocked = True
                result.reason = 'absorbed'
            break
        if hasLoss:
            isJet = True
            jetStart = detail.dist + float(matInfo.armor or 0.0) * 0.001

    if not result.reason:
        result.reason = 'no-damaging-material'
    return result

def hitFlags(result, destroyed=False, wasDead=False):
    from constants import VEHICLE_HIT_FLAGS as VHF
    flags = VHF.ATTACK_IS_DIRECT_PROJECTILE
    if wasDead:
        return flags | VHF.VEHICLE_WAS_DEAD_BEFORE_ATTACK
    if result.ricochet:
        flags |= VHF.RICOCHET
        flags |= VHF.ATTACK_IS_RICOCHET_PROJECTILE
    if result.pierced:
        flags |= VHF.MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE
    elif result.damageFactor and result.nonPiercingFactor > 0.0:
        flags |= VHF.MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_WITH_DAMAGE_BY_PROJECTILE
    elif result.damageFactor:
        flags |= VHF.MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_BY_PROJECTILE
    elif not result.ricochet:
        flags |= VHF.ARMOR_WITH_ZERO_DF_NOT_PIERCED_BY_PROJECTILE
    if result.critOnly or getattr(result, 'hitExtras', None):
        flags |= VHF.DEVICE_PIERCED_BY_PROJECTILE
        flags |= VHF.DEVICE_DAMAGED_BY_PROJECTILE
    if result.componentIdx == 0 or any(('track' in getattr(e, 'name', '').lower() for e in getattr(result, 'hitExtras', ()))):
        flags |= VHF.CHASSIS_DAMAGED_BY_PROJECTILE
    if result.componentIdx == 3 or any(('gun' in getattr(e, 'name', '').lower() for e in getattr(result, 'hitExtras', ()))):
        flags |= VHF.GUN_DAMAGED_BY_PROJECTILE
    if destroyed:
        flags |= VHF.VEHICLE_KILLED
    return flags

def describe(result):
    return '%s: %.0fmm at %.0f deg = %.0fmm effective vs %.0fmm penetration (x%.2f damage, %d plates)' % (result.reason,
     result.armour,
     result.angle,
     result.effectiveArmour,
     result.piercingPower,
     result.damageFactor,
     result.plates)