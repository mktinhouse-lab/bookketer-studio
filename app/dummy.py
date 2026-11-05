"""처음 실행 때 화면 흐름을 확인하도록 '샘플(더미) 수집 결과'를 하나 만들어 둔다. 실제 계정·게시물이 아니다."""
from . import storage

SAMPLE_POSTS = [
    ("dummy_bookclub", 48210, 1320, "서점 앞에 줄 선 거 처음 봤어요… 동네서점 10곳에 선결제한 결과",
     ["서점 10곳에 1000만 원 뿌렸더니 생긴 일", "솔직히 망할 줄 알았어요", "오픈 당일 사장님한테 온 연락",
      "30분 만에 첫 마감", "하루 만에 600명이 책을 들고 갔다", "다음 서점은 댓글로 알려드릴게요"],
     ["세상에 서점에 줄이라니 (♥820)", "우리 동네도 와주세요 (♥611)", "@친구 이번 주말에 가자 (♥233)"]),
    ("dummy_readingnote", 23500, 870, "읽다가 멈춘 책이 있다면 이 5가지만 해보세요",
     ["책 끝까지 못 읽는 사람 특징 5가지", "1. 처음부터 순서대로 읽는다", "2. 한 권만 붙잡고 있다",
      "3. 밑줄만 긋고 끝낸다", "4. 혼자 읽는다", "5. 완독을 목표로 한다", "저장해두고 오늘 밤 해보기"],
     ["완전 내 얘기 (♥1203)", "2번 찔림 (♥402)"]),
    ("dummy_publisher", 15890, 2310, "편집자가 몰래 알려주는 베스트셀러 표지의 비밀",
     ["편집자만 아는 표지 비밀", "표지 색은 서점 조명 아래서 정해요", "제목 글자 크기는 3m 거리 기준",
      "띠지는 사실 이렇게 쓰여요", "다음 편: 제목 짓는 법 (팔로우)"],
     ["이런 거 더 알려주세요 (♥540)", "띠지 얘기 신기하다 (♥120)"]),
    ("dummy_library_event", 12750, 5120, "댓글 남기면 추첨으로 책 보내드려요",
     ["댓글만 달면 책 보내드려요", "이번 달 선물 책 3권", "참여 방법 딱 2단계", "당첨자는 다음 주 금요일 발표"],
     ["참여합니다! (♥12)", "@친구 같이 하자 (♥8)"]),
    ("dummy_indiebookshop", 9620, 410, "가을에 꼭 가봐야 할 서울 독립서점 지도",
     ["가을에 꼭 가볼 독립서점 7곳", "성수 · 창가 자리 있는 서점", "망원 · 고양이가 있는 서점",
      "해방촌 · 밤 11시까지 여는 서점", "지도 링크는 댓글에"],
     ["저장 완료 (♥301)", "망원 고양이 서점 어디예요? (♥95)"]),
]


def ensure_sample() -> None:
    if storage.list_names("crawl"):
        return
    posts = []
    for i, (author, likes, comments, caption, slides, cmts) in enumerate(SAMPLE_POSTS, 1):
        posts.append({"code": f"dummy{i}", "url": "", "type": "캐러셀", "author": author, "date": "2026-10-01",
                      "likes": likes, "comments": comments, "views": None, "shares": None, "caption": caption,
                      "top_comments": cmts, "images": [], "slides": len(slides), "slides_text": slides,
                      "source": "샘플"})
    name = storage.new_name("crawl", "샘플", "더미_레퍼런스")
    data = {"label": "샘플 데이터(더미)", "source": "샘플(더미)", "params": {"최소 좋아요": 5000}, "posts": posts}
    body = "# 레퍼런스 수집: 샘플(더미)\n\n- 실제 게시물이 아닌 화면 확인용 더미 데이터입니다.\n" + "\n".join(
        f"\n## 게시물 {i}\n- 작성자: {p['author']}\n- 좋아요: {p['likes']:,}\n\n### 캡션\n{p['caption']}"
        for i, p in enumerate(posts, 1))
    storage.write_md("crawl", name, body, data)
