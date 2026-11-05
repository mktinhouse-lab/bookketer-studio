"""책 제목(+저자)으로 교보문고 → 알라딘 순서로 표지 이미지를 찾아 내려받는다."""
import re
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")


async def find_covers(queries: list[str]) -> list[str | None]:
    """검색어마다 큰 표지 이미지 주소 하나(없으면 None)."""
    out: list[str | None] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(user_agent=UA, locale="ko-KR")
        for q in queries:
            url = None
            try:
                await page.goto("https://search.kyobobook.co.kr/search?keyword=" + urllib.parse.quote(q),
                                wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1200)
                srcs = await page.eval_on_selector_all(
                    "img", "els => els.map(e => e.src).filter(s => s.includes('contents.kyobobook.co.kr') && s.includes('/pdt/'))")
                if srcs:
                    url = re.sub(r"fit-in/\d+x\d+", "fit-in/458x0", srcs[0])
            except Exception:  # noqa: BLE001 - 알라딘으로
                pass
            if not url:
                try:
                    await page.goto("https://www.aladin.co.kr/search/wsearchresult.aspx?SearchTarget=Book&SearchWord="
                                    + urllib.parse.quote(q), wait_until="domcontentloaded", timeout=30000)
                    srcs = await page.eval_on_selector_all("img", "els => els.map(e => e.src).filter(s => s.includes('/cover200/'))")
                    if srcs:
                        url = srcs[0].replace("/cover200/", "/cover500/")
                except Exception:  # noqa: BLE001
                    pass
            out.append(url)
        await browser.close()
    return out


def download(url: str, dest: Path) -> bool:
    for u in (url, url.replace("fit-in/458x0", "fit-in/200x0").replace("/cover500/", "/cover200/")):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if len(data) > 2000:
                dest.write_bytes(data)
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


# ---------------- 교보문고로 실존·저자·절판 확인 ----------------

KYOBO_JS = """() => [...document.querySelectorAll('li.prod_item')].slice(0, 5).map(li => ({
  text: li.innerText.slice(0, 400), img: (li.querySelector('img') || {}).src || '',
  link: (li.querySelector('a.prod_info, a.prod_link') || {}).href || ''}))"""


def _norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def _parse(item: dict) -> dict:
    lines = [ln.strip() for ln in item["text"].split("\n") if ln.strip()]
    title_line = next((ln for ln in lines if ln.startswith("[")), "")
    title = re.sub(r"^\[[^\]]+\]\s*", "", title_line)
    author = next((ln for ln in lines if "저자" in ln), "")
    pub = next((ln for ln in lines if re.search(r"\d{4}년 \d{2}월", ln)), "")
    rating = re.search(r"(\d\.\d) \(([\d,]+)\)", item["text"])
    return {"title": title, "kind": title_line[1:title_line.find("]")] if title_line.startswith("[") else "",
            "author_line": author, "pub": pub, "outofprint": "절판" in item["text"],
            "rating": rating.group(1) if rating else "", "reviews": rating.group(2) if rating else "",
            "img": re.sub(r"fit-in/\d+x\d+", "fit-in/458x0", item["img"]), "link": item["link"]}


async def verify_books(books: list[dict]) -> list[dict]:
    """books = [{title, author}] → 교보문고 첫 결과와 제목이 맞는지·저자·절판 여부 등을 붙여 돌려준다."""
    out = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(user_agent=UA, locale="ko-KR")
        for b in books:
            info = {"verified": False, "note": "교보문고에서 찾지 못함"}
            try:
                await page.goto("https://search.kyobobook.co.kr/search?keyword="
                                + urllib.parse.quote(f"{b['title']} {b.get('author', '')}".strip()),
                                wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(1000)
                items = [_parse(x) for x in await page.evaluate(KYOBO_JS)]
                want = _norm(b["title"])
                hit = next((x for x in items if x["kind"] == "국내도서" and (want in _norm(x["title"]) or _norm(x["title"]) in want)), None) \
                    or next((x for x in items if want and (want in _norm(x["title"]) or _norm(x["title"]) in want)), None)
                if hit:
                    a_ok = not b.get("author") or any(_norm(part) in _norm(hit["author_line"])
                                                      for part in re.split(r"[,·/ ]+", b["author"]) if len(_norm(part)) >= 2)
                    info = {**hit, "verified": True, "author_ok": a_ok,
                            "note": ("절판" if hit["outofprint"] else "판매 중") + ("" if a_ok else " · 저자 확인 필요")}
            except Exception as e:  # noqa: BLE001
                info["note"] = f"확인 실패: {e.__class__.__name__}"
            out.append({**b, "kyobo": info})
        await browser.close()
    return out
