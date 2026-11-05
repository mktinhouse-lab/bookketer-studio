"""핀터레스트에서 썸네일 배경 후보를 찾는다 (로그인 없이).

검색 화면이 받아 오는 JSON(BaseSearchResource)에서 핀 주소·원본 이미지·설명을 읽고,
JSON을 못 읽으면 화면의 이미지로 대신한다. 원본 핀 링크를 함께 남겨 출처를 확인할 수 있게 한다.
"""
import asyncio
import json
import re
import urllib.parse
import urllib.request

from playwright.async_api import async_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")


def _pins_from_json(obj, out: dict, query: str):
    if isinstance(obj, dict):
        imgs = obj.get("images")
        pid = obj.get("id")
        if isinstance(imgs, dict) and pid and isinstance(pid, str) and pid.isdigit():
            orig = (imgs.get("orig") or {})
            best = orig.get("url") or (imgs.get("736x") or {}).get("url")
            if best and pid not in out:
                out[pid] = {"pin": f"https://www.pinterest.com/pin/{pid}/", "img_url": best,
                            "src": (imgs.get("236x") or {}).get("url", best),
                            "alt": (obj.get("grid_title") or obj.get("auto_alt_text") or obj.get("description") or "")[:120],
                            "w": orig.get("width"), "h": orig.get("height"), "query": query}
        for v in obj.values():
            _pins_from_json(v, out, query)
    elif isinstance(obj, list):
        for v in obj:
            _pins_from_json(v, out, query)


async def search(queries: list[str], per_query: int = 6, exclude: set[str] | None = None,
                 scrolls: int = 2) -> list[dict]:
    exclude = exclude or set()
    results: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(user_agent=UA, locale="ko-KR", viewport={"width": 1400, "height": 1000})
        for q in queries:
            page = await ctx.new_page()
            got: dict[str, dict] = {}
            pending = set()

            async def on_resp(resp, q=q, got=got):
                if "BaseSearchResource" in resp.url or "SearchResource" in resp.url:
                    try:
                        _pins_from_json(json.loads(await resp.text()), got, q)
                    except Exception:  # noqa: BLE001
                        pass

            page.on("response", lambda r: pending.add(asyncio.ensure_future(on_resp(r))))
            try:
                await page.goto("https://www.pinterest.com/search/pins/?q=" + urllib.parse.quote(q),
                                wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(3000)
                for _ in range(scrolls):
                    await page.mouse.wheel(0, 2400)
                    await page.wait_for_timeout(1500)
                await asyncio.gather(*pending, return_exceptions=True)
                if not got:  # JSON을 못 읽었으면 화면 이미지로
                    for it in await page.eval_on_selector_all(
                            "img[src*='i.pinimg.com']", "els => els.map(e => ({src: e.currentSrc || e.src, alt: e.alt || ''}))"):
                        if re.search(r"/\d+x\d+/", it["src"]):
                            continue
                        key = it["src"].split("/")[-1]
                        got.setdefault(key, {"pin": "", "src": it["src"], "alt": it["alt"][:120], "query": q,
                                             "img_url": re.sub(r"/(\d+x|originals)/", "/736x/", it["src"]), "w": None, "h": None})
            except Exception:  # noqa: BLE001 - 한 검색어가 실패해도 나머지는 계속
                pass
            await page.close()
            n = 0
            for c in got.values():
                if c["pin"] in exclude or c["img_url"] in exclude:
                    continue
                results.append(c)
                exclude.add(c["pin"] or c["img_url"])
                n += 1
                if n >= per_query:
                    break
        await browser.close()
    return results


def download(url: str, dest) -> bool:
    if not re.match(r"^https://i\.pinimg\.com/", url):
        return False
    for u in (url, re.sub(r"/originals/", "/736x/", url)):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Referer": "https://www.pinterest.com/"})
            with urllib.request.urlopen(req, timeout=30) as r:
                dest.write_bytes(r.read())
            return True
        except Exception:  # noqa: BLE001 - 원본이 막히면 736 크기로
            continue
    return False
