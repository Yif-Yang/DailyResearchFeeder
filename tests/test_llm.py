from dailyresearchfeeder.llm import ReasoningClient


def test_parse_json_object_tolerates_raw_newlines_in_strings() -> None:
    raw = '{"overview":"line1\nline2","takeaways":["a","b"]}'
    raw = raw.replace("\\n", "\n")

    payload = ReasoningClient._parse_json_object(raw)

    assert payload["overview"] == "line1 line2"
    assert payload["takeaways"] == ["a", "b"]