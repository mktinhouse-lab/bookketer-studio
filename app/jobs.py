"""오래 걸리는 작업(수집·기획·이미지 찾기·저장)을 백그라운드 스레드에서 돌리고 진행률을 남긴다.

Playwright와 Agent SDK는 서브프로세스를 띄우므로 Windows에서는 Proactor 이벤트 루프가 필요하다.
작업마다 전용 스레드 + 전용 루프를 만들어 웹 서버 루프와 분리한다.
"""
import asyncio
import datetime as dt
import secrets
import sys
import threading
import time
import traceback

_jobs: dict[str, "Job"] = {}


class Stopped(Exception):
    """[멈추기]를 눌러 작업을 중간에 끝냈다. 저장된 지점부터 이어서 할 수 있다."""


class Job:
    def __init__(self, label: str, meta: dict | None = None):
        self.id = secrets.token_hex(6)
        self.label = label
        self.meta = {"title": label, **(meta or {})}
        self.status = "running"
        self.log_lines: list[str] = []
        self.result = None
        self.error: str | None = None
        self.started = time.time()
        self.pct: float | None = None
        self.step_label = ""
        self.stop_requested = False

    def check(self) -> None:
        if self.stop_requested:
            raise Stopped()

    def log(self, msg: str) -> None:
        self.log_lines.append(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}")

    def progress(self, pct: float | None, label: str = "") -> None:
        self.pct = None if pct is None else max(0.0, min(99.0, pct))
        if label:
            self.step_label = label
            self.log(label)

    def to_dict(self) -> dict:
        elapsed = time.time() - self.started
        prog = None
        if self.pct is not None or self.step_label:
            prog = {"label": self.step_label}
            if self.pct:
                p = round(self.pct)
                remaining = elapsed * (100 - self.pct) / self.pct
                prog.update(pct=p, remaining=round(remaining), over=remaining < 5)
        return {"id": self.id, "label": self.label, "meta": self.meta, "status": self.status,
                "log": self.log_lines[-300:], "result": self.result, "error": self.error,
                "elapsed": round(elapsed), "progress": prog}


def new_loop() -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.ProactorEventLoop()
    return asyncio.new_event_loop()


def run_in_new_loop(coro_factory):
    loop = new_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro_factory())
    finally:
        loop.close()


def start_job(label: str, coro_factory, meta: dict | None = None) -> Job:
    """coro_factory(job) -> coroutine. 결과는 job.result 로."""
    job = Job(label, meta)
    _jobs[job.id] = job

    def target():
        try:
            job.result = run_in_new_loop(lambda: coro_factory(job))
            job.status = "done"
            job.pct = 100
        except Stopped:
            job.status = "stopped"
            job.log("멈췄습니다. 저장된 지점부터 이어서 할 수 있어요.")
        except Exception as e:  # noqa: BLE001 - 화면에 그대로 보여준다
            job.error = str(e) or e.__class__.__name__
            job.status = "error"
            job.log(f"오류: {job.error}")
            traceback.print_exc()

    threading.Thread(target=target, daemon=True).start()
    return job


def get_job(job_id: str) -> Job | None:
    return _jobs.get(job_id)


def stop_job(job_id: str) -> bool:
    job = _jobs.get(job_id)
    if job and job.status == "running":
        job.stop_requested = True
        job.log("멈추는 중… (지금 하던 게시물까지 저장하고 멈춥니다)")
        return True
    return False


def running_jobs() -> list[dict]:
    return [j.to_dict() for j in _jobs.values() if j.status == "running"]
