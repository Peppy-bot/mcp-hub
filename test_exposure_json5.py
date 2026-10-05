"""The json5 reader the tests of this repository share: it reads the forms
the exposure documents use, and refuses every other form instead of reading
it wrong."""

from __future__ import annotations

import pytest

from exposure_json5 import Json5Error, parse_json5


def test_strings_keep_their_comment_markers() -> None:
    assert parse_json5('{ a: "http://x", b: 1 /* c */ } // d') == {"a": "http://x", "b": 1}
    assert parse_json5("{ a: 'it\\'s // not /* a */ comment' }") == {"a": "it's // not /* a */ comment"}


def test_escapes_read_as_the_text_they_name() -> None:
    document = '{ a: "say \\"hi\\"\\n\\tit\\\'s \\\\ done" }'
    assert parse_json5(document) == {"a": "say \"hi\"\n\tit's \\ done"}


def test_the_forms_the_documents_use_are_read() -> None:
    document = """// A comment before the document.
    {
      bare: 1,
      "double": "x // not a comment",
      'single': 'it\\'s',
      /* a block comment */ nested: { list: [true, false, null, -2.5e1, .5, 3.,], empty: {}, none: [] },
      quoted: "say \\"hi\\"",
    }"""
    assert parse_json5(document) == {
        "bare": 1,
        "double": "x // not a comment",
        "single": "it's",
        "nested": {"list": [True, False, None, -25.0, 0.5, 3.0], "empty": {}, "none": []},
        "quoted": 'say "hi"',
    }


def test_a_comment_separates_what_stands_on_its_two_sides() -> None:
    assert parse_json5("{ a: [1/* c */,2] }") == {"a": [1, 2]}
    for terminator in ("\n", "\r", "\u2028", "\u2029"):
        assert parse_json5(f"{{ a: 1 // c{terminator}, b: 2 }}") == {"a": 1, "b": 2}


def test_the_white_space_of_json5_is_read() -> None:
    # A byte order mark, tab, vertical tab, form feed, a no-break space, an
    # ideographic space (a space separator) and the two Unicode line
    # terminators.
    document = "\ufeff{\ta:\v1,\f b:\xa0 2,\u3000c:\u2028 3\u2029}"
    assert parse_json5(document) == {"a": 1, "b": 2, "c": 3}


def test_a_number_has_a_leading_zero_only_when_its_integer_part_is_zero() -> None:
    assert parse_json5("[0, -0, 0.5, 0e1, 10, 1.]") == [0, 0, 0.5, 0.0, 10, 1.0]


def test_an_object_keeps_the_order_of_its_keys() -> None:
    assert list(parse_json5("{ b: 1, a: 2, c: 3 }")) == ["b", "a", "c"]


def test_an_int_stays_an_int() -> None:
    assert parse_json5("[7, -7, +7]") == [7, -7, 7]
    assert all(type(value) is int for value in parse_json5("[7, -7, +7]"))


@pytest.mark.parametrize(
    "document",
    [
        "{ a: 0x10 }",
        "{ a: Infinity }",
        "{ a: NaN }",
        "{ a: 1 } trailing",
        "{ a: 1, a: 2 }",
        '{ a: "\\u0041" }',
        '{ a: "line \\\n continued" }',
        '{ a: "open }',
        "{ a: 'two\nlines' }",
        "{ a 1 }",
        "{ a: 1 b: 2 }",
        "[1 2]",
        "{ 1a: 1 }",
        "",
        "{ a: 007 }",
        "[00]",
        "[01.5]",
        "{ a: 1 } /* open",
        "{ a: -/* c */1 }",
        "{ a: tr/* c */ue }",
        "{\x1ca: 1 }",
        "{\x85a: 1 }",
        '{ a: "x\u2028y" }',
        '{ a: "x\\\u2028y" }',
    ],
)
def test_a_form_the_reader_does_not_read_is_refused(document: str) -> None:
    with pytest.raises(Json5Error):
        parse_json5(document)
