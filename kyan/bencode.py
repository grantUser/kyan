from io import BytesIO

__all__ = ["encode", "decode", "BencodeException", "MalformedBencodeException"]


class BencodeException(Exception):
    pass


class MalformedBencodeException(BencodeException):
    pass


_DIGITS = b"0123456789"
_B_INT = b"i"
_B_LIST = b"l"
_B_DICT = b"d"
_B_END = b"e"


def _pairwise(iterable):
    """Returns items from an iterable two at a time, e.g., [0, 1, 2, 3] -> [(0, 1), (2, 3)]"""
    a = iter(iterable)
    return zip(a, a)


def _bencode_decode(file_object, decode_keys_as_utf8=True):
    if isinstance(file_object, str):
        file_object = file_object.encode("utf-8")
    if isinstance(file_object, bytes):
        file_object = BytesIO(file_object)

    def create_ex(msg):
        return MalformedBencodeException(
            f"{msg} at position {file_object.tell()} (0x{file_object.tell():02X} hex)"
        )

    def _read_list():
        items = []
        while True:
            value = _bencode_decode(
                file_object, decode_keys_as_utf8=decode_keys_as_utf8
            )
            if value is None:
                break
            items.append(value)
        return items

    kind = file_object.read(1)
    if not kind:
        raise create_ex("EOF, expecting kind")

    if kind == _B_INT:
        int_bytes = b""
        while True:
            c = file_object.read(1)
            if not c:
                raise create_ex("EOF, expecting more integer")
            elif c == _B_END:
                try:
                    return int(int_bytes.decode("utf-8"))
                except Exception:
                    raise create_ex("Unable to parse int")
            if (c not in _DIGITS + b"-") or (c == b"-" and int_bytes):
                raise create_ex("Unexpected input while reading an integer: " + repr(c))
            else:
                int_bytes += c
    elif kind == _B_LIST:
        return _read_list()
    elif kind == _B_DICT:
        keys_and_values = _read_list()
        if len(keys_and_values) % 2 != 0:
            raise MalformedBencodeException("Uneven amount of key/value pairs")
        decoded_dict = dict(
            (k.decode("utf-8") if decode_keys_as_utf8 else k, v)
            for k, v in _pairwise(keys_and_values)
        )
        return decoded_dict
    elif kind == _B_END and file_object.tell() > 0:
        return None
    elif kind in _DIGITS:
        str_len_bytes = kind
        while True:
            c = file_object.read(1)
            if not c:
                raise create_ex("EOF, expecting more string len")
            if c in _DIGITS:
                str_len_bytes += c
            elif c == b":":
                break
            else:
                raise create_ex(
                    "Unexpected input while reading string length: " + repr(c)
                )
        try:
            str_len = int(str_len_bytes.decode())
        except Exception:
            raise create_ex("Unable to parse bytestring length")
        bytestring = file_object.read(str_len)
        if len(bytestring) != str_len:
            raise create_ex(f"Read only {len(bytestring)} bytes, {str_len} wanted")
        return bytestring
    else:
        raise create_ex(f"Unexpected data type ({repr(kind)})")


def _bencode_int(value):
    return _B_INT + str(value).encode("utf-8") + _B_END


def _bencode_bytes(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return str(len(value)).encode("utf-8") + b":" + value


def _bencode_list(value):
    return _B_LIST + b"".join(_bencode(item) for item in value) + _B_END


def _bencode_dict(value):
    dict_keys = sorted(value.keys())
    return (
        _B_DICT
        + b"".join(_bencode_bytes(key) + _bencode(value[key]) for key in dict_keys)
        + _B_END
    )


def _bencode(value):
    if isinstance(value, int):
        return _bencode_int(value)
    elif isinstance(value, (str, bytes)):
        return _bencode_bytes(value)
    elif isinstance(value, list):
        return _bencode_list(value)
    elif isinstance(value, dict):
        return _bencode_dict(value)
    raise BencodeException(f"Unsupported type {type(value)}")


# The functions call themselves
encode = _bencode
decode = _bencode_decode
