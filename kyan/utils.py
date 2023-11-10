import hashlib
import random
import string
from collections import OrderedDict
from functools import wraps

import flask


def sha1_hash(input_bytes):
    """Hash given bytes with hashlib.sha1 and return the digest (as bytes)"""
    return hashlib.sha1(input_bytes).digest()


def sorted_pathdict(input_dict):
    """Sorts a parsed torrent filelist dict by alphabet, directories first"""
    directories = OrderedDict()
    files = OrderedDict()

    for key, value in sorted(input_dict.items()):
        if isinstance(value, dict):
            directories[key] = sorted_pathdict(value)
        else:
            files[key] = value

    return OrderedDict(list(directories.items()) + list(files.items()))


def random_string(length, charset=None):
    if charset is None:
        charset = string.ascii_letters + string.digits
    return "".join(random.choice(charset) for _ in range(length))


def cached_function(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        if not hasattr(f, "_cached_value"):
            f._cached_value = f(*args, **kwargs)
        return f._cached_value

    return decorator


def flatten_dict(d, result=None):
    if result is None:
        result = {}
    for key, value in d.items():
        if isinstance(value, dict):
            value1 = {}
            for keyIn, valueIn in value.items():
                value1["/".join([key, keyIn])] = valueIn
            flatten_dict(value1, result)
        elif isinstance(value, (list, tuple)):
            for indexB, element in enumerate(value):
                if isinstance(element, dict):
                    value1 = {}
                    index = 0
                    for keyIn in element:
                        newkey = "/".join([key, keyIn])
                        value1[newkey] = value[indexB][keyIn]
                        index += 1
                    for keyA in value1:
                        flatten_dict(value1, result)
        else:
            result[key] = value
    return result


def chain_get(source, *args):
    """Tries to return values from the source by the given keys.
    Returns None if none match.
    Note: can return a None from the source."""
    for key in args:
        value = source.get(key)
        if value is not None:
            return value
    return None


def admin_only(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if flask.g.user and flask.g.user.is_superadmin:
            return f(*args, **kwargs)
        else:
            flask.abort(401)

    return wrapper
