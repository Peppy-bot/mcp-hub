"""Read the json5 documents of this repository with the standard library alone.

peppy reads an exposure with serde_json5. The tests of this repository run
where the pull request workflow installs pytest and nothing else, so they read
the documents with this module: `strip_comments` and `unescape` for a test
that looks at the text, and `parse_json5` for a test that needs the document's
structure, such as which tool of which target has which operation. A regular
expression cannot cut one tool entry out of a document, because the entries
nest braces (`restrict`, `representation`).

`parse_json5` reads the part of json5 that the documents use: objects with
bare or quoted keys, arrays, trailing commas, strings in single or double
quotes, decimal numbers, true, false and null. Anything else (a hexadecimal
number, Infinity, NaN, a `\\u` or `\\x` escape, a string continued on the next
line) raises Json5Error, which says where the reader stopped. So a document
that the reader cannot read fails its test, and no test passes a document it
did not read.
"""

from __future__ import annotations

import re

_ESCAPE = re.compile(r"\\(.)")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}
# The escapes `unescape` does not read as json5 does: each would give a wrong
# text, so `parse_json5` refuses a string that holds one.
_UNREAD_ESCAPES = frozenset("bfv0123456789xu\n\r")
_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_LITERALS = {"true": True, "false": False, "null": None}


class Json5Error(ValueError):
    """A document that `parse_json5` does not read, with where it stopped."""


def strip_comments(text: str) -> str:
    """The document without its `//` and `/* */` comments. String contents
    are kept as they are, comment markers inside them included."""
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
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def unescape(body: str) -> str:
    """The text of a string literal's body: `\\"` reads as `"`, `\\\\` as
    `\\`, and the whitespace escapes as the whitespace they name."""
    return _ESCAPE.sub(lambda m: _ESCAPES.get(m.group(1), m.group(1)), body)


def parse_json5(text: str) -> object:
    """The value the json5 document `text` holds: an object as a dict whose
    keys keep their document order, an array as a list, a number as an int
    or a float. Raises Json5Error for a form this module does not read, and
    for an object that holds one key twice, which serde_json5 refuses too."""
    reader = _Reader(strip_comments(text))
    value = reader.read_value()
    reader.read_end()
    return value


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
            if self.text[end] in "\n\r":
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
        return unescape(body)

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
        """Move past white space, a byte order mark included."""
        while self.pos < len(self.text) and _is_space(self.text[self.pos]):
            self.pos += 1

    def _error(self, expected: str) -> Json5Error:
        near = self.text[self.pos : self.pos + 40]
        return Json5Error(f"expected {expected} at offset {self.pos} of the comment-free text, near {near!r}")


def _is_space(char: str) -> bool:
    return char.isspace() or char == "﻿"


def _number(literal: str) -> int | float:
    if any(mark in literal for mark in ".eE"):
        return float(literal)
    return int(literal)
