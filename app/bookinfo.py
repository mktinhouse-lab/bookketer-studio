"""알라딘 상품 페이지에서 책 정보·성과를 직접 읽는다(API 키 없음).

AI는 책을 '고르기'만 하고, 제목·저자·출판사·출간일·표지·책소개·쪽수·판매지수·베스트 순위는 여기서 실제 페이지로 확인한다.
- 찾지 못한 책은 None(목록에서 뺀다).
- 페이지에 없는 값은 None → 화면에서 '확인 불가'.
- 값마다 출처 링크(상품 페이지)를 함께 돌려준다.
"""
import html as htmllib
import re
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")
BASE = "https://www.aladin.co.kr"


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


def _text(s: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


def search(title: str, author: str = "") -> list[dict]:
    """알라딘 검색 결과 중 우리말로 나온 종이책([국내도서] = 번역서 포함). 큰글자·전자책·중고·외국어 원서는 뺀다."""
    q = f"{title} {author}".strip()
    params = {"SearchTarget": "Book", "SearchWord": q}
    h = _get(f"{BASE}/search/wsearchresult.aspx?" + urllib.parse.urlencode(params))
    out = []
    for b in h.split('class="ss_book_box"')[1:]:
        m = re.search(r'itemId="(\d+)"', b)
        if not m:
            continue
        t = _text(b[:4000])
        if "[국내도서]" not in t or "[큰글자도서]" in t:
            continue
        tm = re.search(r'class="bo3">(.*?)</a>', b)
        name = _text(tm.group(1)) if tm else ""
        name = re.split(r"\s+-\s+", name)[0].strip()  # 부제(' - …')는 뺀다
        am = re.search(r'<li><a href="/Search/wSearchResult.aspx[?]AuthorSearch.*?</li>', b, flags=re.S | re.I)
        head = _text(am.group(0)) + " |" if am else t.split("[국내도서]", 1)[1]
        meta = re.search(r"([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d{4}년 \d{1,2}월)", head)
        sp = re.search(r"세일즈포인트\s*:\s*([\d,]+)", t)
        out.append({"item_id": m.group(1), "title": name,
                    "author_line": meta.group(1).strip() if meta else "",
                    "publisher": meta.group(2).strip() if meta else "",
                    "month": meta.group(3) if meta else "",
                    "sales_point": int(sp.group(1).replace(",", "")) if sp else None})
    return out


def _pick(results: list[dict], title: str, author: str) -> dict | None:
    nt, na = norm(title), norm(author)
    best, score = None, 0
    for r in results:
        rt = norm(r["title"])
        s = 0
        if rt == nt:
            s = 3
        elif nt and (nt in rt or rt in nt):
            s = 2
        if s and na and na[:3] in norm(r["author_line"]):
            s += 2
        if s > score:
            best, score = r, s
    return best if score >= 2 else None


def product(item_id: str) -> dict:
    url = f"{BASE}/shop/wproduct.aspx?ItemId={item_id}"
    h = _get(url)

    def meta(prop):
        m = re.search(rf'<meta (?:property|name|itemprop)="{prop}" content="([^"]*)"', h)
        return htmllib.unescape(m.group(1)).strip() if m else None

    title = None
    m = re.search(r'class="Ere_bo_title">([^<]+)<', h)
    if m:
        title = htmllib.unescape(m.group(1)).strip()
    sub = re.search(r'<li class="Ere_sub2_title">(.*?)</li>', h, flags=re.S)
    sub_t = _text(sub.group(1)) if sub else ""
    pub = None
    if sub:
        pubs = re.findall(r'PublisherSearch=[^"]*"[^>]*>([^<]+)<', sub.group(1))
        pub = htmllib.unescape(pubs[0]).strip() if pubs else None
    date = meta("datePublished") or (re.search(r"(\d{4}-\d{2}-\d{2})", sub_t).group(1) if re.search(r"\d{4}-\d{2}-\d{2}", sub_t) else None)
    sp = re.search(r"Sales Point\s*:\s*<strong>([\d,]+)</strong>", h)
    # 'Sales Point' 바로 앞: "소설/시/희곡 주간 52위 , 종합 1위 16주 |" → 지금 순위 / 베스트 기록(알라딘 표기 그대로)
    rank, best = None, None
    i = h.find("Sales Point :")
    if i > 0:
        before = _text(h[max(0, i - 1500):i]).rstrip(" |")
        tail = before.split(";")[-1].split("}")[-1]
        rm = re.search(r"((?:[^\s,|]+\s)?(?:주간|월간|일간)\s*\d+위)\s*(?:,\s*((?:종합|[^\s,|]+)\s*(?:top\s*\d+|\d+위)\s*\d+주))?\s*$", tail)
        if rm:
            rank, best = rm.group(1).strip(), (rm.group(2) or "").strip() or None
        else:
            bm = re.search(r"((?:종합|[^\s,|]+)\s*(?:top\s*\d+|\d+위)\s*\d+주)\s*$", tail)
            best = bm.group(1).strip() if bm else None
    pages = re.search(r"<li>(\d+)쪽</li>", h)
    cat = None
    cm = re.search(r'class="conts_info_list2">(.*?)</div>', h, flags=re.S)
    if cm:
        paths = [_text(x).replace("접기", "").strip() for x in re.findall(r"<li[^>]*>(.*?)</li>", cm.group(1), flags=re.S)]
        paths = [p for p in paths if p.startswith("국내도서")] or paths
        cat = re.sub(r"\s*>\s*", " > ", paths[0]) if paths else None
    status = "판매 중"
    if re.search(r"절판|품절되었습니다|구매 불가", _text(h[:200000][h.find("Ere_prod_titlewrap"):h.find("Ere_prod_titlewrap") + 30000])):
        status = "품절·절판 의심"
    desc = meta("og:description") or meta("description")
    return {
        "item_id": item_id, "url": url, "title": title or (meta("og:title") or "").split("|")[0].strip(),
        "author": meta("author"), "author_line": sub_t.split(pub)[0].strip() if pub and pub in sub_t else sub_t,
        "publisher": pub, "pub_date": date, "cover": meta("og:image"), "isbn": meta("og:barcode"),
        "description": desc, "pages": int(pages.group(1)) if pages else None, "category": cat,
        "sales_point": int(sp.group(1).replace(",", "")) if sp else None, "rank_now": rank, "best_record": best, "status": status,
        "checked_at": time.strftime("%Y-%m-%d %H:%M"),
    }


def lookup(title: str, author: str = "") -> dict | None:
    """제목(+저자)으로 찾아 상품 정보를 돌려준다. 못 찾으면 None."""
    try:
        res = search(title, author)
        hit = _pick(res, title, author) or (_pick(search(title), title, author) if author else None)
    except Exception:  # noqa: BLE001
        return None
    if not hit:
        return None
    try:
        return product(hit["item_id"])
    except Exception:  # noqa: BLE001
        return None


def by_publisher(publisher: str, n: int = 40) -> list[dict]:
    """출판사 책 목록(필로틱 1권 포함 옵션용). 출판사 이름으로 검색하고 출판사가 같은 책만 남긴다."""
    try:
        res = search(publisher)
    except Exception:  # noqa: BLE001
        return []
    return [r for r in res if norm(r["publisher"]) == norm(publisher)][:n]


def intro(item_id: str, limit: int = 3500) -> str:
    """책소개·출판사 제공 책소개·목차 일부(설명글의 근거). 못 읽으면 빈 문자열."""
    try:
        h = _get(f"{BASE}/shop/wproduct.aspx?ItemId={item_id}")
        m = re.search(r'id="([A-Za-z]?\d+[Xx]?)_Introduce"', h)  # K062833889 처럼 K로 시작하거나 ISBN10(8972750034) 그대로
        if not m:
            return ""
        out = []
        for name in ("Introduce", "PublisherDesc"):
            req = urllib.request.Request(f"{BASE}/shop/product/getContents.aspx?ISBN={m.group(1)}&name={name}&type=0&date=11",
                                         headers={"User-Agent": UA, "Referer": f"{BASE}/shop/wproduct.aspx?ItemId={item_id}"})
            with urllib.request.urlopen(req, timeout=25) as r:
                t = r.read().decode("utf-8", "replace")
            t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
            t = _text(t)
            t = re.sub(r"(접기|더보기|펼치기)\s*", " ", t)
            out.append(t)
        text = " ".join(out)
        return re.sub(r"\s+", " ", text)[:limit]
    except Exception:  # noqa: BLE001
        return ""
