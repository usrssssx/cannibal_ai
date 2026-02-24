from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx


def _load_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _write_env(path: Path, updates: dict[str, str]) -> None:
    lines = []
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen = set()
    for line in existing:
        if "=" in line and not line.lstrip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in updates:
                lines.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        lines.append(line)
    for key, value in updates.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _pick_https_url(payload: dict[str, Any]) -> str | None:
    tunnels = payload.get("tunnels") or []
    for tunnel in tunnels:
        if tunnel.get("proto") == "https":
            return tunnel.get("public_url")
    return None


def main() -> None:
    api_url = "http://127.0.0.1:4040/api/tunnels"
    response = httpx.get(api_url, timeout=5.0)
    response.raise_for_status()
    data = response.json()
    url = _pick_https_url(data)
    if not url:
        raise SystemExit("No https tunnel found in ngrok API.")

    env_path = Path(".env")
    _write_env(env_path, {"WEBAPP_URL": url})
    print(url)


if __name__ == "__main__":
    main()
