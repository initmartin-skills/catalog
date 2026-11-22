#!/usr/bin/env python3
"""Read public GitHub fork metadata. Never clone, import, or execute fork contents."""
import argparse
import base64
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
REPO = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+")
SHA = re.compile(r"[0-9a-f]{40}")
TAG = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")


class ScanError(RuntimeError):
    pass


class GitHub:
    def __init__(self, token=None):
        self.token = token
        self.requests = 0

    def get(self, path):
        if not path.startswith("/") or "://" in path:
            raise ScanError("Invalid API path")
        headers = {"Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "initmartin-skills-catalog"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        for attempt in range(3):
            if self.requests >= 4500:
                raise ScanError("Request budget reached; retry on the next scan")
            self.requests += 1
            try:
                with urlopen(Request("https://api.github.com" + path, headers=headers), timeout=30) as response:
                    return json.load(response)
            except HTTPError as exc:
                # Do not print request headers, credentials, response bodies or signed URLs.
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(min(20, 2 ** (attempt + 1)))
                    continue
                raise ScanError(f"GitHub HTTP {exc.code}") from None
            except (URLError, TimeoutError):
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise ScanError("GitHub connection failed") from None

    def pages(self, path):
        separator = "&" if "?" in path else "?"
        for page in range(1, 1001):
            rows = self.get(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(rows, list):
                raise ScanError("Expected a paginated repository list")
            yield from rows
            if len(rows) < 100:
                return
        raise ScanError("Repository pagination limit reached")


def clean(value, limit=500):
    if not isinstance(value, str):
        return ""
    return " ".join("".join(c if ord(c) >= 32 else " " for c in value).split())[:limit]


def metadata(text):
    """Read only top-level name/description scalar fields, never deserialize YAML objects."""
    lines = text.lstrip("\ufeff").splitlines()
    result = {}
    if not lines or lines[0].strip() != "---":
        return result
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        return result
    i = 1
    while i < end:
        match = re.match(r"^(name|description):\s*(.*)$", lines[i])
        if match:
            key, value = match.groups()
            if value in ("|", "|-", "|+", ">", ">-", ">+") or not value:
                continuation = []
                while i + 1 < end and (not lines[i + 1].strip() or lines[i + 1][0].isspace()):
                    i += 1
                    continuation.append(lines[i].strip())
                value = " ".join(continuation)
            elif value.startswith('"') and value.endswith('"'):
                try:
                    value = json.loads(value)
                except ValueError:
                    value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1].replace("''", "'")
            if value.startswith(("!", "&", "*", "[", "{")):
                value = ""  # unsupported YAML constructs fall back to repository metadata
            result[key] = clean(value, 100 if key == "name" else 500)
        i += 1
    return result


def safe_skill_path(path):
    return (isinstance(path, str) and path.endswith("SKILL.md")
            and PurePosixPath(path).name == "SKILL.md"
            and not path.startswith("/") and "\\" not in path and "?" not in path and "#" not in path
            and not any(part in ("", ".", "..") for part in path.split("/"))
            and not any(ord(c) < 32 for c in path))


def skill_files(api, repo, tree_sha, limit):
    recursive = api.get(f"/repos/{repo}/git/trees/{tree_sha}?recursive=1")
    if not recursive.get("truncated"):
        entries = recursive["tree"]
        if len(entries) > limit:
            raise ScanError("Repository tree exceeds configured limit")
    else:
        # Recursive Git trees can be truncated. Walk subtree objects instead of silently dropping skills.
        entries, queue, cache = [], [("", tree_sha)], {}
        while queue:
            prefix, sha = queue.pop()
            if sha not in cache:
                tree = api.get(f"/repos/{repo}/git/trees/{sha}")
                if tree.get("truncated"):
                    raise ScanError("A non-recursive subtree was truncated")
                cache[sha] = tree["tree"]
            for item in cache[sha]:
                item = dict(item, path=prefix + item["path"])
                entries.append(item)
                if len(entries) > limit:
                    raise ScanError("Repository tree exceeds configured limit")
                if item["type"] == "tree":
                    queue.append((item["path"] + "/", item["sha"]))
    return sorted((x for x in entries if x["type"] == "blob"
                   and x["mode"] in ("100644", "100755") and safe_skill_path(x["path"])),
                  key=lambda x: x["path"])


def scan_repository(api, listed, previous, config):
    full_name = listed["full_name"]
    if not REPO.fullmatch(full_name):
        raise ScanError("Invalid repository name")
    detail = api.get(f"/repos/{full_name}")
    if detail.get("private") or not detail.get("fork"):
        raise ScanError("Source is no longer a public fork")
    upstream = detail.get("parent", {}).get("full_name")
    if not isinstance(upstream, str) or not REPO.fullmatch(upstream):
        raise ScanError("Fork parent is unavailable")
    branch = quote(detail["default_branch"], safe="")
    head = api.get(f"/repos/{full_name}/git/ref/heads/{branch}")["object"]["sha"]
    if not SHA.fullmatch(head):
        raise ScanError("Invalid commit SHA")
    tree_sha = api.get(f"/repos/{full_name}/git/commits/{head}")["tree"]["sha"]
    old_skills = {s["path"]: s for s in (previous or {}).get("skills", [])}
    skills, metadata_errors = [], 0
    for item in skill_files(api, full_name, tree_sha, config["max_tree_entries"]):
        path = str(PurePosixPath(item["path"]).parent)
        old = old_skills.get(path, {})
        metadata_error = None
        if old.get("blob_sha") == item["sha"] and not old.get("metadata_error"):
            extracted = old.get("extracted", {})
        elif item.get("size", 0) > config["max_blob_bytes"]:
            extracted = {}
        else:
            try:
                blob = api.get(f"/repos/{full_name}/git/blobs/{item['sha']}")
                if blob.get("encoding") != "base64":
                    raise ScanError("Unsupported blob encoding")
                raw = base64.b64decode(blob["content"])
                extracted = metadata(raw.decode("utf-8", errors="replace")) if len(raw) <= config["max_blob_bytes"] else {}
            except (ScanError, ValueError) as exc:
                # Preserve partial progress in very large collections; retry failed blobs next time.
                extracted = old.get("extracted", {})
                metadata_error = clean(str(exc), 150)
                metadata_errors += 1
        license_id = (detail.get("license") or {}).get("spdx_id")
        license_id = license_id if license_id and license_id != "NOASSERTION" else "未识别；需核对来源许可"
        notes = "自动收录；尚未审阅或安装。许可证来自仓库元数据，采用前需核对具体技能。"
        if item.get("size", 0) > config["max_blob_bytes"]:
            notes += " 文件较大，未读取正文元数据。"
        skills.append({
            "id": f"gh-{detail['id']}-{hashlib.sha256(path.encode()).hexdigest()[:16]}",
            "repository_id": detail["id"], "blob_sha": item["sha"], "extracted": extracted,
            "metadata_error": metadata_error,
            "name": extracted.get("name") or (PurePosixPath(path).name if path != "." else detail["name"]),
            "summary": extracted.get("description") or clean(detail.get("description")) or "自动发现的技能，待补充用途说明。",
            "category": "inbox", "tags": ["auto-imported"] + [
                t for t in detail.get("topics", []) if TAG.fullmatch(t) and t != "auto-imported"][:10],
            "upstream": upstream, "fork": full_name, "path": path, "commit": head,
            "license": license_id, "status": "saved", "reviewed_at": None,
            "customized": False, "used_in": [], "notes": notes
        })
    return {"id": detail["id"], "full_name": full_name, "upstream": upstream,
            "head": head, "skills": skills, "available": True,
            "error": f"{metadata_errors} 个技能文件元数据暂未读取完整；下次继续" if metadata_errors else None,
            "signature": signature(listed)}


def signature(repo):
    return [repo.get(k) for k in ("full_name", "pushed_at", "updated_at", "default_branch")]


def discover(api, config, previous, today, refresh=False):
    owners = config.get("owners", [])
    if config.get("schema_version") != 1 or not owners:
        raise ScanError("Invalid sources.json")
    excluded = {s.lower() for s in config.get("exclude_repositories", [])}
    listed = {}
    for owner in owners:
        login = owner["login"]
        if not re.fullmatch(r"[A-Za-z0-9-]+", login) or owner["type"] not in ("org", "user"):
            raise ScanError("Invalid source owner")
        endpoint = f"/orgs/{login}/repos?type=public" if owner["type"] == "org" else f"/users/{login}/repos?type=owner"
        # A failed owner listing aborts before writing anything. It must never look like mass deletion.
        for repo in api.pages(endpoint):
            if repo.get("fork") and not repo.get("private") and repo["full_name"].lower() not in excluded:
                listed[str(repo["id"])] = repo
    previous = previous or {"repositories": {}}
    repos = {}
    report = {"checked_date": today, "forks": len(listed), "scanned": 0, "cached": 0, "errors": []}
    for rid, repo in sorted(listed.items()):
        old = previous.get("repositories", {}).get(rid)
        if old and old.get("available") and not old.get("error") and old.get("signature") == signature(repo) and not refresh:
            repos[rid] = copy.deepcopy(old)
            report["cached"] += 1
            continue
        try:
            repos[rid] = scan_repository(api, repo, old, config)
            report["scanned"] += 1
            if repos[rid].get("error"):
                report["errors"].append({"repo": repo["full_name"], "error": repos[rid]["error"]})
        except (ScanError, ValueError, KeyError) as exc:
            message = clean(str(exc), 150)
            repos[rid] = copy.deepcopy(old) if old else {
                "id": repo["id"], "full_name": repo["full_name"], "skills": [], "available": True}
            repos[rid]["error"] = message
            report["errors"].append({"repo": repo["full_name"], "error": message})
    owner_names = {o["login"].lower() for o in owners}
    for rid, old in previous.get("repositories", {}).items():
        name = old["full_name"].lower()
        if rid not in repos and name not in excluded and name.split("/")[0] in owner_names:
            repos[rid] = dict(copy.deepcopy(old), available=False, error="不在本次公开 Fork 列表中；保留上次记录")
    report["skills_found"] = sum(len(r.get("skills", [])) for r in repos.values())
    report["unavailable"] = sum(not r.get("available", True) for r in repos.values())
    snapshot = {"schema_version": 1, "checked_date": today, "repositories": repos}
    return snapshot, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="rescan even unchanged repositories")
    args = parser.parse_args()
    try:
        config = json.loads((ROOT / "sources.json").read_text())
        snapshot_path = ROOT / "discovered.json"
        previous = json.loads(snapshot_path.read_text()) if snapshot_path.exists() else None
        api = GitHub(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
        today = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        snapshot, report = discover(api, config, previous, today, args.refresh)
        report["api_requests"] = api.requests
        temp = ROOT / "discovered.json.tmp"
        temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
        temp.replace(snapshot_path)
        (ROOT / "scan-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(report, ensure_ascii=False))
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as f:
                f.write(f"## 自动收录\n\n公开 Fork：{report['forks']} · 技能文件：{report['skills_found']} · 本次扫描：{report['scanned']} · 缓存：{report['cached']} · 异常：{len(report['errors'])} · 暂不可用：{report['unavailable']}\n")
        return 0
    except (ScanError, OSError, ValueError) as exc:
        print("Scan failed; previous snapshot retained: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
