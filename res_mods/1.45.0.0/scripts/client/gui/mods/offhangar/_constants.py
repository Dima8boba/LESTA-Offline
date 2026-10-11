# -- coding: utf-8 --
import pickle
import zlib
import ResMgr
from chat_shared import CHAT_RESPONSES, CHAT_ACTIONS, CHAT_COMMANDS
from gui.mods.offhangar.utils import jsonParse
from gui.mods.offhangar.logging import LOG_DEBUG
from preferred_maps import SlotTypeId

IS_REQUEST_CATCHING = False

OFFLINE_SERVER_ADDRES = 'wargaming.net'
OFFLINE_NICKNAME = 'test'
OFFLINE_LOGIN = OFFLINE_NICKNAME + '@' + OFFLINE_SERVER_ADDRES
OFFLINE_PWD = '123456'
OFFLINE_DBID = 1

OFFLINE_GUI_CTX = pickle.dumps(
    {
        'databaseID': OFFLINE_DBID,
        'logUXEvents': True,
        'aogasStartedAt': 0,
        'sessionStartedAt': 0,
        'isAogasEnabled': False,
        'collectUiStats': False,
        'isLongDisconnectedFromCenter': False,
    },
    protocol=2
)

def _normalizeServerSettings(value):
    if isinstance(value, dict):
        return {
            str(key).strip(): _normalizeServerSettings(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalizeServerSettings(item) for item in value]
    if isinstance(value, str):
        return value.strip()
    return value

_section = ResMgr.openSection('helpers/offhangar/initialServerSettings.json')
if _section is None:
    raise IOError('Cannot open helpers/offhangar/initialServerSettings.json')

_rawServerSettings = jsonParse(_section.asBinary)
_normalizedSettings = _normalizeServerSettings(_rawServerSettings)

_REQUIRED_INBATTLE_CONFIGS = [
    'spgRedesignFeatures', 'ranked_config', 'battle_royale_config', 'epic_config',
    'vehicle_post_progression_config', 'comp7_config', 'fun_random_config',
    'battle_context_hints_config', 'comp7_skills_config',
]
for key in _REQUIRED_INBATTLE_CONFIGS:
    if key not in _normalizedSettings:
        _normalizedSettings[key] = {}

_STORY_MODE_DEFAULTS = {
    'enabled': False,
    'hideGameLoadingTimeout': 1,
    'joinToQueueFromLogin': False,
    'quotums': [1, 1, 1],
    'waitTimeQueue': 1
}
if 'story_mode_settings' not in _normalizedSettings:
    _normalizedSettings['story_mode_settings'] = _STORY_MODE_DEFAULTS
else:
    for k, v in _STORY_MODE_DEFAULTS.items():
        _normalizedSettings['story_mode_settings'].setdefault(k, v)

_normalizedSettings.setdefault('tank_academy_config', {})

_lootBoxesConfig = _normalizedSettings.get('lootBoxes_config')
if not isinstance(_lootBoxesConfig, dict) or not all(
        isinstance(v, dict) for v in _lootBoxesConfig.values()):
    LOG_DEBUG('lootBoxes_config is not a valid {id: dict} mapping, resetting to {}. Was: %s', _lootBoxesConfig)
    _normalizedSettings['lootBoxes_config'] = {}

_PERSONAL_RESERVES_CATEGORIES = ('PERSONAL', 'CLAN', 'EVENT')

_personalReserves = _normalizedSettings.get('personal_reserves_config')
if not isinstance(_personalReserves, dict):
    _personalReserves = {}
    _normalizedSettings['personal_reserves_config'] = _personalReserves

_personalReserves.setdefault('isReservesInBattleActivationEnabled', False)
_supportedQueueTypes = _personalReserves.get('supportedQueueTypes')
if not isinstance(_supportedQueueTypes, dict):
    _supportedQueueTypes = {}
    _personalReserves['supportedQueueTypes'] = _supportedQueueTypes

for _cat in _PERSONAL_RESERVES_CATEGORIES:
    _supportedQueueTypes.setdefault(_cat, [])

_preferredMaps = _normalizedSettings.get('preferredMaps_config')
if not isinstance(_preferredMaps, dict):
    _preferredMaps = {}
    _normalizedSettings['preferredMaps_config'] = _preferredMaps

_preferredMaps.setdefault('slots', {})
_preferredMaps.setdefault('defaultSlots', 1)
_preferredMaps.setdefault('premiumSlots', 0)
_preferredMaps.setdefault('slotCooldown', 14400)
_preferredMaps.setdefault('mapIDs', [])

CHAT_ACTION_DATA = {
    'requestID': None,
    'action': None,
    'actionResponse': CHAT_RESPONSES.connectTimeout.index(),
    'time': 0,
    'sentTime': 0,
    'channel': 0,
    'originator': 0,
    'originatorNickName': '',
    'group': 0,
    'data': {'type': 0, 'message': '', 'messageID': 0, 'tenant': ''},
    'flags': 0,
}

REQUEST_CALLBACK_TIME = 0.5

_normalizedSettings['random_battles_config'] = {
    'isEnabled': True,
    'levels': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
}

OFFLINE_SERVER_SETTINGS = zlib.compress(
    pickle.dumps(_normalizedSettings, protocol=2)
)