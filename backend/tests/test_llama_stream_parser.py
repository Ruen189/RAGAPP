from app.services.llama_client import parse_llama_stream_line


def test_parse_llama_server_sse_json_line():
    assert parse_llama_stream_line('data: {"content":"Привет"}') == "Привет"


def test_parse_llama_server_plain_json_line():
    assert parse_llama_stream_line('{"token":"!"}') == "!"


def test_parse_llama_server_done_line():
    assert parse_llama_stream_line("data: [DONE]") == ""
