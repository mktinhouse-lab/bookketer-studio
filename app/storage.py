"""md 기록 저장/조회.

- 파일 이름: 20261013-142137_<꼬리표>_<내용>.md  (초 단위 시각, 같은 이름이 있으면 _2, _3 … 을 붙여 덮어쓰지 않음)
- 화면이 쓰는 구조화 데이터는 md 맨 끝 '원본 데이터' 블록(json)에 함께 넣는다. md 하나만 있으면 다시 열 수 있다.
- 이미지는 md 옆 폴더(<이름>_assets, 완성본은 <이름>_cards)에 둔다.
"""
import datetime as dt
import json
import re
import shutil
import threading
from pathlib import Path

from .config import DATA_DIR, MD_KINDS, PROJECTS_FILE, SEEN_FILE, SETTINGS_FILE, TRASH_DIR

_lock = threading.Lock()
DATA_MARK = "<!-- DATA -->"


def now() -> dt.datetime:
    return dt.datetime.now()


def stamp(t: dt.datetime | None = None) -> str:
    return (t or now()).strftime("%Y%m%d-%H%M%S")


def slugify(text: str, maxlen: int = 30) -> str:
    text = re.sub(r'[\\/:*?"<>|#%&{}$!\'@`=+\[\]\r\n\t.,·]', " ", str(text or ""))
    text = re.sub(r"\s+", "_", text.strip())
    return text[:maxlen].strip("_") or "무제"


def kind_dir(kind: str) -> Path:
    assert kind in MD_KINDS
    return DATA_DIR / kind


def new_name(kind: str, tag: str, slug: str) -> str:
    """덮어쓰지 않는 새 파일 이름을 예약한다(빈 파일을 먼저 만들어 둠)."""
    with _lock:
        base = f"{stamp()}_{slugify(tag, 20)}_{slugify(slug)}"
        name, n = f"{base}.md", 2
        while (kind_dir(kind) / name).exists():
            name, n = f"{base}_{n}.md", n + 1
        (kind_dir(kind) / name).write_text("", encoding="utf-8")
    return name


def safe_path(kind: str, name: str) -> Path:
    if kind not in MD_KINDS or not re.fullmatch(r"[^\\/]+\.md", name or "") or ".." in name:
        raise FileNotFoundError(name)
    return kind_dir(kind) / name


def assets_dir(kind: str, name: str, suffix: str = "_assets") -> Path:
    p = safe_path(kind, name).with_name(name[:-3] + suffix)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_md(kind: str, name: str, body: str, data: dict) -> None:
    text = body.rstrip() + f"\n\n---\n\n## 원본 데이터\n\n{DATA_MARK}\n```json\n" \
        + json.dumps(data, ensure_ascii=False, indent=2) + "\n```\n"
    safe_path(kind, name).write_text(text, encoding="utf-8")


def read_md(kind: str, name: str) -> dict:
    path = safe_path(kind, name)
    if not path.exists():
        raise FileNotFoundError(name)
    text = path.read_text(encoding="utf-8")
    data = {}
    if DATA_MARK in text:
        body, raw = text.split(DATA_MARK, 1)
        m = re.search(r"```json\n(.*)\n```", raw, flags=re.S)
        if m:
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                data = {}
        body = re.sub(r"\n---\n\n## 원본 데이터\s*$", "", body.rstrip())
    else:
        body = text
    return {"name": name, "content": body, "data": data}


def read_data(kind: str, name: str) -> dict:
    return read_md(kind, name)["data"]


def list_names(kind: str) -> list[str]:
    return sorted((p.name for p in kind_dir(kind).glob("*.md") if p.stat().st_size), reverse=True)


def move_to_trash(items: list[dict]) -> dict:
    folder = TRASH_DIR / stamp()
    moved = []
    for it in items:
        try:
            path = safe_path(it["kind"], it["name"])
        except FileNotFoundError:
            continue
        if not path.exists():
            continue
        dest = folder / it["kind"]
        dest.mkdir(parents=True, exist_ok=True)
        for p in [path, *path.parent.glob(it["name"][:-3] + "_*")]:
            if p.exists():
                shutil.move(str(p), str(dest / p.name))
        moved.append(it["name"])
    return {"moved": moved, "trash": str(folder)}


# ---------------- 작은 json 저장소 ----------------

def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path: Path, value) -> None:
    with _lock:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load_projects() -> dict:
    return _load(PROJECTS_FILE, {})


def save_projects(p: dict) -> None:
    _save(PROJECTS_FILE, p)


DEFAULT_SETTINGS = {"headless": False}


def load_settings() -> dict:
    return {**DEFAULT_SETTINGS, **_load(SETTINGS_FILE, {})}


def save_settings(s: dict) -> None:
    _save(SETTINGS_FILE, s)


def load_seen() -> set[str]:
    return set(_load(SEEN_FILE, []))


def add_seen(codes) -> None:
    seen = load_seen() | set(codes)
    _save(SEEN_FILE, sorted(seen))
