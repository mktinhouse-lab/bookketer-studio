"""수집 → 기획 → 이미지 후보 → 썸네일 → 완성본 흐름의 실제 작업과 md 기록 형식."""
import asyncio
import base64
import datetime as dt
import os
import re
import shutil
from pathlib import Path

from . import bookcover, claude_ai, formats, instagram, pinterest, storage
from .config import ASSETS_DIR, DATA_DIR, DESKTOP_OUT
from .render import render_cards

MODE_KO = formats.MODE_KO


def img_url(kind: str, folder: str, name: str) -> str:
    from urllib.parse import quote
    return f"/api/img/{kind}/{quote(folder)}/{quote(name)}"


def when_of(name: str) -> str:
    m = re.match(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})", name)
    return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}" if m else ""


def folder_of(name: str, suffix: str = "_assets") -> str:
    return name[:-3] + suffix


# =============== 수집 ===============

def crawl_md(d: dict, folder: str) -> str:
    p = d["params"]
    L = [f"# 레퍼런스 수집: {d['source']}", "", f"- 수집 방식: {d['label']}"]
    L += [f"- {k}: {v}" for k, v in p.items()]
    L += [f"- 수집 게시물: {len(d['posts'])}개", f"- 이미지 폴더: {folder}"]
    for i, x in enumerate(d["posts"], 1):
        L += ["", f"## 게시물 {i}", f"- 링크: {x['url']}", f"- 유형: {x['type']} · {x['slides']}장",
              f"- 작성자: {x['author']}", f"- 날짜: {x['date']}", f"- 좋아요: {x['likes'] or 0:,}",
              f"- 댓글 수: {x['comments'] or 0:,}", f"- 슬라이드 이미지: {', '.join(x['images']) or '없음'}",
              "", "### 캡션", x["caption"] or "(없음)"]
        if x["top_comments"]:
            L += ["", "### 댓글"] + [f"- {c}" for c in x["top_comments"]]
        if x["images"]:
            L += ["", " ".join(f"![{n}]({folder}/{n})" for n in x["images"][:4])]
    return "\n".join(L)


async def crawl_job(job, *, keyword="", urls=None, min_likes=5000, fmt=None, recent_days=0, fresh=False):
    tag = "링크" if urls else ("새로찾기" if fresh else "검색")
    name = storage.new_name("crawl", tag, keyword or f"{len(urls)}개")
    folder = storage.assets_dir("crawl", name)
    try:
        if urls:  # 링크는 로그인 없이 공개 임베드 페이지로
            res = await instagram.fetch_public(job, urls, folder)
        else:
            res = await instagram.crawl(job, keyword=keyword, min_likes=min_likes, fmt=fmt,
                                        recent_days=recent_days, fresh=fresh,
                                        headless=storage.load_settings().get("headless", False), assets=folder)
    except Exception:
        storage.safe_path("crawl", name).unlink(missing_ok=True)
        shutil.rmtree(folder, ignore_errors=True)
        raise
    params = {"최소 좋아요": min_likes} if not urls else {}
    if not urls:
        params.update({"형식": MODE_KO.get(fmt, "전체(릴스 2개까지)"), "최근": f"{recent_days}일" if recent_days else "전체",
                       "새로 찾기": "예" if fresh else "아니오"})
    params["검사한 게시물"] = res["checked"]
    d = {"label": "링크로 가져오기(로그인 없이)" if urls else "검색 스크롤 수집", "source": keyword or f"링크 {len(urls)}개",
         "params": params, "posts": res["posts"]}
    storage.write_md("crawl", name, crawl_md(d, folder.name), d)
    return {"file": name, "count": len(res["posts"])}


# =============== 이미지 후보 ===============

def images_md(d: dict) -> str:
    L = [f"# 이미지 후보: {d['copy'].splitlines()[0] if d['copy'] else ''}", "", "> 확정 카피"]
    L += [f"> {ln}" for ln in d["copy"].split("\n")]
    L += ["", f"- 검색어: {' / '.join(d['queries'])}", f"- 후보: {len(d['candidates'])}장", f"- 이미지 폴더: {d['assets']}",
          "- 주의: 핀터레스트 이미지는 저작권·초상권이 있을 수 있습니다. 게시 전 사용 권한을 확인하세요.", "", "## AI 추천"]
    L += [f"{i}. {r['file']} — {r['score']}점 · {r['reason']}" for i, r in enumerate(d["ranking"], 1)]
    for i, c in enumerate(d["candidates"], 1):
        L += ["", f"## 후보 {i}", f"- 파일: {c['file']}", f"- 원본 핀: {c['pin'] or '(없음)'}", f"- 검색어: {c['query']}",
              f"- 설명: {c['alt'] or '-'}", f"- 원본 크기: {c.get('w') or '?'}×{c.get('h') or '?'}",
              f"![{c['file']}]({d['assets']}/{c['file']})"]
    return "\n".join(L)


async def _fetch_images(queries, folder: Path, start: int, exclude: set[str], per_query=5):
    found = await pinterest.search(queries, per_query=per_query, exclude=exclude)
    out = []
    n = start
    for c in found:
        n += 1
        fname = f"c{n:02d}.jpg"
        ok = await asyncio.to_thread(pinterest.download, c["img_url"], folder / fname)
        if ok:
            out.append({**c, "file": fname})
    return out


async def find_images(job, copy: str, image_guide: str, queries: list[str], plan_file: str, round_n: int,
                      cand_n: int) -> dict:
    name = storage.new_name("generate", "이미지후보", copy.split("\n")[0])
    folder = storage.assets_dir("generate", name)
    cands = await _fetch_images(queries[:3], folder, 0, set())
    ranking = await claude_ai.rank_images(copy, image_guide, folder, [c["file"] for c in cands], job) if cands else []
    d = {"type": "이미지후보", "copy": copy, "image": image_guide, "queries": queries[:3], "candidates": cands,
         "ranking": ranking, "analysis_file": plan_file, "round": round_n, "cand": cand_n, "assets": folder.name, "file": name}
    storage.write_md("generate", name, images_md(d), d)
    return img_ref(d)


def img_ref(d: dict) -> dict:
    top = (d["ranking"] or [{}])[0].get("file") or (d["candidates"][0]["file"] if d["candidates"] else "")
    by = {c["file"]: c for c in d["candidates"]}
    r = next((x for x in d["ranking"] if x["file"] == top), {})
    return {"file": d["file"], "assets": d["assets"], "bg": top, "pin": by.get(top, {}).get("pin", ""),
            "reason": r.get("reason", "")}


async def more_images_job(job, cand_file: str, direction: str):
    d = storage.read_data("generate", cand_file)
    folder = storage.assets_dir("generate", cand_file)
    if direction:
        job.progress(10, "원하는 방향으로 검색어 만드는 중")
        queries = await claude_ai.image_queries(d["copy"], d.get("image", ""), direction, job)
    else:
        queries = d["queries"]
    job.progress(30, "핀터레스트에서 찾는 중: " + " · ".join(queries))
    exclude = {c["pin"] or c["img_url"] for c in d["candidates"]}
    new = await _fetch_images(queries, folder, len(d["candidates"]), exclude, per_query=4)
    job.progress(70, f"새 이미지 {len(new)}장 · AI가 고르는 중")
    rank = await claude_ai.rank_images(d["copy"], direction or d.get("image", ""), folder, [c["file"] for c in new], job) if new else []
    d["candidates"] += new
    d["queries"] = list(dict.fromkeys(d["queries"] + queries))
    d["ranking"] = rank + [r for r in d["ranking"] if r["file"] not in {x["file"] for x in rank}]
    storage.write_md("generate", cand_file, images_md(d), d)
    newset = {c["file"] for c in new}
    ordered = [r["file"] for r in rank] + [c["file"] for c in new if c["file"] not in {r["file"] for r in rank}]
    return {"file": cand_file, "new": [f for f in ordered if f in newset], "queries": queries}


# =============== 기획 ===============

def plan_md(d: dict) -> str:
    pj = d["project"]
    L = [f"# 기획 · {pj.get('name', '')} · {MODE_KO[d['mode']]}", "",
         f"- 수집 파일: {d['crawl_file']}", f"- 레퍼런스: {' '.join('#' + str(n) for n in d['picks'])}",
         f"- 핵심 메시지: {pj.get('message', '')}"]
    a = d.get("auto")
    if a:
        L += ["", "## 자동 준비 (레퍼런스 → 썸네일 카피 → 책 찾기)", ""]
        if a.get("variations"):
            v = a["variations"]
            L += [f"- 레퍼런스 원본 카피: {v['original'].replace(chr(10), ' / ')}", f"- 공식: {v['formula']}",
                  f"- 고른 썸네일 카피: **{pj.get('thumb', '')}**", "- 베리에이션:"]
            L += [f"  {i}. {x['copy'].replace(chr(10), ' / ')}{' ← 추천' if i == v['recommend'] else ''}"
                  for i, x in enumerate(v["variations"], 1)]
        L += [f"- 고른 책 ({a.get('books_file') or '-'}):"]
        L += [f"  {i}. {b['title']} — {b['author']} · 교보문고 {(b.get('kyobo') or {}).get('note', '-')}"
              for i, b in enumerate(a.get("books") or [], 1)]
    for r in d["rounds"]:
        L += ["", f"## 라운드 {r['n']} ({r['time']})", ""]
        if r.get("feedback"):
            L += [f"**반영한 피드백{' (후보 ' + str(r['target']) + ' 기준)' if r.get('target') else ''}:** {r['feedback']}", ""]
        L += [f"**{'바꾼 점' if r['n'] > 1 else '레퍼런스에서 가져온 핵심'}:** {r['summary']}"]
        if r.get("check"):
            L += ["", "**팩트체크 결과**", "", "| 책 | 판정 | 교보문고 | 고친 점 |", "|---|---|---|---|"]
            L += [f"| {b['title']} | {b['status']} | {b.get('kyobo', '')} | {' / '.join(b['issues']) or '-'} |" for b in r["check"]["books"]]
        for k, c in enumerate(r["candidates"], 1):
            L += ["", f"### 후보 {k} — {c['angle']}", ""] + [f"> {ln}" for ln in c["copy"].split("\n")]
            L += ["", f"- 라벨: {c.get('label') or '-'}", f"- 공식: {c['pattern']}", f"- 공유 명분: {c['share']}",
                  f"- 레퍼런스에서: {c['from_ref']}", f"- 이미지 가이드: {c['image']}",
                  f"- 핀터레스트 검색어: {' · '.join(c['pins'])}"]
            if c.get("img"):
                L.append(f"- 추천 이미지: {c['img']['file']} / {c['img']['bg']} (원본 핀: {c['img']['pin'] or '-'})")
            for i, s in enumerate(c.get("slides") or [], 2):
                L.append(f"- {i}장 `{s['template']}`: **{s['label']}** {s['headline']} {s['body']} "
                         + " / ".join(s.get("bullets") or []))
            L += content_md(c.get("content"))
            if c.get("cta"):
                L.append(f"- 마지막 장: {c['cta']['headline']} / {c['cta']['body']}")
            L += ["", "**캡션**", "", c["caption"], "", "**고정댓글**", "", c["comment"]]
    return "\n".join(L).replace("\\n", " / ")


def content_md(ct: dict | None) -> list[str]:
    """형식(책추천·30초 요약)별 내용 요약 줄."""
    if not ct:
        return []
    L = []
    for i, b in enumerate(ct.get("books") or [], 1):
        L.append(f"- 책 {i}: **{b['title']}** — {b['author']} {' '.join(b['tags'])} · " + " / ".join(b["lines"]))
    if ct.get("keywords"):
        L.append(f"- 목차: {ct['book_title']} · {ct['subtitle']}")
        L += [f"- KEYWORD {i:02d} **{k['title']}** ({k['en']}): {k['line1']} / {k['line2']}" for i, k in enumerate(ct["keywords"], 1)]
        ch = ct["check"]
        L.append(f"- 셀프체크 {ch['title']}: " + " / ".join(ch["items"]))
    if ct.get("cta"):
        L.append(f"- 마지막 장: {ct['cta']['headline']} / {ct['cta']['body']}")
    return L


def _refs(d: dict) -> tuple[list[dict], str]:
    if not d.get("crawl_file") or not d.get("picks"):
        return [], ""
    crawl = storage.read_data("crawl", d["crawl_file"])
    posts = crawl.get("posts") or []
    refs = [{**posts[n - 1], "n": n} for n in d["picks"] if 0 < n <= len(posts)]
    return refs, f"crawl/{folder_of(d['crawl_file'])}"


async def _attach_images(job, d: dict, rnd: dict, prev: dict | None):
    async def one(k, c):
        keep = c.get("keep_image_from") or 0
        if keep and prev and 0 < keep <= len(prev["candidates"]) and prev["candidates"][keep - 1].get("img"):
            c["img"] = prev["candidates"][keep - 1]["img"]
            return
        try:
            c["img"] = await find_images(job, c["copy"], c["image"], c["pins"], d["file"], rnd["n"], k)
        except Exception as e:  # noqa: BLE001 - 이미지는 캔버스에서 다시 찾을 수 있다
            job.log(f"  후보 {k} 이미지 찾기 실패: {e}")
            c["img"] = None
    job.progress(60, "후보마다 핀터레스트 이미지 찾고 AI가 고르는 중")
    await asyncio.gather(*(one(k, c) for k, c in enumerate(rnd["candidates"], 1)))


def _plain(s: str) -> str:
    return re.sub(r"\[\[|\]\]|\{\{|\}\}", "", s or "")


async def _auto_books(job, d: dict, refs: list[dict], rel: str):
    """책추천: 책 목록이 비어 있으면 레퍼런스 카피 베리에이션 → 책 찾기(교보문고 확인)까지 자동으로 준비한다."""
    pj, mode = d["project"], d["mode"]
    count = formats.get(mode).get("count", 3)
    auto = {}
    if refs and not pj.get("thumb"):
        ref = max(refs, key=lambda r: r.get("likes") or 0)
        job.progress(3, f"@{ref.get('author', '')} 레퍼런스 썸네일 카피 분석·베리에이션 중 (AI)")
        v = await claude_ai.copy_variations(ref, rel, pj.get("name") or pj.get("message") or "", mode, job)
        k = min(max(v.get("recommend") or 1, 1), len(v["variations"]))
        pick = v["variations"][k - 1]["copy"]
        alts = [x["copy"] for i, x in enumerate(v["variations"], 1) if i != k][:4]
        pj["thumb"] = pick.replace("\n", " / ")  # ' / ' = 표지 줄바꿈
        pj["thumb_alts"] = [a.replace("\n", " / ") for a in alts]
        lite = {x: ref.get(x) for x in ("author", "url", "likes", "caption", "images")}
        vd = {"type": "카피베리에이션", "crawl_file": d["crawl_file"], "n": ref["n"], "topic": pj.get("name", ""), "ref": lite, **v}
        vname = storage.new_name("analysis", "카피베리에이션", ref.get("author") or "레퍼런스")
        storage.write_md("analysis", vname, variations_md(vd), vd)
        auto["variations"] = {**v, "file": vname}
    topic = pj.get("thumb") or pj.get("name") or pj.get("message")
    if not topic:
        raise RuntimeError("레퍼런스를 고르거나 1번에 썸네일 카피·주제를 적어 주세요.")
    job.progress(20, f"'{_plain(topic)[:20]}'에 맞는 책 찾는 중 (AI 웹 검색)")
    hint = ""
    if auto.get("variations"):
        hint = f"레퍼런스 공식: {auto['variations']['formula']}"
    r = await claude_ai.find_books(_plain(topic), count, " / ".join(x for x in (pj.get("message"), hint) if x), [], job)
    job.progress(45, f"후보 {len(r['books'])}권 교보문고에서 실존·저자·절판 확인 중")
    books = await bookcover.verify_books(r["books"])
    good = [b for b in books if b["kyobo"].get("verified") and not b["kyobo"].get("outofprint") and b["kyobo"].get("author_ok", True)]
    rest = [b for b in books if b not in good]
    chosen = (good + rest)[:count]
    if len(good) < count:
        job.log(f"  교보문고에서 확인된 책이 {len(good)}권뿐이라 나머지는 확인 필요 표시로 넣었어요.")
    bd = {"type": "책찾기", "topic": _plain(topic), "count": count, "prefs": pj.get("message", ""), "summary": r["summary"], "books": books}
    bname = storage.new_name("analysis", "책찾기", _plain(topic))
    storage.write_md("analysis", bname, books_md(bd), bd)
    pj["books"] = chr(10).join(f"{b['title']} / {b['author']} / {b['hook']}" for b in chosen)
    if not pj.get("name"):
        pj["name"] = _plain(topic)[:30]
    auto.update(books=[{k: b.get(k) for k in ("title", "author", "why", "hook", "tags", "kyobo")} for b in chosen],
                books_file=bname, summary=r["summary"])
    d["auto"] = auto


async def plan_job(job, body: dict):
    if body.get("plan_file"):  # ---- 피드백으로 다시 기획
        name = body["plan_file"]
        d = storage.read_data("analysis", name)
        d["file"] = name
        refs, rel = _refs(d)
        tr = body.get("target_round") or len(d["rounds"])
        prev = d["rounds"][tr - 1]
        job.progress(5, "피드백 반영해 다시 기획 중 (AI)")
        out = await claude_ai.plan_again(refs, rel, d["project"], d["mode"], prev, body["feedback"],
                                         body.get("target") or 0, job)
        rnd = {"n": len(d["rounds"]) + 1, "time": storage.now().strftime("%Y-%m-%d %H:%M"),
               "feedback": body["feedback"], "target": body.get("target") or 0, "target_round": tr, **out}
    else:  # ---- 첫 기획
        d = {"crawl_file": body.get("crawl_file") or "", "picks": body.get("picks") or [], "mode": body["mode"],
             "project": body["project"], "rounds": []}
        refs, rel = _refs(d)
        if not refs and formats.kind(d["mode"]) == "free":
            raise RuntimeError("고른 레퍼런스를 찾지 못했습니다.")
        name = storage.new_name("analysis", MODE_KO[d["mode"]], (d["project"].get("name") or "기획") + "_기획")
        d["file"] = name
        job.meta["plan_file"] = name
        try:
            if formats.kind(d["mode"]) == "books" and not (d["project"].get("books") or "").strip():
                await _auto_books(job, d, refs, rel)
            job.progress(60 if d.get("auto") else 5,
                         f"{formats.get(d['mode'])['name']} · 레퍼런스 {len(refs)}개로 후보 3개 기획 중 (AI가 책 소개도 작성)")
            out = await claude_ai.plan_first(refs, rel, d["project"], d["mode"], job)
        except Exception:
            storage.safe_path("analysis", name).unlink(missing_ok=True)
            raise
        rnd = {"n": 1, "time": storage.now().strftime("%Y-%m-%d %H:%M"), "feedback": "", "target": 0, **out}
        prev = None
    await _attach_images(job, d, rnd, prev)
    d["rounds"].append(rnd)
    storage.write_md("analysis", name, plan_md(d), {k: v for k, v in d.items() if k != "file"})
    return {**d, "file": name}


# =============== 썸네일 (캔버스 저장) ===============

def data_url_bytes(data_url: str) -> bytes:
    return base64.b64decode(data_url.split(",", 1)[1])


def save_thumb(png: str, state: dict, copy: str, meta: dict) -> dict:
    name = storage.new_name("generate", "썸네일", copy.split("\n")[0])
    folder = storage.assets_dir("generate", name)
    (folder / "thumb.png").write_bytes(data_url_bytes(png))
    d = {"type": "썸네일", "copy": copy, "meta": meta, "state": state, "png": "thumb.png", "assets": folder.name,
         "analysis_file": meta.get("analysis_file", ""), "cand_file": meta.get("cand_file", "")}
    body = (f"# 썸네일 편집본\n\n> {copy.replace(chr(10), ' / ')}\n\n- 배경 출처: {meta.get('pin') or '-'}\n"
            f"- 기획: {meta.get('analysis_file') or '-'} (라운드 {meta.get('plan_round', '-')}, 후보 {meta.get('plan_cand', '-')})\n\n"
            f"![썸네일]({folder.name}/thumb.png)")
    storage.write_md("generate", name, body, d)
    return {"file": name, "url": img_url("generate", folder.name, "thumb.png")}


# =============== 완성본 ===============

def _cta_slide(c: dict, bg: str) -> dict:
    return {"template": "dark_cta", "headline": c["cta"]["headline"], "body": c["cta"]["body"], "image": bg}


def publish_md(p: dict) -> str:
    L = [f"# 완성본 · {p['copy'].splitlines()[0]}", "", f"- 형식: {MODE_KO[p['mode']]} · 카드 {len(p['cards'])}장",
         f"- 기획: {p['plan_file']} (라운드 {p['round']}, 후보 {p['cand']})", f"- 썸네일: {p['thumb_file']}",
         f"- 배경 출처: {p.get('pin') or '-'}", f"- 바탕화면 폴더: {(p.get('desktop') or {}).get('folder', '-')}", "", "## 카드", ""]
    L += [" ".join(f"![{i + 1}]({p['folder']}/{c['file']})" for i, c in enumerate(p["cards"]))]
    L += ["", "## 캡션", "", p["caption"], "", "## 고정댓글", "", p["comment"]]
    return "\n".join(L)


def _asset_copy(name: str, src_dir: Path) -> str:
    """assets/<name> 이 있으면 카드 폴더 src/ 로 복사하고 data 기준 경로를 돌려준다."""
    p = ASSETS_DIR / name
    if not p.exists():
        return ""
    src_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(p, src_dir / name)
    return f"generate/{src_dir.parent.name}/src/{name}"


async def format_slides(job, mode: str, ct: dict, folder: Path, bgsrc: str) -> tuple[list[dict], dict]:
    """책추천·30초 요약 형식의 본문 장과 팔로우 장을 만든다(책 표지·키워드 사진은 자동으로 찾아 둔다)."""
    src = folder / "src"
    src.mkdir(parents=True, exist_ok=True)
    rel = lambda f: f"generate/{folder.name}/src/{f}"  # noqa: E731
    book_bg = _asset_copy("book_bg.jpg", src) or bgsrc
    avatar = _asset_copy("profile.jpg", src)
    cta = {"template": "follow_cta", "headline": ct["cta"]["headline"], "body": ct["cta"]["body"],
           "image": book_bg, "avatar": avatar}
    slides: list[dict] = []
    if formats.kind(mode) == "books":
        books = ct["books"][: formats.get(mode)["count"]]
        job.progress(35, f"책 표지 {len(books)}권 찾는 중 (교보문고·알라딘)")
        urls = await bookcover.find_covers([f"{b['title']} {b['author']}".strip() for b in books])
        for i, (b, u) in enumerate(zip(books, urls), 1):
            cover = ""
            if u and await asyncio.to_thread(bookcover.download, u, src / f"cover{i}.jpg"):
                cover = rel(f"cover{i}.jpg")
            else:
                job.log(f"  표지를 못 찾았습니다: {b['title']} — 카드 편집에서 올려 주세요")
            slides.append({"template": "book", "title": b["title"], "author": b["author"], "tags": b["tags"],
                           "lines": b["lines"], "cover": cover, "image": book_bg})
        return slides, cta
    # ---- 30초 요약
    kws = ct["keywords"]
    job.progress(35, f"키워드 {len(kws)}개 배경 사진 찾는 중 (핀터레스트)")
    found = await pinterest.search([k["image_query"] for k in kws], per_query=1)
    by_q = {}
    for x in found:
        by_q.setdefault(x["query"], x)
    images = []
    for i, k in enumerate(kws, 1):
        x = by_q.get(k["image_query"])
        ok = bool(x) and await asyncio.to_thread(pinterest.download, x["img_url"], src / f"kw{i:02d}.jpg")
        images.append(rel(f"kw{i:02d}.jpg") if ok else bgsrc)
    slides.append({"template": "summary_index", "tag": "30초 요약", "title": ct["book_title"], "subtitle": ct["subtitle"],
                   "items": [f"{i:02d} {k['title']}" for i, k in enumerate(kws, 1)], "footer": ct["index_footer"],
                   "image": bgsrc})
    for j in range(0, len(kws), 2):
        slides.append({"template": "keyword_pair", "items": [
            {"no": f"KEYWORD {i + 1:02d}", "title": kws[i]["title"], "en": kws[i]["en"], "line1": kws[i]["line1"],
             "line2": kws[i]["line2"], "image": images[i]} for i in range(j, min(j + 2, len(kws)))]})
    ch = ct["check"]
    slides.append({"template": "self_check", "tag": "SELF CHECK", "title": ch["title"], "subtitle": ch["subtitle"],
                   "items": ch["items"], "footer": ch["footer"], "image": images[-1] if images else bgsrc})
    return slides, cta


def _bg_rel(img: dict | None) -> str:
    return f"generate/{img['assets']}/{img['bg']}" if img and img.get("bg") else ""


async def publish_job(job, plan_file: str, round_n: int, cand_n: int, thumb_file: str):
    plan = storage.read_data("analysis", plan_file)
    c = plan["rounds"][round_n - 1]["candidates"][cand_n - 1]
    thumb = storage.read_data("generate", thumb_file)
    name = storage.new_name("generate", "완성본", c["copy"].split("\n")[0])
    folder = storage.assets_dir("generate", name, "_cards")
    bg = _bg_rel(c.get("img"))
    # 썸네일에서 배경을 바꿨으면 그 사진을 본문 사진 장에도 쓴다
    pin = thumb.get("meta", {}).get("pin") or (c.get("img") or {}).get("pin", "")
    bgsrc = thumb.get("meta", {}).get("bg_rel") or bg

    shutil.copy(DATA_DIR / "generate" / thumb["assets"] / thumb["png"], folder / "c01.png")
    cards = [{"file": "c01.png", "kind": "thumb"}]
    if formats.kind(plan["mode"]) == "free":
        slides = [{**s, "image": bgsrc} for s in (c.get("slides") or [])] if plan["mode"] == "long" else []
        cta = None if (ASSETS_DIR / "cta.png").exists() else _cta_slide(c, bgsrc)
    else:
        slides, cta = await format_slides(job, plan["mode"], c["content"], folder, bgsrc)
    total = 1 + len(slides) + 1
    todo = []
    for s in slides:
        f = f"c{len(cards) + 1:02d}.png"
        cards.append({"file": f, "kind": "body", "slide": s})
        todo.append((s, len(cards) - 1, total, folder / f))
    f = f"c{len(cards) + 1:02d}.png"
    if cta is None:
        shutil.copy(ASSETS_DIR / "cta.png", folder / f)
        cards.append({"file": f, "kind": "cta"})
    else:
        cards.append({"file": f, "kind": "cta", "slide": cta})
        todo.append((cta, len(cards) - 1, total, folder / f))
    job.progress(70, f"카드 {total}장 만드는 중")
    await render_cards(todo)
    proof = plan["project"].get("proof", "").strip()
    caption = c["caption"] if not proof or proof in c["caption"] else c["caption"].rstrip() + "\n⠀\n" + proof
    p = {"type": "발행", "mode": plan["mode"], "project": plan["project"].get("name", ""), "copy": thumb.get("copy") or c["copy"],
         "caption": caption, "comment": c["comment"], "cards": cards, "plan_file": plan_file, "thumb_file": thumb_file,
         "cand_file": (c.get("img") or {}).get("file", ""), "round": round_n, "cand": cand_n, "pin": pin,
         "folder": folder.name, "file": name}
    job.progress(85, "바탕화면 › 카드뉴스 완성본 폴더에 저장 중")
    p["desktop"] = export_desktop(p)
    storage.write_md("generate", name, publish_md(p), p)
    return p


def export_desktop(p: dict) -> dict:
    old = p.get("desktop") or {}
    folder = Path(old["folder"]) if old.get("folder") else DESKTOP_OUT / dt.datetime.now().strftime("%m%d")
    folder.mkdir(parents=True, exist_ok=True)
    for f in old.get("files", []):
        (folder / f).unlink(missing_ok=True)
    head = old.get("prefix") or dt.datetime.now().strftime("%H%M") + "_" + storage.slugify(p["copy"].split("\n")[0], 16)
    files = []
    src = DATA_DIR / "generate" / p["folder"]
    for i, c in enumerate(p["cards"], 1):
        f = f"{head}_{i:02d}.png"
        shutil.copy(src / c["file"], folder / f)
        files.append(f)
    cap = f"{head}_캡션.txt"
    (folder / cap).write_text(p["caption"] + "\n\n──── 고정댓글 ────\n\n" + p["comment"], encoding="utf-8")
    files.append(cap)
    return {"folder": str(folder), "files": files, "prefix": head}


def save_publish(p: dict) -> dict:
    p["desktop"] = export_desktop(p)
    storage.write_md("generate", p["file"], publish_md(p), p)
    return p


def open_folder(path: str) -> None:
    if hasattr(os, "startfile"):
        os.startfile(path)  # noqa: S606 - 사용자가 누른 버튼으로 탐색기를 연다


# =============== 책 찾기 · 썸네일 카피 베리에이션 · 팩트체크 ===============

def books_md(d: dict) -> str:
    L = [f"# 책 찾기 · {d['topic']}", "", f"- 필요한 권수: {d['count']}", f"- 조건: {d.get('prefs') or '-'}", "",
         "## AI가 고른 기준", "", d["summary"], "", "## 후보 (교보문고 확인 결과)", "",
         "| # | 제목 | 저자 | 교보문고 | 평점(리뷰) | 결 |", "|---|---|---|---|---|---|"]
    for i, b in enumerate(d["books"], 1):
        k = b.get("kyobo") or {}
        L.append(f"| {i} | {b['title']} | {b['author']}{' / ' + b['translator'] + ' 옮김' if b.get('translator') else ''} | "
                 f"{'✔ ' + k.get('note', '') if k.get('verified') else '⚠ ' + k.get('note', '')} | "
                 f"{k.get('rating') or '-'}({k.get('reviews') or '-'}) | {b.get('tone', '')} |")
    for i, b in enumerate(d["books"], 1):
        L += ["", f"### {i}. {b['title']} — {b['author']}", "", f"- 고른 이유: {b['why']}", f"- 훅: {b['hook']}",
              f"- 키워드: {' '.join(b['tags'])}", f"- 교보문고: {(b.get('kyobo') or {}).get('link') or '-'}"]
    return "\n".join(L)


async def find_books_job(job, topic: str, count: int, prefs: str, exclude: list[str]):
    job.progress(5, "AI가 웹에서 책 후보 찾는 중 (서점 정보 확인)")
    r = await claude_ai.find_books(topic, count, prefs, exclude, job)
    job.progress(75, f"후보 {len(r['books'])}권 교보문고에서 실존·저자·절판 확인 중")
    books = await bookcover.verify_books(r["books"])
    books.sort(key=lambda b: (not (b["kyobo"].get("verified") and not b["kyobo"].get("outofprint")),
                              not b["kyobo"].get("author_ok", False)))
    d = {"type": "책찾기", "topic": topic, "count": count, "prefs": prefs, "summary": r["summary"], "books": books}
    name = storage.new_name("analysis", "책찾기", topic)
    storage.write_md("analysis", name, books_md(d), d)
    return {**d, "file": name}


def variations_md(d: dict) -> str:
    L = [f"# 썸네일 카피 베리에이션 · @{d['ref']['author']}", "", f"- 레퍼런스: {d['ref'].get('url') or '-'} · 좋아요 {d['ref'].get('likes') or 0:,}",
         f"- 수집 파일: {d['crawl_file']} #{d['n']}", f"- 우리 주제: {d.get('topic') or '-'}", "",
         f"> 원본 카피: {d['original'].replace(chr(10), ' / ')}", "", f"**공식:** {d['formula']}", "", "## 베리에이션", ""]
    for i, v in enumerate(d["variations"], 1):
        L.append(f"{i}. **{v['copy'].replace(chr(10), ' / ')}**{' ← 추천' if i == d['recommend'] else ''} — {v['why']}")
    return "\n".join(L)


async def variations_job(job, crawl_file: str, n: int, topic: str, mode: str):
    posts = storage.read_data("crawl", crawl_file).get("posts") or []
    if not 0 < n <= len(posts):
        raise RuntimeError("레퍼런스를 찾지 못했습니다.")
    ref = posts[n - 1]
    job.progress(10, f"@{ref.get('author', '')} 표지 카피 분석·베리에이션 만드는 중 (AI)")
    r = await claude_ai.copy_variations(ref, f"crawl/{folder_of(crawl_file)}", topic, mode, job)
    lite = {k: ref.get(k) for k in ("author", "url", "likes", "caption", "images")}
    d = {"type": "카피베리에이션", "crawl_file": crawl_file, "n": n, "topic": topic, "ref": lite, **r}
    name = storage.new_name("analysis", "카피베리에이션", ref.get("author") or "레퍼런스")
    storage.write_md("analysis", name, variations_md(d), d)
    return {**d, "file": name}


async def factcheck_job(job, plan_file: str, round_n: int, cand_n: int):
    d = storage.read_data("analysis", plan_file)
    rnd = d["rounds"][round_n - 1]
    c = rnd["candidates"][cand_n - 1]
    books = (c.get("content") or {}).get("books") or []
    if not books:
        raise RuntimeError("책추천 형식 후보만 팩트체크할 수 있어요.")
    job.progress(5, f"책 {len(books)}권 교보문고 확인 중")
    kyobo = await bookcover.verify_books([{"title": b["title"], "author": b["author"]} for b in books])
    job.progress(20, "AI가 웹 검색으로 줄거리·인용·숫자 사실 확인 중")
    rep = await claude_ai.fact_check([{"title": b["title"], "author": b["author"], "lines": b["lines"], "tags": b["tags"]}
                                      for b in books], job)
    fixed = []
    for b, k, chk in zip(books, kyobo, rep["books"] + [{}] * len(books)):
        nb = dict(b)
        if chk:
            nb.update(title=chk.get("fixed_title") or b["title"], author=chk.get("fixed_author") or b["author"],
                      lines=chk.get("fixed_lines") or b["lines"])
        fixed.append(nb)
        if chk is not None:
            chk["kyobo"] = k["kyobo"].get("note", "")
    report = {"summary": rep["summary"], "books": rep["books"], "kyobo": [k["kyobo"] for k in kyobo]}
    new_c = {**c, "content": {**c["content"], "books": fixed}, "angle": c["angle"] + " (팩트체크 반영)"}
    others = [x for i, x in enumerate(rnd["candidates"], 1) if i != cand_n]
    d["rounds"].append({"n": len(d["rounds"]) + 1, "time": storage.now().strftime("%Y-%m-%d %H:%M"),
                        "feedback": f"라운드 {round_n} 후보 {cand_n} 팩트체크", "target": 1, "target_round": round_n,
                        "summary": rep["summary"], "check": report, "candidates": [new_c] + others})
    storage.write_md("analysis", plan_file, plan_md({**d, "file": plan_file}), d)
    return {**d, "file": plan_file}
