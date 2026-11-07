"""
디스코드 아침 브리핑 (D 담당)

data/notices.json, data/weather.json, data/profile.json을 읽어서
오늘 날씨 / 마감 임박 / 새 공지를 정리한 브리핑을 디스코드 웹후크로 보낸다.

실행:
  python src/discord_notify.py            # 디스코드로 보내기 (DISCORD_WEBHOOK 필요)
  python src/discord_notify.py --dry-run  # 보내지 않고 화면에만 출력 (테스트용)
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
MAX_PER_SECTION = 8   # 구역마다 최대 몇 개까지 보여줄지


def load_json(path, default):
    """파일이 없거나 깨져 있으면 기본값을 돌려준다."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"{path}를 읽지 못해서 기본값을 씁니다: {e}")
        return default


def today_kst():
    return datetime.datetime.now(KST).date()


def days_left(deadline):
    """마감일까지 남은 날 수. 마감이 없거나 형식이 이상하면 None."""
    if not deadline:
        return None
    try:
        d = datetime.date.fromisoformat(deadline[:10])
    except ValueError:
        return None
    return (d - today_kst()).days


def dday_text(n):
    left = days_left(n.get("deadline"))
    if left is None:
        return ""
    if left == 0:
        dl = n["deadline"]
        return f"오늘 {dl[11:16]}" if len(dl) > 10 else "오늘 마감"
    return f"D-{left}"


def stars(relevance):
    if isinstance(relevance, int) and relevance > 0:
        return "★" * relevance
    return "관련도 미정"


def is_urgent(n, profile):
    """D-3 이내면 마감 임박, 준비물이 있으면 D-7부터."""
    left = days_left(n.get("deadline"))
    if left is None or left < 0:
        return False
    limit = profile.get("urgent_days", 3)
    if n.get("materials"):
        limit = profile.get("preparation_days", 7)
    return left <= limit


def line(n, new_mark=False):
    """[분류] 제목 | 관련도 | D-day  + 다음 줄에 한 줄 요약"""
    parts = [f"[{n.get('category') or '미분류'}] {n.get('title', '(제목 없음)')}",
             stars(n.get("relevance"))]
    dd = dday_text(n)
    if dd:
        parts.append(dd)
    text = " | ".join(parts)
    if new_mark and n.get("is_new"):
        text = "🆕 " + text
    if n.get("url"):
        text = f"{text}\n   <{n['url']}>"   # <> 로 감싸면 링크 미리보기가 안 붙음
    summary = n.get("relevance_reason") or summary_from(n)
    if summary:
        text += f"\n   └ {summary}"
    return "• " + text


def summary_from(n):
    """관련도 이유가 없을 때 할 일·준비물로 한 줄 만들기."""
    bits = []
    if n.get("actions"):
        bits.append(", ".join(n["actions"]))
    if n.get("materials"):
        bits.append("준비물: " + ", ".join(n["materials"]))
    return " / ".join(bits)


def sort_key(n):
    """관련도 높은 순 → 마감 가까운 순"""
    rel = n.get("relevance") if isinstance(n.get("relevance"), int) else 0
    left = days_left(n.get("deadline"))
    return (-rel, left if left is not None else 9999)


def build_briefing(notices, weather, profile):
    # 숨김(0)과 지난 마감 공지는 빼기
    visible = [n for n in notices
               if n.get("relevance") != 0
               and not ((days_left(n.get("deadline")) or 0) < 0)]

    urgent = sorted([n for n in visible if is_urgent(n, profile)], key=sort_key)
    urgent_ids = {n.get("id") for n in urgent}
    # 마감 임박에 오른 공지는 새 공지에서 뺀다
    new = sorted([n for n in visible if n.get("is_new") and n.get("id") not in urgent_ids],
                 key=sort_key)

    today = today_kst()
    weekday = "월화수목금토일"[today.weekday()]
    lines = [f"☀️ **{today.month}월 {today.day}일 ({weekday}) 아침 브리핑**", ""]

    if weather and weather.get("summary"):
        lines.append(f"🌤 **오늘 날씨** ({weather.get('location', '학교')}): {weather['summary']}")
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
    notices = load_json(NOTICES_PATH, [])
    weather = load_json(WEATHER_PATH, None)
    profile = load_json(PROFILE_PATH, {})

    messages = split_messages(build_briefing(notices, weather, profile))

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
