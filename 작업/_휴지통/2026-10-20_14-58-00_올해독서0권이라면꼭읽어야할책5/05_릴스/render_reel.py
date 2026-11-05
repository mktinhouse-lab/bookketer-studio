# '올해 독서 0권이라면' 릴스 MP4. 편집 틀 = 캡컷 템플릿 '3. AI음악비트 (2)'(레퍼런스 릴스 DY1S4dryPkX 원본 프로젝트)에서 잰 값.
# 훅 0~2.13s(손동작 촬영본 7.2s~ + 연두 2줄 카피 반짝 등장 + 반짝 효과음) -> 공간회전 전환 0.47s
# -> 독서 영상 밝기 0.34 위에 책 5권(『제목』·표지·설명), 컷은 템플릿 음악 비트 그대로.
import json, subprocess, random
from pathlib import Path
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).resolve().parent
WORK = HERE.parent
DL = Path("C:/Users/user/Downloads")
TPL = Path("C:/Users/user/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft/3. AI음악비트 (2)")
MUSIC = TPL / "materials/audio/AQPf0rKGxsjD6wHw-hkZMKRsPtJFMLvNVgdTwrLgARTf_-KuxPkNY1meSMUx0UB8G5nj_7AmLUKEB-gf6zOS56davLjMXWpZ7pmnLuk.mp4"
MUSIC_IN = 1.366666
GLITTER = TPL / "materials/audio/a1b1f0a18d773da4ad361862767b08d5.mp3"
W, H, FPS = 1080, 1920, 30
FM = str(Path.home() / "AppData/Local/Microsoft/Windows/Fonts/Pretendard-Medium.otf")
HOOK_COL, BOOK_COL = (203, 251, 1), (206, 255, 0)

HOOK_SRC, HOOK_IN = DL / "Jandi_20261105_094042.mov", 7.2
READ_SRC, READ_IN = DL / "Jandi_20261105_095650.mov", 6.0
CUTS = [0, 2.133333, 4.066666, 6.0, 7.766666, 9.5, 11.733333]       # 템플릿 컷(음악 비트)
TRANS = 0.466666                                                       # 공간회전 길이
COVERS = {"소년이 온다": "9788936434120 (1).jpg", "혼모노": "images (9).jpg", "완벽한 원시인": "XL (21).jpg",
          "싯다르타": "9788937460586 (1).jpg", "모순": "9788998441012.jpg"}

state = json.loads((WORK / "state.json").read_text(encoding="utf-8"))
slides = state["cards"]["slides"]
thumb = next(s for s in slides if s["type"] == "thumb")
books = [s for s in slides if s["type"] == "book"]


def text_layer(lines, size, center_y, color, line_h=None, stroke=0.03):
    f = ImageFont.truetype(FM, size)
    lh = line_h or size * 1.2
    top = center_y - lh * len(lines) / 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text((W / 2, top + lh * i + lh / 2), l.strip(), font=f, fill=color + (255,), anchor="mm",
               stroke_width=max(2, round(size * stroke)), stroke_fill=(0, 0, 0, 255))
    return img


def over(base, rgba):
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (base.astype(np.float32) * (1 - a) + rgba[..., :3][..., ::-1].astype(np.float32) * a).astype(np.uint8)


def frames(src, t0, n):
    cap = cv2.VideoCapture(str(src)); cap.set(cv2.CAP_PROP_POS_MSEC, t0 * 1000)
    out = []
    for _ in range(n):
        ok, fr = cap.read()
        if not ok: fr = out[-1]
        out.append(fr if fr.shape[:2] == (H, W) else cv2.resize(fr, (W, H)))
    return out


def spin(img, p, sign):
    """공간회전 근사: p 0..1 만큼 돌며 확대 + 흐림."""
    if p <= 0: return img
    acc = np.zeros_like(img, dtype=np.float32); k = 6
    for i in range(k):
        q = p * (0.7 + 0.3 * i / (k - 1))
        M = cv2.getRotationMatrix2D((W / 2, H / 2), sign * 90 * q, 1 + 0.6 * q)
        acc += cv2.warpAffine(img, M, (W, H), borderMode=cv2.BORDER_REFLECT)
    return (acc / k).astype(np.uint8)


def f_(t): return int(round(t * FPS))


# ---------- 훅 ----------
hook_lines = [thumb["line1"], thumb["line2"]]
hook_text = np.array(text_layer(hook_lines, 84, 1107, HOOK_COL, stroke=0.031))
glow = np.array(Image.fromarray(hook_text).filter(ImageFilter.GaussianBlur(16)))
ys, xs = np.where(hook_text[..., 3] > 0)
bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
random.seed(7)
sparks = [(random.uniform(bx0 - 30, bx1 + 30), random.uniform(by0 - 60, by1 + 60), random.uniform(0.0, 0.9), random.uniform(6, 15)) for _ in range(90)]

out = []
nh = f_(CUTS[1])
for i, fr in enumerate(frames(HOOK_SRC, HOOK_IN, nh)):
    t = i / FPS
    rev = min(1, t / 0.6); rev = 1 - (1 - rev) ** 2          # '눈이 펄럭이는 것'(0.97s): 가운데서 펼쳐지며 빛나다 가라앉음
    half = (bx1 - bx0) / 2 * rev + 1; cx = (bx0 + bx1) / 2
    mask = np.zeros((H, W), np.float32); mask[:, int(max(0, cx - half)):int(min(W, cx + half))] = 1
    mask = cv2.GaussianBlur(mask, (0, 0), 18)
    lay = hook_text.copy(); lay[..., 3] = (lay[..., 3] * mask).astype(np.uint8)
    g = max(0.0, 1 - max(0, t - 0.3) / 0.67)
    if g > 0:
        gl = glow.copy(); gl[..., :3] = (120, 255, 200)[::-1] if False else (200, 255, 120)
        gl[..., 3] = np.clip(gl[..., 3] * mask * 1.8 * g, 0, 255).astype(np.uint8)
        fr = over(fr, gl)
    fr = over(fr, lay)
    sp = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(sp)
    for (x, y, born, r) in sparks:
        age = t - born
        if 0 <= age < 0.5 and abs(x - cx) <= half + 40:
            a = int(255 * (1 - age / 0.5)); rr = r * (1 - age)
            d.line([(x - rr, y), (x + rr, y)], fill=(255, 255, 220, a), width=2)
            d.line([(x, y - rr), (x, y + rr)], fill=(255, 255, 220, a), width=2)
            d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=(255, 255, 255, a))
    fr = over(fr, np.array(sp))
    out.append(fr)
cv2.imwrite(str(HERE / "cover_frame.jpg"), out[f_(1.2)])

# ---------- 책 5권 ----------
nb_total = f_(CUTS[-1]) - nh
bg = frames(READ_SRC, READ_IN, nb_total)
for bi, b in enumerate(books):
    lines = [l["text"] for l in b["lines"]]
    lay = text_layer([f"『{b['title']}』"], 71, 475, BOOK_COL, stroke=0.027)
    cov = Image.open(DL / COVERS[b["title"]]).convert("RGB")
    ch = 677; cw = round(cov.width * ch / cov.height)
    lay.paste(cov.resize((cw, ch), Image.LANCZOS), ((W - cw) // 2, 960 - ch // 2))
    lay = Image.alpha_composite(lay, text_layer(lines, 45, 1437 + max(0, len(lines) - 3) * 49 / 2, BOOK_COL, line_h=49, stroke=0.027))
    lay = np.array(lay)
    for fi in range(f_(CUTS[bi + 1]), f_(CUTS[bi + 2])):
        fr = (bg[fi - nh].astype(np.float32) * 0.34).astype(np.uint8)
        out.append(over(fr, lay))

# 공간회전 전환: 컷 앞뒤 반씩
c = nh; hw = f_(TRANS / 2)
for k in range(hw):
    out[c - hw + k] = spin(out[c - hw + k], (k + 1) / hw, 1)
    out[c + k] = spin(out[c + k], 1 - k / hw, -1)

# ---------- 내보내기 (배경음 + 반짝 효과음) ----------
dst = HERE / "올해독서0권이라면_릴스.mp4"
dur = len(out) / FPS
p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                      "-ss", f"{MUSIC_IN}", "-t", f"{dur:.3f}", "-i", str(MUSIC), "-t", "0.8", "-i", str(GLITTER),
                      "-filter_complex", "[2:a]volume=0.775[g];[1:a][g]amix=inputs=2:duration=first:normalize=0,afade=t=out:st=%.3f:d=0.4[a]" % (dur - 0.4),
                      "-map", "0:v", "-map", "[a]", "-t", f"{dur:.3f}",
                      "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                      "-movflags", "+faststart", str(dst)], stdin=subprocess.PIPE)
for fr in out: p.stdin.write(fr.tobytes())
p.stdin.close(); p.wait()
print("done", dst, f"{dur:.2f}s", len(out), "frames")
