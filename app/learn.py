"""0단계 · 북케터밈 학습.

북케터밈 계정의 캐러셀(카드뉴스) 게시물을 전부 모아(수집) → 장마다 글자를 읽고(분석) →
'북케터밈 스타일 가이드'(버전별)와 '사용한 책 DB'를 만든다. 결과는 작업 폴더와 따로 00_북케터밈학습/ 에 쌓인다.

- 수집: Graph API 토큰이 있으면 API(인사이트 포함), 없으면 저장된 인스타 로그인 세션(웹)으로.
- 모든 단계는 게시물 하나 끝날 때마다 저장한다. [멈추기] 뒤나 프로그램을 껐다 켜도 이어서 한다.
- 학습 업데이트: 새 게시물만 수집·분석하고 가이드는 새 버전으로, 책 DB는 갱신.
"""
import asyncio
import collections
import datetime as dt
import json
import random
import re
import statistics
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from . import claude_ai, instagram
from .config import INSTAGRAM_HANDLE, PROMPTS_DIR, ROOT

HANDLE = INSTAGRAM_HANDLE.lstrip("@")
LEARN_DIR = ROOT / "00_북케터밈학습"
RAW_DIR = LEARN_DIR / "01_수집원본"
IMG_DIR = RAW_DIR / "이미지"
POSTS_FILE = RAW_DIR / "게시물목록.json"
ANA_DIR = LEARN_DIR / "02_게시물분석"
GUIDE_DIR = LEARN_DIR / "03_스타일가이드"
APPLIED_FILE = GUIDE_DIR / "적용버전.json"
BOOK_DIR = LEARN_DIR / "04_사용한책DB"
BOOKS_JSON = BOOK_DIR / "사용한책DB.json"
BOOKS_MD = BOOK_DIR / "사용한책DB.md"
STATE_FILE = LEARN_DIR / "진행상황.json"
DESIGN_SPEC = PROMPTS_DIR / "design_spec.md"

for d in (RAW_DIR, IMG_DIR, ANA_DIR, GUIDE_DIR, BOOK_DIR):
    d.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
UA = instagram.UA
ANALYZE_PARALLEL = 3


def ts(t: dt.datetime | None = None) -> str:
    return (t or dt.datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path: Path, value) -> None:
    with _lock:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def load_posts() -> dict:
    return _load(POSTS_FILE, {"account": HANDLE, "posts": {}, "skipped": {}})


def save_posts(db: dict) -> None:
    db["updated"] = ts()
    _save(POSTS_FILE, db)


def load_state() -> dict:
    return _load(STATE_FILE, {})


def save_state(s: dict) -> None:
    _save(STATE_FILE, s)


def folder_of(p: dict) -> str:
    return f"{p.get('date') or '0000-00-00'}_{p['code']}"


def images_of(p: dict) -> list[Path]:
    d = IMG_DIR / folder_of(p)
    return sorted(d.glob("*.jpg")) if d.exists() else []


def analysis_path(p: dict) -> Path:
    return ANA_DIR / f"{folder_of(p)}.json"


def hashtags(caption: str) -> list[str]:
    return re.findall(r"#[\w가-힣]+", caption or "")


def _merge(db: dict, p: dict) -> bool:
    """게시물을 목록에 넣거나 숫자를 갱신한다. 새 게시물이면 True."""
    code = p["code"]
    old = db["posts"].get(code)
    keep = {k: v for k, v in (old or {}).items() if k in ("insights", "media_id", "timestamp", "images")}
    new = {**(old or {}), **{k: v for k, v in p.items() if v is not None}, **{k: v for k, v in keep.items() if v and not p.get(k)}}
    new["hashtags"] = hashtags(new.get("caption", ""))
    new["collected_at"] = (old or {}).get("collected_at") or ts()
    db["posts"][code] = new
    return old is None


# ---------------- 현황 ----------------

def overview() -> dict:
    db = load_posts()
    posts = list(db["posts"].values())
    with_imgs = sum(1 for p in posts if images_of(p))
    analyzed = sum(1 for p in posts if analysis_path(p).exists())
    st = load_state()
    return {
        "account": HANDLE, "total": len(posts), "with_images": with_imgs, "analyzed": analyzed,
        "skipped": collections.Counter(db.get("skipped", {}).values()),
        "with_insights": sum(1 for p in posts if p.get("insights")),
        "index_done": st.get("index_done", False), "feed_total": st.get("feed_total"),
        "last_collect": st.get("last_collect"), "last_source": st.get("source"),
        "guides": list_guides(), "applied": applied_guide_name(),
        "books": len(_load(BOOKS_JSON, {}).get("books", {})),
        "folder": str(LEARN_DIR),
    }


def list_posts() -> list[dict]:
    out = []
    for p in sorted(load_posts()["posts"].values(), key=lambda p: p.get("timestamp") or p.get("date") or "", reverse=True):
        a = _load(analysis_path(p), None)
        imgs = images_of(p)
        out.append({
            "code": p["code"], "url": p.get("url"), "date": p.get("date"), "likes": p.get("likes"),
            "comments": p.get("comments"), "slides": p.get("slides"), "insights": p.get("insights") or {},
            "folder": folder_of(p), "thumb": imgs[0].name if imgs else None, "images": len(imgs),
            "analyzed": a is not None,
            "kind": (a or {}).get("post_kind"),
            "copy": " / ".join(x["text"] for x in ((a or {}).get("thumbnail") or {}).get("copy_lines", [])),
            "books": [b["title"] for b in (a or {}).get("books", [])],
        })
    return out


def post_detail(code: str) -> dict:
    p = load_posts()["posts"].get(code)
    if not p:
        raise FileNotFoundError(code)
    return {"post": {k: v for k, v in p.items() if k != "remote_images"}, "folder": folder_of(p),
            "images": [i.name for i in images_of(p)], "analysis": _load(analysis_path(p), None)}


# ---------------- 1. 수집 ----------------

async def collect(job, update: bool = False) -> dict:
    """보안상 이 프로그램은 북케터밈 계정 키(Windsor·인스타 토큰·로그인 세션)를 저장하지 않는다.
    새 게시물 수집은 Claude 대화에서 한다("북케터밈 학습 업데이트 해줘") → import_rows + fetch_public_slides 로 같은 형식에 저장."""
    raise RuntimeError("보안상 계정 키를 저장하지 않아 이 화면에서는 수집하지 않아요. "
                       "Claude 대화창에 '북케터밈 학습 업데이트 해줘'라고 하면 새 게시물을 넣어 드려요.")


# ---------------- 2. 게시물 분석 ----------------

LINE = {"type": "object", "additionalProperties": False, "required": ["text", "color"],
        "properties": {"text": {"type": "string"}, "color": {"type": "string", "description": "흰색 / 민트 / 검정 / 기타 색 이름"}}}

ANALYSIS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["post_kind", "thumbnail", "slides", "books", "cta", "design", "notes"],
    "properties": {
        "post_kind": {"type": "string", "enum": ["책추천(여러 권)", "책 한 권 소개", "책 요약", "이벤트·공지", "기타"]},
        "thumbnail": {
            "type": "object", "additionalProperties": False,
            "required": ["copy_lines", "chips", "sticker", "background", "cutout"],
            "properties": {
                "copy_lines": {"type": "array", "items": LINE, "description": "썸네일 큰 카피를 줄 단위로, 보이는 그대로"},
                "chips": {"type": "array", "items": {"type": "string"}, "description": "좌상단 라벨 칩 글자(예: 북케터 밈, 책 추천)"},
                "sticker": {"type": "string", "description": "곡선 스티커·말풍선 글자, 없으면 빈 문자열"},
                "background": {"type": "string", "description": "배경 사진 묘사(장면·분위기·색감)"},
                "cutout": {"type": "string", "description": "누끼 인물·사물이 있으면 묘사, 없으면 빈 문자열"},
            },
        },
        "slides": {"type": "array", "description": "모든 장을 순서대로",
                   "items": {"type": "object", "additionalProperties": False, "required": ["index", "role", "text"],
                             "properties": {"index": {"type": "integer"},
                                            "role": {"type": "string", "enum": ["썸네일", "책 소개", "책 요약·내용", "CTA", "기타"]},
                                            "text": {"type": "string", "description": "그 장의 글자 전부, 줄바꿈은 \\n"}}}},
        "books": {"type": "array", "description": "책 소개 장마다 한 권",
                  "items": {"type": "object", "additionalProperties": False,
                            "required": ["slide", "title", "author", "hashtags", "description_lines"],
                            "properties": {
                                "slide": {"type": "integer"},
                                "title": {"type": "string", "description": "책 제목 칩/표지에 보이는 제목 그대로"},
                                "author": {"type": "string", "description": "표지·카드·캡션에 보일 때만. 안 보이면 빈 문자열(추측 금지)"},
                                "hashtags": {"type": "array", "items": {"type": "string"}, "description": "흰 해시태그 칩 글자"},
                                "description_lines": {"type": "array", "items": LINE, "description": "표지 아래 설명글, 줄 단위·색 그대로"},
                            }}},
        "cta": {"type": "string", "description": "마지막 장 문구 전부"},
        "design": {"type": "object", "additionalProperties": False, "required": ["background", "colors", "layout", "fonts"],
                   "properties": {"background": {"type": "string"}, "colors": {"type": "string"},
                                  "layout": {"type": "string"}, "fonts": {"type": "string"}}},
        "notes": {"type": "string", "description": "잘 안 읽힌 글자·확신 없는 부분. 없으면 빈 문자열"},
    },
}

ANALYSIS_SYSTEM = """너는 인스타그램 책 계정 @bookketer_mim(북케터밈)의 카드뉴스를 읽어 텍스트로 옮기는 사람이다.
- 이미지에 보이는 글자를 한 글자도 바꾸지 말고 그대로 옮긴다(맞춤법·띄어쓰기도 보이는 대로). 줄바꿈도 카드 그대로.
- 색은 흰색 / 민트(연두, #D4FEBE 계열) / 검정 처럼 보이는 대로 적는다.
- 책 저자는 이미지나 캡션에 보일 때만 적는다. 기억으로 채우지 않는다.
- 읽기 어려운 곳은 추측해 채우지 말고 notes 에 적는다.
- 파일은 Read 도구로 하나씩 연다. 모든 장을 다 본 뒤 답한다."""


def _desc_text(b: dict) -> str:
    return "\n".join(x["text"] for x in b.get("description_lines", []))


def _count(text: str) -> dict:
    return {"chars": len(text.replace("\n", "")), "chars_no_space": len(re.sub(r"\s", "", text)),
            "lines": len([x for x in text.split("\n") if x.strip()])}


def _analysis_md(p: dict, a: dict) -> str:
    ins = p.get("insights") or {}
    lines = [f"# {p.get('date')} · {p['code']}", "",
             f"- 링크: {p.get('url')}",
             f"- 좋아요 {p.get('likes')} · 댓글 {p.get('comments')} · 장 수 {p.get('slides')}"
             + "".join(f" · {k} {ins[v]}" for k, v in (("저장", "saved"), ("공유", "shares"), ("도달", "reach"), ("조회", "views")) if ins.get(v) is not None),
             f"- 종류: {a['post_kind']}", "",
             "## 썸네일 카피", *[f"- ({x['color']}) {x['text']}" for x in a["thumbnail"]["copy_lines"]],
             f"- 칩: {', '.join(a['thumbnail']['chips'])}" if a["thumbnail"]["chips"] else "",
             f"- 스티커: {a['thumbnail']['sticker']}" if a["thumbnail"]["sticker"] else "", ""]
    if a["books"]:
        lines.append("## 소개한 책")
        for b in a["books"]:
            c = b.get("count", {})
            lines += [f"### {b['slide']}p · {b['title']}" + (f" — {b['author']}" if b["author"] else ""),
                      f"해시태그: {' '.join(b['hashtags'])}", "",
                      *[f"> ({x['color']}) {x['text']}" for x in b["description_lines"]],
                      "", f"글자 수 {c.get('chars')}(공백 제외 {c.get('chars_no_space')}) · {c.get('lines')}줄", ""]
    lines += ["## 장 구성", *[f"{s['index']}. [{s['role']}] {s['text'].replace(chr(10), ' / ')}" for s in a["slides"]], "",
              "## CTA", a["cta"] or "-", "", "## 디자인",
              *[f"- {k}: {v}" for k, v in a["design"].items()], "",
              "## 캡션", p.get("caption", ""), ""]
    if a.get("notes"):
        lines += ["## 확인 필요", a["notes"]]
    return "\n".join(x for x in lines if x is not None)


async def _analyze_one(p: dict, job) -> None:
    imgs = images_of(p)
    files = "\n".join(f"- {i.as_posix()}" for i in imgs)
    prompt = (f"게시물 {p.get('url')} ({p.get('date')}), 장 {len(imgs)}개.\n이미지 파일(순서대로 1장, 2장 …):\n{files}\n\n"
              f"캡션:\n{p.get('caption', '')[:3000]}\n\n모든 장을 열어 보고 스키마대로 옮겨 줘.")
    a = await claude_ai.run_structured(prompt, ANALYSIS_SYSTEM, ANALYSIS_SCHEMA, job, max_turns=len(imgs) + 8,
                                       effort="medium", cwd=IMG_DIR / folder_of(p), quiet=True)
    save_analysis(p, a, claude_ai.MODEL)


def save_analysis(p: dict, a: dict, by: str) -> None:
    """분석 한 건 저장(json + 사람이 읽는 md). 프로그램 안 AI든 바깥 Claude 세션이든 같은 모양으로."""
    missing = [k for k in ANALYSIS_SCHEMA["required"] if k not in a]
    if missing:
        raise ValueError(f"분석 결과에 빠진 항목: {missing}")
    for b in a.get("books", []):
        b["count"] = _count(_desc_text(b))
    a.update(code=p["code"], url=p.get("url"), date=p.get("date"), analyzed_at=ts(), model=by)
    _save(analysis_path(p), a)
    analysis_path(p).with_suffix(".md").write_text(_analysis_md(p, a), encoding="utf-8")


async def analyze(job, codes: list[str] | None = None, redo: bool = False) -> dict:
    db = load_posts()
    posts = [p for p in db["posts"].values() if images_of(p)]
    if codes:
        posts = [p for p in posts if p["code"] in codes]
    todo = [p for p in posts if redo or not analysis_path(p).exists()]
    todo.sort(key=lambda p: p.get("timestamp") or p.get("date") or "", reverse=True)
    total_all = len(db["posts"])
    done_before = sum(1 for p in db["posts"].values() if analysis_path(p).exists()) - (len(todo) if redo else 0)
    done = 0
    failed = []
    sem = asyncio.Semaphore(ANALYZE_PARALLEL)

    async def one(p):
        nonlocal done
        async with sem:
            job.check()
            try:
                await _analyze_one(p, job)
            except Exception as e:  # noqa: BLE001 - 한 게시물 실패로 전체를 멈추지 않는다
                if "로그인" in str(e):
                    raise
                failed.append(p["code"])
                job.log(f"  분석 실패 {p.get('date')} {p['code']}: {str(e)[:120]}")
                return
            done += 1
            job.progress(done / max(1, len(todo)) * 99,
                         f"분석 {done_before + done}/{total_all} 완료 (이번 {done}/{len(todo)}) · {p.get('date')}")

    if not todo:
        job.progress(99, "새로 분석할 게시물이 없습니다")
    results = await asyncio.gather(*(one(p) for p in todo), return_exceptions=True)
    for e in results:
        if isinstance(e, BaseException):
            if done:
                rebuild_books()
            raise e
    if done:
        rebuild_books()
    return {"analyzed": done, "failed": failed}


def load_analyses() -> list[tuple[dict, dict]]:
    out = []
    for p in load_posts()["posts"].values():
        a = _load(analysis_path(p), None)
        if a:
            out.append((p, a))
    out.sort(key=lambda x: x[0].get("timestamp") or x[0].get("date") or "")
    return out


# ---------------- 4. 사용한 책 DB ----------------

def book_key(title: str) -> str:
    return re.sub(r"[\s\W_]+", "", title or "").lower()


def rebuild_books() -> dict:
    """분석 결과 + 발행 기록(수동 추가)으로 사용한 책 DB 를 다시 만든다."""
    old = _load(BOOKS_JSON, {"books": {}})
    books: dict[str, dict] = {k: {**v, "posts": [x for x in v.get("posts", []) if x.get("source") != "학습"]}
                              for k, v in old.get("books", {}).items()}
    for p, a in load_analyses():
        for b in a.get("books", []):
            k = book_key(b["title"])
            if not k:
                continue
            e = books.setdefault(k, {"title": b["title"], "author": "", "posts": []})
            if b.get("author") and not e.get("author"):
                e["author"] = b["author"]
            e["posts"].append({"code": p["code"], "date": p.get("date"), "url": p.get("url"),
                               "likes": p.get("likes"), "source": "학습"})
    books = {k: v for k, v in books.items() if v["posts"]}
    for v in books.values():
        v["posts"].sort(key=lambda x: x.get("date") or "")
        v["last_used"] = v["posts"][-1].get("date")
        v["times"] = len(v["posts"])
    db = {"updated": ts(), "count": len(books), "books": books}
    _save(BOOKS_JSON, db)
    rows = sorted(books.values(), key=lambda v: v.get("last_used") or "", reverse=True)
    md = [f"# 사용한 책 DB (@{HANDLE})", "", f"- 갱신: {db['updated']} · 총 {len(books)}권", "",
          "| 책 제목 | 저자 | 소개 횟수 | 마지막 소개 | 게시물 |", "|---|---|---|---|---|"]
    for v in rows:
        links = " ".join(f"[{x['date']}]({x['url']})" for x in v["posts"])
        md.append(f"| {v['title']} | {v.get('author') or ''} | {v['times']} | {v.get('last_used') or ''} | {links} |")
    BOOKS_MD.write_text("\n".join(md) + "\n", encoding="utf-8")
    return db


def used_books() -> dict:
    return _load(BOOKS_JSON, {"books": {}})


def add_used_book(title: str, author: str, url: str, date: str, source: str = "발행") -> None:
    """7단계 발행 뒤 자동으로 부른다."""
    db = used_books()
    k = book_key(title)
    e = db.setdefault("books", {}).setdefault(k, {"title": title, "author": author, "posts": []})
    e["posts"].append({"code": url.rstrip("/").split("/")[-1], "date": date, "url": url, "likes": None, "source": source})
    _save(BOOKS_JSON, db)
    rebuild_books()


# ---------------- 3. 스타일 가이드 ----------------

def _stat(vals: list[float]) -> dict | None:
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return None
    q = statistics.quantiles(vals, n=4) if len(vals) >= 4 else [min(vals), statistics.median(vals), max(vals)]
    return {"n": len(vals), "avg": round(statistics.mean(vals), 1), "min": min(vals), "max": max(vals),
            "p25": round(q[0], 1), "median": round(statistics.median(vals), 1), "p75": round(q[-1], 1),
            "sd": round(statistics.pstdev(vals), 1)}


def compute_stats(pairs: list[tuple[dict, dict]]) -> dict:
    descs = [b for _, a in pairs for b in a.get("books", []) if b.get("description_lines")]
    book_posts = [(p, a) for p, a in pairs if a.get("books")]
    copy_lines = [x["text"] for _, a in pairs for x in a["thumbnail"]["copy_lines"]]
    tags = collections.Counter(t for p, _ in pairs for t in p.get("hashtags", []))
    days = collections.Counter("월화수목금토일"[dt.date.fromisoformat(p["date"]).weekday()] for p, _ in pairs if p.get("date"))
    hours = collections.Counter(p["timestamp"][11:13] for p, _ in pairs if len(p.get("timestamp") or "") >= 13)
    color_alt = sum(1 for b in descs if len({x["color"] for x in b["description_lines"]}) > 1)
    return {
        "posts": len(pairs), "book_posts": len(book_posts),
        "kinds": dict(collections.Counter(a["post_kind"] for _, a in pairs)),
        "slides": _stat([p.get("slides") for p, _ in pairs]),
        "books_per_post": dict(collections.Counter(len(a["books"]) for _, a in book_posts)),
        "desc_chars": _stat([b["count"]["chars"] for b in descs]),
        "desc_chars_no_space": _stat([b["count"]["chars_no_space"] for b in descs]),
        "desc_lines": _stat([b["count"]["lines"] for b in descs]),
        "desc_line_chars": _stat([len(x["text"]) for b in descs for x in b["description_lines"]]),
        "desc_color_alternating": f"{color_alt}/{len(descs)}",
        "hashtag_chips_per_book": _stat([len(b.get("hashtags", [])) for b in descs]),
        "thumb_lines": _stat([len(a["thumbnail"]["copy_lines"]) for _, a in pairs]),
        "thumb_line_chars": _stat([len(t) for t in copy_lines]),
        "caption_chars": _stat([len(p.get("caption", "")) for p, _ in pairs]),
        "caption_hashtags": _stat([len(p.get("hashtags", [])) for p, _ in pairs]),
        "top_hashtags": tags.most_common(30),
        "weekday": dict(days), "hour": dict(sorted(hours.items())),
        "likes": _stat([p.get("likes") for p, _ in pairs]),
        "comments": _stat([p.get("comments") for p, _ in pairs]),
        "saved": _stat([(p.get("insights") or {}).get("saved") for p, _ in pairs]),
        "shares": _stat([(p.get("insights") or {}).get("shares") for p, _ in pairs]),
        "reach": _stat([(p.get("insights") or {}).get("reach") for p, _ in pairs]),
    }


def _score(p: dict, use_insights: bool) -> float:
    """성과 점수: 게시물 절반 이상에 인사이트가 있으면 저장·공유를 무겁게, 아니면 모두 좋아요+댓글로(섞으면 비교가 틀어짐)."""
    ins = p.get("insights") or {}
    if use_insights:
        return (p.get("likes") or 0) + 3 * (p.get("comments") or 0) + 5 * (ins.get("saved") or 0) + 8 * (ins.get("shares") or 0)
    return (p.get("likes") or 0) + 3 * (p.get("comments") or 0)


def _brief(p: dict, a: dict, full: bool) -> str:
    ins = p.get("insights") or {}
    m = f"♥{p.get('likes')} 💬{p.get('comments')}" + (f" 저장{ins.get('saved')} 공유{ins.get('shares')} 도달{ins.get('reach')}" if ins else "")
    copy = " / ".join(f"{x['text']}({x['color']})" for x in a["thumbnail"]["copy_lines"])
    s = f"- {p.get('date')} [{a['post_kind']}, {p.get('slides')}장] {m} | 썸네일: {copy}"
    if full:
        for b in a["books"]:
            s += f"\n    · {b['title']} {' '.join(b['hashtags'])} → " + " / ".join(x["text"] for x in b["description_lines"])
        s += f"\n    · CTA: {a['cta'][:80]}\n    · 캡션: {p.get('caption', '')[:400].replace(chr(10), ' ')}"
    return s


GUIDE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["copy_patterns", "description_format", "design_format", "caption_hashtags", "performance", "summary"],
    "properties": {k: {"type": "string", "description": d} for k, d in {
        "summary": "가이드 맨 위 5줄 요약(마크다운 목록)",
        "copy_patterns": "① 썸네일 카피 패턴: 자주 쓰는 구조(빈칸 템플릿과 실제 예시), 반응이 좋았던 카피 유형과 근거 수치. 마크다운",
        "description_format": "② 책 설명글 형식: 말투, 문장 구조(줄별 역할), 마무리 방식, 색 교차 규칙, 글자 수(주어진 숫자 그대로 인용), 실제 예시 3개. 마크다운",
        "design_format": "③ 디자인 포맷: 장 구성, 텍스트 위치, 폰트 느낌, 배경 스타일, 색감. 주어진 템플릿 규격과 실제 게시물에서 다른 점이 있으면 표시. 마크다운",
        "caption_hashtags": "④ 캡션·해시태그 패턴: 캡션 구조, 길이, 고정 문구, 자주 쓰는 해시태그 묶음. 마크다운",
        "performance": "⑤ 성과 상위 vs 하위 차이(좋아요·저장·공유 기준): 카피·책 선정·구성·게시 시간에서 갈린 점, 다음 제작에 쓸 규칙. 마크다운",
    }.items()},
}

GUIDE_SYSTEM = """너는 출판 마케팅 인스타 계정 @bookketer_mim(북케터밈)의 콘텐츠 분석가다.
지금까지 올린 카드뉴스 분석 데이터를 종합해 '북케터밈 스타일 가이드'를 쓴다. 이 가이드는 다음 카드뉴스의
썸네일 카피·책 설명글·디자인·캡션을 AI가 만들 때 그대로 기준이 된다.
- 데이터에 있는 것만 말한다. 수치는 주어진 통계를 그대로 인용하고 새로 지어내지 않는다.
- 패턴은 '빈칸 템플릿 + 실제 예시(날짜)'로 적어, 다음 생성 때 바로 따라 쓸 수 있게 한다.
- 표본이 적어 확신하기 어려운 결론은 '(표본 n개, 참고)'처럼 표시한다.
- 인사이트(저장·공유·도달)가 없는 게시물이 많으면 그 사실을 밝히고 좋아요·댓글 기준으로 판단한다."""


def prepare_guide() -> dict:
    """가이드를 쓸 AI에게 줄 입력(통계·상위/하위 전문·표본)을 만든다."""
    pairs = load_analyses()
    if not pairs:
        raise RuntimeError("분석된 게시물이 없습니다. 수집·분석을 먼저 해 주세요.")
    stats = compute_stats(pairs)
    use_ins = sum(1 for p, _ in pairs if (p.get("insights") or {}).get("saved") is not None) >= len(pairs) / 2
    ranked = sorted(pairs, key=lambda x: _score(x[0], use_ins), reverse=True)
    k = max(3, min(12, len(ranked) // 5))
    top, bottom = ranked[:k], ranked[-k:] if len(ranked) > k else []
    rest = [x for x in pairs if x not in top and x not in bottom]
    random.seed(len(pairs))
    samples = random.sample(rest, min(15, len(rest)))
    spec = DESIGN_SPEC.read_text(encoding="utf-8") if DESIGN_SPEC.exists() else ""
    prompt = "\n\n".join(x for x in [
        f"[계정] @{HANDLE} · 분석한 캐러셀 {len(pairs)}개 ({pairs[0][0].get('date')} ~ {pairs[-1][0].get('date')})",
        "[통계 — 프로그램이 계산한 값, 그대로 인용]\n" + json.dumps(stats, ensure_ascii=False),
        "[모든 게시물 썸네일 카피와 반응]\n" + "\n".join(_brief(p, a, False) for p, a in pairs),
        f"[성과 상위 {len(top)}개 — 전문]\n" + "\n".join(_brief(p, a, True) for p, a in top),
        f"[성과 하위 {len(bottom)}개 — 전문]\n" + "\n".join(_brief(p, a, True) for p, a in bottom),
        f"[그 밖의 표본 {len(samples)}개 — 전문]\n" + "\n".join(_brief(p, a, True) for p, a in samples),
        "[디자인 메모(게시물별 AI 관찰) 일부]\n" + "\n".join(
            f"- {p.get('date')}: 배경 {a['design']['background']} / 색 {a['design']['colors']} / 배치 {a['design']['layout']} / 글꼴 {a['design']['fonts']}"
            for p, a in ranked[:15]),
        "[사용자가 준 디자인 템플릿 규격(실측)]\n" + spec if spec else "",
        "성과 점수 = " + ("좋아요 + 3×댓글 + 5×저장 + 8×공유" if use_ins else
                         "좋아요 + 3×댓글 (인사이트가 있는 게시물이 절반 미만이라 저장·공유는 점수에서 뺌)"),
    ] if x)
    return {"prompt": prompt, "stats": stats, "n": len(pairs), "first": pairs[0][0].get("date"),
            "last": pairs[-1][0].get("date"), "with_ins": sum(1 for p, _ in pairs if p.get("insights")),
            "top": len(top), "bottom": len(bottom)}


def save_guide(g: dict, prep: dict, by: str = "") -> str:
    """AI가 쓴 ①~⑤ 본문 + 프로그램이 계산한 숫자 기준을 묶어 새 버전 파일로 저장한다."""
    stats = prep["stats"]
    name = f"스타일가이드_{ts()}.md"
    rules = {
        "desc_chars": stats["desc_chars"], "desc_chars_no_space": stats["desc_chars_no_space"],
        "desc_lines": stats["desc_lines"], "desc_line_chars": stats["desc_line_chars"],
        "thumb_lines": stats["thumb_lines"], "thumb_line_chars": stats["thumb_line_chars"],
        "caption_chars": stats["caption_chars"], "top_hashtags": [t for t, _ in stats["top_hashtags"][:15]],
    }
    md = "\n".join([
        f"# 북케터밈 스타일 가이드 — {name[7:-3]}", "",
        f"- 기준: @{HANDLE} 캐러셀 {prep['n']}개 ({prep['first']} ~ {prep['last']}) · 인사이트 있는 게시물 {prep['with_ins']}개",
        f"- 성과 상위 {prep['top']}개 / 하위 {prep['bottom']}개 비교" + (f" · 작성: {by}" if by else ""), "",
        "## 요약", g["summary"], "",
        "## ① 썸네일 카피 패턴", g["copy_patterns"], "",
        "## ② 책 설명글 형식", g["description_format"], "",
        "## ③ 디자인 포맷", g["design_format"], "",
        "## ④ 캡션·해시태그 패턴", g["caption_hashtags"], "",
        "## ⑤ 성과 상위 vs 하위", g["performance"], "",
        "## 숫자 기준 (프로그램이 계산, 4단계 글자 수 범위 기본값에 쓰임)",
        _stats_table(stats), "",
        "<!-- RULES -->", "```json", json.dumps(rules, ensure_ascii=False, indent=2), "```", "",
    ])
    (GUIDE_DIR / name).write_text(md, encoding="utf-8")
    (GUIDE_DIR / (name[:-3] + "_통계.json")).write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    return name


async def build_guide(job) -> dict:
    job.progress(5, "통계 계산 중")
    prep = prepare_guide()
    job.progress(15, f"AI가 분석 {prep['n']}개로 스타일 가이드를 쓰는 중 (몇 분 걸려요)")
    g = await claude_ai.run_structured(prep["prompt"], GUIDE_SYSTEM, GUIDE_SCHEMA, job, max_turns=4, effort="high", quiet=True)
    return {"name": save_guide(g, prep, claude_ai.MODEL)}


def _stats_table(s: dict) -> str:
    rows = [("설명글 글자 수(공백 포함)", "desc_chars"), ("설명글 글자 수(공백 제외)", "desc_chars_no_space"),
            ("설명글 줄 수", "desc_lines"), ("설명글 한 줄 글자 수", "desc_line_chars"),
            ("썸네일 카피 줄 수", "thumb_lines"), ("썸네일 카피 한 줄 글자 수", "thumb_line_chars"),
            ("장 수", "slides"), ("캡션 글자 수", "caption_chars"), ("캡션 해시태그 수", "caption_hashtags"),
            ("좋아요", "likes"), ("댓글", "comments"), ("저장", "saved"), ("공유", "shares"), ("도달", "reach")]
    out = ["| 항목 | 표본 | 평균 | 최소 | 25% | 중앙 | 75% | 최대 |", "|---|---|---|---|---|---|---|---|"]
    for label, key in rows:
        v = s.get(key)
        if v:
            out.append(f"| {label} | {v['n']} | {v['avg']} | {v['min']} | {v['p25']} | {v['median']} | {v['p75']} | {v['max']} |")
    out.append(f"\n- 설명글 줄 색 교차(민트/흰): {s['desc_color_alternating']} · 책 수 분포: {s['books_per_post']} · 게시물 종류: {s['kinds']}")
    return "\n".join(out)


def list_guides() -> list[str]:
    return sorted((p.name for p in GUIDE_DIR.glob("스타일가이드_*.md")), reverse=True)


def applied_guide_name() -> str | None:
    pinned = _load(APPLIED_FILE, {}).get("pinned")
    guides = list_guides()
    if pinned and pinned in guides:
        return pinned
    return guides[0] if guides else None


def pin_guide(name: str | None) -> dict:
    if name and name not in list_guides():
        raise FileNotFoundError(name)
    _save(APPLIED_FILE, {"pinned": name, "at": ts()})
    return {"applied": applied_guide_name(), "pinned": name}


def read_guide(name: str) -> str:
    if name not in list_guides():
        raise FileNotFoundError(name)
    return (GUIDE_DIR / name).read_text(encoding="utf-8")


def save_guide_edit(base: str, text: str) -> dict:
    """수정본은 덮어쓰지 않고 새 버전으로 저장한다."""
    name = f"스타일가이드_{ts()}_수정.md"
    (GUIDE_DIR / name).write_text(text, encoding="utf-8")
    return {"name": name, "from": base}


def applied_guide() -> tuple[str, dict]:
    """다른 단계가 쓰는 가이드 본문과 숫자 기준."""
    name = applied_guide_name()
    if not name:
        return "", {}
    text = read_guide(name)
    rules = {}
    m = re.search(r"<!-- RULES -->\s*```json\n(.*?)\n```", text, flags=re.S)
    if m:
        try:
            rules = json.loads(m.group(1))
        except json.JSONDecodeError:
            rules = {}
    body = text.split("## 숫자 기준")[0]
    return body, rules


# ---------------- 한 번에 ----------------

async def run_all(job, update: bool = False) -> dict:
    """[학습 시작·이어서] / [학습 업데이트]: 수집 → 분석 → 가이드 새 버전 → 책 DB."""
    before = load_posts()["posts"].keys() | set()
    sub = _Sub(job, 0, 35)
    await collect(sub, update=update)
    after = set(load_posts()["posts"])
    new_codes = sorted(after - before)
    sub = _Sub(job, 35, 85)
    r = await analyze(sub)
    if update and not new_codes and not r["analyzed"] and list_guides():
        job.progress(99, "새 게시물이 없어 가이드는 그대로 둡니다")
        return {"new": 0, "guide": applied_guide_name()}
    g = await build_guide(_Sub(job, 85, 99))
    rebuild_books()
    return {"new": len(new_codes), "analyzed": r["analyzed"], "failed": r["failed"], "guide": g["name"]}


class _Sub:
    """하위 작업의 진행률(0~100)을 전체 진행률의 한 구간으로 바꿔 준다."""

    def __init__(self, job, lo: float, hi: float):
        self.job, self.lo, self.hi = job, lo, hi

    def progress(self, pct, label=""):
        self.job.progress(None if pct is None else self.lo + (self.hi - self.lo) * pct / 100, label)

    def log(self, msg):
        self.job.log(msg)

    def check(self):
        self.job.check()


# ---------------- Windsor.ai 등 바깥에서 받은 게시물 행 + 공개 임베드 이미지 ----------------

def import_rows(rows: list[dict], source: str) -> int:
    """Windsor(인스타 API) 행을 게시물 목록에 넣는다. 성과 수치는 insights 로. 새 게시물 수를 돌려준다."""
    db = load_posts()
    new = 0
    for r in rows:
        code = r.get("media_shortcode")
        if not code:
            continue
        try:
            local = dt.datetime.strptime(r["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone()
        except (KeyError, ValueError):
            local = None
        ins = {k: r.get(f"media_{k}") for k in ("saved", "shares", "reach", "views", "follows", "profile_visits")}
        p = {"code": code, "media_id": r.get("media_id"), "url": f"https://www.instagram.com/p/{code}/",
             "timestamp": local.isoformat() if local else "", "date": local.strftime("%Y-%m-%d") if local else "",
             "likes": r.get("media_like_count"), "comments": r.get("media_comments_count"),
             "insights": {k: v for k, v in ins.items() if v is not None}, "source": source}
        new += _merge(db, p)
        db["posts"][code]["insights"] = p["insights"]  # 최신 수치로 갱신
    save_posts(db)
    st = load_state()
    st.update(index_done=True, source=source, last_collect=ts())
    save_state(st)
    return new


async def fetch_public_slides(job) -> dict:
    """장 이미지가 없는 게시물을 로그인 없이(공개 임베드 페이지) 받는다. 캡션·장 수도 채운다."""
    import shutil
    import tempfile
    db = load_posts()
    todo = [p for p in db["posts"].values() if not images_of(p)]
    if not todo:
        return {"fetched": 0}
    tmp = Path(tempfile.mkdtemp(prefix="bk_embed_"))
    try:
        res = await instagram.fetch_public(job, [p["url"] for p in todo], tmp)
        got = 0
        for i, q in enumerate(res["posts"], 1):
            p = db["posts"].get(q["code"])
            if not p:
                continue
            d = IMG_DIR / folder_of(p)
            d.mkdir(parents=True, exist_ok=True)
            for k, name in enumerate(q["images"], 1):
                shutil.move(str(tmp / name), str(d / f"{k:02d}.jpg"))
            if q.get("caption") and not p.get("caption"):
                p["caption"] = q["caption"]
                p["hashtags"] = hashtags(q["caption"])
            p["slides"] = q.get("slides") or len(q["images"])
            got += 1
        save_posts(db)
        return {"fetched": got, "asked": len(todo)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
