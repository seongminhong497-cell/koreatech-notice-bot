"""
디스코드 아침 브리핑 (D 담당)

data/notices.json, data/weather.json, data/profile.json을 읽어서
오늘 날씨 / 마감 임박 / 새 공지를 정리한 브리핑을 디스코드 웹후크로 보낸다.

보내는 공지 조건:
  - 예시 공지(is_sample: true)가 아님
  - AI 정리(extracted)와 관련도 계산(processed)이 모두 끝남
  - 관련도가 0(숨김)이 아님
  - 마감이 아직 지나지 않음 (마감 시각이 있으면 현재 한국 시간과 비교)

실행:
  python src/discord_notify.py                      # 디스코드로 보내기 (DISCORD_WEBHOOK 필요)
  python src/discord_notify.py --dry-run            # 보내지 않고 화면에만 출력
  python src/discord_notify.py --dry-run --samples  # 예시·미처리 공지도 포함해서 모양 확인
"""

import datetime
import json
import os
import sys

import requests

NOTICES_PATH = "data/notices.json"
WEATHER_PATH = "data/weather.json"
PROFILE_PATH = "data/profile.json"
PAGE_URL = "https://seongminhong497-cell.github.io/koreatech-notice-bot/"

KST = datetime.timezone(datetime.timedelta(hours=9))
MAX_LEN = 1900        # 디스코드 메시지 한 개 최대 2000자 (여유를 둠)
MAX_PER_SECTION = 5   # 구역마다 최대 몇 개까지 보여줄지 (나머지는 웹페이지에서)


def load_json(path, default):
    """파일이 없거나 깨져 있으면 기본값을 돌려준다."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"{path}를 읽지 못해서 기본값을 씁니다: {e}")
        return default


def now_kst():
    return datetime.datetime.now(KST)


def parse_deadline(deadline):
    """마감 문자열을 (날짜, 시각 또는 None)으로 바꾼다. 형식이 이상하면 (None, None)."""
    if not deadline:
        return None, None
    try:
        if len(deadline) > 10:
            dt = datetime.datetime.fromisoformat(deadline)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            dt = dt.astimezone(KST)
            return dt.date(), dt
        return datetime.date.fromisoformat(deadline), None
    except ValueError:
        return None, None


def is_expired(n):
    """마감이 지났는지. 시각이 있으면 지금 시각과, 날짜만 있으면 그날 끝까지 유효."""
    day, moment = parse_deadline(n.get("deadline"))
    if day is None:
        return False
    if moment is not None:
        return moment <= now_kst()
    return day < now_kst().date()


def days_left(n):
    """마감일까지 남은 날 수 (날짜 기준). 마감이 없으면 None."""
    day, _ = parse_deadline(n.get("deadline"))
    if day is None:
        return None
    return (day - now_kst().date()).days


def dday_text(n):
    left = days_left(n)
    if left is None:
        return ""
    if left == 0:
        _, moment = parse_deadline(n.get("deadline"))
        return f"오늘 {moment:%H:%M}" if moment else "오늘 마감"
    return f"D-{left}"


def stars(relevance):
    if isinstance(relevance, int) and relevance > 0:
        return "★" * relevance
    return "관련도 미정"


def is_urgent(n, profile):
    """D-3 이내면 마감 임박, 준비물이 있으면 D-7부터."""
    left = days_left(n)
    if left is None or is_expired(n):
        return False
    limit = profile.get("urgent_days", 3)
    if n.get("materials"):
        limit = profile.get("preparation_days", 7)
    return left <= limit


def cut(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summary_from(n):
    """관련도 이유가 없을 때 할 일·준비물로 한 줄 만들기."""
    bits = []
    if n.get("actions"):
        bits.append(", ".join(n["actions"]))
    if n.get("materials"):
        bits.append("준비물: " + ", ".join(n["materials"]))
    return " / ".join(bits)


def md_escape(text):
    """디스코드 마크다운에서 특별한 뜻이 있는 글자 앞에 \\ 를 붙인다."""
    for ch in "\\[]()*_~`|>":
        text = text.replace(ch, "\\" + ch)
    return text


def line(n, new_mark=False):
    """• [분류] 제목(링크) · ★★★ · D-day  + 다음 줄에 한 줄 요약"""
    title = md_escape(cut(n.get("title") or "(제목 없음)", 80))
    url = (n.get("url") or "").replace("&prefix_id=", "")   # 빈 값 주소 조각은 빼서 길이 줄이기
    if url and len(url) <= 500 and " " not in url:
        title = f"[{title}](<{url}>)"   # 제목을 누르면 공지로 이동, <> 는 미리보기 끄기
    parts = [f"`{n.get('category') or '미분류'}` {title}", stars(n.get("relevance"))]
    dd = dday_text(n)
    if dd:
        parts.append(f"**{dd}**")
    text = " · ".join(parts)
    if new_mark and n.get("is_new"):
        text = "🆕 " + text
    summary = n.get("relevance_reason") or summary_from(n)
    if summary:
        text += f"\n   └ {md_escape(cut(summary, 100))}"
    return "• " + text


def sort_key(n):
    """관련도 높은 순 → 마감 가까운 순"""
    rel = n.get("relevance") if isinstance(n.get("relevance"), int) else 0
    left = days_left(n)
    return (-rel, left if left is not None else 9999)


def is_sendable(n, include_samples=False):
    if include_samples:
        return n.get("relevance") != 0 and not is_expired(n)
    return (
        not n.get("is_sample")
        and n.get("extracted") is True
        and n.get("processed") is True
        and n.get("relevance") != 0
        and not is_expired(n)
    )


def build_briefing(notices, weather, profile, include_samples=False):
    visible = [n for n in notices if is_sendable(n, include_samples)]

    urgent = sorted([n for n in visible if is_urgent(n, profile)], key=sort_key)
    urgent_ids = {n.get("id") for n in urgent}
    # 마감 임박에 오른 공지는 새 공지에서 뺀다
    new = sorted([n for n in visible if n.get("is_new") and n.get("id") not in urgent_ids],
                 key=sort_key)

    today = now_kst().date()
    weekday = "월화수목금토일"[today.weekday()]
    lines = [f"☀️ **{today.month}월 {today.day}일 ({weekday}) 아침 브리핑**", ""]

    if weather and weather.get("summary"):
        lines.append(f"🌤 **오늘 날씨** ({weather.get('location', '학교')}): {cut(weather['summary'], 300)}")
    else:
        lines.append("🌤 **오늘 날씨**: 정보를 가져오지 못했어요")
    lines.append("")

    lines.append(f"⏰ **마감 임박** ({len(urgent)}개)")
    lines += [line(n, new_mark=True) for n in urgent[:MAX_PER_SECTION]] or ["• 없음"]
    if len(urgent) > MAX_PER_SECTION:
        lines.append(f"• …외 {len(urgent) - MAX_PER_SECTION}개")
    lines.append("")

    lines.append(f"🆕 **새 공지** ({len(new)}개)")
    lines += [line(n) for n in new[:MAX_PER_SECTION]] or ["• 없음"]
    if len(new) > MAX_PER_SECTION:
        lines.append(f"• …외 {len(new) - MAX_PER_SECTION}개")
    lines.append("")

    lines.append(f"📋 전체 보기: {PAGE_URL}")
    return lines


def split_messages(lines):
    """2000자 제한에 맞춰 여러 메시지로 나누기 (공지 한 개는 중간에 안 자름)."""
    messages, cur = [], ""
    for l in lines:
        l = cut(l, MAX_LEN - 1)
        if len(cur) + len(l) + 1 > MAX_LEN and cur:
            messages.append(cur)
            cur = ""
        cur += l + "\n"
    if cur.strip():
        messages.append(cur)
    return messages


def send(webhook, messages):
    for i, msg in enumerate(messages, 1):
        r = requests.post(webhook, json={"content": msg}, timeout=15)
        if r.status_code >= 300:
            print(f"디스코드 전송 실패 ({i}/{len(messages)}): {r.status_code} {r.text[:200]}")
            return False
    print(f"디스코드로 브리핑을 보냈습니다 ({len(messages)}개 메시지)")
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    include_samples = dry_run and "--samples" in sys.argv
    notices = load_json(NOTICES_PATH, [])
    weather = load_json(WEATHER_PATH, None)
    profile = load_json(PROFILE_PATH, {})

    messages = split_messages(build_briefing(notices, weather, profile, include_samples))

    webhook = os.environ.get("DISCORD_WEBHOOK")
    if dry_run or not webhook:
        if not webhook and not dry_run:
            print("DISCORD_WEBHOOK이 없어서 보내지 않고 화면에만 출력합니다.")
        for m in messages:
            print(m)
            print("-" * 40)
        return

    if not send(webhook, messages):
        sys.exit(1)


if __name__ == "__main__":
    main()"""
디스코드 아침 브리핑 (D 담당)

data/notices.json, data/weather.json, data/profile.json을 읽어서
오늘 날씨 / 마감 임박 / 새 공지를 정리한 브리핑을 디스코드 웹후크로 보낸다.

보내는 공지 조건:
  - 예시 공지(is_sample: true)가 아님
  - AI 정리(extracted)와 관련도 계산(processed)이 모두 끝남
  - 관련도가 0(숨김)이 아님
  - 마감이 아직 지나지 않음 (마감 시각이 있으면 현재 한국 시간과 비교)

실행:
  python src/discord_notify.py                      # 디스코드로 보내기 (DISCORD_WEBHOOK 필요)
  python src/discord_notify.py --dry-run            # 보내지 않고 화면에만 출력
  python src/discord_notify.py --dry-run --samples  # 예시·미처리 공지도 포함해서 모양 확인
"""

import datetime
import json
import os
import sys

import requests

NOTICES_PATH = "data/notices.json"
WEATHER_PATH = "data/weather.json"
PROFILE_PATH = "data/profile.json"
PAGE_URL = "https://seongminhong497-cell.github.io/koreatech-notice-bot/"

KST = datetime.timezone(datetime.timedelta(hours=9))
MAX_LEN = 1900        # 디스코드 메시지 한 개 최대 2000자 (여유를 둠)
MAX_PER_SECTION = 5   # 구역마다 최대 몇 개까지 보여줄지 (나머지는 웹페이지에서)


def load_json(path, default):
    """파일이 없거나 깨져 있으면 기본값을 돌려준다."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"{path}를 읽지 못해서 기본값을 씁니다: {e}")
        return default


def now_kst():
    return datetime.datetime.now(KST)


def parse_deadline(deadline):
    """마감 문자열을 (날짜, 시각 또는 None)으로 바꾼다. 형식이 이상하면 (None, None)."""
    if not deadline:
        return None, None
    try:
        if len(deadline) > 10:
            dt = datetime.datetime.fromisoformat(deadline)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            dt = dt.astimezone(KST)
            return dt.date(), dt
        return datetime.date.fromisoformat(deadline), None
    except ValueError:
        return None, None


def is_expired(n):
    """마감이 지났는지. 시각이 있으면 지금 시각과, 날짜만 있으면 그날 끝까지 유효."""
    day, moment = parse_deadline(n.get("deadline"))
    if day is None:
        return False
    if moment is not None:
        return moment <= now_kst()
    return day < now_kst().date()


def days_left(n):
    """마감일까지 남은 날 수 (날짜 기준). 마감이 없으면 None."""
    day, _ = parse_deadline(n.get("deadline"))
    if day is None:
        return None
    return (day - now_kst().date()).days


def dday_text(n):
    left = days_left(n)
    if left is None:
        return ""
    if left == 0:
        _, moment = parse_deadline(n.get("deadline"))
        return f"오늘 {moment:%H:%M}" if moment else "오늘 마감"
    return f"D-{left}"


def stars(relevance):
    if isinstance(relevance, int) and relevance > 0:
        return "★" * relevance
    return "관련도 미정"


def is_urgent(n, profile):
    """D-3 이내면 마감 임박, 준비물이 있으면 D-7부터."""
    left = days_left(n)
    if left is None or is_expired(n):
        return False
    limit = profile.get("urgent_days", 3)
    if n.get("materials"):
        limit = profile.get("preparation_days", 7)
    return left <= limit


def cut(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summary_from(n):
    """관련도 이유가 없을 때 할 일·준비물로 한 줄 만들기."""
    bits = []
    if n.get("actions"):
        bits.append(", ".join(n["actions"]))
    if n.get("materials"):
        bits.append("준비물: " + ", ".join(n["materials"]))
    return " / ".join(bits)


def md_escape(text):
    """디스코드 마크다운에서 특별한 뜻이 있는 글자 앞에 \\ 를 붙인다."""
    for ch in "\\[]()*_~`|>":
        text = text.replace(ch, "\\" + ch)
    return text


def line(n, new_mark=False):
    """• [분류] 제목(링크) · ★★★ · D-day  + 다음 줄에 한 줄 요약"""
    title = md_escape(cut(n.get("title") or "(제목 없음)", 80))
    url = (n.get("url") or "").replace("&prefix_id=", "")   # 빈 값 주소 조각은 빼서 길이 줄이기
    if url and len(url) <= 500 and " " not in url:
        title = f"[{title}](<{url}>)"   # 제목을 누르면 공지로 이동, <> 는 미리보기 끄기
    parts = [f"`{n.get('category') or '미분류'}` {title}", stars(n.get("relevance"))]
    dd = dday_text(n)
    if dd:
        parts.append(f"**{dd}**")
    text = " · ".join(parts)
    if new_mark and n.get("is_new"):
        text = "🆕 " + text
    summary = n.get("relevance_reason") or summary_from(n)
    if summary:
        text += f"\n   └ {md_escape(cut(summary, 100))}"
    return "• " + text


def sort_key(n):
    """관련도 높은 순 → 마감 가까운 순"""
    rel = n.get("relevance") if isinstance(n.get("relevance"), int) else 0
    left = days_left(n)
    return (-rel, left if left is not None else 9999)


def is_sendable(n, include_samples=False):
    if include_samples:
        return n.get("relevance") != 0 and not is_expired(n)
    return (
        not n.get("is_sample")
        and n.get("extracted") is True
        and n.get("processed") is True
        and n.get("relevance") != 0
        and not is_expired(n)
    )


def build_briefing(notices, weather, profile, include_samples=False):
    visible = [n for n in notices if is_sendable(n, include_samples)]

    urgent = sorted([n for n in visible if is_urgent(n, profile)], key=sort_key)
    urgent_ids = {n.get("id") for n in urgent}
    # 마감 임박에 오른 공지는 새 공지에서 뺀다
    new = sorted([n for n in visible if n.get("is_new") and n.get("id") not in urgent_ids],
                 key=sort_key)

    today = now_kst().date()
    weekday = "월화수목금토일"[today.weekday()]
    lines = [f"☀️ **{today.month}월 {today.day}일 ({weekday}) 아침 브리핑**", ""]

    if weather and weather.get("summary"):
        lines.append(f"🌤 **오늘 날씨** ({weather.get('location', '학교')}): {cut(weather['summary'], 300)}")
    else:
        lines.append("🌤 **오늘 날씨**: 정보를 가져오지 못했어요")
    lines.append("")

    lines.append(f"⏰ **마감 임박** ({len(urgent)}개)")
    lines += [line(n, new_mark=True) for n in urgent[:MAX_PER_SECTION]] or ["• 없음"]
    if len(urgent) > MAX_PER_SECTION:
        lines.append(f"• …외 {len(urgent) - MAX_PER_SECTION}개")
    lines.append("")

    lines.append(f"🆕 **새 공지** ({len(new)}개)")
    lines += [line(n) for n in new[:MAX_PER_SECTION]] or ["• 없음"]
    if len(new) > MAX_PER_SECTION:
        lines.append(f"• …외 {len(new) - MAX_PER_SECTION}개")
    lines.append("")

    lines.append(f"📋 전체 보기: {PAGE_URL}")
    return lines


def split_messages(lines):
    """2000자 제한에 맞춰 여러 메시지로 나누기 (공지 한 개는 중간에 안 자름)."""
    messages, cur = [], ""
    for l in lines:
        l = cut(l, MAX_LEN - 1)
        if len(cur) + len(l) + 1 > MAX_LEN and cur:
            messages.append(cur)
            cur = ""
        cur += l + "\n"
    if cur.strip():
        messages.append(cur)
    return messages


def send(webhook, messages):
    for i, msg in enumerate(messages, 1):
        r = requests.post(webhook, json={"content": msg}, timeout=15)
        if r.status_code >= 300:
            print(f"디스코드 전송 실패 ({i}/{len(messages)}): {r.status_code} {r.text[:200]}")
            return False
    print(f"디스코드로 브리핑을 보냈습니다 ({len(messages)}개 메시지)")
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    include_samples = dry_run and "--samples" in sys.argv
    notices = load_json(NOTICES_PATH, [])
    weather = load_json(WEATHER_PATH, None)
    profile = load_json(PROFILE_PATH, {})

    messages = split_messages(build_briefing(notices, weather, profile, include_samples))

    webhook = os.environ.get("DISCORD_WEBHOOK")
    if dry_run or not webhook:
        if not webhook and not dry_run:
            print("DISCORD_WEBHOOK이 없어서 보내지 않고 화면에만 출력합니다.")
        for m in messages:
            print(m)
            print("-" * 40)
        return

    if not send(webhook, messages):
        sys.exit(1)


if __name__ == "__main__":
    main()
