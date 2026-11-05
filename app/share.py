"""팀원과 함께 쓰는 공유 링크 (Cloudflare 빠른 터널 + 공유 비밀번호) — 북타쿠 스튜디오와 같은 방식.

- 이 PC 에서만 켜고 끈다. 공유 링크로 들어온 사람은 비밀번호를 넣어야 들어올 수 있다.
- 공유 링크로 들어온 사람은 이 PC 에 창을 띄우는 기능(인스타·Claude 로그인, 바탕화면 폴더 열기)과 공유 설정을 쓸 수 없다.
- 고정 주소: ngrok 무료 고정 도메인(https://<이름>.ngrok-free.app)을 정해 두면 그 주소로 연다(프로그램을 켜면 자동으로 공유도 켜짐).
  ngrok 인증 토큰은 ngrok 자체 설정(ngrok.yml)에만 저장하고 이 프로그램 파일에는 남기지 않는다.
- 고정 주소가 없으면 임시 주소 https://<무작위>.trycloudflare.com (다시 켜면 바뀜).
"""
import hashlib
import hmac
import re
import secrets
import subprocess
import sys
import threading
import time

from . import storage
from .config import ROOT

TOOL = ROOT / "tools" / "cloudflared.exe"
NGROK = ROOT / "tools" / "ngrok.exe"
COOKIE = "bk_share"
_state = {"proc": None, "url": "", "since": "", "error": ""}
_lock = threading.Lock()
_fails: dict[str, list[float]] = {}


def _settings() -> dict:
    return storage.load_settings()


def has_password() -> bool:
    return bool(_settings().get("share_hash"))


def set_password(pw: str) -> None:
    s = _settings()
    salt = secrets.token_hex(8)
    s["share_salt"] = salt
    s["share_hash"] = hashlib.sha256((salt + pw).encode()).hexdigest()
    s["share_secret"] = secrets.token_hex(16)  # 비밀번호를 바꾸면 기존 접속도 다시 로그인해야 한다
    storage.save_settings(s)


def check_password(pw: str, ip: str) -> bool:
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 300]
    if len(recent) >= 8:
        raise PermissionError("비밀번호를 너무 여러 번 틀렸습니다. 5분 뒤에 다시 시도해 주세요.")
    s = _settings()
    ok = bool(s.get("share_hash")) and hmac.compare_digest(
        hashlib.sha256((s.get("share_salt", "") + pw).encode()).hexdigest(), s["share_hash"])
    if not ok:
        _fails[ip] = recent + [now]
    return ok


def token() -> str:
    s = _settings()
    return hmac.new(s.get("share_secret", "x").encode(), b"bookketer-share", hashlib.sha256).hexdigest()


def valid_cookie(value: str | None) -> bool:
    return bool(value) and has_password() and hmac.compare_digest(value, token())


def is_remote(headers) -> bool:
    """공유 링크(Cloudflare·ngrok 터널)를 거쳐 들어온 요청인지. 이 PC 에서 직접 연 화면만 아니라고 본다."""
    if "cf-connecting-ip" in headers or "cf-ray" in headers or "x-forwarded-for" in headers:
        return True
    host = (headers.get("host") or "").split(":")[0].lower()
    return host not in ("127.0.0.1", "localhost", "")


def ngrok_domain() -> str:
    return _settings().get("ngrok_domain", "")


def fixed_ready() -> bool:
    return bool(ngrok_domain()) and NGROK.exists()


def set_ngrok(token: str, domain: str) -> dict:
    """ngrok 인증 토큰은 ngrok 설정에만 넣고, 고정 도메인 이름만 이 프로그램 설정에 남긴다."""
    if not NGROK.exists():
        raise RuntimeError("ngrok 프로그램(tools/ngrok.exe)이 아직 없습니다.")
    domain = re.sub(r"^https?://", "", (domain or "").strip()).strip("/")
    if domain and not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", domain):
        raise RuntimeError("고정 도메인은 ngrok 화면에 나온 그대로(예: abc-def.ngrok-free.app) 넣어 주세요.")
    if token.strip():
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        r = subprocess.run([str(NGROK), "config", "add-authtoken", token.strip()], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30, creationflags=flags)
        if r.returncode != 0:
            raise RuntimeError("ngrok 토큰을 저장하지 못했습니다: " + (r.stderr or r.stdout)[-200:])
    s = _settings()
    if domain:
        s["ngrok_domain"] = domain
    storage.save_settings(s)
    return status()


def status() -> dict:
    p = _state["proc"]
    on = bool(p and p.poll() is None)
    if not on and p is not None and not _state["error"]:
        _state["error"] = "공유 프로그램이 멈췄습니다. 다시 켜 주세요."
    return {"on": on, "url": _state["url"] if on else "", "since": _state["since"], "error": "" if on else _state["error"],
            "has_password": has_password(), "tool": TOOL.exists(), "fixed": ngrok_domain(), "ngrok": NGROK.exists()}


def start(port: int = 8765) -> dict:
    with _lock:
        if not TOOL.exists():
            raise RuntimeError("공유 도구(tools/cloudflared.exe)가 없습니다.")
        if not has_password():
            raise RuntimeError("공유 비밀번호부터 정해 주세요.")
        p = _state["proc"]
        if p and p.poll() is None:
            return status()
        _state.update(url="", error="", since="")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        fixed = ngrok_domain() if fixed_ready() else ""
        if fixed:  # 고정 주소(ngrok)
            cmd = [str(NGROK), "http", "--url", f"https://{fixed}", f"127.0.0.1:{port}", "--log", "stdout", "--log-format", "logfmt"]
        else:  # 임시 주소(cloudflared)
            cmd = [str(TOOL), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", creationflags=flags)
        _state["proc"] = proc
        _state["log"] = []

        def reader():
            for line in proc.stdout:
                _state["log"] = (_state.get("log") or [])[-20:] + [line.strip()]
                if fixed:
                    if "started tunnel" in line or f"url=https://{fixed}" in line:
                        if not _state["url"]:
                            _state["url"] = f"https://{fixed}"
                            _state["since"] = time.strftime("%m/%d %H:%M")
                    elif "lvl=eror" in line or "ERR_NGROK" in line:
                        _state["error"] = "ngrok 오류: " + line.strip()[-200:]
                    continue
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m and not _state["url"]:
                    _state["url"] = m.group(0)
                    _state["since"] = time.strftime("%m/%d %H:%M")
        threading.Thread(target=reader, daemon=True).start()
    for _ in range(60):  # 주소가 나올 때까지 최대 30초
        if _state["url"] or proc.poll() is not None:
            break
        time.sleep(0.5)
    if not _state["url"]:
        err = _state.get("error") or "공유 링크를 만들지 못했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요."
        stop()
        _state["error"] = err
    return status()


def stop() -> dict:
    with _lock:
        p = _state["proc"]
        if p and p.poll() is None:
            p.terminate()
        _state.update(proc=None, url="")
    return status()
