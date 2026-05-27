import json
import os
import pathlib
import urllib.error
import urllib.request


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


def main() -> None:
    token_payload = post_json("/api/auth/login", {"login": ADMIN_LOGIN, "password": ADMIN_PASS})
    token = token_payload["access_token"]

    for file_path in sorted(SEED_DIR.glob("*.md")):
        content = file_path.read_text(encoding="utf-8")
        payload = {
            "title": file_path.stem.replace("_", " ").title(),
            "content": content,
            "source_uri": f"seed://{file_path.name}",
            "metadata_json": {"domain": "project-management", "seed": True},
        }
        result = post_json("/api/knowledge/upload", payload, token=token)
        print(f"indexed: {result['title']} ({result['id']})")


if __name__ == "__main__":
    main()
