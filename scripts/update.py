#!/usr/bin/env python3
"""Build TVBox multi-depot subscriptions without merging spider dependencies."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
import datetime
import json
import os
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config" / "sources.json"
OUTPUT_DIR = Path(os.environ.get("TVBOX_OUTPUT_DIR", ROOT / "output"))
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT = (8, 25)
WORKERS = 4


def idn_encode(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host + (f":{parsed.port}" if parsed.port else "")
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def parse_lenient(text):
    text = text.lstrip("\ufeff").strip()
    text = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )
    return json.loads(text, strict=False)


def valid_single_depot(data):
    return (
        isinstance(data, dict)
        and isinstance(data.get("sites"), list)
        and len(data["sites"]) > 0
    )


def absolutize(value, base_url):
    """Keep cached configs usable by resolving relative dependency paths."""
    if isinstance(value, dict):
        return {key: absolutize(item, base_url) for key, item in value.items()}
    if isinstance(value, list):
        return [absolutize(item, base_url) for item in value]
    if isinstance(value, str) and value.startswith(("./", "../")):
        if ";md5;" in value:
            path, suffix = value.split(";md5;", 1)
            return f"{urljoin(base_url, path)};md5;{suffix}"
        return urljoin(base_url, value)
    return value


def fetch_one(url):
    target = idn_encode(url)
    last_error = None
    for attempt in range(2):
        try:
            response = requests.get(
                target,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json,text/plain,*/*",
                },
                timeout=TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()
            if len(response.content) > MAX_BYTES:
                raise ValueError("配置超过 8 MiB，已停止处理")
            data = parse_lenient(response.text)
            if not valid_single_depot(data):
                raise ValueError("返回内容不是含非空 sites 的单仓配置")
            return absolutize(data, response.url), response.url, None
        except Exception as exc:  # Network and upstream format errors are source-local.
            last_error = f"{type(exc).__name__}: {str(exc)[:240]}"
            if attempt == 0:
                time.sleep(1)
    return None, None, last_error


def read_cache(source_id):
    path = OUTPUT_DIR / f"{source_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if valid_single_depot(data) else None
    except (OSError, ValueError):
        return None


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def public_base_url():
    configured = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    repo = os.environ.get("GITHUB_REPOSITORY", "YOUR_NAME/tvbox-config")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/output"


def process_source(source):
    source_id = source["id"]
    errors = []
    for url in source.get("urls", []):
        data, final_url, error = fetch_one(url)
        if data is not None:
            atomic_write(OUTPUT_DIR / f"{source_id}.json", data)
            return {
                "id": source_id,
                "name": source["name"],
                "project": source.get("project", "independent"),
                "category": source.get("category", "general"),
                "recommended": bool(source.get("recommended")),
                "status": "fresh",
                "used_url": url,
                "final_url": final_url,
            }
        errors.append({"url": url, "error": error})

    cached = read_cache(source_id)
    if cached is not None:
        return {
            "id": source_id,
            "name": source["name"],
            "project": source.get("project", "independent"),
            "category": source.get("category", "general"),
            "recommended": bool(source.get("recommended")),
            "status": "cached",
            "errors": errors,
        }

    return {
        "id": source_id,
        "name": source["name"],
        "project": source.get("project", "independent"),
        "category": source.get("category", "general"),
        "recommended": bool(source.get("recommended")),
        "status": "failed",
        "errors": errors,
    }


def subscription(entries, base_url):
    return {
        "urls": [
            {
                "name": entry["name"] + ("（缓存）" if entry["status"] == "cached" else ""),
                "url": f"{base_url}/{entry['id']}.json",
            }
            for entry in entries
        ]
    }


def main():
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    sources = config.get("sources", [])
    if not sources:
        raise SystemExit("config/sources.json 中没有配置源")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(process_source, source): source for source in sources}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"[{result['status'].upper()}] {result['name']}", flush=True)

    order = {source["id"]: index for index, source in enumerate(sources)}
    results.sort(key=lambda item: order[item["id"]])
    usable = [item for item in results if item["status"] in ("fresh", "cached")]
    recommended = [item for item in usable if item["recommended"]]
    qist = [item for item in usable if item["project"] == "qist"]
    adult = [item for item in usable if item["category"] == "adult"]
    issue = [item for item in usable if item["category"] == "issue"]

    if not usable:
        atomic_write(OUTPUT_DIR / "status.json", {"sources": results})
        raise SystemExit("没有可用的新配置或缓存，保留旧订阅并返回失败")

    base_url = public_base_url()
    atomic_write(OUTPUT_DIR / "subscription.json", subscription(recommended, base_url))
    atomic_write(OUTPUT_DIR / "qist-all.json", subscription(qist, base_url))
    atomic_write(OUTPUT_DIR / "subscription-adult.json", subscription(adult, base_url))
    atomic_write(OUTPUT_DIR / "subscription-issue.json", subscription(issue, base_url))
    atomic_write(OUTPUT_DIR / "subscription-full.json", subscription(usable, base_url))
    atomic_write(
        OUTPUT_DIR / "status.json",
        {
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "public_base_url": base_url,
            "summary": {
                "fresh": sum(item["status"] == "fresh" for item in results),
                "cached": sum(item["status"] == "cached" for item in results),
                "failed": sum(item["status"] == "failed" for item in results),
            },
            "sources": results,
        },
    )
    print(
        f"完成：{len(recommended)} 个推荐仓，{len(qist)} 个 Qist 仓，"
        f"共 {len(usable)} 个可用仓。",
        flush=True,
    )


if __name__ == "__main__":
    main()
