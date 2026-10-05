"""Read the json5 documents of this repository with the standard library alone.

peppy reads an exposure with serde_json5. The tests of this repository run
where the pull request workflow installs pytest and nothing else, so every
test reads the documents with this module. `exposure_documents` finds the
exposures of a checkout, `read_json5` reads one file, and `parse_json5` reads
a text. A test reads the structure of a document, never its text. A regular
expression cannot cut one tool entry out of a document, because the entries
nest braces (`restrict`, `representation`). It also misses the forms of
json5 that it does not expect, such as a quoted key or a string in single
quotes.

`parse_json5` reads these forms of json5:

- objects with bare or quoted keys, and arrays, both with trailing commas;
- strings in single or double quotes;
- decimal numbers, a sign, an exponent and a leading or trailing decimal
  point included;
- true, false and null.

It reads white space and comments as serde_json5 does, and it refuses what
serde_json5 refuses:

- a number with a leading zero;
- a `/*` comment that does not close;
- a character that json5 does not count as white space.

It also refuses forms that the documents do not use:

- a hexadecimal number, Infinity and NaN;
- a `\\u` or `\\x` escape;
- a string continued on the next line.

Each refusal raises Json5Error, which says where the reader stopped. So a
document that the reader cannot read fails its test, and no test passes a
document that peppy refuses to read.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# The schema of an MCP exposure document.
EXPOSURE_SCHEMA = "mcp_exposure/v1"
# Directories that hold no document of this repository.
_SKIP_DIRS = frozenset({".git", ".peppy", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"})

# The characters that end a line in json5: they end a `//` comment, and a
# string does not hold one.
_LINE_TERMINATORS = "\n\r\u2028\u2029"
_LINE_TERMINATOR = re.compile(f"[{_LINE_TERMINATORS}]")
# The white space of json5 that is not a line terminator or a space
# separator (Unicode category Zs). That is tab, vertical tab, form feed and
# the byte order mark.
_SPACE = "\t\v\f\ufeff"
_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}
# The escapes `_unescape` does not read as json5 does: each would give a wrong
# text, so `parse_json5` refuses a string that holds one.
_UNREAD_ESCAPES = frozenset("bfv0123456789xu" + _LINE_TERMINATORS)
_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
# A decimal number of json5: its integer part is 0 or has no leading zero.
_NUMBER = re.compile(r"[+-]?(?:(?:0|[1-9]\d*)(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_LITERALS = {"true": True, "false": False, "null": None}


class Json5Error(ValueError):
    """A document that `parse_json5` does not read, with where it stopped."""


def exposure_documents(root: Path) -> list[Path]:
    """Every json5 document under `root` whose schema is an MCP exposure,
    listed in the repository index or not. A rule of the tests holds for
    any document that could be published. Raises Json5Error, naming the
    file, for a json5 document this module does not read."""
    found = []
    for path in sorted(root.rglob("*.json5")):
        if _SKIP_DIRS.intersection(path.relative_to(root).parts):
            continue
        document = read_json5(path)
        if isinstance(document, dict) and document.get("peppy_schema") == EXPOSURE_SCHEMA:
            found.append(path)
    return found


def read_json5(path: Path) -> object:
    """The value of the json5 document at `path`, as `parse_json5` gives it.
    Raises Json5Error, naming the file, for a form this module does not
    read."""
    try:
        return parse_json5(path.read_text(encoding="utf-8"))
    except Json5Error as error:
        raise Json5Error(f"{path}: {error}") from error


def parse_json5(text: str) -> object:
    """The value the json5 document `text` holds. An object is a dict whose
    keys keep their document order, an array is a list, and a number is an
    int or a float. Raises Json5Error for a form this module does not read,
    and for an object that holds one key twice, which peppy refuses too."""
    reader = _Reader(_strip_comments(text))
    value = reader.read_value()
    reader.read_end()
    return value


def _strip_comments(text: str) -> str:
    """The document with each `/* */` comment read as one space, and each
    `//` comment read as nothing up to the end of its line. So a comment
    separates what stands on its two sides, as in serde_json5. String
    contents are kept as they are, comment markers inside them included.
    Raises Json5Error for a `/*` comment that does not close."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            end = _LINE_TERMINATOR.search(text, i)
            i = n if end is None else end.start()
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            if j < 0:
                raise Json5Error(f"expected `*/` to close the comment at offset {i}")
            out.append(" ")
            i = j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _unescape(body: str) -> str:
    """The text of a string literal's body: `\\"` reads as `"`, `\\\\` as
    `\\`, and the whitespace escapes as the whitespace they name."""
    return _ESCAPE.sub(lambda m: _ESCAPES.get(m.group(1), m.group(1)), body)


class _Reader:
    """A cursor over comment-free json5 text."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def read_value(self) -> object:
        self._skip_space()
        char = self.text[self.pos : self.pos + 1]
        if char == "{":
            return self._read_object()
        if char == "[":
            return self._read_array()
        if char and char in "\"'":
            return self._read_string()
        number = _NUMBER.match(self.text, self.pos)
        if number:
            self.pos = number.end()
            return _number(number.group())
        word = _IDENTIFIER.match(self.text, self.pos)
        if word and word.group() in _LITERALS:
            self.pos = word.end()
            return _LITERALS[word.group()]
        raise self._error("a value")

    def read_end(self) -> None:
        self._skip_space()
        if self.pos < len(self.text):
            raise self._error("the end of the document")

    def _read_object(self) -> dict[str, object]:
        self.pos += 1
        members: dict[str, object] = {}
        while not self._read_char("}"):
            key = self._read_key()
            if key in members:
                raise self._error(f"a key other than {key!r}, which the object already holds")
            self._require_char(":")
            members[key] = self.read_value()
            if not self._read_char(","):
                self._require_char("}")
                break
        return members

    def _read_array(self) -> list[object]:
        self.pos += 1
        items: list[object] = []
        while not self._read_char("]"):
            items.append(self.read_value())
            if not self._read_char(","):
                self._require_char("]")
                break
        return items

    def _read_key(self) -> str:
        self._skip_space()
        if self.text[self.pos : self.pos + 1] in ("\"", "'"):
            return self._read_string()
        word = _IDENTIFIER.match(self.text, self.pos)
        if not word:
            raise self._error("a key")
        self.pos = word.end()
        return word.group()

    def _read_string(self) -> str:
        quote = self.text[self.pos]
        end = self.pos + 1
        while end < len(self.text) and self.text[end] != quote:
            if self.text[end] in _LINE_TERMINATORS:
                raise self._error(f"a closing {quote} on the line the string opens")
            if self.text[end] == "\\":
                if self.text[end + 1 : end + 2] in _UNREAD_ESCAPES:
                    raise self._error("an escape other than \\n, \\t, \\r or a quoted character")
                end += 2
            else:
                end += 1
        if end >= len(self.text):
            raise self._error(f"a closing {quote}")
        body = self.text[self.pos + 1 : end]
        self.pos = end + 1
        return _unescape(body)

    def _read_char(self, char: str) -> bool:
        """Whether the next character after any space is `char`, read if so."""
        self._skip_space()
        if self.text.startswith(char, self.pos):
            self.pos += 1
            return True
        return False

    def _require_char(self, char: str) -> None:
        if not self._read_char(char):
            raise self._error(f"`{char}`")

    def _skip_space(self) -> None:
        """Move past the white space of json5, a byte order mark included."""
        while self.pos < len(self.text) and _is_space(self.text[self.pos]):
            self.pos += 1

    def _error(self, expected: str) -> Json5Error:
        near = self.text[self.pos : self.pos + 40]
        return Json5Error(f"expected {expected} at offset {self.pos} of the comment-free text, near {near!r}")


def _is_space(char: str) -> bool:
    """Whether `char` is white space in json5."""
    return char in _SPACE or char in _LINE_TERMINATORS or unicodedata.category(char) == "Zs"


def _number(literal: str) -> int | float:
    if any(mark in literal for mark in ".eE"):
        return float(literal)
    return int(literal)
