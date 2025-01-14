import ast
from types import FrameType
from typing import Any, Optional, Tuple

from .. import info_variables, utils
from ..ft_gettext import current_lang, please_report
from ..message_parser import get_parser
from ..tb_data import TracebackData  # for type checking only
from ..typing_info import CauseInfo  # for type checking only

parser = get_parser(KeyError)
_ = current_lang.translate


@parser._add
def popitem_from_empty_dict(message: str, tb_data: TracebackData) -> CauseInfo:
    if "popitem(): dictionary is empty" not in message:
        return {}

    frame = tb_data.exception_frame
    name, _obj = find_empty_dict_like_obj(frame, tb_data.bad_line)
    if name is None:  # pragma: no cover
        cause = _(
            "You tried to retrieve an item from an empty `dict`\n"
            "or a similar object which I cannot identify.\n"
        )
        return {"cause": cause + please_report()}

    hint = _("`{name}` is an empty `dict`.\n").format(name=name)
    cause = _(
        "You tried to retrieve an item from `{name}` which is an empty `dict`.\n"
    ).format(name=name)
    return {"cause": cause, "suggest": hint}


@parser._add
def popitem_from_empty_chain_map(message: str, tb_data: TracebackData) -> CauseInfo:
    if "No keys found in the first mapping." not in message:
        return {}

    # The exception is not raised in the user's code, but inside the
    # collection module. Unlike essentially all the other cases,
    # we search the information from the frame calling frame, and not
    # the one where the exception was raised.
    name, _obj = find_empty_dict_like_obj(
        tb_data.program_stopped_frame, tb_data.program_stopped_bad_line
    )
    if name is None:  # pragma: no cover
        cause = _(
            "You tried to retrieve an item from an empty ChainMap\n"
            "or similar object which I cannot identify.\n"
        )
        return {"cause": cause + please_report()}

    hint = _("`{name}` is an empty `ChainMap`.\n").format(name=name)
    cause = _(
        "You tried to retrieve an item from `{name}` which is an empty `ChainMap`.\n"
    ).format(name=name)
    return {"cause": cause, "suggest": hint}


@parser._add
def missing_key_in_chain_map(message: str, tb_data: TracebackData) -> CauseInfo:
    """Missing keys in collections.ChainMap from using pop()
    can trigger a secondary exception with a different message.
    It turns out that this is this second message we capture
    while the correct "bad_line" is identified correctly.
    """
    if "Key not found in the first mapping: " not in message:
        return {}

    frame = tb_data.exception_frame
    value = tb_data.value
    key = value.args[0]
    if not (
        isinstance(key, str) and key.startswith("Key not found in the first mapping: ")
    ):
        return {}  # pragma: no cover

    key = key.replace("Key not found in the first mapping: ", "", 1)
    try:
        key = ast.literal_eval(key)
    except Exception:  # pragma: no cover  # noqa
        pass

    bad_line = tb_data.bad_line.strip()
    if bad_line.startswith("raise "):
        bad_line = tb_data.program_stopped_bad_line.strip()
        frame = tb_data.program_stopped_frame

    if str(key) in bad_line:
        cause = analyze_missing_key(key, frame, bad_line)
        if cause:
            return cause

    return {
        "cause": _(
            "Missing key `{key}` in a `ChainMap` or in a similar object.\n"
        ).format(key=key)
    }  # pragma: no cover


@parser._add
def missing_key_in_dict(_message: str, tb_data: TracebackData) -> CauseInfo:
    value = tb_data.value
    key = value.args[0]
    bad_line = tb_data.bad_line.strip()
    frame = tb_data.exception_frame
    if bad_line.startswith("raise "):
        return {}
    if str(key) not in bad_line:
        return {}

    return analyze_missing_key(key, frame, bad_line)


@parser._add
def missing_key_in_dict_like(_message: str, tb_data: TracebackData) -> CauseInfo:
    """Case where a KeyError is raised internally, from user code"""
    value = tb_data.value
    key = value.args[0]
    bad_line = tb_data.bad_line.strip()
    if not bad_line.startswith("raise "):
        return {}
    bad_line = tb_data.program_stopped_bad_line
    if str(key) not in bad_line:
        return {}
    frame = tb_data.program_stopped_frame

    return analyze_missing_key(key, frame, bad_line)


def analyze_missing_key(key: Any, frame: FrameType, bad_line: str) -> CauseInfo:
    name, obj = find_missing_key_obj(key, frame, bad_line)
    try:
        key_repr = repr(key)
    except Exception:  # noqa
        return {}
    if name is None:
        cause = _(
            "A `dict` or a similar object which I cannot identify\n"
            "does not have `{key}` as a key.\n"
        ).format(key=key_repr)
        return {"cause": cause}

    if isinstance(obj, dict):
        begin_cause = _(
            "The key `{key}` cannot be found in the dict `{name}`.\n"
        ).format(key=key_repr, name=name)
    else:
        obj_type = obj.__class__.__name__
        begin_cause = _(
            "The key `{key}` cannot be found in `{name}`, an object of type `{obj_type}`.\n"
        ).format(key=key_repr, name=name, obj_type=obj_type)

    if isinstance(key, str):
        result = key_is_a_string(key, name, obj)
        if result:
            result["cause"] = begin_cause + result["cause"]
            return result
    elif str(key) in obj.keys():
        additional = _(
            "`{name}` contains a string key which is identical to `str({key})`.\n"
            "Perhaps you forgot to convert the key into a string.\n"
        ).format(name=name, key=key)
        hint = _("Did you forget to convert `{key}` into a string?\n").format(key=key)
        return {"cause": begin_cause + additional, "suggest": hint}

    return {"cause": begin_cause}


def key_is_a_string(key: str, dict_name: str, obj: Any) -> CauseInfo:
    keys = [str(k) for k in obj.keys()]
    if key in keys:
        additional = _(
            "`{key}` is a string.\n"
            "There is a key of `{name}` whose string representation\n"
            "is identical to `{key}`.\n"
        ).format(key=repr(key), name=dict_name)
        hint = _("Did you convert `{key}` into a string by mistake?\n").format(key=key)
        return {"cause": additional, "suggest": hint}

    string_keys = [k for k in obj.keys() if isinstance(k, str)]
    similar = utils.get_similar_words(key, string_keys)
    similar = [repr(k) for k in similar]
    if len(similar) == 1:
        hint = _("Did you mean `{name}`?\n").format(name=similar[0])
        additional = _(
            "`{name}` is a key of `{dict_}` which is similar to `{key}`.\n"
        ).format(name=similar[0], dict_=dict_name, key=repr(key))
        return {"cause": additional, "suggest": hint}

    if similar:
        hint = _("Did you mean `{name}`?\n").format(name=similar[0])
        names = ", ".join(similar)
        additional = _(
            "`{name}` has some keys similar to `{key}` including:\n`{names}`.\n"
        ).format(name=dict_name, key=repr(key), names=names)
        return {"cause": additional, "suggest": hint}

    return {}


def find_empty_dict_like_obj(
    frame: FrameType, bad_line: str
) -> Tuple[Optional[str], Any]:
    all_objects = info_variables.get_all_objects(bad_line, frame)
    for name, obj in all_objects["name, obj"]:
        if hasattr(obj, "keys") and len(obj) == 0:
            return name, obj
    return None, None


def find_missing_key_obj(
    key: Any, frame: FrameType, bad_line: str
) -> Tuple[Optional[str], Any]:
    all_objects = info_variables.get_all_objects(bad_line, frame)
    for name, obj in all_objects["name, obj"]:
        if hasattr(obj, "keys") and key not in obj:
            return name, obj
    return None, None
