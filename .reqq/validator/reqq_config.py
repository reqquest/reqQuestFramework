# -*- coding: utf-8 -*-
"""Validation of config.yaml keys: language, id_prefix, short_title, enforce_layout, openapi."""
import re
from typing import Any, Dict

import reqq_common as C  # noqa: E402


# ISO 639-1 codes, from the Library of Congress ISO 639-2 code list (reqqf#81).
ISO_639_1 = frozenset("""
    aa ab ae af ak am an ar as av ay az ba be bg bi bm bn bo br bs ca ce ch co cr cs cu
    cv cy da de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he
    hi ho hr ht hu hy hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko
    kr ks ku kv kw ky la lb lg li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd
    ne ng nl nn no nr nv ny oc oj om or os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se
    sg si sk sl sm sn so sq sr ss st su sv sw ta te tg th ti tk tl tn to tr ts tt tw ty
    ug uk ur uz ve vi vo wa wo xh yi yo za zh zu
""".split())


def check_language(cfg: Dict[str, Any]) -> None:
    """Exit 3 when config.yaml sets `language` to anything but an ISO 639-1 code.

    The key declares the one language of requirements in the repo; a missing key means
    no declaration and no check (reqqf#81).
    """
    lang = cfg.get("language")
    if lang is not None and str(lang) not in ISO_639_1:
        C._die(3, f"config.yaml: language {lang!r} is not an ISO 639-1 code — "
                "use a lowercase two-letter code, e.g. en, pl")


def check_id_prefix(cfg: Dict[str, Any]) -> None:
    """Exit 3 when config.yaml sets `id_prefix` to anything but 2–6 uppercase letters.

    The key declares the prefix of every requirement ID in the repo; a missing key means
    IDs without a prefix (reqqf#94).
    """
    prefix = cfg.get("id_prefix")
    if prefix is not None and not re.fullmatch(C.ID_PREFIX_PATTERN, str(prefix)):
        C._die(3, f"config.yaml: id_prefix {str(prefix)!r} is not 2–6 uppercase letters A-Z — "
                "use the repository key, e.g. REQA")


def check_short_title(cfg: Dict[str, Any]) -> None:
    """Exit 3 when config.yaml sets `short_title` to anything but true or false.

    `true` requires the front-matter field `short_title` and the file name
    `<id>-<short_title>.md`; a missing key means false (reqqf#134).
    """
    value = cfg.get("short_title", False)
    if not isinstance(value, bool):
        C._die(3, f"config.yaml: short_title {value!r} is not true or false")


def check_enforce_layout(cfg: Dict[str, Any]) -> None:
    """Exit 3 when config.yaml sets `enforce_layout` to anything but true or false.

    `true` requires files under requirements/ to sit in the folder their ID and `type`
    point to, with a matching `category` (reqqf#102); a missing key means false.
    """
    value = cfg.get("enforce_layout", False)
    if not isinstance(value, bool):
        C._die(3, f"config.yaml: enforce_layout {value!r} is not true or false")


OPENAPI_VERSIONS = ("3.0", "3.1", "3.2")
OPENAPI_LEVELS = ("off", "warning", "error")
OPENAPI_DEFAULTS = {"version": "3.2", "level": "warning"}


def openapi_settings(cfg: Dict[str, Any]) -> Dict[str, str]:
    """`version` and `level` of the `openapi` key, with the defaults for what is not set."""
    given = cfg.get("openapi") or {}
    return {**OPENAPI_DEFAULTS, **{key: value for key, value in given.items() if value is not None}}


def check_openapi(cfg: Dict[str, Any]) -> None:
    """Exit 3 when config.yaml sets `openapi` to anything but a mapping of `version` (3.0, 3.1,
    3.2) and `level` (off, warning, error). A missing key or value means the default: 3.2 and
    warning (REQQF-FR-VALIDATION-100 story 8)."""
    value = cfg.get("openapi")
    if value is None:
        return
    if not isinstance(value, dict) or set(value) - set(OPENAPI_DEFAULTS):
        C._die(3, f"config.yaml: openapi {value!r} is not a mapping of version and level")
    settings = openapi_settings(cfg)
    if settings["version"] not in OPENAPI_VERSIONS:
        C._die(3, f"config.yaml: openapi.version {settings['version']!r} is not one of "
                f"{', '.join(OPENAPI_VERSIONS)}")
    if settings["level"] not in OPENAPI_LEVELS:
        C._die(3, f"config.yaml: openapi.level {settings['level']!r} is not one of "
                f"{', '.join(OPENAPI_LEVELS)}")
