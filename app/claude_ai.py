"""Claude Agent SDK로 기획(후보 3개 + 피드백 라운드)과 이미지 순위 매기기를 한다.

API 키를 쓰지 않고, 이 PC에서 `claude auth login`으로 로그인한 구독 계정(OAuth)으로 동작한다.
지침: brand_guide.md(말투·디자인) + prompts/<형식>.md(카피 공식) — 둘 다 고치면 다음 기획부터 반영된다.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKError,
    ResultMessage,
    ToolUseBlock,
    query,
)

from . import formats
from .config import BRAND_GUIDE_FILE, DATA_DIR, MODEL, PROMPTS_DIR

BODY_TEMPLATES = ["paper_title", "photo_box", "paper_box"]


def cli_path() -> str:
    custom = os.environ.get("CLAUDE_CLI_PATH")
    if custom:
        return custom
    import claude_agent_sdk
    exe = "claude.exe" if sys.platform == "win32" else "claude"
    return str(Path(claude_agent_sdk.__file__).parent / "_bundled" / exe)


def _subscription_env() -> dict:
    # API 키가 환경변수에 있으면 종량제로 과금되므로 비워서 구독 로그인만 쓰게 한다.
    return {"ANTHROPIC_API_KEY": ""}


def auth_status() -> dict:
    try:
        out = subprocess.run([cli_path(), "auth", "status"], capture_output=True, text=True, encoding="utf-8",
                             timeout=30, env={**os.environ, **_subscription_env()})
        data = json.loads(out.stdout or "{}")
        return {"logged_in": bool(data.get("loggedIn")), "email": data.get("email")}
    except Exception as e:  # noqa: BLE001
        return {"logged_in": False, "error": str(e)}


_login: dict = {}


def start_login() -> dict:
    """구독 로그인을 화면 안에서 끝낸다: 로그인 링크를 돌려주고(브라우저도 연다), 받은 코드는 submit_login 으로 넣는다.
    (예전 방식은 검은 콘솔 창에 코드를 붙여 넣어야 해서, 창이 뒤에 숨거나 바로 닫히면 진행이 막혔다.)"""
    import re
    import threading
    import webbrowser
    old = _login.get("proc")
    if old and old.poll() is None:
        old.kill()
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen([cli_path(), "auth", "login", "--claudeai"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            env={**os.environ, **_subscription_env()}, creationflags=flags)
    _login.clear()
    _login.update(proc=proc, out=[], url=None)
    got = threading.Event()

    def reader():
        for line in proc.stdout:
            _login["out"].append(line.rstrip())
            m = re.search(r"https://\S+oauth\S+", line)
            if m and not _login["url"]:
                _login["url"] = m.group(0)
                got.set()
        got.set()

    threading.Thread(target=reader, daemon=True).start()
    got.wait(30)
    if not _login.get("url"):
        raise RuntimeError("로그인 링크를 받지 못했습니다: " + " / ".join(_login["out"][-3:]))
    try:
        webbrowser.open(_login["url"])
    except Exception:  # noqa: BLE001
        pass
    return {"url": _login["url"]}


def submit_login(code: str) -> dict:
    proc = _login.get("proc")
    if not proc or proc.poll() is not None:
        raise RuntimeError("로그인을 다시 시작해 주세요([Claude 로그인] 버튼).")
    proc.stdin.write(code.strip() + "\n")
    proc.stdin.flush()
    try:
        proc.wait(60)
    except subprocess.TimeoutExpired:
        proc.kill()
    st = auth_status()
    if not st.get("logged_in"):
        raise RuntimeError("로그인되지 않았습니다. 코드를 처음부터 끝까지 복사했는지 확인하고 다시 해 주세요. "
                           + " / ".join(_login.get("out", [])[-2:]))
    return st


def open_login_window() -> None:
    start_login()


def guide(mode: str) -> str:
    parts = []
    if BRAND_GUIDE_FILE.exists():
        parts.append("[북케터 밈 브랜드 가이드]\n" + BRAND_GUIDE_FILE.read_text(encoding="utf-8"))
    p = PROMPTS_DIR / f"{mode}.md"
    if p.exists():
        parts.append(f"[{formats.get(mode)['name']} 카드뉴스 지침]\n" + p.read_text(encoding="utf-8"))
    if formats.kind(mode) == "books":
        parts.append(book_rules())
        parts.append(book_examples())
    return "\n\n".join(parts)


def book_examples() -> str:
    p = PROMPTS_DIR / "book_copy_examples.md"
    return "[북케터 밈 책 소개 카피 예시집 — 실제 게시물·확정 문안. 이 문장 구조와 말투를 그대로 따른다]\n" + \
        p.read_text(encoding="utf-8") if p.exists() else ""


def book_rules() -> str:
    p = PROMPTS_DIR / "book_rules.md"
    return "[책 추천 카피 규칙 — 실제 작업에서 정리]\n" + p.read_text(encoding="utf-8") if p.exists() else ""


async def run_structured(prompt: str, system: str, schema: dict, job, max_turns: int = 40, effort: str = "high",
                         tools: list[str] | None = None, cwd: Path | None = None, quiet: bool = False) -> dict:
    tools = tools or ["Read"]
    options = ClaudeAgentOptions(
        system_prompt=system, model=MODEL, tools=tools, allowed_tools=tools, cwd=str(cwd or DATA_DIR),
        max_turns=max_turns, setting_sources=[], output_format={"type": "json_schema", "schema": schema},
        env=_subscription_env(), effort=effort,
    )
    result = None
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if not quiet and isinstance(block, ToolUseBlock) and isinstance(block.input, dict):
                        q = block.input.get("query") or block.input.get("url") or Path(block.input.get("file_path", "")).name
                        job.log(f"  AI {'웹 검색' if block.name == 'WebSearch' else '웹 확인' if block.name == 'WebFetch' else '보는 중'}: {q or block.name}")
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    raise ClaudeSDKError(msg.result or msg.subtype)
                result = msg.structured_output
                if result is None and msg.result:
                    try:
                        result = json.loads(msg.result.strip().split("```json")[-1].split("```")[0])
                    except (json.JSONDecodeError, IndexError):
                        result = None
    except ClaudeSDKError as e:
        if "Not logged in" in str(e) or "/login" in str(e):
            raise RuntimeError("Claude 로그인이 필요합니다. 1번 칸의 [Claude 로그인 창 열기]를 눌러 구독 계정으로 로그인하세요.") from e
        raise
    if not isinstance(result, dict):
        raise RuntimeError("AI 응답을 읽지 못했습니다. 다시 시도해 주세요.")
    return result


# ---------------- 기획 ----------------

SLIDE = {
    "type": "object", "additionalProperties": False,
    "required": ["template", "label", "headline", "body", "bullets"],
    "properties": {
        "template": {"type": "string", "enum": BODY_TEMPLATES},
        "label": {"type": "string", "description": "작은 눈썹 문구 또는 박스 제목"},
        "headline": {"type": "string", "description": "paper_title 의 큰 문구. 줄바꿈 \\n, 강조 [[ ]]"},
        "body": {"type": "string", "description": "본문. 줄바꿈 \\n, 강조 **굵게** __물결 밑줄__ [[형광]]"},
        "bullets": {"type": "array", "items": {"type": "string"}},
    },
}

CANDIDATE = {
    "type": "object", "additionalProperties": False,
    "required": ["copy", "label", "callouts", "angle", "pattern", "share", "from_ref", "image", "pins",
                 "keep_image_from", "slides", "cta", "caption", "comment"],
    "properties": {
        "copy": {"type": "string", "description": "썸네일 헤드라인 2~3줄(\\n). 가장 센 단어 하나를 [[ ]]로 연두 강조"},
        "label": {"type": "string", "description": "헤드라인 위 연두 라벨 슬로건(20자 이내, 없으면 빈 문자열)"},
        "callouts": {"type": "array", "items": {"type": "string"}, "description": "사진 위 흰 말풍선 0~2개(각 14자 이내)"},
        "angle": {"type": "string", "description": "이 후보의 기획 각도 한 문장"},
        "pattern": {"type": "string", "description": "훅 공식 이름 · [빈칸 템플릿]"},
        "share": {"type": "string", "description": "보는 사람이 저장·공유·태그할 명분"},
        "from_ref": {"type": "string", "description": "레퍼런스(캡션·댓글 반응)에서 가져온 구조"},
        "image": {"type": "string", "description": "썸네일 배경 사진 가이드(장면·표정·구도·글자 넣을 빈 공간)"},
        "pins": {"type": "array", "items": {"type": "string"}, "description": "핀터레스트 검색어 3개"},
        "keep_image_from": {"type": "integer", "description": "피드백 라운드에서 이전 후보 이미지를 그대로 쓸 때 그 후보 번호(1~3), 아니면 0"},
        "slides": {"type": "array", "items": SLIDE, "description": "본문 장(롱폼만, 단일이면 빈 배열)"},
        "cta": {"type": "object", "additionalProperties": False, "required": ["headline", "body"],
                "properties": {"headline": {"type": "string"}, "body": {"type": "string"}},
                "description": "마지막 장(어두운 사진 + 흰 글자). 팔로우·댓글·저장 유도"},
        "caption": {"type": "string"},
        "comment": {"type": "string", "description": "고정댓글"},
    },
}

BOOK = {
    "type": "object", "additionalProperties": False, "required": ["title", "author", "tags", "lines"],
    "properties": {
        "title": {"type": "string", "description": "책 제목(사용자가 준 그대로, 없으면 서점 표기 그대로)"},
        "author": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "카드 흰 박스 해시태그 2~3개(# 포함): 장르 + 결 + 화제성"},
        "lines": {"type": "array", "items": {"type": "string"},
                  "description": "책 장 소개 3~5줄. 예시집의 실제 카드처럼 설정 → 근데 → 여운 구조, 줄당 30자 이하, "
                                 "'~요' 말하듯한 문체. 훅 1~2줄(또는 그 일부)만 [[ ]]로 연두 강조. 사용자가 메모를 안 줘도 "
                                 "웹 검색으로 확인한 줄거리·설정으로 직접 쓴다"},
    },
}

KEYWORD = {
    "type": "object", "additionalProperties": False, "required": ["title", "en", "line1", "line2", "image_query"],
    "properties": {
        "title": {"type": "string", "description": "키워드(짧게)"},
        "en": {"type": "string", "description": "작은 영문 부제"},
        "line1": {"type": "string", "description": "설명 1줄(흰색): 현상·문제, 22자 안팎"},
        "line2": {"type": "string", "description": "설명 2줄(연두): 한 줄 정의·해법, 22자 안팎"},
        "image_query": {"type": "string", "description": "이 키워드에 어울리는 배경 사진 핀터레스트 검색어"},
    },
}

CONTENT = {
    "books": {
        "type": "object", "additionalProperties": False, "required": ["books", "cta"],
        "properties": {
            "books": {"type": "array", "items": BOOK},
            "cta": {"type": "object", "additionalProperties": False, "required": ["headline", "body"],
                    "properties": {"headline": {"type": "string"}, "body": {"type": "string"}}},
        },
    },
    "summary": {
        "type": "object", "additionalProperties": False,
        "required": ["book_title", "subtitle", "index_footer", "keywords", "check", "cta"],
        "properties": {
            "book_title": {"type": "string"},
            "subtitle": {"type": "string", "description": "목차 장 작은 부제(슬로건·원제·한 줄 정의)"},
            "index_footer": {"type": "string", "description": "목차 장 연두 안내 (예: 키워드 뜻 빠른 요약 보기! →)"},
            "keywords": {"type": "array", "items": KEYWORD},
            "check": {"type": "object", "additionalProperties": False, "required": ["title", "subtitle", "items", "footer"],
                      "properties": {"title": {"type": "string"}, "subtitle": {"type": "string"},
                                     "items": {"type": "array", "items": {"type": "string"}}, "footer": {"type": "string"}}},
            "cta": {"type": "object", "additionalProperties": False, "required": ["headline", "body"],
                    "properties": {"headline": {"type": "string"}, "body": {"type": "string"}}},
        },
    },
}

FORMAT_CANDIDATE_KEYS = ["copy", "angle", "pattern", "share", "from_ref", "image", "pins", "keep_image_from",
                         "content", "caption", "comment"]


def plan_schema(mode: str) -> dict:
    k = formats.kind(mode)
    if k == "free":
        cand = CANDIDATE
    else:
        props = {key: CANDIDATE["properties"][key] for key in FORMAT_CANDIDATE_KEYS if key in CANDIDATE["properties"]}
        props["copy"] = {"type": "string", "description": "표지 헤드라인 2줄(\\n). {{빨강}} [[연두]] 강조 가능"}
        props["content"] = CONTENT[k]
        cand = {"type": "object", "additionalProperties": False, "required": FORMAT_CANDIDATE_KEYS, "properties": props}
    return {
        "type": "object", "additionalProperties": False, "required": ["summary", "candidates"],
        "properties": {
            "summary": {"type": "string", "description": "첫 라운드: 레퍼런스·형식에서 가져온 핵심 / 다음 라운드: 바꾼 점"},
            "candidates": {"type": "array", "items": cand, "minItems": 3, "maxItems": 3},
        },
    }


def _system(mode: str) -> str:
    f = formats.get(mode)
    if f["kind"] == "free":
        shape = "단일 = 썸네일 + 마지막 장 (slides 는 빈 배열)" if mode == "single" else "롱폼 = 썸네일 + 본문 4~7장 + 마지막 장"
        extra = "- 강조 표기: [[단어]] 연두/형광 강조, **굵게**, __빨간 물결 밑줄__. 한 장에 1~2곳만 쓴다."
    elif f["kind"] == "books":
        shape = f"책추천 {f['count']}권 = 표지 + 책 {f['count']}장 + 팔로우 장. content.books 는 정확히 {f['count']}권"
        extra = ("- 책은 사용자가 준 목록에서 고른다. 목록이 더 많으면 주제에 가장 맞는 순서로 고르고, 모자라면 있는 만큼만 쓴다.\n"
                 "  목록이 비어 있으면 주제·썸네일 카피에 맞는, 지금 살 수 있는 유명한 책을 웹 검색으로 확인해 고른다.\n"
                 "- 책 소개(카드 lines·캡션 항목)는 사용자가 따로 쓰지 않는다. 너가 책마다 WebSearch 로 교보문고·예스24·알라딘 "
                 "책소개와 줄거리를 확인하고, 아래 '책 소개 카피 예시집'의 실제 게시물과 같은 문장 구조·길이·말투로 직접 쓴다.\n"
                 "  메모가 있으면 그 내용을 우선 살린다. 확인 안 된 디테일(이름·숫자·관계·인용)은 쓰지 않는다.\n"
                 "- 캡션의 책 항목은 카드 문안을 2~3줄로 줄인 것(예시집 2장). 캡션에는 해시태그를 넣지 않는다.\n"
                 "- 후보 3개는 표지 훅·책 순서·소개 각도를 다르게 한다. 강조 표기: {{빨강}} [[연두]]")
    else:
        shape = "30초 요약 = 표지 + 목차 + 키워드 장(2개씩) + 셀프체크 + 팔로우 장"
        extra = ("- 키워드 개수는 사용자가 정한 만큼(짝수 권장). 책에 있는 내용만 쓴다.\n"
                 "- 후보 3개는 표지 훅·목차 부제·셀프체크 문항을 다르게 한다. 키워드 자체는 책 기준으로 같아도 된다.")
    return f"""너는 출판 마케팅 인스타 계정 '북케터 밈'(@bookketer_mim)의 카드뉴스 기획자다.
정해진 북케터 밈 형식과 잘 된 레퍼런스의 훅 구조를 바탕으로, 사용자가 알리고 싶은 내용을 북케터 밈 말투로 기획한다.

원칙:
- 레퍼런스 슬라이드 이미지가 주어지면 Read 도구로 열어 실제 문구·구성을 확인한다. 추측하지 않는다.
- 사용자가 준 사실(숫자·날짜·장소·이름·후기·책 정보), 널리 알려진 사실, 웹 검색으로 확인한 사실만 쓴다. 지어내지 않는다.
- 후보 3개는 서로 다른 훅·감정·각도로 만든다.
- 표지 카피는 2줄, 줄당 14자 안팎이다.
- 형식: {shape}
{extra}
- 모든 답은 한국어로 한다. 핀터레스트 검색어만 한국어와 영어를 섞어도 된다.

{guide(mode)}"""


def _ref_block(refs: list[dict], assets_rel: str) -> str:
    if not refs:
        return "(고른 레퍼런스 없음 — 위 형식 지침의 기준 게시물 구조를 따른다)"
    out = []
    for r in refs:
        lines = [f"### 레퍼런스 #{r['n']} — @{r.get('author', '')} · {r.get('type', '')} {r.get('slides', '')}장 · "
                 f"좋아요 {r.get('likes') or 0:,} · 댓글 {r.get('comments') or 0:,} · {r.get('date', '')}",
                 "캡션:", (r.get("caption") or "(없음)")[:1500]]
        if r.get("top_comments"):
            lines += ["상위 댓글:"] + [f"- {c}" for c in r["top_comments"][:12]]
        if r.get("slides_text"):
            lines += ["슬라이드 문구:"] + [f"{i + 1}. {t}" for i, t in enumerate(r["slides_text"])]
        if r.get("images"):
            lines += ["슬라이드 이미지(Read 로 모두 열어볼 것):"] + \
                     [str((DATA_DIR / assets_rel / f).resolve()) for f in r["images"][:10]]
        out.append("\n".join(lines))
    return "\n\n".join(out)


def _project_block(p: dict, mode: str) -> str:
    out = (f"- 주제: {p.get('name', '')}\n- 핵심 메시지: {p.get('message', '')}\n"
           f"- 사실 정보·메모:\n{p.get('details', '')}\n- 원하는 행동(CTA): {p.get('cta', '')}\n"
           f"- 캡션 끝에 붙일 고정 문구: {p.get('proof', '') or '(없음)'}")
    k = formats.kind(mode)
    if p.get("thumb"):
        out += f"\n- 정해 둔 썸네일 카피: {p['thumb']} (후보 1은 이 카피를 그대로 표지에 쓰고, 후보 2·3은 같은 공식의 변형. ' / '는 표지 줄바꿈)"
        if p.get("thumb_alts"):
            out += "\n- 후보 2·3 표지에 쓸 베리에이션(레퍼런스에서 뽑음): " + " | ".join(p["thumb_alts"])
    if k == "books":
        style = {"auto": "자동(예시집 3장 기준: 소설은 줄거리 훅형, 심리·인문·자기계발은 공감 훅 + 캡션 개인 감상형)",
                 "story": "줄거리 훅형(설정 → 근데 → 드러나요)", "personal": "개인 감상형(~하던 시기에 읽었는데)",
                 "persona": "성격 진단형(이 책을 좋아하는 당신은 ~한 사람입니다)", "prescribe": "처방 순서형(→ 너 일단 이거부터 읽어)"}
        out += f"\n- 책 소개 카피 스타일: {style.get(p.get('copy_style') or 'auto', style['auto'])}"
        out += (f"\n- 추천할 책 목록(한 줄에 한 권: 제목 / 저자 / 메모 — 메모에 적힌 확인된 정보를 우선 사용):\n"
                f"{p.get('books', '') or '(없음 — 주제에 맞는 널리 알려진 책으로)'}")
    if k == "summary":
        out += (f"\n- 요약할 책: {p.get('book_title', '')} / {p.get('book_author', '')}"
                f"\n- 요약 유형: {'자기계발 핵심 요약' if p.get('summary_type') == 'selfhelp' else '키워드 요약'}"
                f"\n- 키워드 개수: {p.get('kw_count') or 10}")
    return out


def _plan_opts(mode: str) -> dict:
    """책추천 형식은 책 소개를 직접 쓰려고 웹 검색으로 줄거리를 확인한다."""
    if formats.kind(mode) == "books":
        return {"tools": ["WebSearch", "WebFetch", "Read"], "max_turns": 80}
    return {}


async def plan_first(refs: list[dict], assets_rel: str, project: dict, mode: str, job) -> dict:
    prompt = f"""아래 내용으로 북케터 밈 '{formats.get(mode)['name']}' 카드뉴스 후보 3개를 기획해줘.

[알리고 싶은 내용]
{_project_block(project, mode)}

[레퍼런스]
{_ref_block(refs, assets_rel)}
"""
    return await run_structured(prompt, _system(mode), plan_schema(mode), job, **_plan_opts(mode))


async def plan_again(refs: list[dict], assets_rel: str, project: dict, mode: str, prev: dict,
                     feedback: str, target: int, job) -> dict:
    strip = lambda c: {k: v for k, v in c.items() if k not in ("img",)}  # noqa: E731
    base = [strip(c) for c in prev["candidates"]]
    focus = f"후보 {target}을 기준으로 고쳐서" if target else "후보 3개 전체를 보고"
    prompt = f"""지난 라운드 후보에 대한 피드백을 반영해 {focus} 새 후보 3개를 만들어줘.
이미지를 그대로 두라는 요청이면 keep_image_from 에 그 후보 번호를 넣어.

[피드백]
{feedback}

[지난 라운드 후보]
{json.dumps(base, ensure_ascii=False, indent=2)}

[알리고 싶은 내용]
{_project_block(project, mode)}

[레퍼런스 요약]
{_ref_block([{**r, 'images': []} for r in refs], assets_rel)}
"""
    return await run_structured(prompt, _system(mode), plan_schema(mode), job, **_plan_opts(mode))


# ---------------- 이미지 ----------------

RANK_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["ranking"],
    "properties": {"ranking": {"type": "array", "maxItems": 4, "items": {
        "type": "object", "additionalProperties": False,
        "required": ["file", "score", "reason", "front", "emotion", "space"],
        "properties": {
            "file": {"type": "string"}, "score": {"type": "number", "description": "10점 만점"},
            "reason": {"type": "string"}, "front": {"type": "string", "description": "인물 정면 여부/구도"},
            "emotion": {"type": "string", "description": "감정·분위기 강도"},
            "space": {"type": "string", "description": "아래쪽 글자 넣을 여백"},
        }}}},
}


async def rank_images(copy: str, image_guide: str, folder: Path, files: list[str], job) -> list[dict]:
    if not files:
        return []
    paths = "\n".join(str((folder / f).resolve()) for f in files)
    prompt = f"""카드뉴스 썸네일 배경 후보 이미지를 Read 로 모두 열어보고 가장 어울리는 것 최대 4장을 골라 점수를 매겨줘.
썸네일 카피: {copy}
이미지 가이드: {image_guide}
기준: 카피의 감정과 맞는가, 인물이면 정면·표정이 강한가, 세로(4:5)로 잘라도 괜찮은가, 아래쪽에 글자를 얹을 여백이 있는가, 해상도.
file 에는 파일 이름만 쓴다.

{paths}"""
    r = await run_structured(prompt, "너는 인스타 카드뉴스 아트디렉터다. 답은 한국어로.", RANK_SCHEMA, job, effort="medium")
    valid = set(files)
    return [x for x in r["ranking"] if x["file"] in valid]


QUERY_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["queries"],
                "properties": {"queries": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3}}}


async def image_queries(copy: str, image_guide: str, direction: str, job) -> list[str]:
    prompt = f"""썸네일 카피 "{copy}" 의 배경 사진을 핀터레스트에서 찾으려 한다.
기존 이미지 가이드: {image_guide}
사용자가 원하는 방향: {direction}
이 방향에 맞는 핀터레스트 검색어 3개를 만들어줘(구체적인 장면·표정·분위기 단어)."""
    r = await run_structured(prompt, "너는 이미지 리서처다.", QUERY_SCHEMA, job, max_turns=3, effort="low")
    return r["queries"]


# ---------------- 책 찾기 · 썸네일 카피 베리에이션 · 팩트체크 ----------------

WEB = ["WebSearch", "WebFetch", "Read"]

FIND_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "books"],
    "properties": {
        "summary": {"type": "string", "description": "어떤 기준으로 골랐는지 2~3줄"},
        "books": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title", "author", "translator", "why", "hook", "tags", "tone"],
            "properties": {
                "title": {"type": "string", "description": "정확한 국내 출간 제목"},
                "author": {"type": "string"},
                "translator": {"type": "string", "description": "번역서면 옮긴이, 아니면 빈 문자열"},
                "why": {"type": "string", "description": "이 주제·썸네일 카피에 맞는 이유(표본·공감·화제성)"},
                "hook": {"type": "string", "description": "카드에 쓸 줄거리 훅 한두 줄(확인된 사실만)"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "#키워드 3개"},
                "tone": {"type": "string", "description": "결: 예) 반전스릴러 / 따뜻한 후유증 / 위로 / 지적충격"},
            }}},
    },
}


async def find_books(topic: str, count: int, prefs: str, exclude: list[str], job) -> dict:
    """주제·썸네일 카피에 맞는 책 후보를 웹에서 찾는다(사실 확인된 실존 도서만)."""
    want = max(count * 2, count + 3)
    prompt = f"""북케터 밈 카드뉴스 '{topic}' 에 넣을 책 후보 {want}권을 찾아줘. 최종 카드에는 {count}권이 들어간다.
조건: {prefs or '모두가 알 만한 베스트셀러·스테디셀러 위주, 지금 살 수 있는 책'}
{('이미 고른 책(빼고 찾기): ' + ', '.join(exclude)) if exclude else ''}

반드시 WebSearch 로 교보문고·예스24·알라딘 같은 서점 정보를 찾아 제목·저자·줄거리를 확인한 책만 넣어.
확인 안 되는 책, AI 생성 Q&A 사이트에만 나오는 책, 절판된 책은 넣지 마.
hook 은 확인된 줄거리로만 쓰고 지어낸 디테일(숫자·관계·지명)을 넣지 마."""
    return await run_structured(prompt, "너는 출판 마케터의 도서 리서처다. 정확성이 최우선이다. hook 은 예시집 카드 첫 두 줄처럼 쓴다. "
                                "답은 한국어로.\n\n" + book_rules() + "\n\n" + book_examples(),
                                FIND_SCHEMA, job, tools=WEB, max_turns=60)


VAR_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["original", "formula", "variations", "recommend"],
    "properties": {
        "original": {"type": "string", "description": "레퍼런스 표지(1장)에 실제로 적힌 썸네일 카피"},
        "formula": {"type": "string", "description": "왜 터졌는지 공식: 자극 단어 · 권위/숫자 · 정체성/상황"},
        "variations": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["copy", "why"],
            "properties": {"copy": {"type": "string", "description": "표지 카피 2줄(\n)"}, "why": {"type": "string"}}}},
        "recommend": {"type": "integer", "description": "가장 추천하는 베리에이션 번호(1부터)"},
    },
}


async def copy_variations(ref: dict, assets_rel: str, topic: str, mode: str, job) -> dict:
    imgs = [str((DATA_DIR / assets_rel / f).resolve()) for f in (ref.get("images") or [])[:1]]
    prompt = f"""레퍼런스 카드뉴스의 썸네일 카피를 분석하고, 북케터 밈용 베리에이션 8개를 만들어줘.
- 레퍼런스: @{ref.get('author', '')} · 좋아요 {ref.get('likes') or 0:,} · 캡션: {(ref.get('caption') or '')[:600]}
- 표지 이미지(Read 로 열어 실제 카피를 읽을 것): {imgs[0] if imgs else '(없음 — 캡션 첫 줄로 추정)'}
- 우리 주제(있으면 맞춰서): {topic or '(없음 — 레퍼런스와 같은 소재의 책 추천으로)'}
- 형식: {formats.get(mode)['name']}
규칙: 레퍼런스를 베끼지 말고 공식(구조)만 가져온다. 숫자·상황·대상을 바꿔 표본을 넓힌다. 0.5초 안에 읽히게.
몇 개는 세미콜론(;) 반전형, 몇 개는 질문형/호명형으로 섞어."""
    return await run_structured(prompt, "너는 인스타 카드뉴스 썸네일 카피라이터다. 답은 한국어로.\n\n" + book_rules(),
                                VAR_SCHEMA, job, max_turns=8, effort="medium")


CHECK_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["books", "summary"],
    "properties": {
        "summary": {"type": "string"},
        "books": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["title", "status", "issues", "fixed_title", "fixed_author", "fixed_lines"],
            "properties": {
                "title": {"type": "string"},
                "status": {"type": "string", "enum": ["정확", "수정", "확인 필요"]},
                "issues": {"type": "array", "items": {"type": "string"}, "description": "틀린 점·근거"},
                "fixed_title": {"type": "string"}, "fixed_author": {"type": "string"},
                "fixed_lines": {"type": "array", "items": {"type": "string"}, "description": "고친 소개 줄(틀린 게 없으면 원래 줄 그대로)"},
            }}},
    },
}


async def fact_check(books: list[dict], job) -> dict:
    prompt = f"""아래 책 소개 카피를 WebSearch 로 하나씩 사실 확인해줘. 절대 틀린 내용이 있으면 안 된다.
확인할 것: 제목·저자(옮긴이) 정확한지, 줄거리 설정·숫자·인물 관계가 맞는지, 큰따옴표 인용이 원문 그대로인지, 과장된 단정(매번·전부)이 없는지.
틀린 부분은 고치되 문체(근데 구조·~예요·더라구요)와 줄 수는 유지해. 확인이 안 되는 디테일은 빼거나 풀어서 써.

{json.dumps(books, ensure_ascii=False, indent=2)}"""
    return await run_structured(prompt, "너는 출판사 교정·팩트체크 담당이다. 근거 없이 '정확'이라고 하지 않는다. 답은 한국어로.\n\n" + book_rules(),
                                CHECK_SCHEMA, job, tools=WEB, max_turns=60)
