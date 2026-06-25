"""Tests for the Bedrock Vision describer factory (Requirement 7).

The Bedrock client is mocked, so no AWS is needed. Verifies:
  * Converse is called with the image content block (PNG bytes) + prompt
  * the response text is extracted and returned
  * the configured model id is used
"""

from unittest.mock import MagicMock

from vision import make_bedrock_vision_describer, VISION_PROMPT


def _mock_bedrock(text="A block diagram with signals PClkBufIn (input), PClkBufOut (output)."):
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": text}]}}
    }
    return client


def test_describer_returns_text_and_calls_converse_with_image():
    client = _mock_bedrock()
    describe = make_bedrock_vision_describer(
        bedrock_client=client, model_id="test-model-id"
    )
    out = describe(b"\x89PNG-bytes")

    assert "PClkBufIn" in out
    client.converse.assert_called_once()
    kwargs = client.converse.call_args.kwargs
    assert kwargs["modelId"] == "test-model-id"
    content = kwargs["messages"][0]["content"]
    # One text block (the prompt) + one image block carrying the PNG bytes.
    assert any(b.get("text") == VISION_PROMPT for b in content)
    image_blocks = [b for b in content if "image" in b]
    assert len(image_blocks) == 1
    assert image_blocks[0]["image"]["format"] == "png"
    assert image_blocks[0]["image"]["source"]["bytes"] == b"\x89PNG-bytes"


def test_describer_concatenates_multiple_text_parts():
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": "part1 "}, {"text": "part2"}]}}
    }
    describe = make_bedrock_vision_describer(bedrock_client=client)
    assert describe(b"png") == "part1 part2"


def test_describer_propagates_bedrock_error():
    client = MagicMock()
    client.converse.side_effect = RuntimeError("throttled")
    describe = make_bedrock_vision_describer(bedrock_client=client)
    try:
        describe(b"png")
        assert False, "expected the Bedrock error to propagate"
    except RuntimeError as exc:
        assert "throttled" in str(exc)
