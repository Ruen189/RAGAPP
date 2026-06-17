from urllib.parse import quote


def content_disposition_attachment(file_name: str) -> str:
    """Build a Content-Disposition header safe for non-ASCII filenames."""
    try:
        file_name.encode("latin-1")
        return f'attachment; filename="{file_name}"'
    except UnicodeEncodeError:
        ascii_fallback = "".join(char if ord(char) < 128 else "_" for char in file_name).strip("._") or "download"
        encoded_name = quote(file_name, safe="")
        return f"attachment; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_name}"
