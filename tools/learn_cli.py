"""0단계 학습을 화면 없이 돌리는 명령줄 도구.
프로그램 안 Claude 로그인이 안 될 때, 바깥 Claude(Claude Code 대화)가 분석·가이드를 대신 쓰고 같은 형식으로 저장할 때 쓴다.

  python tools/learn_cli.py collect [--update]        수집(목록 + 이미지)
  python tools/learn_cli.py todo <out.json> [N]       분석 안 된 게시물 N개(기본 전부)의 이미지 경로·캡션
  python tools/learn_cli.py save <code> <analysis.json>  분석 한 건 저장(스키마 확인 + 글자 수 계산 + md)
  python tools/learn_cli.py saveall <dir>             <dir>/<code>.json 을 모두 저장
  python tools/learn_cli.py prep <out.txt>            가이드 입력(통계·상위/하위 전문) 파일로
  python tools/learn_cli.py guide <sections.json> [작성자]  ①~⑤ 본문으로 새 가이드 버전 저장
  python tools/learn_cli.py books                     사용한 책 DB 다시 만들기
  python tools/learn_cli.py status
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
from app import learn  # noqa: E402
from app.jobs import new_loop  # noqa: E402

BY = "Claude Code 대화"


class Job:
    stop_requested = False

    def progress(self, pct, label=""):
        if label:
            print(f"[{'' if pct is None else round(pct)}%] {label}", flush=True)

    def log(self, msg):
        print(msg, flush=True)

    def check(self):
        pass


def run(coro):
    loop = new_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "collect":
        print(run(learn.collect(Job(), update="--update" in argv)))
    elif cmd == "todo":
        n = int(argv[2]) if len(argv) > 2 else None
        posts = [p for p in learn.load_posts()["posts"].values() if learn.images_of(p) and not learn.analysis_path(p).exists()]
        posts.sort(key=lambda p: p.get("timestamp") or p.get("date") or "", reverse=True)
        out = [{"code": p["code"], "date": p.get("date"), "url": p.get("url"),
                "images": [i.as_posix() for i in learn.images_of(p)], "caption": p.get("caption", "")[:3000]}
               for p in posts[:n]]
        Path(argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(out)}개 → {argv[1]}")
    elif cmd in ("save", "saveall"):
        db = learn.load_posts()["posts"]
        files = [(argv[1], Path(argv[2]))] if cmd == "save" else [(f.stem, f) for f in sorted(Path(argv[1]).glob("*.json"))]
        ok = 0
        for code, f in files:
            try:
                learn.save_analysis(db[code], json.loads(f.read_text(encoding="utf-8")), BY)
                ok += 1
            except Exception as e:  # noqa: BLE001
                print(f"실패 {code}: {e}")
        learn.rebuild_books()
        print(f"저장 {ok}/{len(files)}")
    elif cmd == "prep":
        prep = learn.prepare_guide()
        Path(argv[1]).write_text(prep["prompt"], encoding="utf-8")
        Path(argv[1]).with_suffix(".prep.json").write_text(json.dumps(prep, ensure_ascii=False), encoding="utf-8")
        print(f"분석 {prep['n']}개, 입력 {len(prep['prompt'])}자 → {argv[1]}")
    elif cmd == "guide":
        prep = learn.prepare_guide()
        g = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        print(learn.save_guide(g, prep, argv[2] if len(argv) > 2 else BY))
    elif cmd == "books":
        print(learn.rebuild_books()["count"], "권")
    else:
        o = learn.overview()
        o.pop("graph", None)
        print(json.dumps(o, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
