#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
真实图片人工筛选工具 — 本地服务端 + 合并脚本

用法：
  1) 启动筛选（自动扫描图片目录、打开浏览器）：
       python 筛选工具.py "D:/富文本数据集打包/cmdd" --category 证据记录

     多人分片（3 人，我筛第 1 份，编号从 0 起）：
       python 筛选工具.py "D:/数据" --category 法律合同 --shard 0 3

  2) 只扫描看规模（不启动服务）：
       python 筛选工具.py "D:/数据" --only-scan

  3) 合并多人的结果（修正“只有一人标过也被算作一致”的问题）：
       python 筛选工具.py --merge "结果1.csv" "结果2.csv" --out "合并结果.csv"

说明：
  - 图片目录会递归扫描 .png/.jpg/.jpeg/.webp/.bmp/.gif/.tif/.tiff。
  - 浏览器界面固定四列，每页 1000 张。1=Yes、2=No（可改键），粗蓝框表示当前图片，
    标记后自动下一张。Ctrl+滚轮统一缩放，B 加书签，Ctrl+Z 撤销。
  - 个人筛选与双人比对分别保存；服务端会同时写入个人 CSV、双人汇总 CSV 和会话 JSON。
  - 批次按“相对路径 + 文件大小”计算，换盘符或换电脑后仍可匹配同一批图片；
    每张图片另有“首尾 32KB”内容校验，用来识别同名但内容不同的情况。
  - 需要 Python 3.7+，只用标准库，无需安装任何第三方包。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import threading
import webbrowser
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
HTML_FILE = HERE / "筛选工具.html"

IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
SKIP_PARTS = {"__MACOSX", ".git", ".svn", ".DS_Store", "Thumbs.db", "desktop.ini"}
SKIP_PREFIX = (".", "_")  # 隐藏文件、下划线开头的临时文件

VERSION = 3
CHUNK = 32768
STATUS_TEXT = {
    "agree_keep": "一致保留",
    "agree_drop": "一致排除",
    "conflict": "有分歧",
    "need_fill": "待补筛",
    "unscreened": "尚未筛选",
}

PERSONAL_HEADER = ["序号", "相对路径", "标签", "分类", "筛选人", "筛选人标识",
                   "内容校验", "批次校验", "导出时间", "格式版本", "淘汰原因"]
SUMMARY_HEADER = ["序号", "相对路径", "分类", "筛选人甲", "筛选人甲标识", "甲判断",
                  "甲淘汰原因", "筛选人乙", "筛选人乙标识", "乙判断", "乙淘汰原因",
                  "比对状态", "第三人复核", "最终结果", "结论来源", "内容校验",
                  "批次校验", "导出时间", "格式版本"]

HEADER_ALIASES = {
    "path": ["相对路径", "图片相对路径", "路径", "file", "path"],
    "label": ["标签", "判断", "结果", "label"],
    "reason": ["淘汰原因", "原因", "reason"],
    "name": ["筛选人", "筛选人名字", "姓名", "筛选人姓名", "name"],
    "id": ["筛选人标识", "筛选人ID", "筛选人id", "标识", "id"],
    "content": ["内容校验", "图片内容校验", "内容指纹"],
    "batch": ["批次校验", "批次校验信息", "批次标识"],
    "exported": ["导出时间", "导出日期"],
    "version": ["格式版本", "版本"],
    "category": ["分类"],
    "a_name": ["筛选人甲"], "a_id": ["筛选人甲标识"], "a_label": ["甲判断"],
    "a_reason": ["甲淘汰原因"],
    "b_name": ["筛选人乙"], "b_id": ["筛选人乙标识"], "b_label": ["乙判断"],
    "b_reason": ["乙淘汰原因"],
    "third": ["第三人复核"], "final": ["最终结果"], "source": ["结论来源"],
}


def _fix_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------- 扫描与校验
def scan_images(root: Path) -> list[str]:
    """递归扫描图片，返回按相对路径排序的列表（相对路径用 / 分隔）。"""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_PARTS and not d.startswith(SKIP_PREFIX)]
        for fn in filenames:
            if fn.startswith(SKIP_PREFIX):
                continue
            p = Path(dirpath) / fn
            if p.suffix.lower() in IMG_EXTS:
                found.append(p.relative_to(root).as_posix())
    found.sort(key=lambda name: [int(p) if p.isdigit() else p.casefold()
                                 for p in re.split(r"(\d+)", name)])
    return found


def content_sig(path: Path) -> str:
    """首尾各 32KB 的 CRC32 + 文件大小；与浏览器端算法一致。"""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            head = f.read(CHUNK)
            f.seek(max(0, size - CHUNK))
            tail = f.read(CHUNK)
        return f"C-{size:x}-{zlib.crc32(head) & 0xFFFFFFFF:08x}-{zlib.crc32(tail) & 0xFFFFFFFF:08x}"
    except OSError:
        return ""


def batch_fingerprint(items: list[dict]) -> str:
    """按 相对路径 + 大小 的 UTF-8 文本做 FNV-1a；换盘符/换电脑不变。"""
    text = "\n".join(f"{it['file']}\t{it.get('size', 0)}" for it in sorted(items, key=lambda x: x["file"]))
    h = 2166136261
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * 16777619) & 0xFFFFFFFF
    return f"B-{h:08x}"


def build_manifest(root: Path, category: str, shard: tuple[int, int] | None,
                   hash_content: bool = True) -> dict:
    files = scan_images(root)
    all_count = len(files)
    if shard:
        i, n = shard
        if n <= 0 or not (0 <= i < n):
            raise SystemExit(f"[错误] --shard 需要是 'i N'，且 0 <= i < N。收到 {i} {n}")
        step = -(-len(files) // n)  # ceil
        files = files[i * step: (i + 1) * step]
    items = []
    for idx, rel in enumerate(files):
        path = root / rel
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        items.append({
            "id": idx + 1,
            "file": rel,
            "size": size,
            "sig": content_sig(path) if hash_content else "",
        })
    batch = batch_fingerprint(items)
    return {
        "version": VERSION,
        "source": "srv-v3-" + batch,
        "batch": batch,
        "source_path": str(root.resolve()),
        "folder_name": root.name,
        "category": category,
        "shard": {"index": shard[0], "total": shard[1]} if shard else None,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "all_count": all_count,
        "items": items,
    }


# ---------------------------------------------------------------- CSV
def normalize_label(value) -> str:
    text = str(value or "").strip().lower()
    if text in ("pass", "yes", "y", "✓", "要", "通过", "保留", "1"):
        return "pass"
    if text in ("reject", "no", "n", "×", "x", "不要", "淘汰", "排除", "0"):
        return "reject"
    return ""


def _read_csv(path: Path) -> list[dict]:
    data = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = data.decode(enc)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    if text is None:
        raise ValueError(f"无法解码 CSV：{path}")
    return list(csv.DictReader(io.StringIO(text)))


def _col_index(header: list[str], key: str) -> int:
    aliases = HEADER_ALIASES[key]
    for i, name in enumerate(header):
        if str(name).replace("\ufeff", "").strip() in aliases:
            return i
    return -1


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    os.replace(tmp, path)


def _label_of(labels: dict, file: str) -> dict:
    value = labels.get(file) if isinstance(labels, dict) else None
    if not isinstance(value, dict):
        return {}
    label = normalize_label(value.get("label"))
    if not label:
        return {}
    return {"label": label, "reason": str(value.get("reason") or "")}


def personal_rows(manifest: dict, profile: dict, labels: dict, category: str,
                  batch: str, exported_at: str) -> list[list]:
    name = str((profile or {}).get("name") or "")
    pid = str((profile or {}).get("id") or "")
    rows = []
    for idx, it in enumerate(manifest.get("items", [])):
        lab = _label_of(labels, it["file"])
        label = lab.get("label", "")
        rows.append([idx + 1, it["file"],
                     "Yes" if label == "pass" else "No" if label == "reject" else "",
                     category, name, pid, it.get("sig", ""), batch, exported_at,
                     VERSION, lab.get("reason", "")])
    return rows


def _status(a: str, b: str) -> str:
    if a and b:
        if a == b:
            return "agree_keep" if a == "pass" else "agree_drop"
        return "conflict"
    if a or b:
        return "need_fill"
    return "unscreened"


def _default_final(status: str) -> str:
    return "pass" if status == "agree_keep" else "reject" if status == "agree_drop" else ""


def summary_rows(manifest: dict, pair: dict, finals: dict, category: str,
                 batch: str, exported_at: str) -> list[list]:
    a, b = pair.get("a", {}), pair.get("b", {})
    rows = []
    for idx, it in enumerate(manifest.get("items", [])):
        la = _label_of(a.get("labels") or {}, it["file"]).get("label", "")
        lb = _label_of(b.get("labels") or {}, it["file"]).get("label", "")
        status = _status(la, lb)
        explicit = _label_of(finals, it["file"])
        final = explicit.get("label") or _default_final(status)
        if explicit.get("label"):
            source = "第三人复核"
        elif final:
            source = "两人一致"
        else:
            source = "待裁决"
        rows.append([
            idx + 1, it["file"], category, a.get("name", ""), a.get("id", ""),
            "Yes" if la == "pass" else "No" if la == "reject" else "",
            _label_of(a.get("labels") or {}, it["file"]).get("reason", ""),
            b.get("name", ""), b.get("id", ""),
            "Yes" if lb == "pass" else "No" if lb == "reject" else "",
            _label_of(b.get("labels") or {}, it["file"]).get("reason", ""),
            STATUS_TEXT[status],
            "Yes" if explicit.get("label") == "pass" else "No" if explicit.get("label") == "reject" else "",
            "Yes" if final == "pass" else "No" if final == "reject" else "",
            source, it.get("sig", ""), batch, exported_at, VERSION,
        ])
    return rows


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")


def load_personal_csv(path: Path, allowed: set[str]) -> dict | None:
    """读取个人 CSV（新版或旧版），返回 labels / profile / batch / exported_at。"""
    try:
        rows = _read_csv(path)
    except (OSError, ValueError):
        return None
    if not rows:
        return None
    names = list(rows[0].keys())
    cols = {key: _col_index(names, key) for key in
            ("path", "label", "reason", "name", "id", "batch", "exported", "content")}
    if cols["path"] < 0 or cols["label"] < 0:
        return None

    def cell(row: dict, key: str) -> str:
        idx = cols[key]
        if idx < 0 or idx >= len(names):
            return ""
        return str(row.get(names[idx]) or "").strip()

    labels: dict[str, dict] = {}
    profile = {"name": "", "id": ""}
    batch = ""
    exported = ""
    for row in rows:
        file = cell(row, "path").replace("\\", "/")
        if not file or file not in allowed:
            continue
        label = normalize_label(cell(row, "label"))
        if label:
            labels[file] = {"label": label, "reason": cell(row, "reason")}
        if not profile["name"]:
            profile["name"] = cell(row, "name")
        if not profile["id"]:
            profile["id"] = cell(row, "id")
        if not batch:
            batch = cell(row, "batch")
        if not exported:
            exported = cell(row, "exported")
    return {"labels": labels, "profile": profile, "batch": batch, "exported_at": exported}


def load_summary_csv(path: Path, allowed: set[str]) -> dict | None:
    try:
        rows = _read_csv(path)
    except (OSError, ValueError):
        return None
    if not rows:
        return None
    names = list(rows[0].keys())
    keys = ("path", "category", "a_name", "a_id", "a_label", "a_reason",
            "b_name", "b_id", "b_label", "b_reason", "third", "content", "batch", "exported")
    cols = {key: _col_index(names, key) for key in keys}
    if cols["a_label"] < 0 or cols["b_label"] < 0:
        return None

    def cell(row: dict, key: str) -> str:
        idx = cols[key]
        if idx < 0 or idx >= len(names):
            return ""
        return str(row.get(names[idx]) or "").strip()

    a = {"name": "", "id": "", "labels": {}}
    b = {"name": "", "id": "", "labels": {}}
    finals: dict[str, dict] = {}
    batch = ""
    exported = ""
    for row in rows:
        file = cell(row, "path").replace("\\", "/")
        if not file or file not in allowed:
            continue
        la = normalize_label(cell(row, "a_label"))
        lb = normalize_label(cell(row, "b_label"))
        if la:
            a["labels"][file] = {"label": la, "reason": cell(row, "a_reason")}
        if lb:
            b["labels"][file] = {"label": lb, "reason": cell(row, "b_reason")}
        third = normalize_label(cell(row, "third"))
        if third:
            finals[file] = {"label": third, "source": "third", "updatedAt": "", "recheck": False}
        if not a["name"]:
            a["name"] = cell(row, "a_name")
        if not a["id"]:
            a["id"] = cell(row, "a_id")
        if not b["name"]:
            b["name"] = cell(row, "b_name")
        if not b["id"]:
            b["id"] = cell(row, "b_id")
        if not batch:
            batch = cell(row, "batch")
        if not exported:
            exported = cell(row, "exported")
    return {"a": a, "b": b, "finals": finals, "batch": batch, "exported_at": exported}


# ---------------------------------------------------------------- HTTP 服务
class Handler(SimpleHTTPRequestHandler):
    manifest: dict = {}
    out_csv: Path | None = None
    save_lock = threading.Lock()

    @classmethod
    def scope(cls) -> str:
        shard = cls.manifest.get("shard")
        suffix = f"|shard={shard['index']}/{shard['total']}" if shard else ""
        return cls.manifest.get("batch", "") + suffix

    @classmethod
    def summary_path(cls) -> Path | None:
        if not cls.out_csv:
            return None
        return cls.out_csv.with_name(cls.out_csv.stem + "_双人比对.csv")

    @classmethod
    def session_path(cls) -> Path | None:
        return cls.out_csv.with_suffix(".session.json") if cls.out_csv else None

    @classmethod
    def load_state(cls) -> dict | None:
        allowed = {it["file"] for it in cls.manifest.get("items", [])}
        session = cls.session_path()
        if session and session.is_file():
            try:
                saved = json.loads(session.read_text(encoding="utf-8"))
                saved_batch = saved.get("batch") or ""
                same = saved_batch == cls.manifest.get("batch") or (
                    not saved_batch and saved.get("source") == cls.manifest.get("source"))
                if same and saved.get("version", 0) >= 3:
                    return saved
                if same and saved.get("labels"):
                    labels = {k: v for k, v in saved.get("labels", {}).items() if k in allowed}
                    return {
                        "version": VERSION, "batch": cls.manifest.get("batch"), "scope": cls.scope(),
                        "personal": {"labels": labels, "bookmarks": saved.get("bookmarks") or [],
                                     "idx": saved.get("idx") or 0, "page": saved.get("page") or 0,
                                     "filter": saved.get("filter") or "all",
                                     "updatedAt": saved.get("updatedAt") or ""},
                        "compare": None,
                    }
            except (OSError, ValueError, AttributeError):
                pass
        personal = None
        if cls.out_csv and cls.out_csv.is_file():
            personal = load_personal_csv(cls.out_csv, allowed)
        summary = None
        summary_path = cls.summary_path()
        if summary_path and summary_path.is_file():
            summary = load_summary_csv(summary_path, allowed)
        if not personal and not summary:
            return None
        state = {
            "version": VERSION,
            "batch": cls.manifest.get("batch"),
            "scope": cls.scope(),
            "personal": None,
            "compare": None,
        }
        if personal:
            stamp = _mtime_iso(cls.out_csv)
            state["personal"] = {
                "version": VERSION, "kind": "personal", "batch": cls.manifest.get("batch"),
                "scope": cls.scope(), "profile": personal["profile"],
                "labels": personal["labels"], "bookmarks": [], "idx": 0, "page": 0,
                "filter": "all", "zoom": 1, "updatedAt": stamp,
            }
        if summary:
            stamp = _mtime_iso(summary_path)
            state["compare"] = {
                "version": VERSION, "kind": "compare", "batch": cls.manifest.get("batch"),
                "scope": cls.scope(),
                "pair": {"a": summary["a"], "b": summary["b"],
                         "importedAt": summary["exported_at"] or stamp,
                         "batch": summary["batch"], "check": None},
                "final": summary["finals"], "bookmarks": [], "idx": 0, "page": 0,
                "filter": "all", "zoom": 1, "updatedAt": stamp,
            }
        return state

    def log_message(self, fmt, *args):
        pass

    def _send_bytes(self, data: bytes, ctype: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = unquote(self.path.split("?", 1)[0])
        if path in ("/", "/index.html"):
            self._send_bytes(HTML_FILE.read_bytes(), "text/html; charset=utf-8")
        elif path == "/manifest.json":
            data = json.dumps(self.manifest, ensure_ascii=False).encode("utf-8")
            self._send_bytes(data, "application/json; charset=utf-8")
        elif path == "/api/state":
            with self.save_lock:
                saved = self.load_state()
            self._send_bytes(json.dumps(saved, ensure_ascii=False).encode("utf-8"),
                             "application/json; charset=utf-8")
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/save":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            self.send_error(400)
            return
        if not isinstance(body, dict):
            self._send_bytes(b'{"ok":false,"error":"bad body"}', "application/json", 400)
            return
        batch = body.get("batch") or ""
        if batch and batch != self.manifest.get("batch"):
            self._send_bytes(b'{"ok":false,"error":"batch mismatch"}', "application/json", 409)
            return
        if body.get("scope") not in (None, self.scope()):
            self._send_bytes(b'{"ok":false,"error":"shard mismatch"}', "application/json", 409)
            return
        try:
            saved = self._save(body)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self._send_bytes(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8"),
                             "application/json", 500)
            return
        resp = json.dumps({"ok": True, "path": str(saved)}).encode("utf-8")
        self._send_bytes(resp, "application/json; charset=utf-8")

    def _save(self, body: dict) -> Path | None:
        if not self.out_csv:
            return None
        allowed = {it["file"] for it in self.manifest.get("items", [])}
        personal = body.get("personal") or {}
        labels = {}
        raw_labels = personal.get("labels") or {}
        if isinstance(raw_labels, dict):
            for file in raw_labels:
                if file in allowed:
                    lab = _label_of(raw_labels, file)
                    if lab:
                        labels[file] = lab
        raw_finals = (body.get("compare") or {}).get("final") or {}
        finals = {}
        if isinstance(raw_finals, dict):
            for file in raw_finals:
                if file in allowed:
                    lab = _label_of(raw_finals, file)
                    if lab:
                        finals[file] = {
                            "label": lab["label"], "source": "third",
                            "updatedAt": str((raw_finals[file] or {}).get("updatedAt") or ""),
                            "recheck": bool((raw_finals[file] or {}).get("recheck")),
                        }
        exported_at = str(body.get("updatedAt") or datetime.now().astimezone().isoformat(timespec="seconds"))
        session_data = {
            **body,
            "version": VERSION,
            "batch": self.manifest.get("batch"),
            "scope": self.scope(),
            "source": self.manifest.get("source"),
            "personal": {**personal, "labels": labels},
        }
        pair = (body.get("compare") or {}).get("pair")
        if isinstance(pair, dict):
            session_data["compare"] = {**(body.get("compare") or {}), "final": finals}
        with self.save_lock:
            existing = self.load_state()
            existing_stamp = ""
            if isinstance(existing, dict):
                existing_stamp = str((existing.get("personal") or {}).get("updatedAt")
                                     or existing.get("updatedAt") or "")
            if existing_stamp and body.get("updatedAt") and existing_stamp > str(body["updatedAt"]):
                return self.out_csv
            session = self.session_path()
            session.parent.mkdir(parents=True, exist_ok=True)
            session_tmp = session.with_suffix(".json.tmp")
            session_tmp.write_text(json.dumps(session_data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(session_tmp, session)
            _write_csv(self.out_csv, PERSONAL_HEADER,
                       personal_rows(self.manifest, body.get("profile") or {}, labels,
                                     self.manifest.get("category", ""), self.manifest.get("batch", ""),
                                     exported_at))
            summary = self.summary_path()
            if isinstance(pair, dict) and summary:
                _write_csv(summary, SUMMARY_HEADER,
                           summary_rows(self.manifest, pair, finals,
                                        self.manifest.get("category", ""),
                                        self.manifest.get("batch", ""), exported_at))
        return self.out_csv


def _pick_port(start: int) -> int:
    for p in range(start, start + 50):
        try:
            ThreadingHTTPServer(("127.0.0.1", p), SimpleHTTPRequestHandler).server_close()
            return p
        except OSError:
            continue
    raise SystemExit("[错误] 找不到可用端口（%d~%d 均被占用）。" % (start, start + 49))


def start_server(root: Path, manifest: dict, out_csv: Path, port: int, no_browser: bool) -> None:
    handler = partial(Handler, directory=str(root))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    Handler.manifest = manifest
    Handler.out_csv = out_csv
    url = f"http://127.0.0.1:{port}/"
    summary = Handler.summary_path()
    print("\n" + "=" * 56)
    print("  真实图片筛选工具已启动（v3）")
    print("=" * 56)
    print(f"  图片目录 : {root}")
    print(f"  本批张数 : {len(manifest['items'])}")
    print(f"  批次校验 : {manifest['batch']}")
    if manifest["category"]:
        print(f"  分类     : {manifest['category']}")
    if manifest["shard"]:
        s = manifest["shard"]
        print(f"  分片     : 第 {s['index'] + 1} / {s['total']} 份")
    print(f"  个人结果 : {out_csv}")
    print(f"  双人汇总 : {summary}")
    print(f"  会话保存 : {out_csv.with_suffix('.session.json')}")
    print(f"  地址     : {url}")
    print()
    print("  快捷键：1=Yes  2=No（可设置）  ←/→=切换  Ctrl+Z=撤销  B=书签")
    print("  个人筛选与双人比对分开保存；粗蓝框=当前图片，固定四列，标记后自动下一张。")
    print("  按 Ctrl+C 停止服务（标注已实时保存）。")
    print("=" * 56 + "\n")
    if not no_browser:
        threading.Thread(target=lambda: webbrowser.open(url), daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。结果保存在：" + str(out_csv))


# ---------------------------------------------------------------- 合并
def merge_results(csv_paths: list[Path], out_path: Path) -> None:
    """按相对路径聚合，只有一人标过的图片记为“待补筛”，不再算作一致。"""
    per_file: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    all_files: list[str] = []
    seen_files: set[str] = set()
    for p in csv_paths:
        src_name = p.stem
        for row in _read_csv(p):
            file = (row.get("相对路径") or "").strip().replace("\\", "/")
            if not file:
                continue
            label = normalize_label(row.get("标签") or "")
            reason = (row.get("淘汰原因") or "").strip()
            per_file[file].append((label, reason, src_name))
            if file not in seen_files:
                seen_files.add(file)
                all_files.append(file)

    rows = []
    stats = Counter()
    for file in all_files:
        entries = per_file[file]
        valid = [e for e in entries if e[0] in ("pass", "reject")]
        detail = "；".join(
            f"{e[2]}:{'Yes' if e[0] == 'pass' else 'No' if e[0] == 'reject' else '未筛'}"
            + (f"({e[1]})" if e[1] else "") for e in valid
        )
        if not valid:
            final, reason, status = "", "", "未标注"
            stats["未标注"] += 1
        elif len(valid) == 1:
            final, reason, status = "", valid[0][1], "待补筛"
            stats["待补筛"] += 1
        else:
            base = valid[0][0]
            if all(e[0] == base for e in valid):
                final, reason, status = ("Yes" if base == "pass" else "No"), valid[0][1], "一致"
                stats["一致"] += 1
            else:
                final, reason, status = "", "", "分歧"
                stats["分歧"] += 1
        rows.append([len(rows) + 1, file, final, reason, len(valid), status, detail])

    with open(out_path, "w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.writer(fp)
        writer.writerow(["序号", "相对路径", "最终标签", "淘汰原因", "标注人数", "比对状态", "标注明细"])
        writer.writerows(rows)

    print("\n合并完成 -> " + str(out_path))
    print(f"  文件总数 : {len(rows)}")
    print(f"  一致     : {stats['一致']}")
    print(f"  分歧     : {stats['分歧']}")
    print(f"  待补筛   : {stats['待补筛']}")
    print(f"  未标注   : {stats['未标注']}")
    if stats["分歧"] or stats["待补筛"]:
        print("  ⚠ 请人工复核「比对状态=分歧／待补筛」的行；只有一人标过的图片不会算作一致。")


# ---------------------------------------------------------------- main
def main() -> int:
    _fix_console()
    ap = argparse.ArgumentParser(description="真实图片人工筛选工具")
    ap.add_argument("dir", nargs="?", help="图片目录（递归扫描图片）")
    ap.add_argument("--category", "-c", default="", help="给这批图标记分类，如：法律合同 / 证据记录 / 交易凭证")
    ap.add_argument("--shard", nargs=2, type=int, metavar=("I", "N"), default=None,
                    help="多人分片：第 I 份（0 起）/ 共 N 份")
    ap.add_argument("--port", type=int, default=8765, help="服务端口（默认 8765，占用自动 +1）")
    ap.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    ap.add_argument("--only-scan", action="store_true", help="只扫描打印规模，不启动服务")
    ap.add_argument("--no-hash", action="store_true",
                    help="跳过图片内容校验（大目录启动更快，但无法识别同名不同图）")
    ap.add_argument("--out", default="", help="结果 CSV 保存路径（默认：图片目录同级的 筛选结果[_分类][_分片N].csv）")
    ap.add_argument("--merge", nargs="+", metavar="CSV", help="合并多个筛选结果 CSV，不进筛选模式")
    args = ap.parse_args()

    if args.merge:
        out = Path(args.out) if args.out else HERE / "合并结果.csv"
        merge_results([Path(p) for p in args.merge], out)
        return 0

    root = Path(args.dir) if args.dir else None
    if root is None:
        try:
            raw = input("请输入图片目录路径：").strip().strip('"')
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        root = Path(raw)
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"[错误] 目录不存在：{root}")

    manifest = build_manifest(root, args.category, tuple(args.shard) if args.shard else None,
                              hash_content=not args.no_hash and not args.only_scan)
    n_items = len(manifest["items"])

    if args.only_scan:
        print(f"图片目录 : {root}")
        print(f"图片总数 : {manifest['all_count']}")
        print(f"批次校验 : {manifest['batch']}")
        if args.category:
            print(f"分类     : {args.category}")
        if args.shard:
            print(f"分片     : 第 {args.shard[0] + 1}/{args.shard[1]} 份 -> 本份 {n_items} 张")
        else:
            print(f"本次筛选 : {n_items} 张")
        return 0

    if n_items == 0:
        raise SystemExit("[错误] 该目录（或分片）下没有找到任何图片。")

    if args.out:
        out_csv = Path(args.out)
    else:
        suffix = ""
        if args.category:
            suffix += "_" + args.category
        if args.shard:
            suffix += f"_分片{args.shard[0] + 1}"
        out_csv = root.parent / f"筛选结果{suffix}.csv"

    port = _pick_port(args.port)
    try:
        start_server(root, manifest, out_csv, port, args.no_browser)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
