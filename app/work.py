"""카드뉴스 작업(1건 = 폴더 1개)과 1단계 레퍼런스.

- 폴더: 작업/2026-10-14_17-05-32_<썸네일카피앞부분>  (카피를 고르기 전에는 _새작업, 2단계에서 카피를 고르면 이름을 바꾼다)
- state.json: 지금 단계·책 권수·단계별 결과(화면이 쓰는 데이터). 꺼도 여기서 이어서 한다.
- 단계별 md: 01_레퍼런스.md … 같은 단계를 다시 저장하면 덮지 않고 01_레퍼런스_<시각>.md 로 새로 만든다.
- 이미지: 폴더 안 하위 폴더(01_레퍼런스_이미지/ …)
"""
import asyncio
import base64
import json
import re
import shutil
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from . import claude_ai, instagram, learn
from .config import ROOT

WORK_DIR = ROOT / "작업"
WORK_DIR.mkdir(parents=True, exist_ok=True)
STEP_FILES = {1: "01_레퍼런스", 2: "02_썸네일카피", 3: "03_책추천", 4: "04_설명글"}
REF_IMG = "01_레퍼런스_이미지"
_lock = threading.Lock()


def _slug(text: str, n: int = 20) -> str:
    text = re.sub(r'[\\/:*?"<>|\r\n\t]', " ", text or "")
    text = re.sub(r"\s+", "", text)
    return text[:n] or "새작업"


def path(wid: str) -> Path:
    if not wid or "/" in wid or "\\" in wid or ".." in wid:
        raise FileNotFoundError(wid)
    p = WORK_DIR / wid
    if not p.is_dir():
        raise FileNotFoundError(wid)
    return p


def load(wid: str) -> dict:
    return json.loads((path(wid) / "state.json").read_text(encoding="utf-8"))


class StaleCards(Exception):
    """편집기가 들고 있는 카드가 서버보다 오래됐다(다른 화면·자동 작업이 먼저 바꿈)."""


def save(wid: str, st: dict) -> dict:
    st["updated"] = learn.ts()
    if isinstance(st.get("cards"), dict):  # 카드가 바뀔 때마다 번호를 올려, 오래된 화면의 저장을 막는다
        st["cards"]["rev"] = (st["cards"].get("rev") or 0) + 1
    with _lock:
        tmp = path(wid) / "state.json.tmp"
        tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path(wid) / "state.json")
    return st


MIN_BOOKS, MAX_BOOKS = 3, 5  # 3단계에서 고른 책 수가 곧 권수


def create(count: int | None = None) -> dict:
    stamp = learn.ts()
    wid = f"{stamp}_새작업"
    (WORK_DIR / wid).mkdir(parents=True)
    st = {"id": wid, "created": stamp, "count": None, "step": 1, "title": "", "refs": [], "steps": {}}
    return save(wid, st)


def rename(wid: str, copy: str) -> str:
    """2단계에서 카피를 고르면 폴더 이름 뒤쪽을 카피 앞부분으로 바꾼다(시각은 그대로)."""
    stamp = wid[:19]
    new = f"{stamp}_{_slug(copy)}"
    if new == wid:
        return wid
    n, cand = 2, new
    while (WORK_DIR / cand).exists():
        cand, n = f"{new}_{n}", n + 1
    shutil.move(str(path(wid)), str(WORK_DIR / cand))
    st = load(cand)
    st["id"] = cand
    save(cand, st)
    return cand


def list_works() -> list[dict]:
    out = []
    for p in sorted(WORK_DIR.iterdir(), reverse=True):
        f = p / "state.json"
        if not f.exists():
            continue
        try:
            st = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append({"id": p.name, "count": st.get("count"), "step": st.get("step"), "title": st.get("title"),
                    "refs": len(st.get("refs", [])), "updated": st.get("updated"),
                    "files": sorted(x.name for x in p.glob("*.md")), "done": bool(st.get("export")),
                    "thumb": _thumb_of(p, st), "copy": _copy_lines(st)})
    return out


def _copy_lines(st: dict) -> list:
    """썸네일에 얹을 카피: 카드 완성 > 고른 카피 > 레퍼런스 카피 순."""
    for s in (st.get("cards") or {}).get("slides", []):
        if s.get("type") == "thumb":
            return [s.get("line1", ""), s.get("line2", ""), s.get("c1") or "#FFFFFF", s.get("c2") or "#D4FEBE"]
    ch = (st.get("copy") or {}).get("chosen")
    if ch:
        return [ch.get("line1", ""), ch.get("line2", ""), "#FFFFFF", "#D4FEBE"]
    return []


def _thumb_of(p: Path, st: dict) -> dict | None:
    """작업 목록 썸네일: 내보낸 PNG 1장 > 카드 썸네일 배경 > 레퍼런스 첫 장."""
    ex = st.get("export")
    if ex and (p / ex["folder"] / ex["files"][0]).exists():
        return {"sub": ex["folder"], "name": ex["files"][0], "final": True}
    for s in (st.get("cards") or {}).get("slides", []):
        if s.get("type") == "thumb" and s.get("bg") and (p / BG_DIR / s["bg"]).exists():
            return {"sub": BG_DIR, "name": s["bg"], "final": False}
    for r in st.get("refs", []):
        if r.get("images"):
            return {"sub": REF_IMG, "name": r["images"][0], "final": False, "ref": True}
    return None


def write_step_md(wid: str, step: int, body: str) -> str:
    """단계 결과 md. 이미 있으면 덮지 않고 시각을 붙인 새 파일로."""
    base = STEP_FILES[step]
    p = path(wid) / f"{base}.md"
    if p.exists():
        p = path(wid) / f"{base}_{learn.ts()}.md"
    p.write_text(body, encoding="utf-8")
    return p.name


def read_file(wid: str, name: str) -> str:
    if "/" in name or "\\" in name or ".." in name or not name.endswith(".md"):
        raise FileNotFoundError(name)
    return (path(wid) / name).read_text(encoding="utf-8")


# ---------------- 1단계 · 레퍼런스 ----------------

REF_SYSTEM = learn.ANALYSIS_SYSTEM.replace("인스타그램 책 계정 @bookketer_mim(북케터밈)의 카드뉴스를",
                                          "인스타그램 카드뉴스(다른 계정의 레퍼런스)를")


async def _analyze_ref(wid: str, ref: dict, job) -> None:
    folder = path(wid) / REF_IMG
    files = "\n".join(f"- {(folder / n).as_posix()}" for n in ref["images"])
    prompt = (f"레퍼런스 게시물 {ref.get('url') or '(직접 올림)'} · 계정 @{ref.get('author') or '?'}, 장 {len(ref['images'])}개.\n"
              f"이미지 파일(순서대로 1장, 2장 …):\n{files}\n\n캡션:\n{(ref.get('caption') or '')[:3000]}\n\n"
              "모든 장을 열어 보고 스키마대로 옮겨 줘. 책 계정이 아니어도 된다.")
    a = await claude_ai.run_structured(prompt, REF_SYSTEM, learn.ANALYSIS_SCHEMA, job, max_turns=len(ref["images"]) + 8,
                                       effort="medium", cwd=folder, quiet=True)
    ref["copy"] = "\n".join(x["text"] for x in a["thumbnail"]["copy_lines"])
    ref["structure"] = "\n".join(f"{s['index']}. [{s['role']}] {s['text'].replace(chr(10), ' / ')}" for s in a["slides"])
    ref["analysis"] = a


async def fetch_refs(job, wid: str, urls: list[str]) -> dict:
    """링크(최대 3개)를 로그인 없이 공개 임베드로 읽고, AI가 장마다 글자를 옮긴다."""
    urls = [u.strip() for u in urls if u.strip()][:3]
    if not urls:
        raise RuntimeError("레퍼런스 링크를 하나 이상 넣어 주세요.")
    folder = path(wid) / REF_IMG
    folder.mkdir(exist_ok=True)
    tmp = folder / f"_받는중_{learn.ts()}"
    tmp.mkdir()
    res = await instagram.fetch_public(learn._Sub(job, 0, 30), urls, tmp)
    st = load(wid)
    start = len(st["refs"])
    new_refs = []
    for i, p in enumerate(res["posts"], 1):
        k = start + i
        names = []
        for j, n in enumerate(p["images"], 1):
            dest = f"ref{k}_{j:02d}.jpg"
            shutil.move(str(tmp / n), str(folder / dest))
            names.append(dest)
        new_refs.append({"no": k, "url": p["url"], "author": p.get("author"), "date": p.get("date"),
                         "likes": p.get("likes"), "comments": p.get("comments"), "caption": p.get("caption", ""),
                         "slides": len(names), "images": names, "top_comments": "", "source": "링크(로그인 없이)",
                         "copy": "", "structure": "", "analysis": None})
    shutil.rmtree(tmp, ignore_errors=True)
    got = {r["url"] for r in new_refs}
    failed = [u for u in urls if not any(code in u for code in (r["url"].rstrip("/").split("/")[-1] for r in new_refs))]
    if not new_refs:
        raise RuntimeError("링크에서 게시물을 읽지 못했습니다(비공개·삭제·릴스일 수 있음). 아래 '직접 올리기'로 이미지를 올려 주세요.")
    job.progress(30, f"{len(new_refs)}개 받음 · AI가 장마다 글자를 읽는 중")
    done = 0

    async def one(r):
        nonlocal done
        try:
            await _analyze_ref(wid, r, job)
        except Exception as e:  # noqa: BLE001
            if "로그인" in str(e):
                raise
            job.log(f"  읽기 실패 @{r.get('author')}: {str(e)[:100]}")
        done += 1
        job.progress(30 + done / len(new_refs) * 69, f"AI 읽기 {done}/{len(new_refs)}")

    await asyncio.gather(*(one(r) for r in new_refs))
    st = load(wid)
    st["refs"].extend(new_refs)
    save(wid, st)
    return {"added": len(new_refs), "failed": failed, "urls": sorted(got)}


def _data_url_bytes(data: str) -> bytes:
    return base64.b64decode(data.split(",", 1)[1] if data.startswith("data:") else data)


def upload_ref(wid: str, images: list[str], caption: str, copy: str, url: str = "") -> dict:
    """링크 수집이 막혔을 때: 이미지 직접 올리기(+카피 직접 입력)."""
    st = load(wid)
    k = len(st["refs"]) + 1
    folder = path(wid) / REF_IMG
    folder.mkdir(exist_ok=True)
    names = []
    for j, d in enumerate(images, 1):
        name = f"ref{k}_{j:02d}.jpg" if "jpeg" in d[:30] or "jpg" in d[:30] else f"ref{k}_{j:02d}.png"
        (folder / name).write_bytes(_data_url_bytes(d))
        names.append(name)
    ref = {"no": k, "url": url, "author": "", "date": "", "likes": None, "comments": None, "caption": caption,
           "slides": len(names), "images": names, "top_comments": "", "source": "직접 올림",
           "copy": copy, "structure": "", "analysis": None}
    st["refs"].append(ref)
    save(wid, st)
    return ref


async def analyze_uploaded(job, wid: str, no: int) -> dict:
    st = load(wid)
    ref = next(r for r in st["refs"] if r["no"] == no)
    if not ref["images"]:
        return ref
    keep_copy = ref.get("copy")
    await _analyze_ref(wid, ref, job)
    if keep_copy:
        ref["copy"] = keep_copy  # 사용자가 직접 넣은 카피가 우선
    st = load(wid)
    st["refs"] = [ref if r["no"] == no else r for r in st["refs"]]
    save(wid, st)
    return ref


def update_refs(wid: str, edits: list[dict]) -> dict:
    """화면에서 고친 카피·장 구성·댓글을 반영한다(삭제 포함)."""
    st = load(wid)
    by_no = {r["no"]: r for r in st["refs"]}
    keep = []
    for e in edits:
        r = by_no.get(e.get("no"))
        if not r:
            continue
        for k in ("copy", "structure", "top_comments", "author", "likes", "comments", "date", "caption"):
            if k in e:
                r[k] = e[k]
        keep.append(r)
    st["refs"] = keep
    return save(wid, st)


def confirm_refs(wid: str) -> dict:
    """1단계 확정: 01_레퍼런스.md 저장하고 2단계로."""
    st = load(wid)
    if not st["refs"]:
        raise ValueError("레퍼런스가 없습니다.")
    lines = [f"# 01 레퍼런스 — {st['id']}", "", f"- 레퍼런스 {len(st['refs'])}개 (권수는 3단계에서 고른 책 수로 정함)", ""]
    for r in st["refs"]:
        lines += [f"## 레퍼런스 {r['no']} · @{r.get('author') or '?'}", "",
                  f"- 링크: {r.get('url') or '(직접 올림)'}",
                  f"- 업로드: {r.get('date') or '?'} · 좋아요 {r.get('likes') if r.get('likes') is not None else '?'}"
                  f" · 댓글 {r.get('comments') if r.get('comments') is not None else '?'} · 장 {r.get('slides')}",
                  f"- 이미지: {REF_IMG}/" + ", ".join(r["images"]), "",
                  "### 썸네일 카피", r.get("copy") or "-", "",
                  "### 장별 구성", r.get("structure") or "-", "",
                  "### 댓글", r.get("top_comments") or "(수집 안 됨)", "",
                  "### 캡션", r.get("caption") or "-", ""]
    name = write_step_md(wid, 1, "\n".join(lines))
    st["steps"]["1"] = {"file": name, "at": learn.ts()}
    st["step"] = max(st.get("step", 1), 2)
    save(wid, st)
    return {"file": name, "state": st}


# ---------------- 2단계 · 썸네일 카피 10개 ----------------

from .config import PROMPTS_DIR  # noqa: E402

RULES_FILE = PROMPTS_DIR / "피드백_규칙.md"

COPY_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["analysis", "copies", "recommend"],
    "properties": {
        "analysis": {
            "type": "object", "additionalProperties": False,
            "required": ["hook", "target", "emotion", "evidence", "formula"],
            "properties": {
                "hook": {"type": "string", "description": "후킹 구조: 카피가 어떤 장치로 멈추게 하는지(1~2문장)"},
                "target": {"type": "string", "description": "타깃: 누구에게 말을 거는지(1문장)"},
                "emotion": {"type": "string", "description": "건드리는 감정(1문장)"},
                "evidence": {"type": "string", "description": "반응 지표 근거: 좋아요·댓글 수·댓글 내용 등 주어진 숫자와 사실만(1~2문장). 없으면 '지표 없음'"},
                "formula": {"type": "string", "description": "레퍼런스 카피를 빈칸 템플릿으로(예: [시간 조건] / [역접]지만 [감각어] 책 N)"},
            }},
        "copies": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["kind", "line1", "line2", "device"],
            "properties": {
                "kind": {"type": "string", "enum": ["베리에이션", "디벨롭"]},
                "line1": {"type": "string", "description": "썸네일 1줄(짧은 조건·훅, 4~9자 안팎)"},
                "line2": {"type": "string", "description": "썸네일 2줄(수식어 + 대상 + 책/소설 + 권수, 17자 이내)"},
                "device": {"type": "string", "description": "쓴 장치 한 줄 설명"},
            }}},
        "recommend": {"type": "object", "additionalProperties": False, "required": ["index", "reason"],
                      "properties": {"index": {"type": "integer", "description": "copies 안에서 추천하는 것의 번호(0부터)"},
                                     "reason": {"type": "string"}}},
    },
}

COPY_SYSTEM = """너는 출판 마케팅 인스타 계정 @bookketer_mim(북케터밈)의 카드뉴스 썸네일 카피를 기획한다.
- 아래 [북케터밈 스타일 가이드]와 [제작 규칙]이 기준이다. 둘 다 그대로 따른다.
- 썸네일은 항상 2줄이다. 끝은 '책 N' 또는 '소설 N'처럼 권수를 붙인다(N은 이번 제작 권수).
- 베리에이션: 레퍼런스 카피의 구조(빈칸 템플릿)를 그대로 두고 표현만 바꾼다. 단 레퍼런스를 베낀 티가 나면 안 된다.
- 디벨롭: 같은 주제에서 각도를 넓힌다(타깃·상황·감정·비교 대상을 바꾸기). 스타일 가이드의 성과 상위 패턴을 우선 쓴다.
- 이미 고정된 카피와 겹치지 않게 쓴다.
- 레퍼런스에 없는 숫자·사실을 '근거'로 지어내지 않는다."""


def _refs_brief(refs: list[dict]) -> str:
    out = []
    for r in refs:
        out.append("\n".join([
            f"[레퍼런스 {r['no']}] @{r.get('author') or '?'} · {r.get('date') or '날짜 ?'} · 좋아요 {r.get('likes') if r.get('likes') is not None else '?'}"
            f" · 댓글 {r.get('comments') if r.get('comments') is not None else '?'} · {r.get('slides')}장",
            "썸네일 카피:\n" + (r.get("copy") or "(없음)"),
            "장별 구성(앞부분):\n" + (r.get("structure") or "")[:1500],
            "캡션(앞부분):\n" + (r.get("caption") or "")[:700],
            "댓글:\n" + ((r.get("top_comments") or "").strip()[:1500] or "(수집 안 됨)"),
        ]))
    return "\n\n".join(out)


def _context(st: dict) -> str:
    guide, rules = learn.applied_guide()
    fb = RULES_FILE.read_text(encoding="utf-8") if RULES_FILE.exists() else ""
    return f"[북케터밈 스타일 가이드 · {learn.applied_guide_name()}]\n{guide}\n\n[제작 규칙 — 사용자 피드백 원장]\n{fb}"


async def gen_copies(job, wid: str, keep_ids: list[str] | None = None) -> dict:
    st = load(wid)
    if not st["refs"]:
        raise RuntimeError("1단계 레퍼런스가 없습니다.")
    cur = (st.get("copy") or {}).get("items", [])
    kept = [c for c in cur if c["id"] in set(keep_ids or [])]
    need_v = 5 - sum(1 for c in kept if c["kind"] == "베리에이션")
    need_d = 5 - sum(1 for c in kept if c["kind"] == "디벨롭")
    if need_v + need_d <= 0:
        raise RuntimeError("10개가 모두 고정돼 있어요. 다시 뽑을 카피의 고정을 풀어 주세요.")
    kept_txt = "\n".join(f"- ({c['kind']}) {c['line1']} / {c['line2']}" for c in kept) or "(없음)"
    prompt = "\n\n".join([
        _context(st),
        "[이번 제작] 책 3~5권 카드뉴스. 권수는 3단계에서 정하니, 썸네일 끝 숫자는 '책 5'처럼 5로 쓴다(3권이 되면 프로그램이 숫자만 바꾼다).",
        "[레퍼런스]\n" + _refs_brief(st["refs"]),
        f"[고정된 카피 — 그대로 두고 겹치지 않게]\n{kept_txt}",
        f"할 일: ① 레퍼런스가 잘된 이유를 짧게 분석한다(analysis). ② 새 카피를 정확히 베리에이션 {max(0, need_v)}개, "
        f"디벨롭 {max(0, need_d)}개 쓴다(copies, 이 순서로). ③ 새 카피 중 하나를 추천하고 이유를 쓴다(recommend).",
    ])
    job.progress(10, f"AI가 카피 {max(0, need_v) + max(0, need_d)}개를 쓰는 중")
    res = await claude_ai.run_structured(prompt, COPY_SYSTEM, COPY_SCHEMA, job, max_turns=4, effort="high", quiet=True)
    stamp = learn.ts()
    new = []
    for i, c in enumerate(res["copies"]):
        new.append({**c, "id": f"{stamp}_{i}", "pinned": False, "recommended": i == res["recommend"]["index"]})
    for c in kept:
        c["recommended"] = False
    items = kept + new
    items.sort(key=lambda c: (c["kind"] != "베리에이션", not c.get("pinned")))
    st = load(wid)
    prev = st.get("copy") or {}
    analysis = res["analysis"] if not kept or not prev.get("analysis") else prev["analysis"]
    st["copy"] = {"analysis": analysis, "items": items, "recommend": res["recommend"]["reason"],
                  "rounds": prev.get("rounds", 0) + 1, "chosen": prev.get("chosen")}
    save(wid, st)
    name = write_step_md(wid, 2, _copy_md(st, final=False))
    return {"file": name, "count": len(new)}


def _copy_md(st: dict, final: bool) -> str:
    c = st["copy"]
    a = c["analysis"]
    lines = [f"# 02 썸네일 카피 — {st['id']}", "", f"- 라운드 {c.get('rounds')} · 가이드 {learn.applied_guide_name()}", ""]
    if final and c.get("chosen"):
        ch = c["chosen"]
        lines += ["## 선택한 카피", f"**{ch['line1']}**", f"**{ch['line2']}**", f"- 장치: {ch.get('device', '')}", ""]
    lines += ["## 레퍼런스가 잘된 이유", f"- 후킹 구조: {a['hook']}", f"- 타깃: {a['target']}", f"- 감정: {a['emotion']}",
              f"- 반응 근거: {a['evidence']}", f"- 공식: {a['formula']}", "", "## 후보 10개"]
    for i, x in enumerate(c["items"], 1):
        tag = (" ★추천" if x.get("recommended") else "") + (" 📌고정" if x.get("pinned") else "")
        lines.append(f"{i}. ({x['kind']}) {x['line1']} / {x['line2']}{tag} — {x['device']}")
    lines += ["", f"추천 이유: {c.get('recommend', '')}"]
    return "\n".join(lines) + "\n"


def save_copies(wid: str, items: list[dict]) -> dict:
    """고정 표시·직접 고친 문구를 반영."""
    st = load(wid)
    by = {c["id"]: c for c in (st.get("copy") or {}).get("items", [])}
    for e in items:
        c = by.get(e.get("id"))
        if c:
            for k in ("line1", "line2", "pinned"):
                if k in e:
                    c[k] = e[k]
    return save(wid, st)


def confirm_copy(wid: str, chosen: dict) -> dict:
    """카피 확정: 02_썸네일카피.md, 폴더 이름 바꾸기, 3단계로."""
    if not (chosen.get("line1") or "").strip() or not (chosen.get("line2") or "").strip():
        raise ValueError("카피 두 줄을 모두 채워 주세요.")
    st = load(wid)
    st["copy"]["chosen"] = {k: chosen.get(k, "") for k in ("line1", "line2", "device", "kind", "id")}
    st["title"] = f"{chosen['line1'].strip()} / {chosen['line2'].strip()}"
    st["step"] = max(st.get("step", 1), 3)
    st["steps"]["2"] = {"at": learn.ts()}
    save(wid, st)
    new_id = rename(wid, chosen["line1"] + chosen["line2"])  # 폴더 이름을 먼저 바꾸고 md 에 새 이름을 적는다
    st = load(new_id)
    name = write_step_md(new_id, 2, _copy_md(st, final=True))
    st["steps"]["2"]["file"] = name
    save(new_id, st)
    return {"file": name, "id": new_id, "state": st}


# ---------------- 3단계 · 책 추천 10권 ----------------

from . import bookinfo  # noqa: E402

PILOTIC = "필로틱"
BOOK_IMG = "03_책표지"

CAND_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["books"],
    "properties": {"books": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["title", "author", "why", "pilotic"],
        "properties": {"title": {"type": "string", "description": "한국어판 정식 제목(부제 빼고)"},
                       "author": {"type": "string", "description": "저자(번역서는 원저자 한국어 표기)"},
                       "why": {"type": "string", "description": "이 카피에 맞는 이유 한 줄(30자 안팎)"},
                       "pilotic": {"type": "boolean", "description": "필로틱 목록에서 고른 책이면 true"}}}}},
}

SUM_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["item_id", "summary"],
        "properties": {"item_id": {"type": "string"},
                       "summary": {"type": "string", "description": "3줄 이내 요약(줄바꿈으로 구분). 주어진 책소개에 있는 내용만"}}}}},
}

BOOK_SYSTEM = """너는 출판 마케팅 인스타 @bookketer_mim(북케터밈)의 책 큐레이터다. 카드뉴스 썸네일 카피에 맞는 책을 고른다.
- [제작 규칙]의 '책 고르기'와 [스타일 가이드]의 성과 분석을 따른다.
- 베스트셀러·스테디셀러 라인 위주로 고른다(알라딘·교보·예스24 베스트, 판매량·화제성이 확인되는 책). 번역서도 된다.
- 지금 한국에서 종이책으로 살 수 있는 책만. 절판·품절된 책은 뺀다.
- 실제로 있는 책인지 모르겠으면 웹 검색으로 확인한다. 제목·저자를 지어내지 않는다.
- 카피의 주제·장르·타깃 감정에 맞아야 한다. 한 카드뉴스 안에서 결이 너무 겹치지 않게 섞는다.
- 카피에 분량·시간 조건(짧은, 얇은, 1시간, 30분, 완독 등)이 있으면 실제로 짧은 책(대략 250쪽 이하)만 고른다.
- why(맞는 이유)에는 쪽수·판매량·순위 같은 숫자를 쓰지 않는다. 숫자는 프로그램이 알라딘에서 확인해 따로 보여 준다.
- 알라딘 확인은 프로그램이 한다. 웹 검색은 주제에 맞는 베스트셀러를 찾는 데만, 많아야 5번 쓴다."""


def _used_keys() -> set:
    return set(learn.used_books().get("books", {}).keys())


def _book_item(info: dict, why: str, pilotic: bool) -> dict:
    cat = (info.get("category") or "").split(" > ")
    return {"key": info["item_id"], "title": info["title"], "author": info.get("author") or info.get("author_line", ""),
            "publisher": info.get("publisher"), "pub_date": info.get("pub_date"),
            "field": " > ".join(cat[1:3]) if len(cat) > 1 else (info.get("category") or None),
            "cover": info.get("cover"), "description": info.get("description"), "pages": info.get("pages"),
            "sales_point": info.get("sales_point"), "rank_now": info.get("rank_now"), "best_record": info.get("best_record"),
            "status": info.get("status"), "url": info["url"], "checked_at": info.get("checked_at"),
            "why": why, "summary": "", "pilotic": pilotic or (info.get("publisher") == PILOTIC),
            "used": learn.book_key(info["title"]) in _used_keys()}


async def _verify(cands: list, job, lo: float, hi: float) -> list:
    sem = asyncio.Semaphore(4)
    done = 0
    out = [None] * len(cands)

    async def one(i, c):
        nonlocal done
        async with sem:
            info = await asyncio.to_thread(bookinfo.lookup, c["title"], c["author"])
            done += 1
            job.progress(lo + (hi - lo) * done / len(cands), f"알라딘에서 확인 {done}/{len(cands)} · {c['title']}")
            if info and info.get("status") == "판매 중":
                out[i] = _book_item(info, c.get("why", ""), c.get("pilotic", False))
            else:
                job.log(f"  뺌: {c['title']} — {'알라딘에서 찾지 못함' if not info else info.get('status')}")

    await asyncio.gather(*(one(i, c) for i, c in enumerate(cands)))
    return [x for x in out if x]


async def _summaries(items: list, job) -> None:
    todo = [b for b in items if not b.get("summary")]
    if not todo:
        return
    prompt = "아래 책마다 3줄 이내 요약을 쓴다. 각 책의 [알라딘 책소개]에 있는 내용만 쓰고, 없는 내용은 지어내지 않는다.\n\n" + "\n\n".join(
        f"item_id={b['key']} · {b['title']} — {b['author']} ({b.get('field') or ''})\n[알라딘 책소개] {b.get('description') or '(없음)'}"
        for b in todo)
    res = await claude_ai.run_structured(prompt, "짧고 정확하게 요약한다. 해요체.", SUM_SCHEMA, job, max_turns=3, effort="low", quiet=True)
    by = {x["item_id"]: x["summary"] for x in res["items"]}
    for b in todo:
        b["summary"] = by.get(b["key"]) or (b.get("description") or "")[:120]


async def gen_books(job, wid: str, keep_keys=None, pilotic: bool = False) -> dict:
    st = load(wid)
    chosen = (st.get("copy") or {}).get("chosen")
    if not chosen:
        raise RuntimeError("2단계 카피를 먼저 확정해 주세요.")
    cur = (st.get("books") or {}).get("items", [])
    kept = [b for b in cur if b["key"] in set(keep_keys or [])]
    need = 10 - len(kept)
    if need <= 0:
        raise RuntimeError("10권이 모두 선택돼 있어요. 바꿀 책의 체크를 풀어 주세요.")
    seen = [f"{b['title']} — {b['author']}" for b in cur]
    used = sorted(v["title"] for v in learn.used_books().get("books", {}).values())
    pil = ""
    if pilotic and not any(b.get("pilotic") for b in kept):
        plist = await asyncio.to_thread(bookinfo.by_publisher, PILOTIC)
        pil = ("[필로틱 도서 목록 — 이 중 카피에 가장 맞는 1권을 반드시 포함하고 pilotic=true]\n"
               + "\n".join(f"- {p['title']} — {p['author_line']} ({p['month']}, 판매지수 {p['sales_point']})" for p in plist))
    guide, _ = learn.applied_guide()
    fb = RULES_FILE.read_text(encoding="utf-8") if RULES_FILE.exists() else ""
    want = need + 6  # 확인에서 빠질 몫까지
    prompt = "\n\n".join(x for x in [
        f"[썸네일 카피] {chosen['line1']} / {chosen['line2']}",
        f"[이번 제작] 사용자가 후보 10권 중 3~5권을 골라 카드뉴스를 만든다. 후보 {need}권을 새로 채운다.",
        "[제작 규칙]\n" + fb, "[스타일 가이드(앞부분)]\n" + guide[:6000],
        "[이미 후보에 있었던 책 — 다시 내지 말 것]\n" + ("\n".join(seen) or "(없음)"),
        "[북케터밈이 이미 소개한 책 — 되도록 피하되, 꼭 맞으면 넣어도 됨]\n" + (", ".join(used) or "(없음)"),
        pil,
        f"할 일: 후보 {want}권을 고른다(확인에서 빠질 수 있어 넉넉히). 베스트셀러 라인 우선.",
    ] if x)
    job.progress(3, f"AI가 웹 검색으로 후보 {want}권을 찾는 중")
    res = await claude_ai.run_structured(prompt, BOOK_SYSTEM, CAND_SCHEMA, job, max_turns=16, effort="medium",
                                         tools=["WebSearch", "WebFetch"])
    have = {learn.book_key(b["title"]) for b in kept}
    cands = []
    for c in res["books"]:
        k = learn.book_key(c["title"])
        if k and k not in have:
            have.add(k)
            cands.append(c)
    verified = await _verify(cands, job, 45, 85)
    kept_keys = {x["key"] for x in kept}
    verified = [b for b in verified if b["key"] not in kept_keys]
    short = re.search(r"짧|얇|완독|\d+\s*(분|시간)", chosen["line1"] + chosen["line2"])
    for b in verified:
        if short and b.get("pages") and b["pages"] > 280:
            b["warn"] = f"{b['pages']}쪽 — 카피의 분량 조건과 맞는지 확인"
    pil_items = [b for b in verified if b["pilotic"]][:1] if pilotic else []
    rest = sorted([b for b in verified if b not in pil_items], key=lambda b: (bool(b.get("warn")), -(b.get("sales_point") or 0)))
    new = (pil_items + rest)[:need]
    job.progress(88, "책 요약 쓰는 중(알라딘 책소개 기준)")
    await _summaries(new, job)
    items = kept + new
    st = load(wid)
    prev = st.get("books") or {}
    st["books"] = {"items": items, "selected": [b["key"] for b in kept], "rounds": prev.get("rounds", 0) + 1,
                   "pilotic": pilotic, "dropped": len(cands) - len(verified)}
    save(wid, st)
    name = write_step_md(wid, 3, _books_md(st, final=False))
    return {"file": name, "new": len(new), "dropped": len(cands) - len(verified)}


def _metric(v, url):
    return f"{v} ([출처]({url}))" if v not in (None, "") else "확인 불가"


def _books_md(st: dict, final: bool) -> str:
    b = st["books"]
    sel = b.get("selected", [])
    items = [x for k in sel for x in b["items"] if x["key"] == k] if final else b["items"]
    lines = [f"# 03 책 추천 — {st['id']}", "", f"- 카피: {st['copy']['chosen']['line1']} / {st['copy']['chosen']['line2']}",
             f"- 라운드 {b.get('rounds')} · {'최종 ' + str(len(sel)) + '권 선택' if final else '후보 10권'}"
             f" · 필로틱 포함 {'예' if b.get('pilotic') else '아니오'} · 알라딘에서 확인 못 해 뺀 후보 {b.get('dropped', 0)}권", ""]
    for i, x in enumerate(items, 1):
        mark = (" ✅선택" if x["key"] in sel and not final else "") + (" · 사용함" if x.get("used") else "") + (" · 필로틱" if x.get("pilotic") else "")
        lines += [f"## {i}. {x['title']} — {x['author']}{mark}",
                  f"- 출판사 {x.get('publisher') or '확인 불가'} · 출간 {x.get('pub_date') or '확인 불가'} · 분야 {x.get('field') or '확인 불가'}"
                  f" · {x.get('pages') or '?'}쪽",
                  f"- 판매지수(알라딘): {_metric(x.get('sales_point'), x['url'])}",
                  f"- 현재 순위: {_metric(x.get('rank_now'), x['url'])}",
                  f"- 베스트셀러 기록(최고 순위·기간, 알라딘 표기): {_metric(x.get('best_record'), x['url'])}",
                  f"- 이 카피에 맞는 이유: {x.get('why') or ''}" + (f" · ⚠️ {x['warn']}" if x.get("warn") else ""), "", x.get("summary") or "", ""]
    return "\n".join(lines)


def search_books(q: str) -> list:
    try:
        return bookinfo.search(q)[:8]
    except Exception:  # noqa: BLE001
        return []


async def add_book(job, wid: str, item_id: str) -> dict:
    """제목으로 검색해서 고른 책을 후보에 직접 추가."""
    info = await asyncio.to_thread(bookinfo.product, item_id)
    st = load(wid)
    books = st.setdefault("books", {"items": [], "selected": [], "rounds": 0})
    if any(b["key"] == info["item_id"] for b in books["items"]):
        return {"exists": True}
    item = _book_item(info, "직접 추가", False)
    await _summaries([item], job)
    st = load(wid)
    st.setdefault("books", {"items": [], "selected": [], "rounds": 0})["items"].append(item)
    save(wid, st)
    return {"added": item["title"]}


def select_books(wid: str, keys: list) -> dict:
    st = load(wid)
    st["books"]["selected"] = keys
    return save(wid, st)


def confirm_books(wid: str, keys: list) -> dict:
    st = load(wid)
    if not MIN_BOOKS <= len(keys) <= MAX_BOOKS:
        raise ValueError(f"책을 {MIN_BOOKS}~{MAX_BOOKS}권 골라 주세요(지금 {len(keys)}권).")
    st["books"]["selected"] = keys
    st["count"] = len(keys)
    changed = _fit_copy_count(st, len(keys))
    folder = path(wid) / BOOK_IMG
    folder.mkdir(exist_ok=True)
    order = {k: i for i, k in enumerate(keys)}
    for b in st["books"]["items"]:
        if b["key"] in order and b.get("cover"):
            dest = folder / f"{order[b['key']] + 1:02d}_{_slug(b['title'], 30)}.jpg"
            if not dest.exists():
                try:
                    req = urllib.request.Request(b["cover"], headers={"User-Agent": bookinfo.UA})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        dest.write_bytes(r.read())
                except Exception:  # noqa: BLE001
                    continue
            b["cover_file"] = dest.name
    st["step"] = max(st.get("step", 1), 4)
    save(wid, st)
    name = write_step_md(wid, 3, _books_md(st, final=True))
    st = load(wid)
    st["steps"]["3"] = {"file": name, "at": learn.ts()}
    save(wid, st)
    if changed:  # 카피 숫자가 바뀌면 폴더 이름도 새 카피로
        wid = rename(wid, st["copy"]["chosen"]["line1"] + st["copy"]["chosen"]["line2"])
        st = load(wid)
    return {"file": name, "id": wid, "state": st, "count": len(keys), "copy_changed": changed}


def _fit_copy_count(st: dict, n: int) -> str | None:
    """고른 권수에 맞춰 썸네일 카피 끝 숫자를 바꾼다(예: '책 5' → '책 3'). 바꿨으면 새 카피를 돌려준다."""
    ch = (st.get("copy") or {}).get("chosen")
    if not ch:
        return None
    old = ch["line2"]
    m = re.search(r"(\d+)(\s*권?\s*)$", old)
    if not m or int(m.group(1)) == n or int(m.group(1)) > 20:
        return None
    ch["line2"] = old[:m.start(1)] + str(n) + old[m.end(1):]
    st["title"] = f"{ch['line1']} / {ch['line2']}"
    return st["title"]


# ---------------- 4단계 · 카드 완성 (설명글·캡션 + 배경 + 편집을 한 번에) ----------------

from . import pinterest  # noqa: E402

BG_DIR = "04_배경"
OUT_DIR = "04_완성본"

DESC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["books", "caption", "keywords"],
    "properties": {
        "books": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["key", "tags", "lines"],
            "properties": {
                "key": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "해시태그 칩 2~3개(# 포함): 장르 + 결·감정 + 화제성"},
                "lines": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["text", "color"],
                    "properties": {"text": {"type": "string", "description": "카드 한 줄(대략 18~30자)"},
                                   "color": {"type": "string", "enum": ["흰색", "민트"]}}},
                          "description": "설명글 3~5줄. 문장 단위로 흰색·민트를 번갈아"},
            }}},
        "caption": {"type": "string", "description": "인스타 캡션 전문(해시태그 없이)"},
        "keywords": {"type": "array", "items": {"type": "string"}, "description": "썸네일 배경용 핀터레스트 검색어 3~5개"},
    },
}

DESC_SYSTEM = """너는 @bookketer_mim(북케터밈) 카드뉴스의 책 소개 카드 문구와 캡션을 쓴다.
- [스타일 가이드]의 ② 책 설명글 형식과 ④ 캡션 패턴, [제작 규칙]을 그대로 따른다.
- 책마다 [알라딘 책소개]에 있는 내용만 근거로 쓴다. 책에 없는 설정·인물·수치를 지어내지 않는다.
- 설명글: **줄거리 스토리텔링 위주**(최우선). 3~5줄, 한 줄 18~30자 안팎, 말하듯 해요체. 주인공과 사건을 장면처럼 보여 주고 [상황] → '근데' 사건이 비틀림 → 다음이 궁금한 데서 끊는다(결말·반전은 말하지 않음). '~하는 책이에요' 같은 소개·평가·주제 요약은 쓰지 않거나 마지막 한 줄만. 에세이·논픽션도 책에 실린 실제 장면·사례로 이야기처럼 시작한다. 가치 입증(평점·판매량)은 쓰지 않는다.
- 줄 색: 문장 단위로 흰색과 민트를 번갈아 쓴다(보통 흰색 문장으로 시작).
- 캡션: 📚 제목 → 1~2줄 도입 → 1️⃣ 제목 — 저자 + 2~3줄(카드 문구와 겹치지 않게, 1인칭 감상 가능) → 📌 마무리 🤍. 해시태그 없음, 짧게.
- 배경 검색어: 20대 여성이 좋아할 **감성 실사 사진**이 나오는 핀터레스트 검색어 3~5개. 필름 카메라 느낌, 자연광, 카페·창가·침대·기차에서 책 읽는 장면, 일상 스냅, 썸네일 카피 분위기를 담는다. 'aesthetic photo', 'film photography', '감성 사진', '필름 사진' 같은 말을 붙이고, anime·illustration·art·AI·wallpaper 처럼 그림이나 AI 이미지가 나오는 말은 쓰지 않는다."""


def _desc_range() -> tuple[int, int]:
    _, rules = learn.applied_guide()
    d = rules.get("desc_chars") or {}
    if d.get("avg") is not None and d.get("sd") is not None:
        return max(int(d.get("min", 0)), int(d["avg"] - d["sd"])), min(int(d.get("max", 999)), int(d["avg"] + d["sd"]) + 1)
    return 75, 140


def _count_lines(lines: list) -> int:
    return len("".join(x["text"] for x in lines))


def _selected_books(st: dict) -> list:
    sel = st["books"]["selected"]
    by = {b["key"]: b for b in st["books"]["items"]}
    return [by[k] for k in sel if k in by]


INTRO_MIN = 300  # 알라딘 책소개가 이보다 짧으면(없으면) 웹 검색으로 줄거리 근거를 찾는다


async def _write_texts(st: dict, books: list, job, only_key: str | None = None, instruction: str = "") -> dict:
    guide, _ = learn.applied_guide()
    fb = RULES_FILE.read_text(encoding="utf-8") if RULES_FILE.exists() else ""
    todo = [b for b in books if not only_key or b["key"] == only_key]  # 다시 쓰기는 그 책만 읽는다
    intros = await asyncio.gather(*(asyncio.to_thread(bookinfo.intro, b["key"], 6000) for b in todo))
    lo, hi = _desc_range()
    ch = st["copy"]["chosen"]
    cur = {s.get("key"): s for s in (st.get("cards") or {}).get("slides", []) if s.get("type") == "book"}
    blocks, need_web = [], []
    for b, it in zip(todo, intros):
        block = (f"key={b['key']} · {b['title']} — {b['author']} ({b.get('field') or ''}, {b.get('pages') or '?'}쪽)\n"
                 f"[알라딘 책소개] {it or b.get('description') or '(없음)'}")
        if len(it or "") < INTRO_MIN:
            need_web.append(b["title"])
            block += ("\n[알라딘 책소개가 없거나 짧다 → 이 책은 쓰기 전에 반드시 WebSearch 를 먼저 한 번 이상 해서(기억에만 기대지 말 것) "
                      "교보문고·예스24·출판사 책소개·서평에서 줄거리(주인공·사건)를 찾아 "
                      "그 내용만 근거로 쓴다. 찾지 못한 내용은 지어내지 않는다]")
        if only_key and cur.get(b["key"]):
            # 다시 쓰기: 지금 문구를 보여 주고 다른 문장으로, 줄거리 스토리텔링으로 새로 쓰게 한다
            block += ("\n[지금 카드 문구 — 사용자가 마음에 들지 않아 다시 쓰기를 눌렀다. 이것과 다른 문장으로, "
                      "책 홍보·출간 이력·평가가 아니라 주인공과 사건의 줄거리 스토리텔링으로 새로 쓴다]\n"
                      + "\n".join(l["text"] for l in cur[b["key"]].get("lines", [])))
        blocks.append(block)
    prompt = "\n\n".join([
        f"[썸네일 카피] {ch['line1']} / {ch['line2']}  · 책 {len(books)}권",
        "[스타일 가이드]\n" + guide, "[제작 규칙]\n" + fb,
        f"[설명글 길이] 책마다 {lo}~{hi}자(공백 포함, 줄 합계)",
        "[책]\n" + "\n\n".join(blocks),
        (f"[사용자 요청 — 가장 우선해서 반영] {instruction.strip()}" if instruction.strip() else ""),
        ("할 일: 이 책 한 권의 카드 문구만 다시 쓴다(caption·keywords 는 빈 값으로)." if only_key else
         "할 일: 책마다 해시태그 칩과 설명글, 캡션 전문, 배경 검색어를 쓴다. 캡션의 책 순서는 위 순서대로."),
    ])
    prompt = "\n\n".join(x for x in prompt.split("\n\n") if x != "")
    if need_web:  # 책소개가 없는 책이 있으면 웹 검색을 허용한다(사실 검증이 뒤에서 한 번 더 확인)
        job.log(f"  알라딘 책소개가 없어 웹에서 줄거리 찾기: {', '.join(need_web)}")
        return await claude_ai.run_structured(prompt, DESC_SYSTEM, DESC_SCHEMA, job, max_turns=12 + 3 * len(need_web),
                                              effort="medium", tools=["WebSearch", "WebFetch"])
    return await claude_ai.run_structured(prompt, DESC_SYSTEM, DESC_SCHEMA, job, max_turns=4, effort="medium", quiet=True)


BAN = re.compile(r"(anime|manga|illustrat|drawing|cartoon|webtoon|midjourney|stable ?diffusion|dall-?e|ai ?art|ai ?generated|"
                 r"digital ?art|fan ?art|3d ?render|render|wallpaper|clipart|vector|painting|애니|일러스트|그림|웹툰|만화|ai그림|인공지능)", re.I)

SCREEN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["items"],
    "properties": {"items": {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": ["file", "real_photo", "score", "why"],
        "properties": {"file": {"type": "string"},
                       "real_photo": {"type": "boolean", "description": "카메라로 찍은 실제 사진이면 true. AI 생성·애니·일러스트·그림·3D·합성 티 나는 이미지면 false"},
                       "score": {"type": "integer", "description": "20대 여성이 좋아할 감성(필름·자연광·일상)과 카피 분위기에 맞는 정도 1~5"},
                       "why": {"type": "string"}}}}},
}
SCREEN_SYSTEM = """너는 인스타 책 계정 북케터밈의 썸네일 배경 사진을 고르는 사람이다. 이미지를 하나씩 열어 본다.
- 실제 카메라로 찍은 사진만 real_photo=true. AI가 만든 이미지(지나치게 매끈한 피부, 이상한 손가락·글자, 비현실적 조명), 애니메이션, 일러스트, 그림, 3D 렌더, 웹툰은 모두 false.
- 판단이 애매하면 false 로 둔다(사용자가 AI 이미지와 애니 느낌을 절대 원하지 않는다).
- score 는 20대 여성이 좋아할 감성(필름 카메라 느낌, 자연광, 카페·창가·독서·일상)과 썸네일 카피 분위기에 맞는 정도."""


async def _collect_bg(wid: str, keywords: list, job, lo: float, hi: float, copy_text: str = "") -> list:
    folder = path(wid) / BG_DIR
    folder.mkdir(exist_ok=True)
    tmp = folder / "_검사중"
    tmp.mkdir(exist_ok=True)
    job.progress(lo, f"핀터레스트에서 감성 사진 찾는 중: {', '.join(keywords[:3])}")
    pins = await pinterest.search(keywords[:5], per_query=10, scrolls=3)
    pins = [p for p in pins if not BAN.search(f"{p.get('alt') or ''} {p.get('query') or ''}")]
    big = [p for p in pins if p.get("w") and p.get("h") and p["w"] >= 700 and 1.1 <= p["h"] / p["w"] <= 1.9]
    big.sort(key=lambda p: -(p["w"] * p["h"]))
    cands = (big + [p for p in pins if p not in big and (not p.get("w") or p["w"] >= 600)])[:24]
    # 작은 미리보기(236px)로 먼저 검사한다
    files = []
    for i, p in enumerate(cands):
        name = f"c{i:02d}.jpg"
        if await asyncio.to_thread(pinterest.download, p.get("src") or p["img_url"], tmp / name):
            files.append((name, p))
    job.progress(lo + (hi - lo) * 0.35, f"AI가 후보 {len(files)}장을 직접 보고 실사 감성 사진만 고르는 중")
    keep = []
    if files:
        listing = "\n".join(f"- {(tmp / n).as_posix()}" for n, _ in files)
        res = await claude_ai.run_structured(
            f"[썸네일 카피] {copy_text}\n후보 이미지(하나씩 Read 로 열어 볼 것):\n{listing}\n\nfile 에는 파일 이름(c00.jpg 처럼)만 쓴다.",
            SCREEN_SYSTEM, SCREEN_SCHEMA, job, max_turns=len(files) + 6, effort="low", cwd=tmp, quiet=True)
        verdict = {Path(x["file"]).name: x for x in res["items"]}
        for n, p in files:
            v = verdict.get(n)
            if v and v["real_photo"] and v["score"] >= 3:
                keep.append((v["score"], p, v["why"]))
        keep.sort(key=lambda x: (-x[0], -((x[1].get("w") or 0) * (x[1].get("h") or 0))))
    out = []
    for k, (score, p, why) in enumerate(keep[:10]):
        name = f"bg_{learn.ts()}_{k:02d}.jpg"
        if await asyncio.to_thread(pinterest.download, p["img_url"], folder / name):
            out.append({"file": name, "pin": p.get("pin"), "w": p.get("w"), "h": p.get("h"), "query": p.get("query"),
                        "alt": p.get("alt"), "score": score, "why": why})
        job.progress(lo + (hi - lo) * (0.7 + 0.3 * (k + 1) / max(1, len(keep[:10]))), f"원본 저장 {len(out)}/{len(keep[:10])}")
    shutil.rmtree(tmp, ignore_errors=True)
    job.log(f"  배경: 후보 {len(files)}장 중 실사 감성 사진 {len(out)}장 통과")
    return out


def _default_slides(st: dict, books: list, texts: dict, bgs: list) -> dict:
    ch = st["copy"]["chosen"]
    by = {x["key"]: x for x in texts["books"]}
    bg0 = bgs[0]["file"] if bgs else None
    slides = [{"type": "thumb", "line1": ch["line1"], "line2": ch["line2"], "c1": "#FFFFFF", "c2": "#D4FEBE",
               "chip1": "북케터 밈", "chip2": "책 추천", "size": 1.0, "dy": 0,
               "bg": bg0, "zoom": 1.0, "px": 50, "py": 50, "shade": 1.0}]
    for b in books:
        t = by.get(b["key"]) or {"tags": [], "lines": []}
        slides.append({"type": "book", "key": b["key"], "title": b["title"], "tags": " ".join(t["tags"]),
                       "lines": t["lines"], "cover": b.get("cover_file"), "size": 1.0, "dy": 0})
    slides.append({"type": "cta", "main": "북케터밈을 팔로우하고,", "sub": "분야별 추천 도서를 빠르게 챙겨가세요!"})
    return {"slides": slides, "body_bg": bg0, "body_opacity": 0.27, "body_zoom": 1.0, "body_px": 50, "body_py": 50,
            "bgs": bgs, "caption": texts.get("caption", ""), "keywords": texts.get("keywords", []), "range": list(_desc_range())}


async def build_cards(job, wid: str) -> dict:
    """책 확정 뒤 자동: (설명글·캡션·검색어) → (핀터레스트 배경) → 템플릿 배치 → 04_설명글.md"""
    st = load(wid)
    books = _selected_books(st)
    if not books:
        raise RuntimeError("3단계 책을 먼저 확정해 주세요.")
    job.progress(3, f"책 {len(books)}권 설명글·캡션 쓰는 중 (알라딘 책소개 기준)")
    texts = await _write_texts(st, books, job)
    st = load(wid)
    st["cards"] = _default_slides(st, books, texts, [])
    st["step"] = max(st.get("step", 1), 4)
    save(wid, st)
    job.progress(45, "배경 찾기와 사실 검증을 함께 하는 중")
    ch = st["copy"]["chosen"]
    bgs, _ = await asyncio.gather(
        _collect_bg(wid, texts.get("keywords") or ["film photography girl reading book aesthetic"], learn._Sub(job, 45, 97), 0, 100,
                    f"{ch['line1']} / {ch['line2']}"),
        factcheck(learn._Sub(job, 45, 97), wid))
    st = load(wid)
    st["cards"]["bgs"] = bgs
    bg0 = bgs[0]["file"] if bgs else None
    st["cards"]["body_bg"] = st["cards"].get("body_bg") or bg0
    for s in st["cards"]["slides"]:
        if s["type"] == "thumb" and not s.get("bg"):
            s["bg"] = bg0
    save(wid, st)
    name = write_step_md(wid, 4, _cards_md(st))
    st = load(wid)
    st["steps"]["4"] = {"file": name, "at": learn.ts()}
    save(wid, st)
    return {"file": name, "bgs": len(bgs)}


def _cards_md(st: dict) -> str:
    c = st["cards"]
    lo, hi = c.get("range", [75, 140])
    lines = [f"# 04 설명글·캡션 — {st['id']}", "", f"- 카피: {st['copy']['chosen']['line1']} / {st['copy']['chosen']['line2']}",
             f"- 설명글 길이 기준 {lo}~{hi}자 (스타일 가이드 평균 ±1 표준편차)", ""]
    for s in c["slides"]:
        if s["type"] != "book":
            continue
        n = _count_lines(s["lines"])
        flag = "" if lo <= n <= hi else f" ⚠️ 범위 밖({lo}~{hi})"
        lines += [f"## {s['title']}", f"해시태그: {s['tags']}", "", *[f"> ({x['color']}) {x['text']}" for x in s["lines"]],
                  "", f"글자 수 {n}자{flag}", ""]
    fc = c.get("factcheck")
    if fc:
        lines += [f"## 사실 검증 ({fc.get('at')})"]
        for x in fc.get("copy_fit", []):
            lines.append(f"- ⚠️ 카피와 안 맞음: {x}")
        for b in fc.get("books", []):
            if not b["issues"]:
                lines.append(f"- ✅ {b['title']}: 문제 없음")
            for i in b["issues"]:
                lines.append(f"- ✏️ {b['title']} ({i['where']}) \"{i['text']}\" → {i['problem']} · 근거: {i['evidence']}")
        for i in fc.get("caption", []):
            lines.append(f"- ✏️ 캡션 \"{i['text']}\" → {i['problem']} · 근거: {i['evidence']}")
        lines.append("")
    lines += ["## 캡션", "", c.get("caption", ""), "", "## 배경 후보(핀터레스트 원본 링크)",
              *[f"- {b['file']} · {b.get('w')}×{b.get('h')} · {b.get('pin') or '링크 없음'} · 검색어 '{b.get('query')}'" for b in c.get("bgs", [])]]
    return "\n".join(lines) + "\n"


async def rewrite_book(job, wid: str, key: str, instruction: str = "") -> dict:
    st = load(wid)
    books = _selected_books(st)
    res = await _write_texts(st, books, job, only_key=key, instruction=instruction)
    t = next((x for x in res["books"] if x["key"] == key), None)
    if not t:
        raise RuntimeError("다시 쓰지 못했습니다.")
    st = load(wid)
    for s in st["cards"]["slides"]:
        if s.get("key") == key:
            s["tags"], s["lines"] = " ".join(t["tags"]), t["lines"]
    save(wid, st)
    await factcheck(job, wid, keys=[key])
    return {"key": key}


async def more_bg(job, wid: str, keywords: list) -> dict:
    ch = load(wid)["copy"]["chosen"]
    bgs = await _collect_bg(wid, keywords, job, 5, 98, f"{ch['line1']} / {ch['line2']}")
    st = load(wid)
    st["cards"]["bgs"] = bgs + st["cards"].get("bgs", [])
    st["cards"]["keywords"] = keywords
    save(wid, st)
    return {"added": len(bgs)}


def upload_asset(wid: str, data: str, kind: str) -> str:
    sub = BG_DIR if kind == "bg" else BOOK_IMG
    folder = path(wid) / sub
    folder.mkdir(exist_ok=True)
    ext = ".png" if data.startswith("data:image/png") else ".jpg"
    name = f"{'bg' if kind == 'bg' else 'cover'}_up_{learn.ts()}{ext}"
    (folder / name).write_bytes(_data_url_bytes(data))
    if kind == "bg":
        st = load(wid)
        st["cards"].setdefault("bgs", []).insert(0, {"file": name, "pin": None, "query": "직접 올림"})
        save(wid, st)
    return name


def save_cards(wid: str, cards: dict) -> dict:
    st = load(wid)
    if cards.get("rev") != st["cards"].get("rev"):
        raise StaleCards()
    keep = {k: st["cards"].get(k) for k in ("bgs", "range", "factcheck")}
    st["cards"] = {**cards, **{k: v for k, v in keep.items() if v is not None}}
    return save(wid, st)


async def export_cards(job, wid: str, base_url: str) -> dict:
    """편집기와 같은 템플릿(/render)을 화면 없는 브라우저로 1080×1350 PNG 로 찍는다."""
    from playwright.async_api import async_playwright
    st = load(wid)
    n = len(st["cards"]["slides"])
    out = path(wid) / OUT_DIR
    if out.exists() and any(out.iterdir()):
        out = path(wid) / f"{OUT_DIR}_{learn.ts()}"
    out.mkdir(parents=True, exist_ok=True)
    files = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
        for i in range(n):
            await page.goto(f"{base_url}render?wid={urllib.parse.quote(wid)}&i={i}", wait_until="networkidle")
            await page.wait_for_function("window.__ready === true", timeout=20000)
            f = out / f"{i + 1:02d}.png"
            await page.screenshot(path=str(f), clip={"x": 0, "y": 0, "width": 1080, "height": 1350})
            files.append(f.name)
            job.progress((i + 1) / n * 99, f"PNG 저장 {i + 1}/{n}")
        await browser.close()
    st = load(wid)
    st["export"] = {"folder": out.name, "files": files, "at": learn.ts()}
    st["done"] = True  # 발행은 프로그램 밖에서 직접(보안상 계정 연동 없음)
    save(wid, st)
    write_step_md(wid, 4, _cards_md(st))
    return {"folder": out.name, "files": files}


# ---------------- 4단계 · 사실 검증 (카드 문구·해시태그·캡션) ----------------

FC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["books", "caption_issues", "fixed_caption", "copy_fit"],
    "properties": {
        "books": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["key", "issues", "fixed_tags", "fixed_lines"],
            "properties": {
                "key": {"type": "string"},
                "issues": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["where", "text", "problem", "evidence"],
                    "properties": {"where": {"type": "string", "enum": ["카드", "해시태그"]},
                                   "text": {"type": "string", "description": "문제가 된 원래 문구"},
                                   "problem": {"type": "string", "description": "틀림 / 근거 없음 / 과장 중 무엇이고 왜인지"},
                                   "evidence": {"type": "string", "description": "확인한 출처와 실제 내용(가능하면 주소)"}}}},
                "fixed_tags": {"type": "string", "description": "고친 해시태그 칩 전체(문제 없으면 원래 그대로)"},
                "fixed_lines": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["text", "color"],
                    "properties": {"text": {"type": "string"}, "color": {"type": "string", "enum": ["흰색", "민트"]}}},
                    "description": "고친 카드 문구 전체(문제 없으면 원래 그대로). 줄 수·말투·색 교차는 유지"},
            }}},
        "caption_issues": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "problem", "evidence"],
            "properties": {"text": {"type": "string"}, "problem": {"type": "string"}, "evidence": {"type": "string"}}}},
        "fixed_caption": {"type": "string", "description": "caption_issues 가 하나라도 있으면 그 부분을 실제로 고친 캡션 전체(원문과 달라야 함). 문제 없으면 원래 그대로"},
        "copy_fit": {"type": "array", "items": {"type": "string"},
                     "description": "썸네일 카피의 조건(분량·시간·장르·대상)과 실제 책이 맞지 않는 점. 예: '1시간 완독'인데 456쪽. 없으면 빈 배열"},
    },
}

FC_SYSTEM = """너는 출판 마케팅 카드뉴스의 사실 검증 담당이다. 틀린 정보가 하나라도 나가면 안 된다.
- 책마다 [알라딘 책소개]와 [알라딘 상품 정보]를 먼저 근거로 삼고, 거기 없는 주장(수상·판매량·드라마/영화화·작가 이력·인물 이름·줄거리 세부)은 웹 검색으로 확인한다.
- 문제로 잡는 것: ① 사실과 다른 것 ② 근거를 찾을 수 없는 것 ③ 근거보다 부풀린 것(예: 판매량·순위·'밀리언셀러'). 확인되면 문제 삼지 않는다.
- 줄거리 묘사는 책소개·서평과 맞으면 통과. 스포일러 수준의 과장·왜곡은 문제.
- 고칠 때는 최소한만 고친다. 말투(해요체), 줄 수, 흰색/민트 교차, 궁금하게 끝내는 구조를 유지한다. 근거 없는 주장은 확인된 사실로 바꾸거나 뺀다.
- 캡션도 같은 기준으로 본다. 오늘 날짜와 맞지 않는 계절·시기 표현도 문제다.
- 썸네일 카피의 조건(분량·시간·장르·대상)과 책이 맞지 않으면 copy_fit 에 적는다(카드 문구는 고치지 않는다).
- 웹 검색은 필요한 것만, 책당 많아야 2~3번."""


def _fc_input(st: dict) -> tuple[str, list]:
    books = _selected_books(st)
    by = {s.get("key"): s for s in st["cards"]["slides"] if s["type"] == "book"}
    ch = st["copy"]["chosen"]
    return f"{ch['line1']} / {ch['line2']}", [(b, by.get(b["key"])) for b in books if by.get(b["key"])]


async def factcheck(job, wid: str, keys: list | None = None) -> dict:
    """카드 문구·해시태그·캡션을 알라딘 책소개 + 웹 검색으로 대조하고, 틀린 곳은 고쳐 넣는다(바뀐 내용은 기록)."""
    st = load(wid)
    copy_text, pairs = _fc_input(st)
    if keys:
        pairs = [(b, s) for b, s in pairs if b["key"] in keys]
    job.progress(5, f"사실 검증: 책 {len(pairs)}권 책소개 다시 읽는 중")
    intros = await asyncio.gather(*(asyncio.to_thread(bookinfo.intro, b["key"], 6000) for b, _ in pairs))
    blocks = []
    for (b, s), it in zip(pairs, intros):
        blocks.append("\n".join([
            f"key={b['key']} · 『{b['title']}』 — {b['author']}",
            f"[알라딘 상품 정보] 출판사 {b.get('publisher')} · 출간 {b.get('pub_date')} · {b.get('pages') or '?'}쪽 · 분야 {b.get('field')}"
            f" · 판매지수 {b.get('sales_point')} · 베스트 기록 {b.get('best_record') or '없음'} · {b.get('url')}",
            f"[알라딘 책소개] {it or b.get('description') or '(없음)'}",
            f"[카드 해시태그] {s.get('tags', '')}",
            "[카드 문구]\n" + "\n".join(f"({l['color']}) {l['text']}" for l in s.get("lines", [])),
        ]))
    prompt = "\n\n".join([
        f"[오늘 날짜] {learn.ts()[:10]}",
        f"[썸네일 카피] {copy_text}",
        "[책]\n" + "\n\n".join(blocks),
        "[캡션]\n" + (st["cards"].get("caption") or "") if not keys else "[캡션] (이번엔 검사하지 않음 — caption_issues 는 빈 배열, fixed_caption 은 빈 문자열)",
    ])
    job.progress(20, "사실 검증: AI가 책소개·웹 검색으로 대조하는 중")
    res = await claude_ai.run_structured(prompt, FC_SYSTEM, FC_SCHEMA, job, max_turns=30, effort="medium",
                                         tools=["WebSearch", "WebFetch"])
    st = load(wid)
    log = {"at": learn.ts(), "books": [], "caption": [], "copy_fit": res.get("copy_fit", [])}
    by = {s.get("key"): s for s in st["cards"]["slides"] if s["type"] == "book"}
    for r in res["books"]:
        s = by.get(r["key"])
        if not s:
            continue
        entry = {"key": r["key"], "title": s["title"], "issues": r["issues"], "changed": False}
        if r["issues"]:
            before = {"tags": s["tags"], "lines": s["lines"]}
            if r.get("fixed_lines"):
                s["lines"] = r["fixed_lines"]
            if r.get("fixed_tags"):
                s["tags"] = r["fixed_tags"]
            entry.update(changed=before != {"tags": s["tags"], "lines": s["lines"]}, before=before)
        log["books"].append(entry)
    if not keys and res.get("caption_issues"):
        log["caption"] = res["caption_issues"]
        fixed = (res.get("fixed_caption") or "").strip()
        if fixed and fixed != (st["cards"].get("caption") or "").strip():
            log["caption_before"] = st["cards"].get("caption")
            st["cards"]["caption"] = fixed
        else:  # 문제는 찾았는데 고친 캡션을 못 받았으면, 그대로 두지 않고 화면에 '직접 고쳐야 함'으로 알린다
            log["caption_unfixed"] = True
    st["cards"]["factcheck"] = log
    save(wid, st)
    write_step_md(wid, 4, _cards_md(st))
    n = sum(len(b["issues"]) for b in log["books"]) + len(log["caption"])
    return {"issues": n, "copy_fit": len(log["copy_fit"])}



# ---------------- 작업 관리: 휴지통 · 복제 · zip ----------------

TRASH_DIR = WORK_DIR / "_휴지통"


def delete_works(ids: list) -> dict:
    """바로 지우지 않고 작업/_휴지통 으로 옮긴다(되살릴 수 있음)."""
    TRASH_DIR.mkdir(exist_ok=True)
    moved = []
    for wid in ids:
        try:
            src = path(wid)
        except FileNotFoundError:
            continue
        dest, n = TRASH_DIR / wid, 2
        while dest.exists():
            dest, n = TRASH_DIR / f"{wid}_{n}", n + 1
        shutil.move(str(src), str(dest))
        moved.append(wid)
    return {"moved": moved}


def list_trash() -> list:
    out = []
    if TRASH_DIR.exists():
        for p in sorted(TRASH_DIR.iterdir(), reverse=True):
            f = p / "state.json"
            if f.exists():
                try:
                    st = json.loads(f.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    st = {}
                out.append({"id": p.name, "title": st.get("title") or "(카피 고르기 전)", "step": st.get("step"),
                            "updated": st.get("updated"), "done": bool(st.get("export"))})
    return out


def restore_work(tid: str) -> str:
    if "/" in tid or "\\" in tid or ".." in tid or not (TRASH_DIR / tid).is_dir():
        raise FileNotFoundError(tid)
    name, n = tid, 2
    while (WORK_DIR / name).exists():
        name, n = f"{tid}_{n}", n + 1
    shutil.move(str(TRASH_DIR / tid), str(WORK_DIR / name))
    st = load(name)
    st["id"] = name
    save(name, st)
    return name


def duplicate_work(wid: str) -> str:
    """같은 레퍼런스·카피로 다른 버전을 만들 때: 폴더째 복사(시각은 새로, 완성 표시는 지움)."""
    src = path(wid)
    stamp = learn.ts()
    new = f"{stamp}_{wid[20:] or '새작업'}"
    shutil.copytree(src, WORK_DIR / new, ignore=shutil.ignore_patterns("state.json.tmp"))
    st = load(new)
    st.update(id=new, created=stamp, title=(st.get("title") or "") + (" (복사)" if st.get("title") else ""))
    st.pop("export", None)
    st.pop("done", None)
    save(new, st)
    return new


def export_zip(wid: str) -> tuple[str, bytes]:
    """마지막으로 내보낸 PNG + 캡션(txt)을 zip 하나로."""
    import io
    import zipfile
    st = load(wid)
    ex = st.get("export")
    if not ex:
        raise FileNotFoundError("아직 PNG로 내보내지 않았어요.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in ex["files"]:
            p = path(wid) / ex["folder"] / f
            if p.exists():
                z.write(p, f)
        z.writestr("캡션.txt", (st.get("cards") or {}).get("caption", ""))
    return f"{wid}.zip", buf.getvalue()
