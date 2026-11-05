"""북케터 밈 카드뉴스 템플릿(HTML/CSS)을 Playwright로 1080×1350 PNG로 렌더링한다."""
import base64
import html
import mimetypes
import re
from pathlib import Path

from playwright.async_api import async_playwright

from .config import DATA_DIR, INSTAGRAM_HANDLE

W, H = 1080, 1350

FONT_CSS = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css"

BASE_CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
html, body { width:1080px; height:1350px; overflow:hidden; }
body { font-family:'Pretendard', 'Malgun Gothic', sans-serif; word-break:keep-all; color:#1f2a36; }
.card { position:relative; width:1080px; height:1350px; overflow:hidden; }
.bg { position:absolute; inset:0; background-size:cover; background-position:center; }
.bg.empty { background:linear-gradient(160deg,#6b5a48 0%,#3a3128 55%,#1d1a17 100%); }
.handle { position:absolute; top:52px; left:46px; font-size:34px; font-weight:700; letter-spacing:-0.5px; }
.box { background:#fff; border:5px solid #1a1a1a; }
.wavy { text-decoration:underline wavy #e5484d; text-decoration-thickness:3px; text-underline-offset:10px; }
b { font-weight:800; }

/* 1. 사진 표지 */
.cover_photo .shade { position:absolute; inset:0;
  background:linear-gradient(to bottom, rgba(0,0,0,0) 40%, rgba(0,0,0,.45) 62%, rgba(18,18,20,.93) 92%); }
.cover_photo .callout { position:absolute; background:#fff; border:2px solid #1a1a1a; font-size:34px;
  font-weight:500; padding:20px 30px; text-align:center; line-height:1.4; color:#111; }
.cover_photo .callout.c0 { top:120px; right:122px; }
.cover_photo .callout.c1 { top:340px; left:86px; }
.cover_photo .bottom { position:absolute; left:0; right:0; bottom:130px; text-align:center; padding:0 60px; }
.cover_photo .pill { display:inline-block; background:#c8f6c2; color:#1a1a1a; font-size:36px; font-weight:500;
  padding:6px 14px; margin-bottom:26px; }
.cover_photo .headline { color:#fff; font-size:92px; font-weight:800; line-height:1.24; letter-spacing:-2px;
  text-shadow:0 2px 18px rgba(0,0,0,.35); }
.cover_photo .hl { color:#b9f6a8; }

/* 모눈종이 배경 */
.paper { background-color:#edebe6;
  background-image:linear-gradient(rgba(0,0,0,.055) 1.5px, transparent 1.5px),
                   linear-gradient(90deg, rgba(0,0,0,.055) 1.5px, transparent 1.5px);
  background-size:54px 54px; }

/* 2. 타이포 표지 */
.paper_title .eyebrow { position:absolute; top:96px; left:90px; font-size:30px; letter-spacing:8px; color:#5b6470; }
.paper_title .stack { position:absolute; top:190px; left:90px; right:90px; bottom:170px;
  display:flex; flex-direction:column; justify-content:center; }
.paper_title .headline { font-size:128px; font-weight:900; line-height:1.16; letter-spacing:-4px; color:#1f2a36; }
.paper_title .hl { background:linear-gradient(transparent 52%, #f5d547 52%); }
.paper_title .body { margin-top:64px; font-size:42px; line-height:1.55; color:#2b3440; }
.paper_title .foot { position:absolute; left:90px; right:90px; bottom:70px; display:flex; justify-content:space-between;
  font-size:28px; color:#5b6470; letter-spacing:2px; }
.paper_title .foot .mono { font-family:'Courier New', monospace; font-weight:700; letter-spacing:0; }

/* 3·4. 박스형 본문 */
.photo_box .wash { position:absolute; inset:0; background:rgba(242,240,234,.52); }
.boxed .title { position:absolute; top:230px; left:50%; transform:translateX(-50%); padding:26px 40px;
  font-size:50px; font-weight:500; white-space:nowrap; letter-spacing:-1px; color:#111; }
.boxed .title b { font-weight:800; }
.boxed .content { position:absolute; left:90px; right:90px; bottom:150px; padding:56px 44px; text-align:center;
  font-size:41px; line-height:1.62; color:#111; letter-spacing:-0.5px; }
.boxed .content .hl { font-weight:800; }
.boxed .content.has-bullets { text-align:left; }
.boxed .content h3 { font-size:54px; font-weight:800; margin-bottom:22px; }
.boxed .content .dots { border-top:4px dotted #1a1a1a; margin:0 0 30px; }
.boxed .content ul { list-style:none; }
.boxed .content li { position:relative; padding-left:46px; margin:10px 0; }
.boxed .content li::before { content:''; position:absolute; left:4px; top:22px; width:18px; height:18px; border-radius:50%; background:#111; }
.boxed .content .lead { margin-bottom:24px; }
.paper_box .content { bottom:auto; top:50%; transform:translateY(-42%); }
.boxed .page { position:absolute; right:60px; bottom:56px; font-size:28px; color:#5b6470; letter-spacing:4px; }

/* 5. 마지막 장 */
.dark_cta .shade { position:absolute; inset:0; background:rgba(22,22,24,.74); }
.dark_cta .headline { position:absolute; top:100px; left:60px; right:60px; text-align:center; color:#fff;
  font-size:66px; font-weight:800; line-height:1.3; letter-spacing:-1.5px; }
.dark_cta .body { position:absolute; top:380px; left:70px; right:70px; text-align:center; color:#fff;
  font-size:54px; font-weight:500; line-height:1.45; letter-spacing:-1px; }
.dark_cta .hl { color:#b9f6a8; }
.dark_cta .handle { top:auto; bottom:80px; left:0; right:0; text-align:center; color:#fff; opacity:.85; }

/* ===== 형식 카드 (책추천 · 30초 요약) — 북케터 밈 실제 게시물 비율로 맞춤 ===== */
.dim { position:absolute; inset:0; background:rgba(0,0,0,.55); }
.mint, .sumx .hl, .kwp .hl, .follow .hl { color:#c9f5b7; }
.red { color:#ff3b30; }
.mtag { display:inline-block; background:#c8f6c2; color:#111; font-weight:600; }

/* 책 한 장 */
.book { text-align:center; color:#fff; }
.book .btitle { position:absolute; top:142px; left:0; right:0; }
.book .btitle span { background:#c8f6c2; color:#111; font-size:40px; font-weight:700; padding:8px 20px; letter-spacing:-1px; }
.book .btags { position:absolute; top:236px; left:0; right:0; }
.book .btags span { background:#fff; color:#111; font-size:34px; padding:8px 24px; letter-spacing:-.5px; }
.book .bcover { position:absolute; top:362px; left:0; right:0; height:530px; display:flex; justify-content:center; align-items:center; }
.book .bcover img { max-height:530px; max-width:440px; box-shadow:0 12px 40px rgba(0,0,0,.45); }
.book .bcover .nocover { width:330px; height:480px; border:3px dashed rgba(255,255,255,.6); display:grid; place-items:center;
  font-size:30px; color:rgba(255,255,255,.8); }
.book .blines { position:absolute; top:968px; left:60px; right:60px; font-size:35px; line-height:1.55; letter-spacing:-.8px; }
.book .blines .hl { color:#c9f5b7; }

/* 팔로우 장 */
.follow { text-align:center; color:#fff; }
.follow .fhead { position:absolute; top:430px; left:40px; right:40px; font-size:48px; font-weight:800; letter-spacing:-1px; }
.follow .fbody { position:absolute; top:505px; left:40px; right:40px; font-size:40px; line-height:1.45; letter-spacing:-1px; }
.follow .pill { position:absolute; top:660px; left:150px; width:780px; height:220px; background:#fff; border-radius:110px;
  display:flex; align-items:center; padding:0 40px; gap:28px; box-shadow:0 10px 40px rgba(0,0,0,.3); }
.follow .pill .av { width:140px; height:140px; border-radius:50%; background:#ddd center/cover; flex:none; border:4px solid #eee; }
.follow .pill .nm { font-size:42px; font-weight:800; color:#111; flex:1; text-align:left; }
.follow .pill .fb { background:#4b5cf0; color:#fff; font-size:44px; font-weight:800; padding:22px 40px; border-radius:22px; position:relative; }
.follow .pill .fb svg { position:absolute; right:-36px; bottom:-48px; width:86px; height:86px; }

/* 30초 요약: 목차 · 셀프체크 */
.sumx { color:#fff; }
.sumx .dim { background:rgba(0,0,0,.42); }
.sumx .stag { position:absolute; top:117px; left:82px; font-size:25px; padding:9px 22px; }
.sumx .stitle { position:absolute; top:182px; left:82px; right:60px; font-size:72px; font-weight:800; letter-spacing:-2px; line-height:1.15; }
.sumx .ssub { position:absolute; top:282px; left:82px; right:60px; font-size:25px; opacity:.92; }
.sumx .slist { position:absolute; top:372px; left:82px; right:60px; font-size:36px; line-height:1.48; letter-spacing:-.5px; }
.sumx .sfoot { position:absolute; left:82px; right:60px; font-size:36px; letter-spacing:-.5px; }

/* 30초 요약: 키워드 2개 */
.kwp { display:flex; flex-direction:column; }
.kwp .half { position:relative; flex:1; overflow:hidden; color:#fff; }
.kwp .half + .half { border-top:3px solid #111; }
.kwp .half .bg { position:absolute; inset:0; background-size:cover; background-position:center; }
.kwp .half .dim { background:rgba(0,0,0,.48); }
.kwp .ktag { position:absolute; top:117px; left:82px; font-size:25px; padding:9px 18px; }
.kwp .ktitle { position:absolute; top:178px; left:82px; right:50px; font-size:76px; font-weight:800; letter-spacing:-2px; white-space:nowrap; }
.kwp .ken { position:absolute; top:290px; left:82px; font-size:25px; opacity:.92; }
.kwp .kl1 { position:absolute; top:372px; left:82px; right:50px; font-size:37px; letter-spacing:-.8px; }
.kwp .kl2 { position:absolute; top:430px; left:82px; right:50px; font-size:37px; letter-spacing:-.8px; }
"""

CURSOR_SVG = ('<svg viewBox="0 0 24 24"><path d="M4 2l16 9-7 2-3 7z" fill="#111" stroke="#fff" stroke-width="1.5"/>'
              '<path d="M14 3l2-2M18 6l3-1M17 1l1-1" stroke="#111" stroke-width="1.5"/></svg>')


def markup(text: str) -> str:
    t = html.escape(text or "")
    t = re.sub(r"\[\[(.+?)\]\]", r'<span class="hl">\1</span>', t)
    t = re.sub(r"\{\{(.+?)\}\}", r'<span class="red">\1</span>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__(.+?)__", r'<span class="wavy">\1</span>', t)
    return t.replace("\\n", "<br>").replace("\n", "<br>")


def image_data_uri(rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    path = (DATA_DIR / rel_path).resolve()
    if not path.is_file() or DATA_DIR.resolve() not in path.parents:
        return None
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _bg(slide: dict) -> str:
    uri = image_data_uri(slide.get("image"))
    if uri:
        return f'<div class="bg" style="background-image:url(\'{uri}\')"></div>'
    return '<div class="bg empty"></div>'


def slide_inner(slide: dict, idx: int, total: int) -> str:
    t = slide.get("template") or "photo_box"
    label, headline, body = slide.get("label", ""), slide.get("headline", ""), slide.get("body", "")
    bullets = [b for b in slide.get("bullets") or [] if b.strip()]
    page = f"{idx + 1}  /  {total}"
    handle_text = INSTAGRAM_HANDLE.lstrip("@")

    if t == "book":
        cover = image_data_uri(slide.get("cover"))
        cv = f'<img src="{cover}">' if cover else '<div class="nocover">표지 이미지를<br>올려 주세요</div>'
        tags = " ".join(slide.get("tags") or [])
        lines = "<br>".join(markup(x) for x in slide.get("lines") or [])
        return (f'<div class="card book">{_bg(slide)}<div class="dim"></div>'
                f'<div class="btitle"><span>{html.escape(slide.get("title", ""))}</span></div>'
                + (f'<div class="btags"><span>{html.escape(tags)}</span></div>' if tags else "")
                + f'<div class="bcover">{cv}</div><div class="blines">{lines}</div></div>')

    if t == "follow_cta":
        av = image_data_uri(slide.get("avatar"))
        return (f'<div class="card follow">{_bg(slide)}<div class="dim"></div>'
                f'<div class="fhead">{markup(slide.get("headline", ""))}</div><div class="fbody">{markup(slide.get("body", ""))}</div>'
                f'<div class="pill"><div class="av" style="{f"background-image:url({av})" if av else ""}"></div>'
                f'<div class="nm">{handle_text}</div><div class="fb">팔로우{CURSOR_SVG}</div></div></div>')

    if t in ("summary_index", "self_check"):
        items = slide.get("items") or []
        if t == "self_check":
            items = [("☐ " + x if not x.startswith("☐") else x) for x in items]
        foot_top = 372 + int(36 * 1.48 * len(items)) + 50
        return (f'<div class="card sumx">{_bg(slide)}<div class="dim"></div>'
                f'<div class="stag mtag">{html.escape(slide.get("tag", ""))}</div>'
                f'<div class="stitle">{markup(slide.get("title", ""))}</div><div class="ssub">{html.escape(slide.get("subtitle", ""))}</div>'
                f'<div class="slist">{"<br>".join(markup(x) for x in items)}</div>'
                f'<div class="sfoot mint" style="top:{foot_top}px">{markup(slide.get("footer", ""))}</div></div>')

    if t == "keyword_pair":
        halves = ""
        for it in (slide.get("items") or [])[:2]:
            uri = image_data_uri(it.get("image"))
            bg = f'<div class="bg" style="background-image:url(\'{uri}\')"></div>' if uri else '<div class="bg empty"></div>'
            halves += (f'<div class="half">{bg}<div class="dim"></div><div class="ktag mtag">{html.escape(it.get("no", ""))}</div>'
                       f'<div class="ktitle">{html.escape(it.get("title", ""))}</div><div class="ken">{html.escape(it.get("en", ""))}</div>'
                       f'<div class="kl1">{markup(it.get("line1", ""))}</div><div class="kl2 mint">{markup(it.get("line2", ""))}</div></div>')
        return f'<div class="card kwp">{halves}</div>'

    if t == "cover_photo":
        callouts = "".join(f'<div class="callout c{i}">{markup(c)}</div>'
                           for i, c in enumerate([c for c in slide.get("callouts") or [] if c.strip()][:2]))
        pill = f'<div class="pill">{markup(label)}</div><br>' if label else ""
        return (f'<div class="card cover_photo">{_bg(slide)}<div class="shade"></div>{callouts}'
                f'<div class="bottom">{pill}<div class="headline">{markup(headline)}</div></div></div>')

    if t == "paper_title":
        return (f'<div class="card paper paper_title"><div class="eyebrow">{markup(label)}</div>'
                f'<div class="stack"><div class="headline">{markup(headline)}</div>'
                f'<div class="body">{markup(body)}</div></div>'
                f'<div class="foot"><span>{markup(label)}</span><span class="mono">{INSTAGRAM_HANDLE}</span></div></div>')

    if t == "dark_cta":
        return (f'<div class="card dark_cta">{_bg(slide)}<div class="shade"></div>'
                f'<div class="headline">{markup(headline)}</div><div class="body">{markup(body)}</div>'
                f'<div class="handle">{INSTAGRAM_HANDLE}</div></div>')

    # photo_box / paper_box
    is_paper = t == "paper_box"
    if bullets:
        inner = ""
        if is_paper and label:
            inner += f"<h3>{markup(label)}</h3><div class='dots'></div>"
        if body:
            inner += f'<div class="lead">{markup(body)}</div>'
        inner += "<ul>" + "".join(f"<li>{markup(b)}</li>" for b in bullets) + "</ul>"
        content = f'<div class="content box has-bullets">{inner}</div>'
    else:
        content = f'<div class="content box">{markup(body)}</div>'
    title = "" if (is_paper and bullets) or not label else f'<div class="title box">{markup(label)}</div>'
    bg = "" if is_paper else f'{_bg(slide)}<div class="wash"></div>'
    cls = "paper paper_box" if is_paper else "photo_box"
    return (f'<div class="card boxed {cls}">{bg}<div class="handle">{handle_text}</div>'
            f'{title}{content}<div class="page">{page}</div></div>')


def slide_html(slide: dict, idx: int, total: int) -> str:
    return (f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="{FONT_CSS}">'
            f"<style>{BASE_CSS}</style></head><body>{slide_inner(slide, idx, total)}</body></html>")


async def render_cards(jobs: list[tuple[dict, int, int, Path]]) -> None:
    """jobs = [(슬라이드, 쪽 번호(0부터), 전체 장수, 저장할 경로)]"""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": W, "height": H})
        for slide, idx, total, path in jobs:
            await page.set_content(slide_html(slide, idx, total), wait_until="networkidle")
            await page.evaluate("document.fonts.ready")
            await page.screenshot(path=str(path))
        await browser.close()


async def render_slides(slides: list[dict], out_dir: Path) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    names = [f"slide_{i + 1:02d}.png" for i in range(len(slides))]
    await render_cards([(s, i, len(slides), out_dir / n) for i, (s, n) in enumerate(zip(slides, names))])
    return names
