"""인스타그램 레퍼런스 수집 (Playwright + 로그인 세션 + 인스타 웹 내부 API).

- 방법 A. 해시태그·키워드 검색 화면을 스크롤하며 게시물을 찾고, 게시물마다 /api/v1/media/{pk}/info/ 로
  좋아요·댓글 수·슬라이드 이미지·캡션을 정확히 읽는다. 조건(최소 좋아요·형식·최근 N일)에 맞는 것만 최대 10개.
  [새로 찾기]는 전에 살펴본 게시물을 빼고 더 아래까지 내려가 새로 모은다.
- 방법 B. 게시물 링크 목록을 그대로 수집한다.
- 상위 댓글(좋아요 순)도 함께 모아 기획 때 반응 근거로 쓴다.
- 로그인 세션은 data/.session/instagram_profile(브라우저 프로필)과 instagram_state.json(쿠키 백업)에 저장된다.
"""
import asyncio
import contextlib
import datetime as dt
import json
import os
import random
import re
import socket
import subprocess
import threading
import time
import urllib.parse

from playwright.async_api import BrowserContext, Page, async_playwright

from . import storage
from .config import SESSION_DIR

PROFILE_DIR = SESSION_DIR / "instagram_profile"
STATE_FILE = SESSION_DIR / "instagram_state.json"
BASE = "https://www.instagram.com"
APP_ID = "936619743392459"
SC_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

_profile_lock = threading.Lock()  # 같은 프로필을 두 브라우저가 동시에 열 수 없음


class SessionExpired(RuntimeError):
    pass


def session_status() -> dict:
    try:
        cookies = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("cookies", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return {"logged_in": False}
    sid = next((c for c in cookies if c.get("name") == "sessionid" and "instagram" in c.get("domain", "")), None)
    if not sid:
        return {"logged_in": False}
    if 0 < sid.get("expires", -1) < time.time():
        return {"logged_in": False, "expired": True}
    return {"logged_in": True,
            "saved_at": dt.datetime.fromtimestamp(STATE_FILE.stat().st_mtime).strftime("%m/%d %H:%M")}


def _acquire():
    if not _profile_lock.acquire(blocking=False):
        raise RuntimeError("인스타그램 브라우저가 이미 실행 중입니다. 진행 중인 수집·로그인이 끝난 뒤 다시 시도하세요.")


BROWSERS = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _open(pw, headless: bool, url: str = "about:blank") -> BrowserContext:
    """이 PC 에 설치된 크롬(없으면 엣지)을 '보통 창'으로 수집 전용 프로필에 띄우고 연결한다.
    자동화 모드로 띄우면 인스타 로그인 중 창이 튕기는 경우가 있어, 사람이 여는 창과 같은 방식으로 연다.
    평소 쓰는 크롬 프로필과는 따로다."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    exe = next((b for b in BROWSERS if os.path.exists(b)), None)
    if not exe:
        raise RuntimeError("크롬 또는 엣지를 찾지 못했습니다. 크롬을 설치해 주세요.")
    port = _free_port()
    args = [exe, f"--user-data-dir={PROFILE_DIR}", f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1",
            "--no-first-run", "--no-default-browser-check", "--lang=ko-KR", "--window-size=1280,900"]
    if headless:
        args.append("--headless=new")
    proc = subprocess.Popen(args + [url])
    for _ in range(40):
        try:
            browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            break
        except Exception:  # noqa: BLE001 - 크롬이 뜰 때까지 기다린다
            await asyncio.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("브라우저에 연결하지 못했습니다. 수집 전용 크롬 창이 이미 열려 있다면 닫고 다시 시도하세요.")
    ctx = browser.contexts[0]
    ctx._bk = (browser, proc)  # 닫을 때 쓴다
    return ctx


async def _close(ctx: BrowserContext) -> None:
    browser, proc = getattr(ctx, "_bk", (None, None))
    try:
        if browser:
            await browser.close()
    except Exception:  # noqa: BLE001
        pass
    if proc and proc.poll() is None:
        proc.terminate()


@contextlib.asynccontextmanager
async def opened(pw, headless: bool, url: str = "about:blank"):
    ctx = await _open(pw, headless, url)
    try:
        yield ctx
    finally:
        await _close(ctx)


async def _has_session(ctx: BrowserContext) -> bool:
    return any(c["name"] == "sessionid" for c in await ctx.cookies(BASE))


async def login_flow(job) -> dict:
    """로그인 창은 프로그램이 전혀 연결하지 않은 '평범한 크롬 창'으로 띄운다(원격 연결 흔적이 있으면 로봇 확인이 반복될 수 있음).
    사람이 로그인하고 창을 닫으면, 그때 같은 프로필을 화면 없이 열어 로그인 여부를 확인하고 세션을 저장한다."""
    _acquire()
    try:
        exe = next((b for b in BROWSERS if os.path.exists(b)), None)
        if not exe:
            raise RuntimeError("크롬 또는 엣지를 찾지 못했습니다. 크롬을 설치해 주세요.")
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen([exe, f"--user-data-dir={PROFILE_DIR}", "--no-first-run", "--no-default-browser-check",
                                 "--lang=ko-KR", f"{BASE}/accounts/login/"])
        job.progress(None, "열린 크롬 창에서 로그인한 뒤, 그 창을 닫아 주세요 (최대 15분)")
        for _ in range(900):
            if proc.poll() is not None:
                break
            await asyncio.sleep(1)
        else:
            proc.terminate()
            raise RuntimeError("로그인 시간이 지났습니다. 다시 시도해 주세요.")
        await asyncio.sleep(2)
        job.progress(None, "로그인 확인 중")
        async with async_playwright() as pw, opened(pw, True, f"{BASE}/robots.txt") as ctx:
            await asyncio.sleep(2)
            if not await _has_session(ctx):
                raise RuntimeError("로그인이 확인되지 않았습니다. 창에서 로그인을 끝까지(인증·보안 확인 포함) 마친 뒤 창을 닫아 주세요.")
            await ctx.storage_state(path=str(STATE_FILE))
        return session_status()
    finally:
        _profile_lock.release()


# ---------------- 게시물 데이터 ----------------

def shortcode_to_pk(code: str) -> int:
    pk = 0
    for ch in code[:11]:
        pk = pk * 64 + SC_ALPHABET.index(ch)
    return pk


def _best(versions) -> str | None:
    cands = (versions or {}).get("candidates") or []
    return max(cands, key=lambda c: c.get("width", 0)).get("url") if cands else None


def normalize(m: dict) -> dict:
    """인스타 내부 API(v1)·GraphQL 응답 어느 쪽이든 같은 모양으로."""
    code = m.get("code") or m.get("shortcode")
    mt = m.get("media_type")
    if mt is None:
        mt = 8 if m.get("edge_sidecar_to_children") else (2 if m.get("is_video") else 1)
    is_reel = m.get("product_type") == "clips" or (mt == 2 and m.get("product_type") != "feed")
    kind = {8: "캐러셀", 1: "사진"}.get(mt, "릴스" if is_reel else "동영상")

    images = [u for u in (_best(c.get("image_versions2")) for c in m.get("carousel_media") or []) if u]
    images += [e["node"]["display_url"] for e in (m.get("edge_sidecar_to_children") or {}).get("edges", [])
               if e.get("node", {}).get("display_url")]
    if not images:
        u = _best(m.get("image_versions2")) or m.get("display_url")
        images = [u] if u else []

    caption = m.get("caption")
    if isinstance(caption, dict):
        caption = caption.get("text", "")
    if not caption:
        edges = (m.get("edge_media_to_caption") or {}).get("edges") or []
        caption = edges[0]["node"].get("text", "") if edges else ""
    likes = m.get("like_count")
    if likes is None:
        likes = (m.get("edge_media_preview_like") or m.get("edge_liked_by") or {}).get("count")
    comments = m.get("comment_count")
    if comments is None:
        comments = (m.get("edge_media_to_comment") or m.get("edge_media_to_parent_comment") or {}).get("count")
    taken = m.get("taken_at") or m.get("taken_at_timestamp")
    views = m.get("play_count") or m.get("ig_play_count") or m.get("view_count") or m.get("video_view_count")
    return {
        "code": code, "pk": str(m.get("pk") or m.get("id") or "").split("_")[0],
        "url": f"{BASE}/p/{code}/", "type": kind,
        "author": (m.get("user") or m.get("owner") or {}).get("username", ""),
        "date": dt.datetime.fromtimestamp(taken).strftime("%Y-%m-%d") if isinstance(taken, (int, float)) else "",
        "taken_ts": taken if isinstance(taken, (int, float)) else None,
        "likes": likes if isinstance(likes, int) else None,
        "likes_hidden": bool(m.get("like_and_view_counts_disabled")),
        "comments": comments if isinstance(comments, int) else None,
        "views": views if isinstance(views, int) else None,
        "shares": None,
        "caption": caption or "", "slides": len(images), "remote_images": images,
        "top_comments": [], "images": [], "source": "api",
    }


def _walk(obj, found: dict):
    """검색 화면이 받아 온 JSON 안에서 게시물 덩어리를 모은다."""
    if isinstance(obj, dict):
        code = obj.get("code") or obj.get("shortcode")
        if isinstance(code, str) and ("like_count" in obj or "carousel_media" in obj or "image_versions2" in obj
                                      or "edge_media_preview_like" in obj):
            found[code] = {**found.get(code, {}), **{k: v for k, v in obj.items() if v is not None}}
        for v in obj.values():
            _walk(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, found)


API_JS = """async (path) => {
  const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
  const r = await fetch(path, {credentials: 'include', headers: {
    'X-IG-App-ID': '%s', 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf, 'Accept': '*/*'}});
  return {status: r.status, text: await r.text()};
}""" % APP_ID


POST_JS = """async ([path, form]) => {
  const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '';
  const r = await fetch(path, {method: 'POST', credentials: 'include', body: new URLSearchParams(form), headers: {
    'X-IG-App-ID': '%s', 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf,
    'Content-Type': 'application/x-www-form-urlencoded'}});
  return {status: r.status, text: await r.text()};
}""" % APP_ID


async def tag_top_posts(page: Page, job, tag: str, pages: int = 9) -> dict[str, dict]:
    """해시태그 '인기 게시물' 목록을 여러 페이지 읽는다 (web_info → sections 이어 읽기). 게시물 덩어리에 좋아요 수가 들어 있다."""
    found: dict[str, dict] = {}
    d = await _api(page, f"/api/v1/tags/web_info/?tag_name={urllib.parse.quote(tag)}")
    if not d:
        return found
    _walk(d, found)
    st = (d.get("data") or {}).get("top") or {}
    n = 1
    while st.get("more_available") and n < pages:
        await asyncio.sleep(random.uniform(2.0, 4.0))
        form = {"include_persistent": "0", "max_id": st.get("next_max_id", ""), "page": str(st.get("next_page", n)),
                "surface": "grid", "tab": "top", "next_media_ids": json.dumps(st.get("next_media_ids") or [])}
        try:
            r = await page.evaluate(POST_JS, [f"/api/v1/tags/{urllib.parse.quote(tag)}/sections/", form])
            st = json.loads(r["text"]) if r["status"] == 200 else {}
        except Exception:  # noqa: BLE001
            break
        _walk(st, found)
        n += 1
        job.progress(min(60, 5 + n / pages * 55), f"#{tag} 인기 게시물 {n}/{pages}페이지 · {len(found)}개 살펴봄")
    return found


async def _api(page: Page, path: str) -> dict | None:
    try:
        r = await page.evaluate(API_JS, path)
    except Exception:  # noqa: BLE001 - 페이지 이동 중이면 실패할 수 있다
        return None
    if r["status"] in (401, 403) and "login" in r["text"][:500].lower():
        raise SessionExpired("인스타그램 로그인 세션이 만료됐습니다. [로그인 세션 저장]을 다시 해 주세요.")
    if r["status"] != 200:
        return None
    try:
        return json.loads(r["text"])
    except json.JSONDecodeError:
        return None


async def media_info(page: Page, code: str) -> dict | None:
    d = await _api(page, f"/api/v1/media/{shortcode_to_pk(code)}/info/")
    items = (d or {}).get("items") or []
    return normalize(items[0]) if items else None


async def top_comments(page: Page, pk: str, n: int = 15) -> list[str]:
    d = await _api(page, f"/api/v1/media/{pk}/comments/?can_support_threading=true&permalink_enabled=false")
    out = []
    for c in sorted((d or {}).get("comments") or [], key=lambda c: c.get("comment_like_count", 0), reverse=True)[:n]:
        like = c.get("comment_like_count") or 0
        out.append(f"{(c.get('user') or {}).get('username', '')}: {c.get('text', '')}" + (f" (♥{like})" if like else ""))
    return out


def _fits(p: dict, min_likes: int, fmt: str | None, recent_days: int) -> tuple[bool, str]:
    if p["likes"] is None:
        return False, "좋아요 비공개"
    if p["likes"] < min_likes:
        return False, f"좋아요 {p['likes']:,}"
    if recent_days and p["taken_ts"] and p["taken_ts"] < time.time() - recent_days * 86400:
        return False, "오래된 게시물"
    if fmt == "single" and (p["type"] not in ("사진", "캐러셀") or p["slides"] > 2):
        return False, "단일 형식 아님"
    if fmt == "long" and (p["type"] != "캐러셀" or p["slides"] < 3):
        return False, "롱폼 형식 아님"
    return True, ""


async def _save_images(ctx: BrowserContext, posts: list[dict], folder) -> None:
    for i, p in enumerate(posts, 1):
        for k, u in enumerate(p["remote_images"][:12], 1):
            dest = folder / f"p{i}-{k:02d}.jpg"
            try:
                r = await ctx.request.get(u, timeout=30000)
                if r.ok:
                    dest.write_bytes(await r.body())
                    p["images"].append(dest.name)
            except Exception:  # noqa: BLE001
                pass


def _check_login(page: Page):
    if "/accounts/login" in page.url or "/challenge" in page.url or "/recaptcha" in page.url:
        raise SessionExpired("인스타그램 로그인 세션이 없거나 만료됐습니다. [로그인 세션 저장]을 눌러 다시 로그인해 주세요.")


async def crawl(job, *, keyword: str = "", urls: list[str] | None = None, min_likes: int = 5000,
                fmt: str | None = None, recent_days: int = 0, fresh: bool = False, limit: int = 10,
                headless: bool = False, assets=None) -> dict:
    _acquire()
    try:
        async with async_playwright() as pw, opened(pw, headless) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            # 무거운 인스타 화면 대신 같은 주소의 가벼운 페이지에서 API 를 부른다(보안 확인 화면으로 넘어가는 일을 줄임)
            await page.goto(BASE + "/robots.txt", wait_until="domcontentloaded", timeout=60000)
            if not await _has_session(ctx):
                raise SessionExpired("인스타그램 로그인 세션이 없습니다. [로그인 세션 저장]을 먼저 해 주세요.")

            kept: list[dict] = []
            checked = reels = 0
            visited: set[str] = set()

            if urls:  # ---------- 방법 B. 링크로 수집
                codes = [m.group(2) for u in urls if (m := re.search(r"/(p|reel|tv)/([\w-]+)", u))]
                for n, code in enumerate(codes, 1):
                    job.progress(n / max(1, len(codes)) * 80, f"게시물 확인 {n}/{len(codes)}")
                    p = await media_info(page, code)
                    visited.add(code)
                    checked += 1
                    if p:
                        kept.append(p)
                    else:
                        job.log(f"  읽지 못함: {code}")
                    await asyncio.sleep(random.uniform(1.2, 2.6))
            else:  # ---------- 방법 A. 해시태그 인기 게시물(API) → 안 되면 검색 화면 스크롤
                seen = storage.load_seen() if fresh else set()
                tag = keyword.strip().lstrip("#").split()[0] if keyword.strip() else ""
                top = await tag_top_posts(page, job, tag, pages=15 if fresh else 9) if tag else {}
                if top:
                    posts = sorted((normalize(m) for c, m in top.items() if c not in seen),
                                   key=lambda p: p["likes"] or 0, reverse=True)
                    for p in posts:
                        visited.add(p["code"])
                        checked += 1
                        ok, _ = _fits(p, min_likes, fmt, recent_days)
                        if ok and p["type"] in ("릴스", "동영상"):
                            ok = not fmt and reels < 2
                            reels += ok
                        if ok and len(kept) < limit:
                            kept.append(p)
                            job.log(f"  ✔ @{p['author']} ♥{p['likes']:,} ({p['type']} {p['slides']}장)")
                    job.progress(70, f"#{tag} 인기 게시물 {checked}개 중 조건 통과 {len(kept)}개")
            if not urls and not checked:
                found: dict[str, dict] = {}
                pending: set[asyncio.Task] = set()

                async def on_response(resp):
                    try:
                        if "json" in (resp.headers.get("content-type") or "") or "/graphql" in resp.url:
                            text = await resp.text()
                            if "like_count" in text or "image_versions2" in text:
                                _walk(json.loads(text.removeprefix("for (;;);")), found)
                    except Exception:  # noqa: BLE001
                        pass

                def handler(resp):
                    t = asyncio.ensure_future(on_response(resp))
                    pending.add(t)
                    t.add_done_callback(pending.discard)

                page.on("response", handler)
                q = keyword.strip()
                url = f"{BASE}/explore/search/keyword/?q={urllib.parse.quote(q)}"
                job.progress(2, f"검색 화면 여는 중: {q}")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(4000)
                _check_login(page)

                max_scrolls = 30 if fresh else 14
                for s in range(max_scrolls):
                    hrefs = await page.eval_on_selector_all("a[href*='/p/'], a[href*='/reel/']",
                                                            "els => els.map(e => e.getAttribute('href'))")
                    order = [m.group(2) for h in hrefs if (m := re.search(r"/(p|reel)/([\w-]+)", h or ""))]
                    order += [c for c in found if c not in order]
                    for code in order:
                        if code in visited or code in seen or len(kept) >= limit:
                            continue
                        visited.add(code)
                        m = found.get(code, {})
                        p = normalize(m) if m.get("like_count") is not None and (m.get("carousel_media") or m.get("image_versions2")) else None
                        if not p:
                            p = await media_info(page, code)
                            await asyncio.sleep(random.uniform(1.0, 2.4))
                        if not p:
                            continue
                        checked += 1
                        ok, why = _fits(p, min_likes, fmt, recent_days)
                        if ok and p["type"] in ("릴스", "동영상"):
                            if fmt or reels >= 2:
                                ok, why = False, "릴스"
                            else:
                                reels += 1
                        if ok:
                            kept.append(p)
                            job.log(f"  ✔ @{p['author']} ♥{p['likes']:,} ({p['type']} {p['slides']}장)")
                        job.progress(min(80, 5 + len(kept) / limit * 75),
                                     f"스크롤 {s + 1} · 살펴본 게시물 {checked}개 · 모은 것 {len(kept)}/{limit}")
                    if len(kept) >= limit:
                        break
                    await page.mouse.wheel(0, random.randint(1800, 2800))
                    await page.wait_for_timeout(random.randint(1500, 3000))
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

            kept.sort(key=lambda p: p["likes"] or 0, reverse=True)
            for n, p in enumerate(kept, 1):
                job.progress(80 + n / max(1, len(kept)) * 10, f"댓글 모으는 중 {n}/{len(kept)}")
                if p["pk"]:
                    p["top_comments"] = await top_comments(page, p["pk"])
                    await asyncio.sleep(random.uniform(0.8, 1.8))
            job.progress(92, "슬라이드 이미지 저장 중")
            await _save_images(ctx, kept, assets)
            storage.add_seen(visited)
            await ctx.storage_state(path=str(STATE_FILE))
        for p in kept:
            p.pop("remote_images", None)
            p.pop("taken_ts", None)
        return {"posts": kept, "checked": checked}
    finally:
        _profile_lock.release()


# ---------------- 로그인 없이 링크로 가져오기 (공개 임베드 페이지) ----------------

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")


def _find_media(o):
    if isinstance(o, dict):
        if "shortcode" in o and ("edge_sidecar_to_children" in o or "display_url" in o):
            return o
        for v in o.values():
            r = _find_media(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_media(v)
            if r:
                return r
    return None


async def fetch_public(job, urls: list[str], assets) -> dict:
    """인스타 로그인 없이, 공개 게시물 링크의 임베드 페이지에서 슬라이드·캡션·좋아요 수를 읽는다(댓글 내용은 없음)."""
    import urllib.request
    codes = list(dict.fromkeys(m.group(2) for u in urls if (m := re.search(r"/(p|reel|tv)/([\w-]+)", u))))
    if not codes:
        raise RuntimeError("인스타그램 게시물 링크(https://www.instagram.com/p/…)를 넣어 주세요.")
    posts = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(user_agent=UA, locale="ko-KR")
        for n, code in enumerate(codes, 1):
            job.progress(n / len(codes) * 70, f"게시물 읽는 중 {n}/{len(codes)} (로그인 없이)")
            try:
                await page.goto(f"{BASE}/p/{code}/embed/captioned/", wait_until="domcontentloaded", timeout=40000)
                await page.wait_for_timeout(1500)
                html = await page.content()
                m = re.search(r'"contextJSON":"((?:\\.|[^"\\])*)"', html)
                media = _find_media(json.loads(json.loads('"' + m.group(1) + '"'))) if m else None
                if not media:
                    job.log(f"  읽지 못함(비공개·삭제된 게시물일 수 있음): {code}")
                    continue
                p = normalize(media)
                p["code"] = p["code"] or code
                p["url"] = f"{BASE}/p/{p['code']}/"
                p["source"] = "링크(로그인 없이)"
                posts.append(p)
            except Exception as e:  # noqa: BLE001
                job.log(f"  읽지 못함: {code} ({e.__class__.__name__})")
            await asyncio.sleep(random.uniform(0.8, 1.6))
        await browser.close()
    job.progress(75, "슬라이드 이미지 저장 중")
    for i, p in enumerate(posts, 1):
        for k, u in enumerate(p.pop("remote_images", [])[:12], 1):
            dest = assets / f"p{i}-{k:02d}.jpg"
            try:
                req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://www.instagram.com/"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    dest.write_bytes(r.read())
                p["images"].append(dest.name)
            except Exception:  # noqa: BLE001
                pass
        p.pop("taken_ts", None)
    return {"posts": posts, "checked": len(codes)}
