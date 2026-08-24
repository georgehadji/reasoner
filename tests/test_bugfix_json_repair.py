import pytest

from reasoner.parsing import ParseError, extract_json


def test_extract_json_iterative_repair_key_cutoff():
    """
    Tests that the robust backtracking JSON repair can handle a response
    that was truncated right after a key name started (mid-string or immediately after the quote).
    """
    # Truncated right after "action
    truncated_json = '''```json
{
  "causal_chain": [
    {
      "step": 1,
      "action'''

    result = extract_json(truncated_json)

    # We expect it to drop the `"action` part by backtracking to the last comma,
    # and then cleanly close the array and object.
    assert "causal_chain" in result
    assert isinstance(result["causal_chain"], list)
    assert len(result["causal_chain"]) == 1
    assert result["causal_chain"][0]["step"] == 1
    assert "action" not in result["causal_chain"][0]

def test_extract_json_deeply_nested_truncation():
    """
    Tests deeply nested JSON truncation where trailing incomplete pairs must be chopped.
    """
    truncated_json = '{"a": 1, "b": {"c": 2, "d": {"e": 3, "f'
    result = extract_json(truncated_json)

    assert result["a"] == 1
    assert result["b"]["c"] == 2
    assert result["b"]["d"]["e"] == 3
    assert "f" not in result["b"]["d"]

def test_extract_json_completely_broken_salvages_partial():
    """
    Ensures that if the JSON ends in unrepairable garbage, the fallback loop
    successfully chops it back to the last valid comma boundary and salvages partial data.
    """
    bad_json = '{"a": 1, "b": [ just some random prose that broke the generation'
    result = extract_json(bad_json)

    # It should chop back to `{"a": 1` and repair it.
    assert result == {"a": 1}

def test_extract_json_mid_array_string_truncation():
    """
    Regression test: JSON is truncated inside a string which is itself inside an array.
    This simulates the "massive Greek URL" failure.
    """
    truncated_json = '''{
  "claims": [
    {
      "claim_id": "C1",
      "supporting_sources": [
        "https://example.com/very-long-url-that-gets-cut-off-'''

    result = extract_json(truncated_json)

    # It should backtrack to the opening bracket of the array and close it.
    assert "claims" in result
    assert result["claims"][0]["claim_id"] == "C1"
    assert result["claims"][0]["supporting_sources"] == []

def test_extract_json_unrecoverable_raises_error():
    """
    Ensures that if the string has no valid JSON structure at all, it raises ParseError.
    """
    bad_json = 'just some random prose that broke the generation entirely'
    with pytest.raises(ParseError):
        extract_json(bad_json)
