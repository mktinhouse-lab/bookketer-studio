# -*- coding: utf-8 -*-
"""캡컷 '1105' = 템플릿 프로젝트 '3. AI음악비트 (2)' 를 그대로 복제하고 영상·표지·문구만 바꾼다(캡컷을 끈 상태에서만).
템플릿에서 그대로 가져오는 것: 컷 시점(음악 비트), 배경음·반짝 효과음, 훅 보정 효과·'눈이 펄럭이는 것' 글자 애니, '공간회전' 전환,
독서 영상 불투명 0.34, 글자 크기·색·테두리·위치.
"""
import copy, json, os, shutil, subprocess, time, uuid
from pathlib import Path
from PIL import ImageFont

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
DRAFTS = "C:/Users/user/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"
PROJ = DRAFTS + "/1105"
TPL = DRAFTS + "/3. AI음악비트 (2)"
DL = "C:/Users/user/Downloads/"
FONTS = "C:/Users/user/AppData/Local/Microsoft/Windows/Fonts/"
W, H = 1080, 1920

HOOK_SRC, HOOK_IN = DL + "Jandi_20261105_094042.mov", 7.2      # 1105 에서 잘라 두신 구간 시작
READ_SRC, READ_IN = DL + "Jandi_20261105_095650.mov", 6.0
COVERS = {"소년이 온다": "9788936434120 (1).jpg", "혼모노": "images (9).jpg", "완벽한 원시인": "XL (21).jpg",
          "싯다르타": "9788937460586 (1).jpg", "모순": "9788998441012.jpg"}
COVER_H = 677          # 템플릿 표지 화면 높이(px) = 458x666 사진 x 0.431
DESC_LINE = 49         # 템플릿 설명 한 줄 높이(px, 레퍼런스 화면에서 잼)

state = json.loads((WORK / "state.json").read_text(encoding="utf-8"))
slides = state["cards"]["slides"]
thumb = next(s for s in slides if s["type"] == "thumb")
books = [s for s in slides if s["type"] == "book"]


def probe(path):
    j = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path],
                                  capture_output=True, text=True, encoding="utf-8").stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    return float(j["format"].get("duration", 0) or 0), v["width"], v["height"]


def set_text(mat, text):
    c = json.loads(mat["content"])
    st = c["styles"][0]
    st["range"] = [0, len(text)]
    c["text"], c["styles"] = text, [st]
    mat["content"] = json.dumps(c, ensure_ascii=False)


tpl = json.load(open(TPL + "/draft_content.json", encoding="utf-8"))
old = json.load(open(PROJ + "/draft_content.json", encoding="utf-8"))
draft = copy.deepcopy(tpl)
draft["id"] = old["id"]                          # 1105 의 타임라인 id 유지
MI = {x["id"]: x for v in draft["materials"].values() if isinstance(v, list) for x in v if isinstance(x, dict) and "id" in x}
tr = draft["tracks"]
hook_seg, read_seg = tr[0]["segments"]
title_segs, hook_txt_seg, desc_segs, cover_segs = tr[1]["segments"], tr[2]["segments"][0], tr[3]["segments"], tr[4]["segments"]
assert len(title_segs) == len(desc_segs) == len(cover_segs) == len(books) == 5


def swap_video(seg, path, src_in):
    m = MI[seg["material_id"]]
    d, w, h = probe(path)
    m.update(path=path, material_name=os.path.basename(path), width=w, height=h, duration=int(d * 1e6), local_material_id="")
    seg["source_timerange"]["start"] = int(src_in * 1e6)


swap_video(hook_seg, HOOK_SRC, HOOK_IN)
swap_video(read_seg, READ_SRC, READ_IN)

set_text(MI[hook_txt_seg["material_id"]], f"{thumb['line1']}\n{thumb['line2']}")
hook_txt_seg["clip"]["transform"]["x"] = 0.0

for b, ts, ds, cs in zip(books, title_segs, desc_segs, cover_segs):
    set_text(MI[ts["material_id"]], f"『{b['title']}』")
    lines = [l["text"] for l in b["lines"]]
    set_text(MI[ds["material_id"]], "\n".join(lines))
    ds["clip"]["transform"]["y"] = -0.497 - max(0, len(lines) - 3) * DESC_LINE / 2 / (H / 2)   # 줄이 늘어난 만큼 아래로(표지와 안 겹치게)
    path = DL + COVERS[b["title"]]
    m = MI[cs["material_id"]]
    _, w, h = probe(path)
    m.update(path=path, material_name=os.path.basename(path), width=w, height=h, local_material_id="")
    fit = min(W / w, H / h)
    s = COVER_H / (h * fit)
    cs["clip"]["scale"] = {"x": s, "y": s}
    cs["clip"]["transform"] = {"x": 0.0, "y": 0.0}

# 배경음·효과음: 템플릿 파일을 1105 안으로 복사해 절대 경로로
aud_dir = Path(PROJ) / "materials" / "audio"
aud_dir.mkdir(parents=True, exist_ok=True)
for a in draft["materials"]["audios"]:
    p = a["path"]
    if p.startswith("##_draftpath_placeholder_"):
        p = TPL + p.split("##", 2)[2]
    dst = aud_dir / os.path.basename(p)
    if not dst.exists():
        shutil.copy(p, dst)
    a["path"] = str(dst).replace("\\", "/")
for v in draft["materials"]["videos"]:
    assert not v["path"].startswith("##"), v["path"]

content = json.dumps(draft, ensure_ascii=False, separators=(",", ":"))
for rel in ["draft_content.json", "draft_content.json.bak", "template-2.tmp",
            f"Timelines/{draft['id']}/draft_content.json", f"Timelines/{draft['id']}/draft_content.json.bak", f"Timelines/{draft['id']}/template-2.tmp"]:
    with open(os.path.join(PROJ, rel), "w", encoding="utf-8") as f:
        f.write(content)
shutil.rmtree(os.path.join(PROJ, "Timelines", draft["id"], "attachment", "patch"), ignore_errors=True)
cov = HERE / "cover_frame.jpg"
if cov.exists():
    for rel in ["draft_cover.jpg", f"Timelines/{draft['id']}/draft_cover.jpg"]:
        shutil.copy(cov, os.path.join(PROJ, rel))

meta = json.load(open(PROJ + "/draft_meta_info.json", encoding="utf-8"))
meta["tm_duration"] = draft["duration"]
meta["tm_draft_modified"] = int(time.time() * 1e6)
json.dump(meta, open(PROJ + "/draft_meta_info.json", "w", encoding="utf-8"), ensure_ascii=False)
rp = DRAFTS + "/root_meta_info.json"
root = json.load(open(rp, encoding="utf-8"))
for x in root["all_draft_store"]:
    if x.get("draft_fold_path", "").replace("\\", "/").rstrip("/").endswith("/1105"):
        x["tm_duration"] = draft["duration"]; x["tm_draft_modified"] = int(time.time() * 1e6)
json.dump(root, open(rp, "w", encoding="utf-8"), ensure_ascii=False)
print("1105 <- 템플릿 복제:", draft["duration"] / 1e6, "s")
