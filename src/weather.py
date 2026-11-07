"""B 파트: 기상청 단기예보로 오늘 날씨를 가져온다. 기본은 한기대 1캠퍼스.

사용법
    python src/weather.py
결과를 화면에 보여주고 data/weather.json에 저장한다.
"""

import datetime
import json
import os

import requests

URL = (
    "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/"
    "getVilageFcst"
)
# 지역 이름별 기상청 격자 좌표. 설정에서 지역을 고르게 되면 여기에 추가한다.
LOCATIONS = {
    "한기대": (65, 109),  # 1캠퍼스(천안 병천면), 기본값
}
DEFAULT_LOCATION = "한기대"
SAVE_PATH = "data/weather.json"
KST = datetime.timezone(datetime.timedelta(hours=9))  # 한국 시간

SKY = {"1": "맑음", "3": "구름많음", "4": "흐림"}
PTY = {"1": "비", "2": "비/눈", "3": "눈", "4": "소나기"}


def pick_base(now):
    """오늘 하루 예보가 전부 들어 있는 발표 시각을 고른다.

    02시 발표에 오늘 최저·최고기온이 모두 들어 있다.
    발표 후 10분쯤 지나야 받을 수 있어서 02:15 전이면 전날 23시 발표를 쓴다.
    """
    if now.hour > 2 or (now.hour == 2 and now.minute >= 15):
        return now.strftime("%Y%m%d"), "0200"
    yesterday = now - datetime.timedelta(days=1)
    return yesterday.strftime("%Y%m%d"), "2300"


def fetch_items(base_date, base_time, nx, ny):
    """기상청 API를 불러 예보 항목 목록을 받는다."""
    params = {
        "serviceKey": os.environ["WEATHER_API_KEY"],
        "pageNo": 1,
        "numOfRows": 1000,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }
    res = requests.get(URL, params=params, timeout=20)
    res.raise_for_status()

    # 키 오류 같은 경우 JSON이 아니라 XML로 답이 와서 따로 확인한다
    if res.text.lstrip().startswith("<"):
        raise RuntimeError("기상청 API 오류 응답: " + res.text[:300])

    body = res.json()["response"]
    code = body["header"]["resultCode"]
    if code != "00":
        raise RuntimeError("기상청 API 오류: " + body["header"]["resultMsg"])
    return body["body"]["items"]["item"]


def summarize(items, day, location):
    """오늘(day) 예보만 골라 최저·최고기온, 강수확률, 하늘 상태로 정리한다."""
    today = [x for x in items if x["fcstDate"] == day]
    if not today:
        return None

    def values(category, start="0000", end="2400"):
        return [
            x["fcstValue"] for x in today
            if x["category"] == category and start <= x["fcstTime"] < end
        ]

    temps = [float(v) for v in values("TMP")]
    low = values("TMN")
    high = values("TMX")
    t_min = round(float(low[0])) if low else round(min(temps))
    t_max = round(float(high[0])) if high else round(max(temps))

    # 학생이 밖에 다니는 시간(06~21시) 기준
    pops = [int(v) for v in values("POP", "0600", "2100")]
    pop = max(pops) if pops else 0
    ptys = [v for v in values("PTY", "0600", "2100") if v in PTY]
    sky_morning = values("SKY", "0900", "1000")
    sky = SKY.get(sky_morning[0], "") if sky_morning else ""

    rain = PTY[ptys[0]] if ptys else None
    words = [rain or sky, f"{t_min}~{t_max}도", f"강수확률 {pop}%"]
    summary = ", ".join(w for w in words if w)
    if rain or pop >= 60:
        summary += " (우산 챙기세요)"

    return {
        "location": location,
        "date": f"{day[:4]}-{day[4:6]}-{day[6:]}",
        "min": t_min,
        "max": t_max,
        "pop": pop,
        "sky": sky or None,
        "rain": rain,
        "summary": summary,
    }


def get_weather(location=DEFAULT_LOCATION, now=None):
    """오늘 날씨를 정리해서 돌려준다. 모르는 지역이면 학교 날씨를 쓴다."""
    if location not in LOCATIONS:
        location = DEFAULT_LOCATION
    nx, ny = LOCATIONS[location]
    now = now or datetime.datetime.now(KST)
    base_date, base_time = pick_base(now)
    items = fetch_items(base_date, base_time, nx, ny)
    return summarize(items, now.strftime("%Y%m%d"), location)


if __name__ == "__main__":
    weather = get_weather()
    print(json.dumps(weather, ensure_ascii=False, indent=2))
    os.makedirs(os.path.dirname(SAVE_PATH), exist_ok=True)
    with open(SAVE_PATH, "w", encoding="utf-8") as f:
        json.dump(weather, f, ensure_ascii=False, indent=2)
