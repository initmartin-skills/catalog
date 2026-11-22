#!/usr/bin/env python3
"""Validate and build a metadata-only skills catalog. Python 3.10+, standard library."""
import argparse
import copy
import datetime as dt
import html
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import sys
from urllib.parse import quote

STATUSES = ("saved", "trial", "approved", "paused", "retired")
REPO = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+")
SLUG = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
SHA = re.compile(r"[0-9a-f]{40}")
ROOT = Path(__file__).resolve().parents[1]

def merge_catalog(curated, discovered):
    """Manual records win; automation never changes their adopted commit or review state."""
    data = copy.deepcopy(curated)
    if discovered.get("schema_version") != 1:
        raise ValueError("unsupported discovery schema")
    if "inbox" not in data["categories"]:
        data["categories"].append("inbox")
    repositories = discovered.get("repositories", {})
    automatic = []
    for repo in repositories.values():
        for skill in repo.get("skills", []):
            row = copy.deepcopy(skill)
            row.pop("extracted", None)
            row["source_status"] = ("unavailable" if not repo.get("available", True)
                                    else "scan-error" if repo.get("error") else "available")
            automatic.append(row)
    claimed = set()
    for manual in data["skills"]:
        for auto in automatic:
            same_repository = (manual.get("repository_id") == auto.get("repository_id")
                               if manual.get("repository_id") else manual.get("fork") == auto.get("fork"))
            if manual["id"] == auto["id"] or (same_repository and manual["path"] == auto["path"]):
                claimed.add(auto["id"])
                manual["latest_commit"] = auto["commit"]
                manual["source_status"] = auto["source_status"]
                # A repository transfer/rename changes its address, not the adopted version.
                manual["fork"] = auto["fork"]
                break
        else:
            repo = repositories.get(str(manual.get("repository_id")))
            if repo:
                manual["source_status"] = "missing-skill"
    data["skills"].extend(s for s in automatic if s["id"] not in claimed)
    data["_discovery"] = {
        "checked_date": discovered.get("checked_date", ""),
        "repositories": len(repositories),
        "errors": sum(bool(r.get("error")) for r in repositories.values())
    }
    return data


def load_catalog(root=ROOT):
    curated = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    path = root / "discovered.json"
    return merge_catalog(curated, json.loads(path.read_text(encoding="utf-8"))) if path.exists() else curated


def source_note(skill):
    status = skill.get("source_status")
    if status in ("unavailable", "scan-error", "missing-skill"):
        return {"unavailable": "来源暂不可用，保留历史记录。",
                "scan-error": "本次扫描不完整；部分信息可能来自上次记录。",
                "missing-skill": "最新目录中未找到此技能，保留已采用记录。"}[status]
    if skill.get("latest_commit") and skill["latest_commit"] != skill["commit"]:
        return "来源已有更新；仍保留已采用版本。"
    return ""

def fail(message):
    raise ValueError(message)

def single_line(value, label):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        fail(label + " must be a nonempty single line")
    return value

def valid_date(value):
    return isinstance(value, str) and dt.date.fromisoformat(value).isoformat() == value

def validate(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        fail("unsupported schema_version")
    single_line(data.get("title"), "title")
    cats = data.get("categories")
    if not isinstance(cats, list) or not cats or any(not isinstance(c, str) or not SLUG.fullmatch(c) for c in cats) or len(cats) != len(set(cats)):
        fail("invalid categories")
    rows = data.get("skills")
    if not isinstance(rows, list):
        fail("skills must be an array")
    seen = set()
    for s in rows:
        if not isinstance(s, dict):
            fail("skill must be an object")
        sid = s.get("id")
        if not isinstance(sid, str) or not SLUG.fullmatch(sid) or sid in seen:
            fail("invalid or duplicate skill id")
        seen.add(sid)
        for field in ("name", "summary", "license", "notes"):
            single_line(s.get(field), sid + "." + field)
        if s.get("category") not in cats or s.get("status") not in STATUSES:
            fail(sid + ": invalid category/status")
        for key in ("upstream", "fork"):
            val = s.get(key)
            if key == "fork" and val is None:
                continue
            if not isinstance(val, str) or not REPO.fullmatch(val) or val.split("/")[1] in (".", ".."):
                fail(sid + ": invalid " + key)
        path = s.get("path")
        if not isinstance(path, str) or not path or "\\" in path or path.startswith("/") or any(p in ("", "..") for p in path.split("/")) or "?" in path or "#" in path or any(ord(c) < 32 for c in path):
            fail(sid + ": invalid skill path")
        if not SHA.fullmatch(str(s.get("commit", ""))):
            fail(sid + ": commit must be a full lower-case SHA")
        if not isinstance(s.get("tags"), list) or any(not isinstance(t, str) or not SLUG.fullmatch(t) for t in s["tags"]):
            fail(sid + ": invalid tags")
        if not isinstance(s.get("customized"), bool):
            fail(sid + ": customized must be boolean")
        used = s.get("used_in")
        if not isinstance(used, list) or any(not isinstance(u, str) or not u.strip() or any(ord(c)<32 for c in u) for u in used):
            fail(sid + ": invalid used_in")
        date = s.get("reviewed_at")
        if date is not None:
            try:
                if not valid_date(date): fail("invalid date")
            except (ValueError, TypeError):
                fail(sid + ": invalid reviewed_at")
        if s["status"] == "approved" and (date is None or not used):
            fail(sid + ": approved requires reviewed_at and a real used_in note")
    packs = data.get("packs")
    if not isinstance(packs, dict):
        fail("packs must be an object")
    indexed = {s["id"]: s for s in rows}
    for name, ids in packs.items():
        if not isinstance(name, str) or not SLUG.fullmatch(name) or not isinstance(ids, list) or any(not isinstance(v, str) for v in ids):
            fail("invalid pack")
        if len(ids) != len(set(ids)):
            fail("duplicate pack member")
        for sid in ids:
            if sid not in indexed or indexed[sid]["status"] != "approved":
                fail("packs may include only existing approved skills")
    return data

def md_cell(value):
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("[", "\\[").replace("]", "\\]").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")

def file_url(s, repo=None):
    path = PurePosixPath(s["path"]) / "SKILL.md"
    return "https://github.com/" + (repo or s["fork"] or s["upstream"]) + "/blob/" + s["commit"] + "/" + quote(str(path), safe="/")

def command(s, agent="codex"):
    if s["status"] != "approved" or s.get("source_status") in ("unavailable", "scan-error", "missing-skill"):
        return None
    source = (s["fork"] or s["upstream"]) + "@" + s["commit"]
    return "npx skills add " + shlex.quote(source) + " --skill " + shlex.quote(s["name"]) + " -a " + shlex.quote(agent)

def markdown(data):
    lines = ["# " + md_cell(data["title"]), "", "按用途保存，按验证版本使用。", "", "[打开可搜索目录](https://initmartin-skills.github.io/catalog/) · [维护说明](MAINTAINING.md) · [组织主页](https://github.com/initmartin-skills)", "",
             "自动扫描组织和个人账号的公开 Fork。新条目进入 inbox（待分类）/ saved；catalog.json 中的手工记录优先，采用版本不会被自动更新。", "",
             "[手动立即扫描](https://github.com/initmartin-skills/catalog/actions/workflows/sync-catalog.yml) · [扫描来源配置](sources.json)", "",
             "| Skill | 用途 | 分类 | 状态 | 采用提交 | 来源 |", "| --- | --- | --- | --- | --- | --- |"]
    for s in sorted(data["skills"], key=lambda x: (x["category"], x["id"])):
        lines.append("| [" + md_cell(s["name"]) + "](" + file_url(s) + ") | " + md_cell(s["summary"]) + " | " + s["category"] + " | " + s["status"] + " | " + s["commit"][:10] + " | " + md_cell(s["upstream"]) + (" · " + source_note(s) if source_note(s) else "") + " |")
    if not data["skills"]:
        lines.append("| 尚未收录 | — | — | — | — | — |")
    info = data.get("_discovery", {})
    if info:
        lines += ["", "最近检查（北京时间）：" + str(info["checked_date"]) + " · 来源仓库：" + str(info["repositories"]) + " · 异常：" + str(info["errors"])]
    lines += ["", "## 常用包", ""]
    for name, ids in data["packs"].items():
        lines.append("- **" + name + "**：" + (", ".join(ids) if ids else "尚未选定已验证条目"))
    lines += ["", "## 状态", "", "saved → trial → approved；暂停使用标记 paused，停止采用标记 retired。收藏不等于安装。", "",
              "## 更新目录", "", "```sh", "python3 scripts/build_catalog.py", "python3 scripts/build_catalog.py --check", "```", "",
              "安装由现有客户端或 Skills CLI 完成；本生成器不会联网、运行技能、改名或修改 GitHub 设置。", ""]
    return "\n".join(lines)

CSS = """
:root{color-scheme:light dark;--bg:#f2f0e9;--card:#fffdf8;--ink:#172b29;--muted:#667775;--line:#d7ddd3;--accent:#285e4b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:54px 24px}.kicker{font-size:12px;letter-spacing:.14em;color:var(--accent)}h1{font-size:clamp(32px,5vw,56px);line-height:1.15;letter-spacing:-.04em;margin:18px 0}p{color:var(--muted)}.controls{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px;margin:28px 0}input,select{padding:13px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink);font:inherit;min-width:0}section{display:grid;grid-template-columns:1fr 1fr;gap:16px}article{border:1px solid var(--line);padding:22px;background:var(--card);border-radius:12px}h2{font-size:22px;margin:10px 0}.meta{font-size:12px;color:var(--muted)}a{color:var(--accent)}.tag{display:inline-block;font-size:12px;background:var(--bg);padding:3px 7px;margin:2px;border-radius:5px}code{font-size:12px;overflow-wrap:anywhere}pre{white-space:pre-wrap;padding:12px;background:var(--bg)}label{font-size:12px;color:var(--muted);display:block}.controls label input,.controls label select{display:block;width:100%;margin-top:5px}article[hidden]{display:none}footer{margin-top:40px;font-size:12px;color:var(--muted)}
@media(max-width:650px){.controls,section{grid-template-columns:1fr}main{padding:32px 18px}}
@media(prefers-color-scheme:dark){:root{--bg:#111b19;--card:#1d2b26;--ink:#eff3eb;--muted:#b4c1b6;--line:#3a4d40;--accent:#acd2b8}}
"""
JS = """
const query=document.getElementById('query'),category=document.getElementById('category'),state=document.getElementById('state');
function filter(){
 let visible=0;
 document.querySelectorAll('article').forEach(card=>{
 const match=card.dataset.search.includes(query.value.trim().toLowerCase())&&(!category.value||card.dataset.category===category.value)&&(!state.value||card.dataset.status===state.value);
 card.hidden=!match;if(match)visible++;
 });
 document.getElementById('count').textContent=visible+' 个条目';
 document.getElementById('empty').hidden=visible!==0;
}
[query,category,state].forEach(el=>el.addEventListener('input',filter));filter();
"""

def webpage(data):
    esc = lambda v: html.escape(str(v), quote=True)
    cards=[]
    for s in sorted(data["skills"], key=lambda x:(x["category"], x["id"])):
        searchable=" ".join([s["id"], s["name"], s["summary"],s["category"],s["upstream"],s["status"],*s["tags"]]).lower()
        install = command(s)
        block = "<pre><code>"+esc(install)+"</code></pre>" if install else "<p class='meta'>尚未批准使用；本页不提供安装操作。</p>"
        tags=" ".join("<span class='tag'>"+esc(t)+"</span>" for t in s["tags"])
        cards.append("<article data-search=\""+esc(searchable)+"\" data-category=\""+esc(s["category"])+"\" data-status=\""+esc(s["status"])+"\"><div class='meta'>"+esc(s["category"])+" · "+esc(s["status"])+"</div><h2>"+esc(s["name"])+"</h2><p>"+esc(s["summary"])+"</p><div>"+tags+"</div><p class='meta'>来源 "+esc(s["upstream"])+"<br>固定版本 <code>"+esc(s["commit"][:12])+"</code><br>许可证 "+esc(s["license"])+"</p><a href=\""+esc(file_url(s))+"\">查看保存的技能版本 ↗</a>"+block+"<p class='meta'>"+esc((source_note(s)+" "+s["notes"]).strip())+"</p></article>")
    info=data.get("_discovery", {})
    scan_info=("最近检查（北京时间）："+esc(info.get("checked_date", ""))+" · 来源仓库："+esc(info.get("repositories", 0))+" · 异常："+esc(info.get("errors", 0))) if info else ""
    options=lambda values:"".join("<option value=\""+esc(v)+"\">"+esc("待分类" if v == "inbox" else v)+"</option>" for v in values)
    return "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>"+esc(data["title"])+"</title><style>"+CSS+"</style></head><body><main><div class='kicker'>MARTIN / SKILLS / CATALOG</div><h1>"+esc(data["title"])+"</h1><p>公开 Fork 自动收录，新技能先进入待分类。手工记录与已采用版本始终保留。</p><p class='meta'>"+scan_info+" · <a href='https://github.com/initmartin-skills/catalog/actions/workflows/sync-catalog.yml'>立即扫描</a></p><div class='controls'><label>搜索<input id='query' type='search' placeholder='技能、用途或标签'></label><label>分类<select id='category'><option value=''>全部分类</option>"+options(data["categories"])+"</select></label><label>采用状态<select id='state'><option value=''>全部状态</option>"+options(STATUSES)+"</select></label></div><p id='count' aria-live='polite'></p><section>"+"".join(cards)+"</section><p id='empty' hidden>没有匹配项，换个关键词试试。</p><footer>由手工记录与自动扫描合并生成 · Martin’s Skills Library<br>无外部字体、统计、API或自动安装行为。来源与采用版本以目录记录为准。</footer></main><script>"+JS+"</script></body></html>"

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true",help="verify generated files match catalog.json")
    parser.add_argument("--validate",action="store_true",help="validate metadata without generating files")
    args=parser.parse_args(argv)
    try:
        data=validate(load_catalog())
        if args.validate:
            print("Catalog metadata valid; no skills executed.")
            return 0
        outputs={"README.md":markdown(data),"index.html":webpage(data)}
        if args.check:
            stale=[p for p,text in outputs.items() if not (ROOT/p).is_file() or (ROOT/p).read_text(encoding="utf-8") != text]
            if stale:
                print("Regenerate catalog: "+", ".join(stale),file=sys.stderr)
                return 1
            print("Catalog valid; generated files are current.")
        else:
            for p,text in outputs.items():
                (ROOT/p).write_text(text,encoding="utf-8")
            print("Generated README.md and index.html; no network or installation performed.")
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("Catalog error: "+str(exc),file=sys.stderr)
        return 1
if __name__=="__main__":
    raise SystemExit(main())

