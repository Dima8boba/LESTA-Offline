# -*- coding: utf-8 -*-
"""This module contains common functions that used in game modifications"""

author = 'Iliev Renat'
email = 'iliahonz@gmail.com'

import BigWorld
import ResMgr
import functools
import inspect
import os
import shutil
import tempfile
import time
import json
import re


def byteify(data):
    """Python 3 compatibility stub.

    In Python 2 this forced unicode -> utf-8 bytes.
    In Python 3 we normally want normal str objects.
    """
    return data


def jsonDump(obj, needFmt=False):
    """Serializes an object into a string

    :param obj: Object
    :param needFmt: Indicates that the result should be formatted for human reading
    """
    if needFmt:
        return json.dumps(
            obj,
            ensure_ascii=False,
            indent=4,
            separators=(',', ': '),
            sort_keys=True
        )
    return json.dumps(obj)


def jsonLoad(src):
    """Returns json data from source

    It supports comments in json
    :param src: Data source (file handler or string)
    """
    if hasattr(src, 'read'):
        src = src.read()

    if isinstance(src, bytes):
        src = src.decode('utf-8')

    return jsonParse(src)


def jsonParse(data):
    """Pareses json string into dict
    :param data: JSON string"""
    # Убираем обработку комментариев, так как она ломает ссылки с '//'
    return byteify(json.loads(data, encoding='utf-8', strict=False))


def deepUpdate(obj, new):
    """Recursive updating of the dictionary (including dictionaries in it)

    :param obj: Dictionary to be updated
    :param new: Diff dictionary
    """
    for key, value in new.items():
        if isinstance(value, dict):
            obj[key] = deepUpdate(obj.get(key, {}), value)
        else:
            obj[key] = value
    return obj


def isAlly(vehicle):
    """Checks is vehicle in player's team

    :param vehicle: Entity ID or object
    :return: Is given entity in player team
    """
    player = BigWorld.player()
    vehicles = player.arena.vehicles
    vehicleID = vehicle.id if isinstance(vehicle, BigWorld.Entity) else vehicle
    return vehicleID in vehicles and vehicles[player.playerVehicleID]['team'] == vehicles[vehicleID]['team']


def doLog(project, *args, **kwargs):
    """Prints arguments to stdout with tag

    :param project: Tag for log string
    :param args: Arguments, it reduces to string by join with space
    :param kwargs: Key-value arguments, it reduces to string by repr
    """
    kwargsStr = repr(kwargs) if kwargs else ''
    argsStr = ' '.join([str(s) for s in args])
    print('[%s] %s %s' % (project, argsStr, kwargsStr))


def unpackVFS(prefix, *paths):
    """Unpacks files from VFS with ResMgr into temporary folder

    :param prefix: Prefix for temporary folder name
    :param paths: Path to files in VFS
    :return: List of absolute paths to unpacked files
    """
    folder = os.path.join(tempfile.gettempdir(), '_'.join([str(prefix), str(int(time.time()))]))

    if os.path.exists(folder):
        shutil.rmtree(folder, ignore_errors=True)

    os.makedirs(folder)

    result = []

    for path in paths:
        filepath = os.path.join(folder, os.path.basename(path))
        result.append(filepath)

        section = ResMgr.openSection(path)
        if section is None:
            raise IOError('Cannot open VFS section: {}'.format(path))

        data = section.asBinary

        if isinstance(data, str):
            data = data.encode('utf-8')
        elif not isinstance(data, (bytes, bytearray)):
            data = bytes(str(data), 'utf-8')

        with open(filepath, 'wb') as f:
            f.write(data)

    return result


def override(obj, prop, getter=None, setter=None, deleter=None):
    """Overrides attribute in object.

    Attribute should be property or callable.
    Getter, setter and deleter should be callable or None.

    :param obj: Object
    :param prop: Name of any attribute in object (can be not mangled)
    :param getter: Getter function
    :param setter: Setter function
    :param deleter: Deleter function
    """
    if getter is None and setter is None and deleter is None:
        return functools.partial(override, obj, prop)

    if inspect.isclass(obj) and prop.startswith('__') and not prop.endswith('__'):
        mangled = '_{}{}'.format(obj.__name__, prop)
        if not hasattr(obj, prop) and hasattr(obj, mangled):
            prop = mangled

    src = getattr(obj, prop)

    if isinstance(src, property):
        assert getter is None or callable(getter), 'Getter is not callable!'
        assert setter is None or callable(setter), 'Setter is not callable!'
        assert deleter is None or callable(deleter), 'Deleter is not callable!'

        fget = functools.partial(getter, src.fget) if getter is not None else src.fget
        fset = functools.partial(setter, src.fset) if setter is not None else src.fset
        fdel = functools.partial(deleter, src.fdel) if deleter is not None else src.fdel

        setattr(obj, prop, property(fget, fset, fdel))
        return getter

    assert callable(src), 'Source property is not callable!'
    assert callable(getter), 'Handler is not callable!'

    def getter_new(*args, **kwargs):
        return getter(src, *args, **kwargs)

    try:
        functools.update_wrapper(getter_new, getter, updated=[])
    except Exception:
        pass

    if inspect.isclass(obj):
        raw = None
        for klass in obj.__mro__:
            if prop in klass.__dict__:
                raw = klass.__dict__[prop]
                break

        if isinstance(raw, staticmethod):
            getter_new = staticmethod(getter_new)
        elif isinstance(raw, classmethod):
            getter_new = classmethod(getter_new)

    setattr(obj, prop, getter_new)
    return getter