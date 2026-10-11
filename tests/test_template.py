import json

import pytest

from perfmon.template import TemplateError, placeholders, render, render_json, render_mapping, render_optional


def test_substitutes_names_and_dotted_paths():
    context = {"id": 7, "user": {"name": "ada", "tags": ["a", "b"]}}
    assert render("/u/{{id}}/{{ user.name }}/{{user.tags.1}}", context) == "/u/7/ada/b"


def test_non_strings_are_written_as_json_and_nothing_is_escaped():
    body = render('{"ok": {{flag}}, "l": {{items}}, "s": "{{text}}"}', {"flag": True, "items": ["a"], "text": "<a&b>"})
    assert body == '{"ok": true, "l": ["a"], "s": "<a&b>"}'


def test_missing_names_are_all_reported():
    with pytest.raises(TemplateError, match="no value for: a, b.c"):
        render("{{a}} {{b.c}} {{a}}", {"b": {}})


def test_builtins():
    first, second = render("{{$uuid}}", {}), render("{{$uuid}}", {})
    assert len(first) == 36 and first != second
    assert render("{{$timestamp}}", {}).isdigit()


def test_null_is_an_error_where_nothing_can_be_left_out():
    with pytest.raises(TemplateError, match="style is null"):
        render("/beers/{{style}}/1", {"style": None})


def test_render_optional_leaves_out_a_whole_null_value():
    assert render_optional(" {{a}} ", {"a": None}) is None
    assert render_optional("{{a}}", {"a": "x"}) == "x"
    with pytest.raises(TemplateError, match="a is null"):
        render_optional("Bearer {{a}}", {"a": None})


def test_render_mapping_drops_null_entries_and_writes_literals_as_text():
    mapping = {"id": "{{id}}", "page": 2, "debug": True, "tag": "{{tag}}", "never": None}
    assert render_mapping(mapping, {"id": 7, "tag": None}) == {"id": "7", "page": "2", "debug": "true"}


def test_render_json_removes_keys_and_items_that_are_null():
    template = '{"a": {{a}}, "b": "{{b}}", "c": [1, {{a}}, "{{b}}"], "d": {"e": {{a}}, "f": "é"}}'
    assert json.loads(render_json(template, {"a": None, "b": None})) == {"c": [1], "d": {"f": "é"}}
    assert "é" in render_json(template, {"a": None, "b": None})


def test_render_json_leaves_the_text_alone_without_nulls():
    template = '{ "a":   {{a}} }'
    assert render_json(template, {"a": 1}) == '{ "a":   1 }'


@pytest.mark.parametrize("template", ['{"a": "x {{a}}"}', '{"a": "{{a}}{{a}}"}', "{{a}}"])
def test_render_json_rejects_null_inside_a_longer_value(template: str):
    with pytest.raises(TemplateError, match="a is null, which can only leave out a whole JSON value"):
        render_json(template, {"a": None})


@pytest.mark.parametrize("value", ['He said "hi"', "line1\nline2", "C:\\temp\\new", "tab\there", "blåbær ☕"])
def test_render_json_escapes_text_placed_inside_a_string(value: str):
    rendered = render_json('{"title": "{{v}}", "note": "about {{v}}!", "raw": {{n}}}', {"v": value, "n": "5"})
    assert json.loads(rendered) == {"title": value, "note": f"about {value}!", "raw": 5}


def test_render_json_escapes_non_text_values_inside_a_string_too():
    rendered = render_json('{"a": "tags={{tags}}", "b": {{tags}}, "c": "\\"{{n}}\\""}', {"tags": ["x"], "n": 1})
    assert json.loads(rendered) == {"a": 'tags=["x"]', "b": ["x"], "c": '"1"'}


def test_placeholders_lists_the_names_a_template_needs():
    assert placeholders("/{{a}}/{{ b.c }}?x={{a}}&t={{$uuid}}") == {"a", "b.c"}
