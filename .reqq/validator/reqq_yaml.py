# -*- coding: utf-8 -*-
"""YAML loading for front matter and config files, on PyYAML's `BaseLoader`.

Every scalar stays text, except `true` and `false` in any case, which become booleans, and an
omitted value (`key:`), which becomes None; `key: ""` stays an empty string. Anchors and
aliases are rejected: an alias chain expands exponentially, and this text arrives in pull
requests. `load` reads a document, `load_typed` an OpenAPI fragment, `duplicate_keys` finds
the keys `load` would silently drop."""
import contextlib
import json
import sys
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    print("✖ PyYAML is not installed. Install the validator dependencies with: "
          "python3 -m pip install -r .reqq/validator/requirements.txt "
          "(on a system Python, in an active virtual environment)", file=sys.stderr)
    sys.exit(3)


class YamlError(ValueError):
    """The text is not valid YAML, or its root is not a mapping; `line` is the line of the
    problem in the text (from 1) when the parser marks one."""

    def __init__(self, message: str, line: Optional[int] = None):
        super().__init__(message)
        self.line = line


class _NoAnchors:
    """Loader mixin that refuses anchors and aliases."""

    def compose_node(self, parent, index):
        event = self.peek_event()
        if event.anchor is not None:
            raise yaml.MarkedYAMLError(problem="anchors and aliases are not supported",
                                       problem_mark=event.start_mark)
        return super().compose_node(parent, index)


class _Loader(_NoAnchors, yaml.BaseLoader):
    """BaseLoader that tells an omitted value (`key:`) from an empty string (`key: ""`)
    and refuses anchors and aliases."""

    def construct_scalar(self, node):
        text = super().construct_scalar(node)
        return None if text == "" and node.style is None else text


def _describe(error: yaml.YAMLError) -> str:
    """The problem and its position, without PyYAML's excerpt of the source."""
    problem = getattr(error, "problem", None) or str(error)
    mark = getattr(error, "problem_mark", None)
    return f"{problem} (line {mark.line + 1}, column {mark.column + 1})" if mark else problem


@contextlib.contextmanager
def _translated_errors():
    """PyYAML's errors and a document nested beyond the recursion limit leave as YamlError."""
    try:
        yield
    except yaml.YAMLError as error:
        mark = getattr(error, "problem_mark", None)
        raise YamlError(_describe(error), mark.line + 1 if mark else None) from error
    except RecursionError as error:
        raise YamlError("the document is nested too deeply") from error


def _text(value: str) -> str:
    """`value` with each JSON-style surrogate pair (`"\\uD83D\\uDE00"`) combined into its
    character; YamlError for a surrogate that stays unpaired, which no output can encode."""
    try:
        return value.encode("utf-16-le", "surrogatepass").decode("utf-16-le")
    except UnicodeError as error:
        raise YamlError("the document holds an unpaired surrogate, which is not valid Unicode") from error


def _key(key: Optional[str]) -> str:
    """A mapping key as text; an empty key is a YamlError."""
    if key is None:
        raise YamlError("a mapping key must not be empty")
    return _text(key)


def _normalize(node: Any) -> Any:
    """Booleans for `true`/`false` in any case, at every depth; surrogate pairs combined,
    an unpaired surrogate raises YamlError."""
    if isinstance(node, dict):
        return {_key(key): _normalize(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_normalize(item) for item in node]
    if node is None:
        return None
    if node.lower() in ("true", "false"):
        return node.lower() == "true"
    return _text(node)


def load(text: str) -> Dict[str, Any]:
    """Parse a YAML mapping; an empty document gives `{}`.

    Raises YamlError for a syntax error, an anchor or alias, a document nested too deeply,
    an unpaired surrogate and a root that is not a mapping."""
    with _translated_errors():
        doc = yaml.load(text, Loader=_Loader)
        if doc is None:
            return {}
        if not isinstance(doc, dict):
            raise YamlError("the document root must be a mapping")
        return _normalize(doc)


class _TypedLoader(_NoAnchors, yaml.SafeLoader):
    """SafeLoader that refuses anchors and aliases."""


def load_typed(text: str) -> Dict[str, Any]:
    """Parse a YAML mapping with typed scalars, as JSON data: numbers stay numbers, and keys,
    dates and other non-JSON values become text (`201:` gives the key "201"). For OpenAPI
    fragments, whose schema needs both. An empty document gives `{}`.

    Raises YamlError like `load`."""
    with _translated_errors():
        doc = yaml.load(text, Loader=_TypedLoader)
        if doc is None:
            return {}
        if not isinstance(doc, dict):
            raise YamlError("the document root must be a mapping")
        return json.loads(json.dumps(doc, default=str))


def _repeated(node: Any, path: str) -> List[Tuple[str, str]]:
    """(path, key) of every key repeated within one mapping, at or below `node`."""
    if isinstance(node, yaml.SequenceNode):
        return [pair for n, item in enumerate(node.value) for pair in _repeated(item, f"{path}[{n}]")]
    if not isinstance(node, yaml.MappingNode):
        return []
    pairs = [(_text(key.value), value) for key, value in node.value if isinstance(key, yaml.ScalarNode)]
    counts = Counter(name for name, _ in pairs)
    out = [(path, name) for name, count in counts.items() if count > 1]
    for name, value in pairs:
        out += _repeated(value, f"{path}.{name}" if path else name)
    return out


def duplicate_keys(text: str) -> List[Tuple[str, str]]:
    """(path, key) of every key written twice in one mapping, at any depth; `load` hides
    it, the last one wins. Keys are compared by their parsed value, so quoting and escapes
    do not matter. `path` is the dotted path of the mapping, empty for the root."""
    with _translated_errors():
        return _repeated(yaml.compose(text, Loader=_Loader), "")
