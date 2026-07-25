from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SEARCH_URL = "https://faculty.hqu.edu.cn/search.jsp?urltype=tree.TreeTempUrl&wbtreeid=1006"
API_URL = "https://faculty.hqu.edu.cn/system/resource/tsites/advancesearch.jsp"


def fetch_text(url: str, params: dict[str, Any] | None = None) -> str:
    if params:
        url = url + "?" + urllib.parse.urlencode(params, doseq=False)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "QinmianAI/0.1 (+local student planning prototype)",
            "Referer": SEARCH_URL,
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def clean_label(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw)
    text = html.unescape(text)
    text = re.sub(r"^[|\-]+", "", text)
    return " ".join(text.split()).strip()


def parse_options(page: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    colleges = []
    for match in re.finditer(r'<p id="xy(\d+)" onclick="create_advance_search_conditon\.selectByCollege\(this,(\d+)\)">(.*?)</p>', page, re.S):
        raw_text = match.group(3)
        label = clean_label(raw_text)
        depth = raw_text.count("-")
        if not label or depth < 6:
            continue
        colleges.append({"id": int(match.group(2)), "name": label, "depth": depth})

    ranks = []
    for match in re.finditer(r'<p class="by_rank" id="(\d+)" onclick="create_advance_search_conditon\.selectByRank\(this,(\d+)\)">(.*?)</p>', page, re.S):
        label = clean_label(match.group(3))
        if label:
            ranks.append({"id": int(match.group(2)), "name": label})
    return colleges, ranks


def query_api(pageindex: int, pagesize: int = 100, collegeid: int = 0, rankid: int = 0) -> dict[str, Any]:
    params = {
        "collegeid": collegeid,
        "disciplineid": 0,
        "enrollid": 0,
        "pageindex": pageindex,
        "pagesize": pagesize,
        "rankid": rankid,
        "degreeid": 0,
        "honorid": 0,
        "pinyin": "",
        "profilelen": 100,
        "teacherName": "",
        "searchDirection": "",
        "viewmode": 8,
        "viewid": 1063586,
        "siteOwner": 1980162466,
        "viewUniqueId": 1063586,
        "showlang": "zh_CN",
        "ispreview": "false",
        "basenum": 0,
        "ellipsis": "...",
        "alignright": "false",
        "productType": 0,
        "tutorType": "",
    }
    raw = fetch_text(API_URL, params)
    return json.loads(raw)


def normalize_teacher(row: dict[str, Any]) -> dict[str, Any]:
    homepage = str(row.get("url") or "")
    return {
        "faculty_uid": row.get("uid"),
        "teacher_id": str(row.get("teacherId") or ""),
        "name": str(row.get("teacherName") or row.get("name") or row.get("showName") or "").strip(),
        "english_name": str(row.get("ename") or "").strip(),
        "gender": str(row.get("sex") or "").strip(),
        "title": str(row.get("prorank") or "").strip(),
        "unit_raw": str(row.get("unit") or "").strip(),
        "profile": str(row.get("profile") or "").strip(),
        "graduate_tutor": str(row.get("gtutor") or "").strip(),
        "doctor_tutor": str(row.get("doctorTutor") or "").strip(),
        "academician": str(row.get("academician") or "").strip(),
        "homepage": homepage,
        "pic_url": urllib.parse.urljoin("https://faculty.hqu.edu.cn/", str(row.get("picUrl") or "")),
        "click_times": int(row.get("clickTimes") or 0),
        "colleges": [],
        "college_ids": [],
        "matched_roster_colleges": [],
    }


def merge_record(records: dict[str, dict[str, Any]], row: dict[str, Any], college: dict[str, Any] | None = None) -> None:
    normalized = normalize_teacher(row)
    if not normalized["name"]:
        return
    key = normalized["teacher_id"] or normalized["homepage"] or normalized["name"]
    existing = records.setdefault(key, normalized)
    for field in ["english_name", "gender", "title", "unit_raw", "profile", "graduate_tutor", "doctor_tutor", "academician", "homepage", "pic_url"]:
        if not existing.get(field) and normalized.get(field):
            existing[field] = normalized[field]
    existing["click_times"] = max(int(existing.get("click_times") or 0), int(normalized.get("click_times") or 0))
    if college:
        if college["name"] not in existing["colleges"]:
            existing["colleges"].append(college["name"])
        if college["id"] not in existing["college_ids"]:
            existing["college_ids"].append(college["id"])


def add_roster_colleges(records: dict[str, dict[str, Any]]) -> None:
    roster_path = DATA_DIR / "teacher_roster.json"
    if not roster_path.exists():
        return
    payload = json.loads(roster_path.read_text(encoding="utf-8"))
    by_name: dict[str, list[str]] = {}
    for row in payload.get("teachers", []):
        name = str(row.get("name") or "").strip()
        college = str(row.get("college") or "").strip()
        if name and college:
            by_name.setdefault(name, [])
            if college not in by_name[name]:
                by_name[name].append(college)
    for record in records.values():
        for college in by_name.get(record["name"], []):
            if college not in record["matched_roster_colleges"]:
                record["matched_roster_colleges"].append(college)
            if college not in record["colleges"]:
                record["colleges"].append(college)


def main() -> None:
    page = fetch_text(SEARCH_URL)
    colleges, ranks = parse_options(page)
    records: dict[str, dict[str, Any]] = {}

    first = query_api(pageindex=1, pagesize=100)
    totalpage = int(first.get("totalpage") or 1)
    for row in first.get("teacherData", []):
        merge_record(records, row)
    for pageindex in range(2, totalpage + 1):
        payload = query_api(pageindex=pageindex, pagesize=100)
        for row in payload.get("teacherData", []):
            merge_record(records, row)
        time.sleep(0.05)

    for college in colleges:
        payload = query_api(pageindex=1, pagesize=100, collegeid=college["id"])
        pages = int(payload.get("totalpage") or 1)
        for row in payload.get("teacherData", []):
            merge_record(records, row, college)
        for pageindex in range(2, pages + 1):
            payload = query_api(pageindex=pageindex, pagesize=100, collegeid=college["id"])
            for row in payload.get("teacherData", []):
                merge_record(records, row, college)
            time.sleep(0.05)
        time.sleep(0.03)

    add_roster_colleges(records)

    teachers = sorted(
        records.values(),
        key=lambda item: ((item.get("colleges") or [""])[0], item.get("title", ""), item.get("name", "")),
    )
    payload = {
        "source": {
            "name": "华侨大学教师主页中文门户教师检索",
            "url": SEARCH_URL,
            "api": API_URL,
            "imported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "official_total": int(first.get("totalnum") or len(teachers)),
        },
        "colleges": colleges,
        "ranks": ranks,
        "teachers": teachers,
    }
    out = DATA_DIR / "faculty_profiles.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} with {len(teachers)} teacher profiles, {len(colleges)} colleges, {len(ranks)} ranks")


if __name__ == "__main__":
    main()
