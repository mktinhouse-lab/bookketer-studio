import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
PROMPTS_DIR = ROOT / "prompts"
ASSETS_DIR = ROOT / "assets"          # cta.png(선택): 있으면 마지막 장으로 붙는다
BRAND_GUIDE_FILE = ROOT / "brand_guide.md"

# md 기록 종류: 수집 / 기획 / 생성(이미지 후보·썸네일·완성본)
MD_KINDS = ("crawl", "analysis", "generate")

SESSION_DIR = DATA_DIR / ".session"
TRASH_DIR = DATA_DIR / "휴지통"
PROJECTS_FILE = DATA_DIR / "projects.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
SEEN_FILE = DATA_DIR / ".seen.json"     # [새로 찾기]에서 뺄 이미 본 게시물
DESKTOP_OUT = Path(os.path.expanduser("~")) / "Desktop" / "카드뉴스 완성본"

# 분석·생성에 쓸 모델 (구독 요금제 안에서 동작)
MODEL = os.environ.get("BOOKKETER_MODEL", "claude-opus-5-5")

INSTAGRAM_HANDLE = "@bookketer_mim"
CARD_W, CARD_H = 1080, 1350

for d in (DATA_DIR, SESSION_DIR, PROMPTS_DIR, ASSETS_DIR, *(DATA_DIR / k for k in MD_KINDS)):
    d.mkdir(parents=True, exist_ok=True)
