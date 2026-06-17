from app.http_headers import content_disposition_attachment


def test_content_disposition_ascii_filename():
    header = content_disposition_attachment("guide.txt")
    assert header == 'attachment; filename="guide.txt"'


def test_content_disposition_unicode_filename():
    header = content_disposition_attachment("ГОСТ 7.32-2017.pdf")
    assert header.startswith("attachment; filename=")
    assert "filename*=UTF-8''" in header
    assert "%D0%93%D0%9E%D0%A1%D0%A2%207.32-2017.pdf" in header
