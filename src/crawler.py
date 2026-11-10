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
]

HEADERS = {"User-Agent": "Mozilla/5.0"}

MAX_ATTEMPTS = 3

def get_response(url):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=15,
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

KST = timezone(timedelta(hours=9))

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
    """게시판 장식용 아이콘은 이미지 목록에서 제외한다."""
    image_path = unquote(urlparse(image_url).path).lower()
    return "/upload/skin/board/basic/" in image_path


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
        "script, style, noscript, button, .share, .sns"
    ):
        unwanted.decompose()

    raw_text = extract_text_preserving_spacing(content)
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


def crawl_board(board):
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
        detail_url = urljoin(board_url, title_link["href"])
        published_date = (
            date_cell.get_text(strip=True)
            if date_cell
            else None
        )

        query = parse_qs(urlparse(detail_url).query)
        post_seq = query.get("post_seq", [detail_url])[0]

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
            "id": f"{board['id_prefix']}-{post_seq}",
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


def crawl_all_boards():
    """설정된 게시판을 모두 수집한다."""
    all_notices = []

    for board in BOARDS:
        print(f"\n수집 중: {board['source']}", file=sys.stderr)

        try:
            board_notices = crawl_board(board)
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
    crawled_notices = crawl_all_boards()
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