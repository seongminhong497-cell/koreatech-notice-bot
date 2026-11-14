import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString

from datetime import datetime, timedelta, timezone

BOARDS = [
    {
        "url": (
            "https://www.koreatech.ac.kr/notice/list.es"
            "?mid=a10604010000&board_id=14"
        ),
        "source": "학교-일반",
        "id_prefix": "general",
    },
    {
        "url": (
            "https://www.koreatech.ac.kr/notice/list.es"
            "?mid=a10604020000&board_id=15"
        ),
        "source": "학교-장학",
        "id_prefix": "scholarship",
    },
    {
        "url": (
            "https://www.koreatech.ac.kr/notice/list.es"
            "?mid=a10604030000&board_id=16"
        ),
        "source": "학교-학사",
        "id_prefix": "academic",
    },

                # 기계공학부
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=a70601000000&bid=0072",
        "source": "기계공학부-일반",
        "id_prefix": "mech-general",
        "department": "기계공학부"
    },
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=a70604000000&bid=0075",
        "source": "기계공학부-취업",
        "id_prefix": "mech-employment",
        "department": "기계공학부"
    },

    # 메카트로닉스공학부
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=a80701000000&bid=0085",
        "source": "메카트로닉스공학부-일반",
        "id_prefix": "mechatronics-general",
        "department": "메카트로닉스공학부"
    },
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=a80704000000&bid=0088",
        "source": "메카트로닉스공학부-취업",
        "id_prefix": "mechatronics-employment",
        "department": "메카트로닉스공학부"
    },

    # 전기·전자·통신공학부
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=a90601000000&bid=0097",
        "source": "전기전자통신공학부-일반",
        "id_prefix": "eetc-general",
        "department": "전기·전자·통신공학부"
    },
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=a90603000000&bid=0100",
        "source": "전기전자통신공학부-취업",
        "id_prefix": "eetc-employment",
        "department": "전기·전자·통신공학부"
    },

    # 컴퓨터공학부
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b10601000000&bid=0105",
        "source": "컴퓨터공학부-일반",
        "id_prefix": "cse-general",
        "department": "컴퓨터공학부"
    },
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b10704000000&bid=0109",
        "source": "컴퓨터공학부-취업",
        "id_prefix": "cse-employment",
        "department": "컴퓨터공학부"
    },

    # 디자인공학과
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b20601000000&bid=0114",
        "source": "디자인공학과-일반",
        "id_prefix": "design-general",
        "department": "디자인공학과"
    },
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b20602000000&bid=0115",
        "source": "디자인공학과-취업",
        "id_prefix": "design-employment",
        "department": "디자인공학과"
    },

    # 건축공학과
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b30401000000&bid=0122",
        "source": "건축공학과-일반",
        "id_prefix": "architecture-general",
        "department": "건축공학과"
    },
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b30402000000&bid=0124",
        "source": "건축공학과-취업",
        "id_prefix": "architecture-employment",
        "department": "건축공학과"
    },

    # 에너지신소재화학공학부: 화학공학전공은 접근 불가로 제외
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b40501000000&bid=0130",
        "source": "에너지신소재공학전공-일반",
        "id_prefix": "energy-materials-general",
        "department": "에너지신소재화학공학부"
    },

    # 산업경영학부: 일반공지에 취업·대외활동 포함 / 조율 후 수정 필요
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b60501000000&bid=0145",
        "source": "산업경영학부-일반",
        "id_prefix": "industrial-management-general",
        "department": "산업경영학부"
    },

    # 고용서비스정책학과: 일반공지
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b80601000000&bid=0151",
        "source": "고용서비스정책학과-일반",
        "id_prefix": "employment-policy-general",
        "department": "고용서비스정책학과"
    },

    # 미래융합학부: 일반공지
    {
        "url": "https://www.koreatech.ac.kr/board.es?mid=b70401000000&bid=0148",
        "source": "미래융합학부-일반",
        "id_prefix": "future-convergence-general",
        "department": "미래융합학부"
    },

    # 반도체·디스플레이공학과: 현재 크롤러의 게시판과 구조가 달라 테스트 후 추가 예정
        
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

MAX_ATTEMPTS = 3

def get_response(url):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=(5, 15),
            )
            response.raise_for_status()
            return response

        except (requests.Timeout, requests.ConnectionError) as error:
            if attempt == MAX_ATTEMPTS:
                raise

            wait_seconds = attempt * 2
            print(
                f"요청 실패. {wait_seconds}초 후 재시도 "
                f"({attempt}/{MAX_ATTEMPTS}): {url} ({error})",
                file=sys.stderr,
            )
            time.sleep(wait_seconds)

TEST_LIMIT = None  # 게시판별 전체 수집. 일부만 보려면 숫자를 입력

OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "notices.json"
)
PROFILE_PATH = OUTPUT_PATH.parent / "profile.json"

KST = timezone(timedelta(hours=9))

def load_profile_department():
    """profile.json에서 사용자의 학과를 읽는다."""
    try:
        with PROFILE_PATH.open("r", encoding="utf-8") as file:
            profile = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(
            f"profile.json을 읽지 못해 학과 게시판은 건너뜁니다: {error}",
            file=sys.stderr,
        )
        return None

    department = profile.get("department") if isinstance(profile, dict) else None

    if not isinstance(department, str) or not department.strip():
        print(
            "profile.json에 department 값이 없어 학과 게시판은 건너뜁니다.",
            file=sys.stderr,
        )
        return None

    return department.strip()

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")

SHARE_LABELS = {
    "공유하기",
    "페이스북",
    "트위터",
    "밴드",
    "QR 코드",
    "URL 복사",
}

BLOCK_TAGS = {
    "address", "article", "blockquote", "dd", "div", "dl", "dt",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4",
    "li", "ol", "p", "pre", "section", "table", "tbody", "td",
    "tfoot", "th", "thead", "tr", "ul",
}


def normalize_text(text):
    return re.sub(r"\s+", "", text or "")


def extract_text_preserving_spacing(node):
    """인라인 태그 사이에는 공백을 임의로 넣지 않고 본문을 추출한다."""
    if isinstance(node, NavigableString):
        return str(node)

    tag_name = getattr(node, "name", None)

    if not tag_name:
        return ""

    tag_name = tag_name.lower()

    if tag_name in {"script", "style", "noscript"}:
        return ""

    if tag_name == "br":
        return "\n"

    text = "".join(
        extract_text_preserving_spacing(child)
        for child in node.children
    )

    if tag_name in BLOCK_TAGS:
        return f"\n{text}\n"

    return text


def find_notice_content(soup, title):
    """상세 페이지에서 공지 본문 영역을 찾는다."""
    wanted_title = normalize_text(title)
    articles = soup.select("article")

    for article in articles:
        heading = article.find(["h1", "h2", "h3"])

        if heading:
            heading_text = normalize_text(
                heading.get_text(" ", strip=True)
            )

            if (
                wanted_title
                and (
                    wanted_title in heading_text
                    or heading_text in wanted_title
                )
            ):
                return article

    if len(articles) >= 2:
        return articles[-1]

    for selector in (
        ".view_cont",
        ".view_content",
        ".board_view_cont",
    ):
        content = soup.select_one(selector)

        if content:
            return content

    if articles:
        article_text = articles[0].get_text(" ", strip=True)

        if "공유하기" not in article_text:
            return articles[0]

    return None


def is_skin_icon(image_url):
    """게시판 장식 아이콘과 QR 코드를 이미지 목록에서 제외한다."""
    parsed_url = urlparse(image_url)
    image_path = unquote(parsed_url.path).lower()

    return (
        parsed_url.netloc.lower() == "api.qrserver.com"
        or "/upload/skin/board/basic/" in image_path
    )


def fetch_notice_detail(detail_url, title):
    """상세 페이지에서 본문과 PNG/JPG 이미지 주소를 가져온다."""
    response = get_response(detail_url)
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
    content = find_notice_content(soup, title)

    if content is None:
        print(
            f"본문 영역을 찾지 못했습니다: {detail_url}",
            file=sys.stderr,
        )
        return None, []

    heading = content.find(["h1", "h2", "h3"])
    selected_title = (
        heading.get_text(" ", strip=True)
        if heading
        else "(제목 태그 없음)"
    )
    print(f"선택된 본문 영역: {selected_title}", file=sys.stderr)

    images = set()

    # 본문 안에 직접 삽입된 이미지 주소
    for image in content.select(
        "img[src], img[data-src], img[data-original]"
    ):
        image_url = (
            image.get("src")
            or image.get("data-src")
            or image.get("data-original")
        )

        if not image_url or image_url.startswith("data:"):
            continue

        absolute_url = urljoin(detail_url, image_url)

        if not is_skin_icon(absolute_url):
            images.add(absolute_url)

    # 첨부파일 중 PNG/JPG/JPEG 주소
    for link in soup.select("a[href]"):
        href = link.get("href", "").strip()

        if not href or href.lower().startswith(
            ("javascript:", "#", "mailto:")
        ):
            continue

        link_text = link.get_text(" ", strip=True)
        file_info = unquote(unquote(href + " " + link_text)).lower()

        if any(ext in file_info for ext in IMAGE_EXTENSIONS):
            absolute_url = urljoin(detail_url, href)

            if not is_skin_icon(absolute_url):
                images.add(absolute_url)

    # 본문에 공지 제목이 중복되면 제거
    for heading in content.find_all(["h1", "h2", "h3"]):
        heading_text = normalize_text(
            heading.get_text(" ", strip=True)
        )

        if normalize_text(title) in heading_text:
            heading.decompose()

    # 작성자·등록일 등 게시글 정보 영역 제거
    metadata_labels = ("분류", "작성자", "등록일", "조회수")

    for block in list(content.find_all(["ul", "dl"])):
        block_text = block.get_text(" ", strip=True)
        label_count = sum(
            label in block_text
            for label in metadata_labels
        )

        if label_count >= 2:
            block.decompose()

    # 공유 버튼과 스크립트 제거
    for unwanted in content.select(
        "script, style, noscript, button, .share, .sns, "
        "grammarly-desktop-integration, translator-content-app"
    ):
        unwanted.decompose()

    raw_text = extract_text_preserving_spacing(content)

    # 본문에 글자 형태로 들어온 사이트 안내 문구 제거
    raw_text = re.sub(
        r"Not Allowed Attribute Filtered\s*\([^)]*\)\s*",
        "",
        raw_text,
        flags=re.IGNORECASE,
    )

    # 본문 끝에 붙은 확장 프로그램 태그 제거
    raw_text = re.sub(
        r"</?(?:grammarly-desktop-integration|translator-content-app)\b[^>]*>",
        "",
        raw_text,
        flags=re.IGNORECASE,
    )

    lines = []

    for line in raw_text.splitlines():
        cleaned_line = re.sub(r"[ \t\f\v]+", " ", line).strip()

        if not cleaned_line or cleaned_line in SHARE_LABELS:
            continue

        # 날짜와 문장부호 주변의 불필요한 공백 정리
        cleaned_line = re.sub(
            r"(\d)\s+(년|월|일|시|분)",
            r"\1\2",
            cleaned_line,
        )
        cleaned_line = re.sub(
            r"\s+([,.!?;:])",
            r"\1",
            cleaned_line,
        )
        cleaned_line = re.sub(r"\(\s+", "(", cleaned_line)
        cleaned_line = re.sub(r"\s+\)", ")", cleaned_line)

        if cleaned_line:
            lines.append(cleaned_line)

    body = "\n".join(lines).strip()
    return body or None, sorted(images)


def crawl_board(board, skip_ids=None):
    """게시판 하나의 목록과 상세 내용을 수집한다."""
    board_url = board["url"]

    response = get_response(board_url)
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
    notices = []

    for row in soup.select("tbody tr"):
        title_link = row.select_one('td[aria-label="제목"] a')
        date_cell = row.select_one('td[aria-label="등록일"]')

        if not title_link or not title_link.get("href"):
            continue

        badge = title_link.select_one(".icon_notice")

        if badge:
            badge.decompose()

        title = title_link.get_text(" ", strip=True)
        title = re.sub(r"^새글\s*", "", title).strip()
        detail_url = urljoin(board_url, title_link["href"])
        published_date = (
            date_cell.get_text(strip=True)
            if date_cell
            else None
        )

        if published_date:
            date_match = re.search(
                r"(\d{4})[./-]\s*(\d{1,2})[./-]\s*(\d{1,2})",
                published_date,
            )
            if date_match:
                year, month, day = map(int, date_match.groups())
                published_date = f"{year:04d}-{month:02d}-{day:02d}"

        query = parse_qs(urlparse(detail_url).query)
        post_id = (
            query.get("post_seq", [None])[0]
            or query.get("list_no", [None])[0]
        )
        if not post_id:
            print(f"게시글 번호를 찾지 못했습니다: {detail_url}", file=sys.stderr)
            continue

        notice_id = f"{board['id_prefix']}-{post_id}"

        if notice_id in (skip_ids or set()):
            body, images = None, []
        else:
            if notices:
                time.sleep(1)

            try:
                body, images = fetch_notice_detail(detail_url, title)
            except requests.RequestException as error:
                print(
                    f"상세 페이지 수집 실패: {detail_url} ({error})",
                    file=sys.stderr,
                )
                body, images = None, []

        notices.append({
            "id": notice_id,
            "title": title,
            "url": detail_url,
            "source": board["source"],
            "source_type": "학교",
            "published_date": published_date or None,
            "body": body,
            "images": images,
            "is_sample": False,
            "extracted": False,
            "processed": False,
        })

        if TEST_LIMIT is not None and len(notices) >= TEST_LIMIT:
            break

    return notices


def crawl_all_boards(skip_ids=None):
    """학교 게시판과 프로필 학과 게시판을 수집한다."""
    skip_ids = skip_ids or set()
    profile_department = load_profile_department()
    all_notices = []

    for board in BOARDS:
        board_department = board.get("department")

        # 학과가 지정된 게시판은 프로필 학과와 일치할 때만 수집한다.
        # department가 없는 학교 게시판은 항상 수집한다.
        if (
            board_department is not None
            and board_department != profile_department
        ):
            print(
                f"학과가 달라 수집 건너뜀: {board['source']}",
                file=sys.stderr,
            )
            continue

        print(f"\n수집 중: {board['source']}", file=sys.stderr)

        try:
            board_notices = crawl_board(board, skip_ids)
        except requests.RequestException as error:
            print(
                f"게시판 목록 수집 실패: {board['source']} ({error})",
                file=sys.stderr,
            )
            continue

        all_notices.extend(board_notices)
        print(
            f"{board['source']}: {len(board_notices)}개 수집",
            file=sys.stderr,
        )

    return all_notices

def load_saved_notices():
    """기존 공지 파일을 읽는다."""
    if not OUTPUT_PATH.exists():
        return []

    with OUTPUT_PATH.open("r", encoding="utf-8") as file:
        notices = json.load(file)

    if not isinstance(notices, list):
        raise ValueError("data/notices.json의 최상위 값은 목록이어야 합니다.")

    return [
        notice for notice in notices
        if not notice.get("is_sample", False)
    ]


def is_within_new_period(notice, now):
    """최초 수집 시각으로부터 24시간 이내인지 확인한다."""
    collected_at = notice.get("collected_at")

    if not isinstance(collected_at, str) or not collected_at:
        return False

    try:
        collected_at = datetime.fromisoformat(
            collected_at.replace("Z", "+00:00")
        )
        if collected_at.tzinfo is None:
            collected_at = collected_at.replace(tzinfo=KST)
    except (TypeError, ValueError):
        return False

    age = now - collected_at
    return timedelta(0) <= age < timedelta(hours=24)


def merge_notices(crawled_notices):
    """기존 공지는 유지하고 새 공지만 추가하며, 빈 본문은 복구한다."""
    now = datetime.now(KST)
    saved_notices = load_saved_notices()

    saved_by_id = {
        notice["id"]: notice
        for notice in saved_notices
        if notice.get("id")
    }

    # 기존 공지는 수집 시각을 기준으로 is_new만 갱신한다.
    for notice in saved_notices:
        title = notice.get("title")
        if isinstance(title, str):
            notice["title"] = re.sub(r"^새글\s*", "", title).strip()

        notice["is_new"] = is_within_new_period(notice, now)
        notice.setdefault("relevance", None)
        notice.setdefault("relevance_reason", None)

    for crawled in crawled_notices:
        notice_id = crawled.get("id")
        if not notice_id:
            continue

        saved = saved_by_id.get(notice_id)

        # 처음 보는 공지면 추가한다.
        if saved is None:
            new_notice = dict(crawled)
            new_notice["is_new"] = True
            new_notice["collected_at"] = now.isoformat(timespec="seconds")
            new_notice.setdefault("relevance", None)
            new_notice.setdefault("relevance_reason", None)

            saved_notices.append(new_notice)
            saved_by_id[notice_id] = new_notice
            continue

        # 기존 본문이 비어 있고 이번 수집에서 본문을 얻었으면 본문을 채운다.
        old_body = (saved.get("body") or "").strip()
        new_body = (crawled.get("body") or "").strip()

        if not old_body and new_body:
            saved["body"] = crawled["body"]
            saved["images"] = crawled.get(
                "images",
                saved.get("images", []),
            )
            saved["extracted"] = False
            saved["processed"] = False
            saved["relevance"] = None
            saved["relevance_reason"] = None

    return saved_notices


if __name__ == "__main__":
    saved_notices = load_saved_notices()

    # 본문이 이미 저장된 공지는 상세 페이지 수집을 건너뛴다.
    skip_ids = {
        notice["id"]
        for notice in saved_notices
        if notice.get("id") and (notice.get("body") or "").strip()
    }

    crawled_notices = crawl_all_boards(skip_ids)
    notices = merge_notices(crawled_notices)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(notices, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"\n총 {len(notices)}개 공지를 저장했습니다: "
        f"{OUTPUT_PATH}"
    )