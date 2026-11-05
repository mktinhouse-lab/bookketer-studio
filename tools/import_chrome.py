"""크롬(로그인된 인스타)에서 모은 게시물 JSON 을 북케터 밈 수집 기록(md + 사진)으로 저장한다.

사용: python tools/import_chrome.py <json 파일>
json = [{"tag": "책추천", "params": {...}, "checked": 269, "posts": [{..., "remote_images": [...], "top_comments": [...]}]}]
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import storage, workflow  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"


def fetch(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.instagram.com/"})
        with urllib.request.urlopen(req, timeout=30) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as e:  # noqa: BLE001
        print("  이미지 실패:", e)
        return False


def main(path: str) -> None:
    groups = json.loads(Path(path).read_text(encoding="utf-8"))
    for g in groups:
        name = storage.new_name("crawl", "크롬수집", g["tag"])
        folder = storage.assets_dir("crawl", name)
        posts = []
        for i, p in enumerate(g["posts"], 1):
            imgs = []
            for k, data_url in enumerate(p.get("image_data", [])[:12], 1):  # 크롬에서 받아 둔 사진(data URL)
                f = f"p{i}-{k:02d}.jpg"
                if data_url.startswith("data:image"):
                    (folder / f).write_bytes(workflow.data_url_bytes(data_url))
                    imgs.append(f)
            for k, u in enumerate([] if imgs else p.get("remote_images", [])[:12], 1):
                f = f"p{i}-{k:02d}.jpg"
                if fetch(u, folder / f):
                    imgs.append(f)
            posts.append({"code": p["code"], "url": p["url"], "type": p["type"], "author": p["author"], "date": p["date"],
                          "likes": p["likes"], "comments": p["comments"], "views": p.get("views"), "shares": None,
                          "caption": p["caption"], "top_comments": p.get("top_comments", []), "images": imgs,
                          "slides": p["slides"], "source": "크롬"})
        d = {"label": "크롬 로그인 세션으로 해시태그 인기 게시물 수집", "source": "#" + g["tag"],
             "params": {**g.get("params", {}), "검사한 게시물": g.get("checked", 0)}, "posts": posts}
        storage.write_md("crawl", name, workflow.crawl_md(d, folder.name), d)
        storage.add_seen(p["code"] for p in posts)
        print(name, len(posts), "개,", sum(len(p["images"]) for p in posts), "장")


if __name__ == "__main__":
    main(sys.argv[1])
