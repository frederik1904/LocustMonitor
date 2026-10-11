import pytest

from perfmon.template import TemplateError, render, render_any


def test_substitutes_names_and_dotted_paths():
    context = {"id": 7, "user": {"name": "ada", "tags": ["a", "b"]}}
    assert render("/u/{{id}}/{{ user.name }}/{{user.tags.1}}", context) == "/u/7/ada/b"


def test_non_strings_are_written_as_json_and_nothing_is_escaped():
    body = render('{"ok": {{flag}}, "n": {{none}}, "s": "{{text}}"}', {"flag": True, "none": None, "text": "<a&b>"})
    assert body == '{"ok": true, "n": null, "s": "<a&b>"}'


def test_missing_names_are_all_reported():
    with pytest.raises(TemplateError, match="no value for: a, b.c"):
        render("{{a}} {{b.c}} {{a}}", {"b": {}})


def test_builtins():
    first, second = render("{{$uuid}}", {}), render("{{$uuid}}", {})
    assert len(first) == 36 and first != second
    assert render("{{$timestamp}}", {}).isdigit()


def test_render_any_walks_nested_structures():
    assert render_any({"h": "Bearer {{t}}", "l": ["{{t}}", 1]}, {"t": "x"}) == {"h": "Bearer x", "l": ["x", 1]}
