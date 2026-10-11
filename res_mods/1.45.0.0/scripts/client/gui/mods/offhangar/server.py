# -- coding: utf-8 --
import functools
import pickle
import BigWorld
import AccountCommands
from gui.mods.offhangar._constants import CHAT_ACTION_DATA
from gui.mods.offhangar.logging import LOG_DEBUG

BASE_REQUESTS = {}

class FakeServer(object):
    def __init__(self, name='Server', isMuted=False):
        super(FakeServer, self).__init__()
        self.__isMuted = isMuted
        self.__name = name

    def __call__(self, *args, **kwargs):
        if not self.__isMuted:
            LOG_DEBUG('%s ( %s, %s )' % (self.__name, args, kwargs))

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        try:
            return super(FakeServer, self).__getattribute__(name)
        except AttributeError:
            return FakeServer(name='%s.%s' % (self.__name, name), isMuted=self.__isMuted)

    def chatCommandFromClient(self, requestID, action, channelID, int64Arg, int16Arg, stringArg1, stringArg2):
        pass

    def doCmdStr(self, requestID, cmd, s): self.__doCmd(requestID, cmd, s)
    def doCmdIntStr(self, requestID, cmd, int1, s): self.__doCmd(requestID, cmd, int1, s)
    def doCmdInt(self, requestID, cmd, int1): self.__doCmd(requestID, cmd, int1)
    def doCmdInt2(self, requestID, cmd, int1, int2): self.__doCmd(requestID, cmd, int1, int2)
    def doCmdInt3(self, requestID, cmd, int1, int2, int3): self.__doCmd(requestID, cmd, int1, int2, int3)
    def doCmdInt4(self, requestID, cmd, int1, int2, int3, int4): self.__doCmd(requestID, cmd, int1, int2, int3, int4)
    def doCmdInt2Str(self, requestID, cmd, int1, int2, s): self.__doCmd(requestID, cmd, int1, int2, s)
    def doCmdInt3Str(self, requestID, cmd, int1, int2, int3, s): self.__doCmd(requestID, cmd, int1, int2, int3, s)
    def doCmdIntArr(self, requestID, cmd, arr): self.__doCmd(requestID, cmd, arr)
    def doCmdIntStrArr(self, requestID, cmd, int1, strArr): self.__doCmd(requestID, cmd, int1, strArr)
    def doCmdStrArr(self, requestID, cmd, strArr): self.__doCmd(requestID, cmd, strArr)
    def doCmdIntArrStrArr(self, requestID, cmd, intArr, strArr): self.__doCmd(requestID, cmd, intArr, strArr)

    def __doCmd(self, requestID, cmd, *args):
        cmdCall = BASE_REQUESTS.get(cmd)
        if cmdCall is not None:
            requestID, resultID, errorStr, ext = cmdCall(requestID, *args)
        else:
            resultID = AccountCommands.RES_FAILURE
            errorStr = ''
            ext = None
        player = BigWorld.player()
        if player is None: return
        if ext is not None:
            callback = functools.partial(player.onCmdResponseExt, requestID, resultID, errorStr, pickle.dumps(ext, protocol=2))
        else:
            callback = functools.partial(player.onCmdResponse, requestID, resultID, errorStr)
        BigWorld.callback(0.0, callback)
