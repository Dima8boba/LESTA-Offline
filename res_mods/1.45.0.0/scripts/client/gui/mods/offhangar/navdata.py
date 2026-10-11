

import importlib
import random

import BigWorld

from debug_utils import LOG_CURRENT_EXCEPTION

_MAP_MODULES = {
    '506_battle_for_moscow': 'gui.mods.offhangar.mapdata.m_506_battle_for_moscow',
}

_moduleCache = {}

# tracks which random-mode spawn slots have already been handed out this
# battle, per team, so bots spread across the real slots instead of
# clumping on whichever one random.choice() keeps landing on
_usedRandomSpawnIndices = {1: set(), 2: set()}


def _currentMapName():
    try:
        avatar = BigWorld.player()
        arena = getattr(avatar, 'arena', None)
        arenaType = getattr(arena, 'arenaType', None)
        name = getattr(arenaType, 'geometryName', None)
        if name:
            return name
    except Exception:
        pass
    return None


def _loadMapModule(mapName=None):
    name = mapName or _currentMapName()
    if not name:
        return None

    if name in _moduleCache:
        return _moduleCache[name]

    modPath = _MAP_MODULES.get(name)
    if not modPath:
        _moduleCache[name] = None
        return None

    try:
        mod = importlib.import_module(modPath)
    except Exception:
        LOG_CURRENT_EXCEPTION()
        mod = None

    _moduleCache[name] = mod
    return mod


def hasMapData(mapName=None):
    return _loadMapModule(mapName) is not None


def getAllRandomSpawnPoints(team, mapName=None):
    """Every real per-slot (x, y, z, yaw) spawn slot for `team` baked into
    this map's compiled geometry, or None if we don't have data for the
    current map yet."""
    mod = _loadMapModule(mapName)
    if mod is None:
        return None
    spawns = getattr(mod, 'RANDOM_SPAWNS', {}).get(int(team))
    if not spawns:
        return None
    return list(spawns)


def pickRandomSpawnPoint(team, mapName=None):
    """
    Picks one (x, y, z, yaw) slot for `team`, cycling through all the real
    slots before repeating any (same spirit as bots._pickBotName's
    used-name tracking) so bots don't all pile onto the same spawn.
    Returns None if we don't have extracted data for this map - callers
    should fall back to the old runtime spawn-point lookup in that case.
    """
    team = int(team)
    spawns = getAllRandomSpawnPoints(team, mapName)
    if not spawns:
        return None

    used = _usedRandomSpawnIndices.setdefault(team, set())
    available = [i for i in range(len(spawns)) if i not in used]

    if not available:
        used.clear()
        available = list(range(len(spawns)))

    idx = random.choice(available)
    used.add(idx)
    return spawns[idx]


def resetRandomSpawnTracking():
    """Call this when leaving/clearing a battle so the next one starts
    with a fresh set of available spawn slots."""
    for team in _usedRandomSpawnIndices:
        _usedRandomSpawnIndices[team].clear()


def getGameplayTeamSpawnPoints(gameplayName, team, mapName=None):
    """(x, z) points declared in the arena-def XML's <teamSpawnPoints> for
    a specific gameplay mode (e.g. 'assault2'). Returns None if this map
    or gameplay mode isn't in our data set."""
    mod = _loadMapModule(mapName)
    if mod is None:
        return None
    gp = getattr(mod, 'GAMEPLAY_SPAWNS', {}).get(gameplayName)
    if not gp:
        return None
    return gp.get('teamSpawnPoints', {}).get(int(team))


def getGameplayTeamBasePositions(gameplayName, team, mapName=None):
    """(x, z) points declared in the arena-def XML's <teamBasePositions>
    for a specific gameplay mode (e.g. 'ctf', 'assault2')."""
    mod = _loadMapModule(mapName)
    if mod is None:
        return None
    gp = getattr(mod, 'GAMEPLAY_SPAWNS', {}).get(gameplayName)
    if not gp:
        return None
    return gp.get('teamBasePositions', {}).get(int(team))


def getMapBounds(mapName=None):
    mod = _loadMapModule(mapName)
    if mod is None:
        return None
    return getattr(mod, 'MAP_BOUNDS', None)
