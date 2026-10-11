# Python bytecode 2.7 (decompiled from Python 2.7)
# Embedded file name: G:\World_of_Tanks_EU\res_mods\2.3.1.3\scripts\client\gui\mods\mod_Map_selector_v120.py
# Compiled at: 2026-08-24 13:48:41
"""
Map_selector
Version 1.2.0

Final extended special-map selector based directly on the stable Map_selector 1.1.0.

- original OffHangar2 Demonstrator account flags
- original server-settings map/battle-level fallbacks
- preserve the proven Epic/Frontline path
- expose every installed ArenaType in selector data
- auto-detect fully hidden special gameplays
- add dynamic gameplay tabs/cards from ArenaType.g_cache
- use full arenaTypeID for special selections
- extend OffHangar2 battle.availableMaps() resolver gameplays dynamically
"""
MOD_NAME = 'Map_selector'
MOD_VERSION = '1.2.0'
ENABLE_LOG = True
LOG_FILE = 'map_selector.log'
MIN_VEHICLE_LEVEL = 1
MAX_VEHICLE_LEVEL = 20
VIRTUAL_BATTLE_ROYALE = 'battle_royale'
BATTLE_ROYALE_GEOMETRY_PREFIXES = ('250_br_', '251_br_', '252_br_')
_installed = False
_original_get_maps = None
_original_get_battle_levels = None
_original_demo_set_gameplay_tabs = None
_original_demo_as_set_gameplay_tabs = None
_original_demo_set_maps_list = None
_original_demo_on_battle_start = None

def _log(msg, *args):
    if not ENABLE_LOG:
        return
    try:
        if args:
            msg = msg % args
        line = '[%s %s] %s\n' % (MOD_NAME, MOD_VERSION, msg)
        f = open(LOG_FILE, 'ab')
        try:
            f.write(line.encode('utf-8', 'replace'))
        finally:
            f.close()

    except Exception:
        pass


def _enable_offhangar2_demonstrator_flag():
    try:
        from constants import ACCOUNT_ATTR
        arena_change_bit = int(ACCOUNT_ATTR.ARENA_CHANGE)
        battle_type_change_bit = int(ACCOUNT_ATTR.BATTLE_TYPE_CHANGE)
    except Exception as exc:
        _log('cannot resolve Demonstrator capability flags: %r', exc)
        return False

    try:
        from gui.mods.offhangar2 import config as oh2_config
    except Exception as exc:
        _log('OffHangar2 config not available; account flags not changed: %r', exc)
        return False

    try:
        old_value = int(getattr(oh2_config, 'ACCOUNT_ATTRS'))
        new_value = old_value | arena_change_bit | battle_type_change_bit
        oh2_config.ACCOUNT_ATTRS = new_value
        _log('OffHangar2 ACCOUNT_ATTRS: %d -> %d (ARENA_CHANGE=0x%X BATTLE_TYPE_CHANGE=0x%X)', old_value, new_value, arena_change_bit, battle_type_change_bit)
        return True
    except Exception as exc:
        _log('failed to extend OffHangar2 ACCOUNT_ATTRS: %r', exc)
        return False


def _arena_items():
    try:
        import ArenaType
        cache = ArenaType.g_cache
        try:
            return list(cache.iteritems())
        except Exception:
            return list(cache.items())

    except Exception as exc:
        _log('failed to read ArenaType.g_cache: %r', exc)
        return []


def _gameplay_name(arena_type):
    try:
        return str(getattr(arena_type, 'gameplayName', '') or '').lower()
    except Exception:
        return ''


def _geometry_name(arena_type):
    try:
        return str(getattr(arena_type, 'geometryName', '') or '').lower()
    except Exception:
        return ''


def _is_battle_royale_arena(arena_type):
    geometry = _geometry_name(arena_type)
    return False if not geometry else any((geometry.startswith(prefix) for prefix in BATTLE_ROYALE_GEOMETRY_PREFIXES))


def _virtual_special_groups():
    groups = []
    if any((_is_battle_royale_arena(arena) for arena_id, arena in _arena_items())):
        groups.append(VIRTUAL_BATTLE_ROYALE)
    return tuple(groups)


def _passes_stock_demo_filters(arena_type):
    """Original 1.0.0 visibility rules, without special exceptions."""
    try:
        if bool(getattr(arena_type, 'explicitRequestOnly', False)):
            return False
    except Exception:
        pass

    try:
        from account_helpers import gameplay_ctx
        gameplay_name = getattr(arena_type, 'gameplayName', None)
        if gameplay_name is not None:
            if not gameplay_ctx.isCreationEnabled(gameplay_name, False):
                return False
    except Exception:
        pass

    return True


def _special_gameplays():
    """
    Return gameplay names whose installed ArenaTypes are completely hidden by
    the stock Demonstrator filters. Those gameplays need their own tab/cards.
    
    Mixed gameplays (for example normal CTF plus one explicit event arena) stay
    on the stock tab; the hidden arena itself is still exposed in the generated
    ServerSettings map pairs below.
    """
    stats = {}
    for arena_type_id, arena in _arena_items():
        gameplay = _gameplay_name(arena)
        if not gameplay:
            continue
        visible, hidden = stats.get(gameplay, (0, 0))
        if _passes_stock_demo_filters(arena):
            visible += 1
        else:
            hidden += 1
        stats[gameplay] = (visible, hidden)

    result = []
    for gameplay, values in stats.items():
        visible, hidden = values
        if hidden > 0 and visible == 0:
            result.append(gameplay)

    if 'epic' in stats and 'epic' not in result:
        result.append('epic')
    try:
        result.sort()
    except Exception:
        pass

    _log('special gameplays detected: %r', result)
    return tuple(result)


def _is_stock_demo_arena(arena_type):
    return True


def _build_geometry_gameplay_pairs():
    pairs = set()
    total = 0
    rejected = 0
    for arena_type_id, arena_type in _arena_items():
        total += 1
        try:
            arena_type_id = int(arena_type_id)
        except Exception:
            rejected += 1
            continue

        if not _is_stock_demo_arena(arena_type):
            rejected += 1
            continue
        geometry_id = arena_type_id & 65535
        gameplay_id = arena_type_id >> 16
        pairs.add((geometry_id, gameplay_id))
        try:
            _log('arena include id=%d geometry=%d gameplay=%d geometryName=%r gameplayName=%r explicitRequestOnly=%r stockVisible=%r', arena_type_id, geometry_id, gameplay_id, getattr(arena_type, 'geometryName', None), getattr(arena_type, 'gameplayName', None), getattr(arena_type, 'explicitRequestOnly', None), _passes_stock_demo_filters(arena_type))
        except Exception:
            pass

    pairs = tuple(sorted(pairs))
    _log('arena cache: total=%d usable=%d rejected=%d', total, len(pairs), rejected)
    return pairs


def _build_random_maps_for_demonstrator():
    pairs = _build_geometry_gameplay_pairs()
    result = {}
    for vehicle_level in xrange(MIN_VEHICLE_LEVEL, MAX_VEHICLE_LEVEL + 1):
        result[vehicle_level] = pairs

    _log('built randomMapsForDemonstrator levels %d..%d with %d pairs', MIN_VEHICLE_LEVEL, MAX_VEHICLE_LEVEL, len(pairs))
    return result


def _looks_usable(value):
    if not value:
        return False
    try:
        keys = value.keys()
    except Exception:
        return False

    if not keys:
        return False
    try:
        for key in keys:
            if value[key]:
                return True

    except Exception:
        return False

    return False


def _merge_random_maps(original, generated):
    result = {}
    levels = set()
    try:
        levels.update(original.keys())
    except Exception:
        pass

    try:
        levels.update(generated.keys())
    except Exception:
        pass

    for level in levels:
        merged = []
        seen = set()
        for source in (original, generated):
            try:
                entries = source.get(level, ())
            except Exception:
                entries = ()

            for pair in entries or ():
                try:
                    pair = (int(pair[0]), int(pair[1]))
                except Exception:
                    continue

                if pair in seen:
                    continue
                seen.add(pair)
                merged.append(pair)

        result[level] = tuple(merged)

    return result


def _patched_get_random_maps(self):
    global _original_get_maps
    generated = _build_random_maps_for_demonstrator()
    if _original_get_maps is not None:
        try:
            original = _original_get_maps(self)
            if _looks_usable(original):
                return _merge_random_maps(original, generated)
        except Exception as exc:
            _log('stock getRandomMapsForDemonstrator failed: %r; using local fallback', exc)

    return generated


class _FallbackBattleLevels(object):
    _LEVEL_RANGES = tuple(((1, 12) for _ in xrange(20)))

    def __contains__(self, key):
        return False

    def __getitem__(self, key):
        return self._LEVEL_RANGES

    def __nonzero__(self):
        return True

    def __len__(self):
        pass


def _battle_levels_look_usable(value):
    if not value:
        return False
    try:
        return len(value) > 0
    except Exception:
        return False


def _patched_get_random_battle_levels(self):
    global _original_get_battle_levels
    if _original_get_battle_levels is not None:
        try:
            original = _original_get_battle_levels(self)
            if _battle_levels_look_usable(original):
                return original
        except Exception as exc:
            _log('stock getRandomBattleLevelsForDemonstrator failed: %r; using local fallback', exc)

    return _FallbackBattleLevels()


def _special_arena_entries(gameplay):
    result = []
    gameplay = str(gameplay or '').lower()
    for arena_type_id, arena in _arena_items():
        if gameplay == VIRTUAL_BATTLE_ROYALE:
            if not _is_battle_royale_arena(arena):
                continue
        elif _gameplay_name(arena) != gameplay:
            continue
        try:
            arena_type_id = int(arena_type_id)
        except Exception:
            continue

        geometry_id = arena_type_id & 65535
        gameplay_id = arena_type_id >> 16
        result.append((arena_type_id,
         geometry_id,
         gameplay_id,
         arena))

    try:
        result.sort(key=lambda item: item[1])
    except Exception:
        pass

    return result


def _card_name(arena, gameplay):
    for attr in ('name', 'userString', 'localizedName', 'displayName'):
        try:
            value = getattr(arena, attr, None)
            if callable(value):
                value = value()
            if value:
                return value
        except Exception:
            pass

    try:
        geometry = str(getattr(arena, 'geometryName', '') or '')
    except Exception:
        geometry = ''

    fallback = {'208_bf_epic_normandy': u'Normandie',
     '209_wg_epic_suburbia': u'Kraftwerk',
     '210_bf_epic_desert': u'Fata Morgana'}
    return fallback[geometry] if geometry in fallback else unicode(geometry or gameplay or 'Special Battle')


def _build_special_cards(gameplay):
    cards = []
    for arena_type_id, geometry_id, gameplay_id, arena in _special_arena_entries(gameplay):
        try:
            geometry = str(getattr(arena, 'geometryName', '') or '')
        except Exception:
            geometry = ''

        card_gameplay = gameplay
        if gameplay == VIRTUAL_BATTLE_ROYALE:
            card_gameplay = _gameplay_name(arena) or 'ctf'
        cards.append({'gameplayName': card_gameplay,
         'icon': u'img://gui/maps/icons/map/%s.png' % geometry,
         'points': [],
         'id': int(arena_type_id),
         'enabled': True,
         'name': _card_name(arena, gameplay)})

    return cards


def _inject_special_cards(window, gameplay):
    try:
        dp = getattr(window, '_DemonstratorWindow__mapListDP')
    except Exception:
        return False

    cards = _build_special_cards(gameplay)
    if not cards:
        return False
    else:
        try:
            collection = getattr(dp, 'collection', None)
            if collection is not None:
                del collection[:]
                collection.extend(cards)
            else:
                dp.collection = list(cards)
        except Exception:
            try:
                dp.collection = list(cards)
            except Exception:
                return False

        try:
            setattr(window, '_DemonstratorWindow__availableMapsLength', len(cards))
        except Exception:
            pass

        try:
            from gui.Scaleform.framework.entities.DAAPIDataProvider import ListDAAPIDataProvider
            ListDAAPIDataProvider.refresh(dp)
        except Exception:
            try:
                dp.refresh()
            except Exception:
                pass

        _log('injected %d cards for gameplay=%r', len(cards), gameplay)
        return True


def _gameplay_label(gameplay):
    labels = {'random': u'Standard Battle',
     'ctf': u'Standard Battle',
     'epic': u'Frontline',
     'battle_royale': u'Battle Royale',
     'battleRoyale': u'Battle Royale',
     'comp7': u'Onslaught',
     'comp7_light': u'Onslaught Light',
     'last_stand': u'Last Stand',
     'fun_random': u'Fun Random'}
    if gameplay in labels:
        return labels[gameplay]
    try:
        return unicode(gameplay.replace('_', ' ').title())
    except Exception:
        return unicode(gameplay)


def _internal_gameplay_name(item):
    try:
        if isinstance(item, (tuple, list)):
            return str(item[0])
        return str(item)
    except Exception:
        return ''


def _install_demonstrator_special_patch():
    global _original_demo_as_set_gameplay_tabs
    global _original_demo_set_maps_list
    global _original_demo_set_gameplay_tabs
    global _original_demo_on_battle_start
    try:
        from gui.Scaleform.daapi.view.lobby.DemonstratorWindow import DemonstratorWindow
    except Exception as exc:
        _log('cannot import DemonstratorWindow: %r', exc)
        return False

    tabs_name = '_DemonstratorWindow__setGameplayTabs'
    current_tabs = getattr(DemonstratorWindow, tabs_name, None)
    if current_tabs is None:
        return False
    else:
        if not getattr(current_tabs, '_map_selector_v111', False):
            _original_demo_set_gameplay_tabs = current_tabs
            _original_demo_as_set_gameplay_tabs = DemonstratorWindow.as_setGameplayTabsS

            def _patched_set_gameplay_tabs(self, *args, **kwargs):
                result = _original_demo_set_gameplay_tabs(self, *args, **kwargs)
                attr = '_DemonstratorWindow__availableGameplayTypes'
                selected_attr = '_DemonstratorWindow__gameplaySelected'
                try:
                    internal = list(getattr(self, attr) or ())
                except Exception:
                    internal = []

                existing = set((_internal_gameplay_name(item).lower() for item in internal if _internal_gameplay_name(item)))
                for gameplay in _special_gameplays():
                    if gameplay.lower() not in existing:
                        internal.append((gameplay, True))
                        existing.add(gameplay.lower())

                for gameplay in _virtual_special_groups():
                    if gameplay.lower() not in existing:
                        internal.append((gameplay, True))
                        existing.add(gameplay.lower())

                setattr(self, attr, internal)
                try:
                    selected = int(getattr(self, selected_attr, 0) or 0)
                except Exception:
                    selected = 0

                ui_payload = []
                for item in internal:
                    gameplay = _internal_gameplay_name(item)
                    if not gameplay:
                        gameplay = 'random'
                    ui_payload.append({'enabled': True,
                     'label': _gameplay_label(gameplay)})

                if not ui_payload:
                    ui_payload = [{'enabled': True,
                      'label': u'Standard Battle'}]
                _original_demo_as_set_gameplay_tabs(self, ui_payload, selected)
                _log('gameplay tabs: %r', [ _internal_gameplay_name(item) for item in internal ])
                return result

            _patched_set_gameplay_tabs._map_selector_v111 = True
            setattr(DemonstratorWindow, tabs_name, _patched_set_gameplay_tabs)
        maps_name = '_DemonstratorWindow__setMapsList'
        current_maps = getattr(DemonstratorWindow, maps_name, None)
        if current_maps is None:
            return False
        if not getattr(current_maps, '_map_selector_v111', False):
            _original_demo_set_maps_list = current_maps

            def _patched_set_maps_list(self, *args, **kwargs):
                result = _original_demo_set_maps_list(self, *args, **kwargs)
                try:
                    available = getattr(self, '_DemonstratorWindow__availableGameplayTypes')
                    selected = int(getattr(self, '_DemonstratorWindow__gameplaySelected'))
                    gameplay = _internal_gameplay_name(available[selected]).lower()
                except Exception:
                    gameplay = ''

                if gameplay in _special_gameplays() + _virtual_special_groups():
                    _inject_special_cards(self, gameplay)
                return result

            _patched_set_maps_list._map_selector_v111 = True
            setattr(DemonstratorWindow, maps_name, _patched_set_maps_list)
        current_start = getattr(DemonstratorWindow, 'onBattleStart', None)
        if current_start is not None and not getattr(current_start, '_map_selector_v111', False):
            _original_demo_on_battle_start = current_start

            def _patched_battle_start(self, *args, **kwargs):
                try:
                    available = getattr(self, '_DemonstratorWindow__availableGameplayTypes')
                    selected = int(getattr(self, '_DemonstratorWindow__gameplaySelected'))
                    gameplay = _internal_gameplay_name(available[selected]).lower()
                    map_id = int(getattr(self, '_DemonstratorWindow__mapSelected'))
                except Exception:
                    gameplay = ''
                    map_id = 0

                if gameplay in _special_gameplays() + _virtual_special_groups() and map_id <= 65535:
                    for arena_type_id, geometry_id, gameplay_id, arena in _special_arena_entries(gameplay):
                        if int(geometry_id) == map_id:
                            setattr(self, '_DemonstratorWindow__mapSelected', int(arena_type_id))
                            _log('repaired map selection gameplay=%r geometry=%d arenaTypeID=%d', gameplay, map_id, arena_type_id)
                            break

                if gameplay == VIRTUAL_BATTLE_ROYALE:
                    attr = '_DemonstratorWindow__availableGameplayTypes'
                    original_available = None
                    try:
                        original_available = getattr(self, attr)
                        patched_available = list(original_available)
                        item = patched_available[selected]
                        if isinstance(item, tuple):
                            patched_available[selected] = ('ctf',) + tuple(item[1:])
                        elif isinstance(item, list):
                            patched_available[selected] = ['ctf'] + list(item[1:])
                        else:
                            patched_available[selected] = ('ctf', True)
                        setattr(self, attr, patched_available)
                        _log('Battle Royale request shim: virtual=%r actual=ctf map=%d', gameplay, map_id)
                        return _original_demo_on_battle_start(self, *args, **kwargs)
                    finally:
                        if original_available is not None:
                            try:
                                setattr(self, attr, original_available)
                            except Exception:
                                pass

                return _original_demo_on_battle_start(self, *args, **kwargs)

            _patched_battle_start._map_selector_v111 = True
            DemonstratorWindow.onBattleStart = _patched_battle_start
        return True


def _enable_offhangar2_special_battle_support():
    try:
        from gui.mods.offhangar2 import config as oh2_config
    except Exception as exc:
        _log('cannot import OffHangar2 config for special support: %r', exc)
        return False

    try:
        current = tuple(getattr(oh2_config, 'BATTLE_GAMEPLAYS', ()) or ())
    except Exception:
        current = ()

    normalized = set((str(value).lower() for value in current))
    additions = []
    for gameplay in _special_gameplays():
        if gameplay.lower() not in normalized:
            additions.append(gameplay)
            normalized.add(gameplay.lower())

    if additions:
        try:
            oh2_config.BATTLE_GAMEPLAYS = tuple(current) + tuple(additions)
        except Exception as exc:
            _log('cannot extend BATTLE_GAMEPLAYS: %r', exc)
            return False

    _log('BATTLE_GAMEPLAYS additions: %r', additions)
    return True


def _install_battle_level_patch():
    global _original_get_battle_levels
    try:
        from helpers.server_settings import ServerSettings
    except Exception as exc:
        _log('cannot import ServerSettings for battle-level patch: %r', exc)
        return False

    current = getattr(ServerSettings, 'getRandomBattleLevelsForDemonstrator', None)
    if current is None:
        return False
    elif getattr(current, '_map_selector_v111', False):
        return True
    else:
        _original_get_battle_levels = current
        _patched_get_random_battle_levels._map_selector_v111 = True
        ServerSettings.getRandomBattleLevelsForDemonstrator = _patched_get_random_battle_levels
        return True


def _install_map_data_patch():
    global _original_get_maps
    try:
        from helpers.server_settings import ServerSettings
    except Exception as exc:
        _log('cannot import ServerSettings: %r', exc)
        return False

    current = getattr(ServerSettings, 'getRandomMapsForDemonstrator', None)
    if current is None:
        return False
    elif getattr(current, '_map_selector_v111', False):
        return True
    else:
        _original_get_maps = current
        _patched_get_random_maps._map_selector_v111 = True
        ServerSettings.getRandomMapsForDemonstrator = _patched_get_random_maps
        return True


def install():
    global _installed
    if _installed:
        return True
    attrs_ok = _enable_offhangar2_demonstrator_flag()
    levels_ok = _install_battle_level_patch()
    maps_ok = _install_map_data_patch()
    special_ui_ok = _install_demonstrator_special_patch()
    special_battle_ok = _enable_offhangar2_special_battle_support()
    _installed = bool(attrs_ok and levels_ok and maps_ok and special_ui_ok and special_battle_ok)
    _log('install complete: attrs=%s levels=%s maps=%s specialUI=%s specialBattle=%s', attrs_ok, levels_ok, maps_ok, special_ui_ok, special_battle_ok)
    return _installed


try:
    install()
except Exception as exc:
    _log('top-level install failed: %r', exc)