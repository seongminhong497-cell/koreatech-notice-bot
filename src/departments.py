"""한기대 학부(과) 이름 목록과, 공지마다 다르게 적힌 이름을 맞추는 함수.

AI가 뽑은 대상 학과(ai_extract.py)와 사용자 설정(apply_settings.py)이
같은 이름을 써야 관련도 계산에서 학과가 제대로 비교된다.

직접 실행하면 이미 저장된 공지와 프로필의 학과 이름도 표준 이름으로 바꾼다.
  python src/departments.py
"""

import json
import os

NOTICES_PATH = "data/notices.json"
PROFILE_PATH = "data/profile.json"

# 설정 양식에서 고를 수 있는 이름. 2026학년도 학제 개편 기준
DEPARTMENTS = [
    "기계공학부",
    "메카트로닉스공학부",
    "전기·전자·통신공학부",
    "컴퓨터공학부",
    "디자인공학과",
    "건축공학과",
    "에너지신소재화학공학부",
    "산업경영학부",
    "고용서비스정책학과",
    "미래융합학부",
    "반도체·디스플레이공학과",
]

# 공지에 자주 나오는 다른 이름 → 목록의 이름 (띄어쓰기와 가운뎃점은 빼고 비교)
_ALIASES = {
    "전기전자통신공학부": ["전기·전자·통신공학부"],
    "전자전기통신공학부": ["전기·전자·통신공학부"],
    "전기전자공학전공": ["전기·전자·통신공학부"],
    "전자공학전공": ["전기·전자·통신공학부"],
    "전기공학전공": ["전기·전자·통신공학부"],
    "정보통신공학전공": ["전기·전자·통신공학부"],
    "컴퓨터공학전공": ["컴퓨터공학부"],
    "ai/sw전공": ["컴퓨터공학부"],
    "aisw전공": ["컴퓨터공학부"],
    "기계공학전공": ["기계공학부"],
    "기계설계공학전공": ["기계공학부"],
    "디자인공학전공": ["디자인공학과"],
    "건축공학전공": ["건축공학과"],
    "디자인건축공학부": ["디자인공학과", "건축공학과"],
    "에너지신소재공학전공": ["에너지신소재화학공학부"],
    "화학생명공학전공": ["에너지신소재화학공학부"],
    "경영학과": ["산업경영학부"],
    "경영학부": ["산업경영학부"],
    "경영학전공": ["산업경영학부"],
    "융합경영전공": ["산업경영학부"],
    "반도체디스플레이공학과": ["반도체·디스플레이공학과"],
}


def _key(name):
    """비교용: 띄어쓰기, 가운뎃점(·ㆍ•), 마침표를 빼고 소문자로."""
    for ch in " ·ㆍ•.":
        name = name.replace(ch, "")
    return name.lower()


_CANONICAL = {_key(d): [d] for d in DEPARTMENTS}
_CANONICAL.update({_key(k): v for k, v in _ALIASES.items()})


def normalize_departments(names):
    """학과 이름 목록을 표준 이름으로 바꾼다. 모르는 이름은 그대로 둔다."""
    if not isinstance(names, list):
        return names
    result = []
    for name in names:
        for fixed in _CANONICAL.get(_key(name), [name]):
            if fixed not in result:
                result.append(fixed)
    return result


def normalize_notices(notices):
    """저장된 공지들의 target.departments를 표준 이름으로 바꾼다. 바꾼 개수를 돌려준다."""
    changed = 0
    for notice in notices:
        target = notice.get("target")
        if not isinstance(target, dict):
            continue
        names = target.get("departments")
        fixed = normalize_departments(names)
        if fixed != names:
            target["departments"] = fixed
            changed += 1
    return changed


def normalize_profile(profile):
    """프로필의 학과 이름을 표준 이름으로 바꾼다. 바꿨으면 True."""
    name = profile.get("department")
    if not isinstance(name, str) or not name:
        return False
    fixed = normalize_departments([name])
    if len(fixed) == 1 and fixed[0] != name:
        profile["department"] = fixed[0]
        return True
    return False


def _write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def normalize_files(notices_path=NOTICES_PATH, profile_path=PROFILE_PATH):
    """notices.json과 profile.json의 학과 이름을 표준 이름으로 바꾼다. 바뀐 게 없으면 파일을 안 쓴다."""
    if os.path.exists(notices_path):
        with open(notices_path, encoding="utf-8") as f:
            data = json.load(f)
        notices = data["notices"] if isinstance(data, dict) else data
        changed = normalize_notices(notices)
        if changed:
            _write_json(notices_path, data)
        print(f"공지 학과 이름 통일: {changed}개 바꿈")
    if os.path.exists(profile_path):
        with open(profile_path, encoding="utf-8") as f:
            profile = json.load(f)
        if normalize_profile(profile):
            _write_json(profile_path, profile)
            print(f"프로필 학과 이름 통일: {profile['department']}")


if __name__ == "__main__":
    normalize_files()
