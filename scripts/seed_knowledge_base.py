import json
import mimetypes
import os
import pathlib
import urllib.error
import urllib.request
import uuid


API_BASE = os.getenv("API_BASE", "http://localhost:8000")
ADMIN_LOGIN = os.getenv("ADMIN_LOGIN", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin123")
SEED_DIR = pathlib.Path(os.getenv("SEED_DIR", "knowledge_seed"))


def post_json(path: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{API_BASE}{path}", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{path} failed: {exc.code} {body}") from exc


def post_file(path: str, file_path: pathlib.Path, token: str) -> dict:
    boundary = f"----RagAppBoundary{uuid.uuid4().hex}"
    file_bytes = file_path.read_bytes()
    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body = b"".join(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {token}",
    }
    request = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{path} failed: {exc.code} {body}") from exc


def main() -> None:
    token_payload = post_json("/api/auth/login", {"login": ADMIN_LOGIN, "password": ADMIN_PASS})
    token = token_payload["access_token"]

    for file_path in sorted(SEED_DIR.glob("*")):
        if file_path.suffix.lower() not in {".md", ".txt", ".docx", ".pdf"}:
            continue
        result = post_file("/api/knowledge/upload", file_path, token)
        print(f"indexed: {result['file_name']} ({result['id']})")


if __name__ == "__main__":
    main()
