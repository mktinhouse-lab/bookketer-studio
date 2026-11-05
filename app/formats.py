"""1번 칸에서 고르는 카드뉴스 형식.

kind
- free    : 레퍼런스 공식을 따라 자유롭게 (단일 / 롱폼)
- books   : 책 추천 N권 (표지 → 책마다 한 장 → 팔로우 장)
- summary : 책 30초 요약 (표지 → 목차 → 키워드 2개씩 → 셀프체크 → 팔로우 장)
"""

FORMATS = {
    "book3": {
        "name": "책추천 3권", "kind": "books", "count": 3,
        "desc": "표지 + 책 3장 + 팔로우 장",
        "ref": "https://www.instagram.com/p/DdTX_rUH0wZ/",
        "tags": ["북케터 밈", "책 추천"],
    },
    "book5": {
        "name": "책추천 5권", "kind": "books", "count": 5,
        "desc": "표지 + 책 5장 + 팔로우 장",
        "ref": "https://www.instagram.com/p/DcQZE1DGeLA/",
        "tags": ["북케터 밈", "책 추천"],
    },
    "summary": {
        "name": "30초 요약", "kind": "summary",
        "desc": "표지 + 목차 + 키워드(2개씩) + 셀프체크 + 팔로우 장",
        "ref": "https://www.instagram.com/p/DebTFiHnwsf/",
        "tags": ["북케터 밈", "30초 요약"],
    },
    "long": {"name": "자유 롱폼", "kind": "free", "desc": "레퍼런스 공식대로 썸네일 + 본문 4~7장 + 마지막 장"},
    "single": {"name": "자유 단일", "kind": "free", "desc": "썸네일 + 마지막 장 (2장)"},
}

MODE_KO = {k: v["name"] for k, v in FORMATS.items()}


def get(fmt: str) -> dict:
    return FORMATS.get(fmt) or FORMATS["long"]


def kind(fmt: str) -> str:
    return get(fmt)["kind"]
