import asyncio
import io
import secrets
import zipfile

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import claude_ai, formats, instagram, learn, share, storage, workflow
from .config import ASSETS_DIR, BRAND_GUIDE_FILE, DATA_DIR, MD_KINDS, PROMPTS_DIR, STATIC_DIR
from .dummy import ensure_sample
from .jobs import get_job, run_in_new_loop, running_jobs, start_job, stop_job
from .render import render_cards

app = FastAPI(title="북케터 밈 카드뉴스 스튜디오")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
ensure_sample()

# 공유 링크로 들어온 사람이 쓰면 안 되는 기능 (창이 이 PC 에 뜨거나 공유 설정을 바꾸는 것)
HOST_ONLY = ("/api/session/login", "/api/claude/login", "/api/claude/code", "/api/desktop", "/api/share",
             "/api/graph/token", "/api/windsor/key")  # 키·로그인·공유 설정은 이 PC 에서만
OPEN_PATHS = ("/login", "/api/login", "/static/style.css")

LOGIN_HTML = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>북케터 밈 카드뉴스 스튜디오</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(ellipse 62% 48% at 50% 46%,#cfe6df 0%,#d9ece6 22%,#e9f5f0 46%,#f6fbf9 70%,#ffffff 100%) fixed,#f2f8f6;color:#1f2a36;font:15px/1.55 'Malgun Gothic',system-ui,sans-serif;padding:16px}
.box{background:rgba(255,255,255,.85);border:1px solid #dbe8e3;border-radius:20px;padding:30px 28px 24px;width:100%;max-width:380px;box-shadow:0 10px 40px #0002}
.logo{width:44px;height:44px;border-radius:50%;background:#b9f6a8;display:grid;place-items:center;font-weight:900;font-size:18px;margin-bottom:12px}
h1{font-size:18px;margin:0 0 4px}p{margin:0 0 18px;color:#6a6f78;font-size:13.5px}
input{width:100%;box-sizing:border-box;font:inherit;background:#f2f8f6;border:1px solid #dbe8e3;border-radius:11px;padding:11px 13px;outline:none}
button{width:100%;margin-top:10px;border:0;border-radius:11px;padding:11px;font:inherit;font-weight:700;color:#fff;background:#1f2a36;cursor:pointer}
#msg{min-height:20px;margin-top:10px;font-size:13px;color:#e03131}</style></head><body>
<form class="box" id="f"><div class="logo">밈</div><h1>북케터 밈 카드뉴스 스튜디오</h1><p>팀 공유 링크입니다. 전달받은 비밀번호를 넣어 주세요.</p>
<input type="password" id="pw" placeholder="공유 비밀번호" autofocus><button>들어가기</button><div id="msg"></div></form>
<script>document.getElementById('f').onsubmit=async e=>{e.preventDefault();const m=document.getElementById('msg');m.textContent='';
try{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.getElementById('pw').value})});
if(r.ok){location.href='/';return}let t='들어가지 못했습니다.';try{t=(await r.json()).detail||t}catch(_){}m.textContent=t}
catch(_){m.textContent='연결하지 못했습니다. 링크를 보낸 사람의 PC 와 프로그램이 켜져 있는지 확인해 주세요.'}};</script></body></html>"""


@app.middleware("http")
async def share_gate(request, call_next):
    """공유 링크(Cloudflare 터널)로 들어온 요청만 비밀번호를 확인한다. 이 PC 에서 직접 여는 화면은 그대로."""
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
    if share.is_remote(request.headers):
        path = request.url.path
        if not path.startswith(OPEN_PATHS) and not share.valid_cookie(request.cookies.get(share.COOKIE)):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "공유 비밀번호를 다시 넣어 주세요."}, status_code=401)
            return RedirectResponse("/login")
        if path.startswith(HOST_ONLY):
            return JSONResponse({"detail": "이 기능은 프로그램이 켜진 PC 에서만 쓸 수 있어요."}, status_code=403)
        if path == "/login":
            return HTMLResponse(LOGIN_HTML)
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"  # 고친 화면이 새로고침만으로 바로 보이게
    return resp


@app.get("/login")
def login_page():
    from fastapi.responses import HTMLResponse
    return HTMLResponse(LOGIN_HTML)


class LoginReq(BaseModel):
    password: str


@app.post("/api/login")
def share_login(r: LoginReq, request: Request):
    from fastapi.responses import JSONResponse
    ip = request.headers.get("cf-connecting-ip", "local")
    try:
        ok = share.check_password(r.password, ip)
    except PermissionError as e:
        bad(str(e), 429)
    if not ok:
        bad("비밀번호가 맞지 않습니다.", 401)
    res = JSONResponse({"ok": True})
    res.set_cookie(share.COOKIE, share.token(), max_age=30 * 86400, httponly=True, secure=True, samesite="lax")
    return res


@app.get("/api/share")
def share_status():
    return share.status()


class SharePw(BaseModel):
    password: str


@app.post("/api/share/password")
def share_password(r: SharePw):
    if len(r.password.strip()) < 4:
        bad("비밀번호는 4글자 이상으로 정해 주세요.")
    share.set_password(r.password.strip())
    return share.status()


@app.post("/api/share/start")
async def share_start():
    try:
        return await asyncio.to_thread(share.start)
    except RuntimeError as e:
        bad(str(e))


class NgrokReq(BaseModel):
    token: str = ""
    domain: str = ""


@app.post("/api/share/ngrok")
def share_ngrok(r: NgrokReq):
    try:
        return share.set_ngrok(r.token, r.domain)
    except RuntimeError as e:
        bad(str(e))


@app.on_event("startup")
def _auto_share():
    """고정 주소가 정해져 있으면 프로그램을 켤 때 공유도 같이 켠다(팀장님 링크가 늘 같은 주소로 열리게)."""
    import threading
    import time

    def run():
        # PC를 막 켰을 때는 인터넷이 아직 준비 안 돼 실패할 수 있다(ERR_NGROK_4018 등) → 30초 간격으로 최대 10번 다시 시도
        for _ in range(10):
            if share.start().get("on"):
                return
            time.sleep(30)

    if share.fixed_ready() and share.has_password():
        threading.Thread(target=run, daemon=True).start()


@app.post("/api/share/stop")
def share_stop():
    return share.stop()


@app.on_event("shutdown")
def _stop_share():
    share.stop()


def in_thread(coro_factory):
    return asyncio.to_thread(run_in_new_loop, coro_factory)


def bad(msg: str, code: int = 400):
    raise HTTPException(code, msg)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "studio.html")


@app.get("/legacy")
def legacy_index():
    """10/13 판 화면(레퍼런스 → 기획 후보 3개). 새 단계형 화면이 다 갖춰지면 지운다."""
    return FileResponse(STATIC_DIR / "index.html")


# ---------------- 상태 · 설정 ----------------

@app.get("/api/meta")
async def meta(request: Request):
    return {
        "remote": share.is_remote(request.headers),
        "share": None if share.is_remote(request.headers) else share.status(),
        "claude": await asyncio.to_thread(claude_ai.auth_status),
        "session": instagram.session_status(),
        "modes": workflow.MODE_KO,
        "formats": formats.FORMATS,
        "projects": storage.load_projects(),
        "settings": storage.load_settings(),
        "ready": {"prompts": {m: (PROMPTS_DIR / f"{m}.md").exists() for m in workflow.MODE_KO},
                  "brand": BRAND_GUIDE_FILE.exists(), "cta": (ASSETS_DIR / "cta.png").exists(),
                  "book_bg": (ASSETS_DIR / "book_bg.jpg").exists(), "profile": (ASSETS_DIR / "profile.jpg").exists()},
    }


@app.post("/api/claude/login")
def claude_login():
    try:
        return claude_ai.start_login()
    except RuntimeError as e:
        bad(str(e))


class CodeReq(BaseModel):
    code: str


@app.post("/api/claude/code")
def claude_code(r: CodeReq):
    try:
        return claude_ai.submit_login(r.code)
    except RuntimeError as e:
        bad(str(e))


class Project(BaseModel):
    id: str | None = None
    name: str
    message: str = ""
    details: str = ""
    cta: str = ""
    proof: str = ""
    books: str = ""
    book_title: str = ""
    book_author: str = ""
    summary_type: str = "keyword"
    kw_count: int = 10
    fmt: str = ""
    thumb: str = ""
    copy_style: str = "auto"


@app.post("/api/projects")
def save_project(p: Project):
    projects = storage.load_projects()
    pid = p.id or secrets.token_hex(4)
    projects[pid] = {**p.model_dump(exclude={"id"}), "id": pid}
    storage.save_projects(projects)
    return projects[pid]


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    projects = storage.load_projects()
    projects.pop(pid, None)
    storage.save_projects(projects)
    return {"ok": True}


@app.post("/api/settings")
def save_settings(s: dict):
    cur = storage.load_settings()
    cur.update({k: v for k, v in s.items() if k in ("headless",)})
    storage.save_settings(cur)
    return cur


# ---------------- 작업 ----------------

@app.get("/api/jobs")
def jobs():
    return running_jobs()


@app.post("/api/jobs/{job_id}/stop")
def job_stop(job_id: str):
    return {"ok": stop_job(job_id)}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        bad("작업을 찾을 수 없습니다.", 404)
    return job.to_dict()


# ---------------- 수집 ----------------

class SearchReq(BaseModel):
    keyword: str
    min_likes: int = 5000
    fmt: str | None = None
    recent_days: int = 0
    fresh: bool = False


@app.post("/api/crawl/search")
def crawl_search(r: SearchReq):
    if not r.keyword.strip():
        bad("검색어를 입력하세요.")
    label = f"{r.keyword} {'새로 찾기' if r.fresh else '수집'}"
    job = start_job(label, lambda j: workflow.crawl_job(j, keyword=r.keyword.strip(), min_likes=r.min_likes,
                                                         fmt=r.fmt, recent_days=r.recent_days, fresh=r.fresh),
                    {"kind": "crawl"})
    return {"job": job.id}


class UrlsReq(BaseModel):
    urls: list[str]


@app.post("/api/crawl/urls")
def crawl_urls(r: UrlsReq):
    urls = [u.strip() for u in r.urls if u.strip()]
    if not urls:
        bad("게시물 링크를 붙여넣어 주세요.")
    job = start_job(f"링크 {len(urls)}개 가져오기(로그인 없이)", lambda j: workflow.crawl_job(j, urls=urls), {"kind": "crawl"})
    return {"job": job.id}


class FindReq(BaseModel):
    topic: str
    count: int = 3
    prefs: str = ""
    exclude: list[str] = []


@app.post("/api/books/find")
def books_find(r: FindReq):
    if not r.topic.strip():
        bad("썸네일 카피나 장르를 먼저 적어 주세요.")
    return {"job": start_job(f"책 찾기 · {r.topic.strip()[:16]}",
                             lambda j: workflow.find_books_job(j, r.topic.strip(), max(1, min(r.count, 10)),
                                                               r.prefs.strip(), r.exclude), {"kind": "books"}).id}


class VarReq(BaseModel):
    crawl_file: str
    n: int
    topic: str = ""
    mode: str = "book3"


@app.post("/api/variations")
def variations(r: VarReq):
    return {"job": start_job(f"카피 베리에이션 · 레퍼런스 #{r.n}",
                             lambda j: workflow.variations_job(j, r.crawl_file, r.n, r.topic.strip(), r.mode),
                             {"kind": "variations"}).id}


class CheckReq(BaseModel):
    plan_file: str
    round: int
    cand: int


@app.post("/api/factcheck")
def factcheck(r: CheckReq):
    return {"job": start_job(f"팩트체크 · 후보 {r.cand}",
                             lambda j: workflow.factcheck_job(j, r.plan_file, r.round, r.cand),
                             {"kind": "plan", "plan_file": r.plan_file}).id}


@app.get("/api/files/{kind}")
def files(kind: str):
    if kind not in MD_KINDS:
        bad("종류가 잘못됐습니다.")
    return [{"name": n} for n in storage.list_names(kind)]


@app.get("/api/file/{kind}/{name}")
def file_detail(kind: str, name: str):
    try:
        d = storage.read_md(kind, name)
    except FileNotFoundError:
        bad("파일을 찾을 수 없습니다.", 404)
    return d


@app.get("/api/img/{kind}/{folder}/{name}")
def image(kind: str, folder: str, name: str):
    if kind not in MD_KINDS or any(x in (folder + name) for x in ("..", "/", "\\")):
        bad("잘못된 경로", 404)
    p = DATA_DIR / kind / folder / name
    if not p.is_file():
        bad("이미지 없음", 404)
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


class Upload(BaseModel):
    data: str


ASSET_NAMES = {"book_bg": "book_bg.jpg", "profile": "profile.jpg", "cta": "cta.png"}


@app.post("/api/assets/{key}")
def save_asset(key: str, u: Upload):
    """형식 카드에 늘 쓰는 이미지(책 장 배경 · 팔로우 장 프로필 · 마지막 장 고정 이미지)를 assets 폴더에 저장."""
    if key not in ASSET_NAMES:
        bad("알 수 없는 이미지 종류입니다.")
    (ASSETS_DIR / ASSET_NAMES[key]).write_bytes(workflow.data_url_bytes(u.data))
    return {"ok": True}


@app.delete("/api/assets/{key}")
def delete_asset(key: str):
    if key in ASSET_NAMES:
        (ASSETS_DIR / ASSET_NAMES[key]).unlink(missing_ok=True)
    return {"ok": True}


@app.get("/api/assets/{key}")
def get_asset(key: str):
    p = ASSETS_DIR / ASSET_NAMES.get(key, "_none")
    if not p.is_file():
        bad("없음", 404)
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


@app.post("/api/upload")
def upload(u: Upload):
    ext = ".png" if u.data.startswith("data:image/png") else ".jpg"
    folder = DATA_DIR / "generate" / "_uploads"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{storage.stamp()}_{secrets.token_hex(3)}{ext}"
    (folder / name).write_bytes(workflow.data_url_bytes(u.data))
    return {"url": workflow.img_url("generate", "_uploads", name), "rel": f"generate/_uploads/{name}"}


# ---------------- 기획 · 이미지 ----------------

class PlanReq(BaseModel):
    crawl_file: str | None = None
    picks: list[int] = []
    mode: str = "long"
    project: dict | None = None
    plan_file: str | None = None
    feedback: str = ""
    target: int = 0
    target_round: int = 0


@app.post("/api/plan")
def plan(r: PlanReq):
    body = r.model_dump()
    if r.plan_file:
        if not r.feedback.strip():
            bad("수정하고 싶은 내용을 입력하세요.")
        title = f"다시 기획 · {r.feedback[:16]}"
        meta = {"kind": "plan", "plan_file": r.plan_file}
    else:
        if formats.kind(r.mode) == "free" and (not r.crawl_file or not r.picks):
            bad("기획할 레퍼런스를 1~3개 선택하세요.")
        pj = r.project or {}
        auto = formats.kind(r.mode) == "books" and not (pj.get("books") or "").strip()
        if auto and not r.picks and not any(pj.get(k) for k in ("name", "thumb", "message")):
            bad("2번에서 레퍼런스를 고르거나 1번에 썸네일 카피·주제를 적어 주세요.")
        if not auto and not pj.get("name"):
            bad("1번 칸에서 알리고 싶은 내용(프로젝트)을 먼저 입력하세요.")
        title = f"{'자동 기획' if auto else '새 기획'} · {formats.get(r.mode)['name']} · {(pj.get('name') or pj.get('thumb') or '레퍼런스')[:14]}" + \
            (f" · 레퍼런스 {' '.join('#' + str(n) for n in r.picks)}" if r.picks else "")
        meta = {"kind": "plan"}
    return {"job": start_job(title, lambda j: workflow.plan_job(j, body), meta).id}


class MoreReq(BaseModel):
    cand_file: str
    direction: str = ""


@app.post("/api/images/more")
def images_more(r: MoreReq):
    return {"job": start_job("이미지 더 찾기", lambda j: workflow.more_images_job(j, r.cand_file, r.direction.strip())).id}


class CanvasSave(BaseModel):
    png: str
    state: dict
    copy_text: str = ""
    meta: dict = {}


@app.post("/api/canvas/save")
def canvas_save(r: CanvasSave):
    return workflow.save_thumb(r.png, r.state, r.copy_text, r.meta)


# ---------------- 완성본 ----------------

class PublishReq(BaseModel):
    plan_file: str
    round: int
    cand: int
    thumb_file: str


@app.post("/api/publish")
def publish(r: PublishReq):
    job = start_job("저장 · 카드 이미지 만들기",
                    lambda j: workflow.publish_job(j, r.plan_file, r.round, r.cand, r.thumb_file), {"kind": "publish"})
    return {"job": job.id}


def _pub(file: str) -> dict:
    try:
        p = storage.read_data("generate", file)
    except FileNotFoundError:
        bad("완성본을 찾을 수 없습니다.", 404)
    if p.get("type") != "발행":
        bad("완성본 파일이 아닙니다.")
    return p


def _cards_dir(p: dict):
    return DATA_DIR / "generate" / p["folder"]


def _next_card_name(p: dict) -> str:
    used = {c["file"] for c in p["cards"]}
    n = len(used) + 1
    while f"c{n:02d}.png" in used or (_cards_dir(p) / f"c{n:02d}.png").exists():
        n += 1
    return f"c{n:02d}.png"


@app.get("/api/pub/card")
def pub_card(file: str, index: int):
    p = _pub(file)
    c = p["cards"][index]
    state = c.get("state")
    if not state and c["kind"] == "thumb":
        t = storage.read_data("generate", p["thumb_file"])
        return {"card": c, "state": t.get("state"), "thumb": t}
    return {"card": c, "state": state}


class CardSave(BaseModel):
    file: str
    index: int
    png: str
    state: dict


@app.post("/api/pub/card/save")
def pub_card_save(r: CardSave):
    p = _pub(r.file)
    c = p["cards"][r.index]
    (_cards_dir(p) / c["file"]).write_bytes(workflow.data_url_bytes(r.png))
    c["state"] = r.state
    workflow.save_publish(p)
    return {"ok": True}


class SlideSave(BaseModel):
    file: str
    index: int
    slide: dict


@app.post("/api/pub/card/slide")
async def pub_card_slide(r: SlideSave):
    p = _pub(r.file)
    c = p["cards"][r.index]
    c["slide"] = r.slide
    c["kind"] = c["kind"] if c["kind"] in ("body", "cta") else "body"
    await in_thread(lambda: render_cards([(r.slide, r.index, len(p["cards"]), _cards_dir(p) / c["file"])]))
    workflow.save_publish(p)
    return {"ok": True}


class CardImage(BaseModel):
    file: str
    index: int
    mode: str  # replace | insert
    data: str


@app.post("/api/pub/card/image")
def pub_card_image(r: CardImage):
    p = _pub(r.file)
    name = _next_card_name(p)
    (_cards_dir(p) / name).write_bytes(workflow.data_url_bytes(r.data))
    card = {"file": name, "kind": "image"}
    if r.mode == "insert":
        p["cards"].insert(max(1, min(r.index, len(p["cards"]))), card)
    else:
        if r.index == 0:
            card["kind"] = "thumb"
        p["cards"][r.index] = card
    workflow.save_publish(p)
    return {"ok": True}


class CardMove(BaseModel):
    file: str
    index: int
    step: int = 0


@app.post("/api/pub/card/move")
def pub_card_move(r: CardMove):
    p = _pub(r.file)
    j = r.index + r.step
    if r.index < 1 or j < 1 or j >= len(p["cards"]):
        bad("썸네일(첫 장) 자리로는 옮길 수 없습니다.")
    p["cards"][r.index], p["cards"][j] = p["cards"][j], p["cards"][r.index]
    workflow.save_publish(p)
    return {"ok": True}


@app.post("/api/pub/card/remove")
def pub_card_remove(r: CardMove):
    p = _pub(r.file)
    if r.index < 1:
        bad("썸네일은 뺄 수 없습니다. [내 이미지로]나 [편집]으로 바꿔 주세요.")
    p["cards"].pop(r.index)
    workflow.save_publish(p)
    return {"ok": True}


class CaptionSave(BaseModel):
    file: str
    caption: str
    comment: str


@app.post("/api/pub/caption")
def pub_caption(r: CaptionSave):
    p = _pub(r.file)
    p["caption"], p["comment"] = r.caption, r.comment
    workflow.save_publish(p)
    return {"ok": True}


@app.get("/api/pub/zip")
def pub_zip(file: str):
    p = _pub(file)
    buf = io.BytesIO()
    head = storage.slugify(p["copy"].split("\n")[0], 16)
    with zipfile.ZipFile(buf, "w") as z:
        for i, c in enumerate(p["cards"], 1):
            z.write(_cards_dir(p) / c["file"], f"{head}_{i:02d}.png")
        z.writestr(f"{head}_캡션.txt", p["caption"] + "\n\n──── 고정댓글 ────\n\n" + p["comment"])
    buf.seek(0)
    from urllib.parse import quote
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(head)}.zip"})


class FileReq(BaseModel):
    file: str


@app.post("/api/desktop")
def desktop(r: FileReq):
    p = workflow.save_publish(_pub(r.file))
    workflow.open_folder(p["desktop"]["folder"])
    return p["desktop"]


# ---------------- 보관함 · 결과 보기 · 삭제 ----------------

def _all(kind):
    out = []
    for n in storage.list_names(kind):
        try:
            out.append((n, storage.read_data(kind, n)))
        except Exception:  # noqa: BLE001 - 깨진 파일은 건너뛴다
            continue
    return out


@app.get("/api/library")
def library():
    pubs = [d for _, d in _all("generate") if d.get("type") == "발행"]
    items = []
    for name, d in _all("analysis"):
        for r in d.get("rounds", []):
            for k, c in enumerate(r["candidates"], 1):
                mine = [p for p in pubs if p["plan_file"] == name and p["round"] == r["n"] and p["cand"] == k]
                img = c.get("img") or {}
                items.append({
                    "plan_file": name, "round": r["n"], "cand": k, "mode": d["mode"], "project": d["project"].get("name", ""),
                    "copy": c["copy"], "label": c.get("label", ""), "callouts": c.get("callouts", []), "angle": c["angle"],
                    "tags": formats.get(d["mode"]).get("tags", []), "content": c.get("content"),
                    "pattern": c["pattern"], "caption": c["caption"], "comment": c["comment"], "slides": c.get("slides") or [],
                    "img": img or None, "bg": workflow.img_url("generate", img["assets"], img["bg"]) if img.get("bg") else "",
                    "when": workflow.when_of(name), "pub": mine[0] if mine else None, "pubs": len(mine),
                    "status": "저장됨" if mine else "안 쓴 후보"})
    items.sort(key=lambda x: (x["plan_file"], x["round"], -x["cand"]), reverse=True)
    return {"items": items}


@app.get("/api/overview")
def overview():
    crawl, analysis, generate = [], [], []
    for n, d in _all("crawl"):
        posts = d.get("posts") or []
        thumb = next((workflow.img_url("crawl", workflow.folder_of(n), p["images"][0]) for p in posts if p.get("images")), "")
        crawl.append({"name": n, "title": d.get("source", n), "count": len(posts),
                      "top": max((p.get("likes") or 0 for p in posts), default=0), "when": workflow.when_of(n), "thumb": thumb})
    for n, d in _all("analysis"):
        if d.get("type") in ("책찾기", "카피베리에이션"):
            first = (d.get("books") or [{}])[0].get("kyobo", {}).get("img", "") if d["type"] == "책찾기" else                 workflow.img_url("crawl", workflow.folder_of(d["crawl_file"]), d["ref"]["images"][0]) if d.get("ref", {}).get("images") else ""
            analysis.append({"name": n, "parent": d.get("crawl_file"), "type": d["type"], "mode": d["type"],
                             "title": d.get("topic") if d["type"] == "책찾기" else d.get("original", ""),
                             "project": d.get("topic", ""), "picks": [d["n"]] if d.get("n") else [], "rounds": 0,
                             "when": workflow.when_of(n), "thumb": first})
            continue
        last = (d.get("rounds") or [{}])[-1]
        c1 = (last.get("candidates") or [{}])[0]
        img = c1.get("img") or {}
        analysis.append({"name": n, "parent": d.get("crawl_file"), "title": c1.get("copy", "기획"), "mode": workflow.MODE_KO.get(d.get("mode"), ""),
                         "project": (d.get("project") or {}).get("name", ""), "picks": d.get("picks", []),
                         "rounds": len(d.get("rounds", [])), "when": workflow.when_of(n),
                         "thumb": workflow.img_url("generate", img["assets"], img["bg"]) if img.get("bg") else ""})
    used_thumbs = set()
    gens = _all("generate")
    for n, d in gens:
        if d.get("type") == "발행":
            used_thumbs.add(d.get("thumb_file"))
    for n, d in gens:
        t = d.get("type")
        item = {"name": n, "type": t, "when": workflow.when_of(n), "title": d.get("copy", n)}
        if t == "발행":
            item.update(parent=d["plan_file"], group="완성본", pages=len(d["cards"]), parts=[d["thumb_file"], d.get("cand_file")],
                        thumb=workflow.img_url("generate", d["folder"], d["cards"][0]["file"]), mode=workflow.MODE_KO.get(d["mode"], ""))
        elif t == "썸네일":
            item.update(parent=d.get("analysis_file"), group="묶임" if n in used_thumbs else "편집본",
                        thumb=workflow.img_url("generate", d["assets"], d["png"]))
        elif t == "이미지후보":
            top = (d.get("ranking") or [{}])[0].get("file") or (d["candidates"][0]["file"] if d.get("candidates") else "")
            item.update(parent=d.get("analysis_file"), group="묶임", count=len(d.get("candidates", [])),
                        thumb=workflow.img_url("generate", d["assets"], top) if top else "")
        generate.append(item)
    return {"crawl": crawl, "analysis": analysis, "generate": generate}


class DeleteReq(BaseModel):
    items: list[dict]


@app.post("/api/delete")
def delete(r: DeleteReq):
    return storage.move_to_trash(r.items)


# ---------------- 0단계 · 북케터밈 학습 ----------------

_learn_job: dict = {}


def _learn_start(label: str, factory):
    cur = get_job(_learn_job.get("id", ""))
    if cur and cur.status == "running":
        return {"job": cur.id, "already": True}
    job = start_job(label, factory, {"kind": "learn"})
    _learn_job["id"] = job.id
    return {"job": job.id}


@app.get("/api/learn")
def learn_overview():
    o = learn.overview()
    cur = get_job(_learn_job.get("id", ""))
    o["job"] = cur.id if cur and cur.status == "running" else None
    return o


@app.get("/api/learn/posts")
def learn_posts():
    return learn.list_posts()


@app.get("/api/learn/post/{code}")
def learn_post(code: str):
    try:
        return learn.post_detail(code)
    except FileNotFoundError:
        bad("게시물을 찾을 수 없습니다.", 404)


@app.get("/api/learn/img/{folder}/{name}")
def learn_img(folder: str, name: str):
    if "/" in folder or "\\" in folder or ".." in folder or not name.endswith(".jpg") or "/" in name or ".." in name:
        bad("잘못된 경로", 400)
    path = learn.IMG_DIR / folder / name
    if not path.exists():
        bad("이미지가 없습니다.", 404)
    return FileResponse(path)


class LearnRun(BaseModel):
    update: bool = False


@app.post("/api/learn/run")
def learn_run(r: LearnRun):
    label = "학습 업데이트" if r.update else "북케터밈 학습"
    return _learn_start(label, lambda job: learn.run_all(job, update=r.update))


@app.post("/api/learn/collect")
def learn_collect(r: LearnRun):
    return _learn_start("게시물 수집", lambda job: learn.collect(job, update=r.update))


class LearnAnalyze(BaseModel):
    codes: list[str] | None = None
    redo: bool = False


@app.post("/api/learn/analyze")
def learn_analyze(r: LearnAnalyze):
    return _learn_start("게시물 분석", lambda job: learn.analyze(job, codes=r.codes, redo=r.redo))


@app.post("/api/learn/guide")
def learn_guide():
    return _learn_start("스타일 가이드 만들기", learn.build_guide)


@app.get("/api/learn/guide/{name}")
def learn_guide_read(name: str):
    try:
        return {"name": name, "text": learn.read_guide(name), "applied": learn.applied_guide_name()}
    except FileNotFoundError:
        bad("가이드를 찾을 수 없습니다.", 404)


class GuideSave(BaseModel):
    base: str
    text: str


@app.post("/api/learn/guide/save")
def learn_guide_save(r: GuideSave):
    return learn.save_guide_edit(r.base, r.text)


class GuidePin(BaseModel):
    name: str | None = None


@app.post("/api/learn/guide/pin")
def learn_guide_pin(r: GuidePin):
    try:
        return learn.pin_guide(r.name)
    except FileNotFoundError:
        bad("가이드를 찾을 수 없습니다.", 404)


@app.get("/api/learn/books")
def learn_books():
    return learn.used_books()


class TokenReq(BaseModel):
    token: str


@app.get("/api/status")
async def status_all():
    return {"claude": await asyncio.to_thread(claude_ai.auth_status)}


# ---------------- 카드뉴스 작업 · 1단계 레퍼런스 ----------------

from . import work  # noqa: E402


def _work_or_404(wid: str) -> dict:
    try:
        return work.load(wid)
    except FileNotFoundError:
        bad("작업을 찾을 수 없습니다.", 404)


class NewWork(BaseModel):
    count: int | None = None  # 권수는 3단계에서 고른 책 수로 정한다


@app.post("/api/works")
def work_new(r: NewWork):
    try:
        return work.create(r.count)
    except ValueError as e:
        bad(str(e))


@app.get("/api/works")
def work_list():
    return work.list_works()


@app.get("/api/works/{wid}")
def work_get(wid: str):
    return _work_or_404(wid)


@app.get("/api/works/{wid}/file/{name}")
def work_file(wid: str, name: str):
    try:
        return {"name": name, "text": work.read_file(wid, name)}
    except FileNotFoundError:
        bad("파일을 찾을 수 없습니다.", 404)


@app.get("/api/works/{wid}/img/{sub}/{name}")
def work_img(wid: str, sub: str, name: str):
    for x in (sub, name):
        if "/" in x or "\\" in x or ".." in x:
            bad("잘못된 경로")
    try:
        p = work.path(wid) / sub / name
    except FileNotFoundError:
        bad("작업을 찾을 수 없습니다.", 404)
    if not p.exists():
        bad("이미지가 없습니다.", 404)
    return FileResponse(p)


class RefUrls(BaseModel):
    urls: list[str]


@app.post("/api/works/{wid}/refs/fetch")
def work_refs_fetch(wid: str, r: RefUrls):
    _work_or_404(wid)
    return {"job": start_job("레퍼런스 가져오기", lambda job: work.fetch_refs(job, wid, r.urls), {"kind": "refs"}).id}


class RefUpload(BaseModel):
    images: list[str] = []
    caption: str = ""
    thumb_copy: str = ""
    url: str = ""
    analyze: bool = True


@app.post("/api/works/{wid}/refs/upload")
def work_refs_upload(wid: str, r: RefUpload):
    _work_or_404(wid)
    if not r.images and not r.thumb_copy.strip():
        bad("이미지를 올리거나 카피를 직접 입력해 주세요.")
    ref = work.upload_ref(wid, r.images, r.caption, r.thumb_copy, r.url)
    if r.images and r.analyze:
        return {"ref": ref, "job": start_job("올린 이미지 읽기", lambda job: work.analyze_uploaded(job, wid, ref["no"]),
                                             {"kind": "refs"}).id}
    return {"ref": ref}


class RefEdits(BaseModel):
    refs: list[dict]


@app.post("/api/works/{wid}/refs/save")
def work_refs_save(wid: str, r: RefEdits):
    _work_or_404(wid)
    return work.update_refs(wid, r.refs)


@app.post("/api/works/{wid}/refs/confirm")
def work_refs_confirm(wid: str, r: RefEdits):
    _work_or_404(wid)
    work.update_refs(wid, r.refs)
    try:
        return work.confirm_refs(wid)
    except ValueError as e:
        bad(str(e))


# ---------------- 2단계 썸네일 카피 ----------------

class CopyGen(BaseModel):
    keep_ids: list[str] = []


@app.post("/api/works/{wid}/copies/gen")
def work_copies_gen(wid: str, r: CopyGen):
    _work_or_404(wid)
    return {"job": start_job("썸네일 카피 뽑기", lambda job: work.gen_copies(job, wid, r.keep_ids), {"kind": "copies"}).id}


class CopyItems(BaseModel):
    items: list[dict]


@app.post("/api/works/{wid}/copies/save")
def work_copies_save(wid: str, r: CopyItems):
    _work_or_404(wid)
    return work.save_copies(wid, r.items)


class CopyChosen(BaseModel):
    chosen: dict
    items: list[dict] = []


@app.post("/api/works/{wid}/copies/confirm")
def work_copies_confirm(wid: str, r: CopyChosen):
    _work_or_404(wid)
    if r.items:
        work.save_copies(wid, r.items)
    try:
        return work.confirm_copy(wid, r.chosen)
    except ValueError as e:
        bad(str(e))


# ---------------- 3단계 책 추천 ----------------

class BookGen(BaseModel):
    keep_keys: list[str] = []
    pilotic: bool = False


@app.post("/api/works/{wid}/books/gen")
def work_books_gen(wid: str, r: BookGen):
    _work_or_404(wid)
    return {"job": start_job("책 추천", lambda job: work.gen_books(job, wid, r.keep_keys, r.pilotic), {"kind": "books"}).id}


@app.get("/api/books/search")
def books_search(q: str):
    return work.search_books(q)


class BookAdd(BaseModel):
    item_id: str


@app.post("/api/works/{wid}/books/add")
def work_books_add(wid: str, r: BookAdd):
    _work_or_404(wid)
    return {"job": start_job("책 직접 추가", lambda job: work.add_book(job, wid, r.item_id), {"kind": "books"}).id}


class BookKeys(BaseModel):
    keys: list[str]


@app.post("/api/works/{wid}/books/select")
def work_books_select(wid: str, r: BookKeys):
    _work_or_404(wid)
    return work.select_books(wid, r.keys)


@app.post("/api/works/{wid}/books/confirm")
def work_books_confirm(wid: str, r: BookKeys):
    _work_or_404(wid)
    try:
        return work.confirm_books(wid, r.keys)
    except ValueError as e:
        bad(str(e))


# ---------------- 4단계 카드 완성 ----------------

@app.post("/api/works/{wid}/cards/build")
def work_cards_build(wid: str):
    _work_or_404(wid)
    return {"job": start_job("카드 완성(자동)", lambda job: work.build_cards(job, wid), {"kind": "cards"}).id}


class CardsSave(BaseModel):
    cards: dict


@app.post("/api/works/{wid}/cards/save")
def work_cards_save(wid: str, r: CardsSave):
    _work_or_404(wid)
    try:
        st = work.save_cards(wid, r.cards)
    except work.StaleCards:
        bad("다른 화면이나 자동 작업(사실 검증 등)이 먼저 카드를 바꿨어요. 최신 내용을 불러올게요.", 409)
    return {"ok": True, "updated": st["updated"], "rev": st["cards"]["rev"]}


class RewriteReq(BaseModel):
    key: str
    instruction: str = ""  # 사용자가 적은 '어떻게 고칠지'


@app.post("/api/works/{wid}/cards/rewrite")
def work_cards_rewrite(wid: str, r: RewriteReq):
    _work_or_404(wid)
    return {"job": start_job("설명글 다시 쓰기", lambda job: work.rewrite_book(job, wid, r.key, r.instruction), {"kind": "cards"}).id}


class MoreBg(BaseModel):
    keywords: list[str]


@app.post("/api/works/{wid}/cards/bg")
def work_cards_bg(wid: str, r: MoreBg):
    _work_or_404(wid)
    kws = [k.strip() for k in r.keywords if k.strip()][:5]
    if not kws:
        bad("검색어를 넣어 주세요.")
    return {"job": start_job("배경 더 찾기", lambda job: work.more_bg(job, wid, kws), {"kind": "cards"}).id}


class AssetUp(BaseModel):
    data: str
    kind: str = "bg"


@app.post("/api/works/{wid}/cards/upload")
def work_cards_upload(wid: str, r: AssetUp):
    _work_or_404(wid)
    return {"file": work.upload_asset(wid, r.data, r.kind)}


@app.post("/api/works/{wid}/cards/export")
def work_cards_export(wid: str, request: Request):
    _work_or_404(wid)
    port = (request.scope.get("server") or ("127.0.0.1", 8765))[1]
    base = f"http://127.0.0.1:{port}/"  # 공유 링크로 눌러도 내보내기는 이 PC 안에서 찍는다
    return {"job": start_job("PNG 내보내기", lambda job: work.export_cards(job, wid, base), {"kind": "cards"}).id}


@app.get("/render")
def render_page():
    return FileResponse(STATIC_DIR / "render.html")


@app.get("/api/brand/profile")
def brand_profile():
    return FileResponse(ASSETS_DIR / "profile.jpg")


class IdsReq(BaseModel):
    ids: list[str]


@app.post("/api/works/delete")
def works_delete(r: IdsReq):
    return work.delete_works(r.ids)


@app.get("/api/trash")
def trash_list():
    return work.list_trash()


class IdReq(BaseModel):
    id: str


@app.post("/api/trash/restore")
def trash_restore(r: IdReq):
    try:
        return {"id": work.restore_work(r.id)}
    except FileNotFoundError:
        bad("휴지통에서 찾을 수 없습니다.", 404)


@app.post("/api/works/{wid}/duplicate")
def work_duplicate(wid: str):
    _work_or_404(wid)
    return {"id": work.duplicate_work(wid)}


@app.get("/api/works/{wid}/zip")
def work_zip(wid: str):
    _work_or_404(wid)
    try:
        name, data = work.export_zip(wid)
    except FileNotFoundError as e:
        bad(str(e), 404)
    from urllib.parse import quote
    return StreamingResponse(io.BytesIO(data), media_type="application/zip",
                             headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


@app.post("/api/works/{wid}/open-folder")
def work_open_folder(wid: str, request: Request):
    """이 PC 에서만: 탐색기로 작업 폴더 열기."""
    if share.is_remote(request.headers):
        bad("이 기능은 프로그램이 켜진 PC 에서만 쓸 수 있어요.", 403)
    _work_or_404(wid)
    import os
    os.startfile(str(work.path(wid)))  # noqa: S606 - 사용자가 누른 버튼, 자기 PC 폴더
    return {"ok": True}


@app.post("/api/works/{wid}/cards/factcheck")
def work_cards_factcheck(wid: str):
    _work_or_404(wid)
    return {"job": start_job("사실 검증", lambda job: work.factcheck(job, wid), {"kind": "cards"}).id}
