"""
课程难度分析引擎 v2.0
=====================
从教务系统数据 + 评价数据中提取多维度特征，计算课程难度并输出星级评定。

数据源：
  1. data/imported_course_info.xlsx    — 教务系统原始课程汇总（~6090条）
  2. data/course_assignments.json      — 课程安排 JSON（~6198条）
  3. data/course_reviews.json          — 论坛评价（有限，持续扩充）
  4. data/curriculum_templates.json    — 培养方案模板（含课程分类）

难度维度（每项归一化 0-100）：
  - 学分强度 (credit_intensity)        权重 15%  — 学分越高负荷越重
  - 课程类别难度 (category_difficulty)   权重 30%  — 专业必修/学科基础 > 通识选修
  - 知识复杂度 (knowledge_complexity)   权重 20%  — 从课程名提取的领域知识密度
  - 专业化程度 (specialization)        权重 15%  — 面向专业越少越专精
  - 教学强度 (teaching_intensity)      权重 10%  — 师资集中度 + 开课频次
  - 评价反馈 (review_score)            权重 10%  — 来自真实评价的难度感知

星级阈值（基于实际分数分布校准）：
  ⭐⭐⭐⭐⭐ (5) 非常硬核:  ≥ 65   — 顶尖难度的专业核心课
  ⭐⭐⭐⭐  (4) 较难:      ≥ 55   — 有区分度的专业课
  ⭐⭐⭐   (3) 中等难度:   ≥ 45   — 正常课业负担
  ⭐⭐    (2) 比较轻松:   ≥ 35   — 内容基础/技能型课程
  ⭐     (1) 非常轻松:   < 35   — 纯通识/讲座类课程
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# ── 路径 ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"


# ══════════════════════════════════════════════════════════════════════
# 第一部分：数据加载与融合
# ══════════════════════════════════════════════════════════════════════

def load_json(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_xlsx_courses() -> dict[str, dict[str, Any]]:
    """从 imported_course_info.xlsx 读取课程汇总数据"""
    try:
        import openpyxl
    except ImportError:
        print("[WARN] openpyxl 未安装，跳过 XLSX 导入", file=sys.stderr)
        return {}

    path = DATA_DIR / "imported_course_info.xlsx"
    if not path.exists():
        print(f"[WARN] {path} 不存在", file=sys.stderr)
        return {}

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["课程汇总"]
    courses: dict[str, dict[str, Any]] = {}

    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue
        _seq, course_name, credits, teacher, college, major, campus, term = row
        if not course_name:
            continue
        cname = str(course_name).strip()
        if cname not in courses:
            courses[cname] = {
                "name": cname,
                "xlsx_credits": set(),
                "teachers": set(),
                "majors": set(),
                "colleges_raw": set(),
                "campuses_raw": set(),
                "terms_raw": set(),
                "xlsx_count": 0,
            }
        info = courses[cname]
        if credits is not None:
            info["xlsx_credits"].add(float(credits))
        if teacher:
            info["teachers"].add(str(teacher).strip())
        if major:
            info["majors"].add(str(major).strip())
        if college:
            info["colleges_raw"].add(str(college).strip())
        if campus:
            info["campuses_raw"].add(str(campus).strip())
        if term:
            info["terms_raw"].add(str(term).strip())
        info["xlsx_count"] += 1

    wb.close()
    for cname in courses:
        for key in ("xlsx_credits", "teachers", "majors", "colleges_raw", "campuses_raw", "terms_raw"):
            courses[cname][key] = sorted(courses[cname][key])
    return courses


def load_assignments() -> dict[str, dict[str, Any]]:
    """从 course_assignments.json 读取课程安排数据"""
    doc = load_json("course_assignments.json")
    courses: dict[str, dict[str, Any]] = {}
    for a in doc.get("assignments", []):
        cname = a.get("course", "").strip()
        if not cname:
            continue
        if cname not in courses:
            courses[cname] = {
                "name": cname,
                "assign_credits": set(),
                "assign_teachers": set(),
                "assign_majors": set(),
                "assign_colleges": set(),
                "assign_campuses": set(),
                "assign_terms": set(),
                "assign_count": 0,
            }
        info = courses[cname]
        cr = a.get("credits")
        if cr is not None:
            info["assign_credits"].add(float(cr))
        t = a.get("teacher", "").strip()
        if t:
            info["assign_teachers"].add(t)
        for m in a.get("majors", []):
            if m:
                info["assign_majors"].add(m.strip())
        c = a.get("college", "").strip()
        if c:
            info["assign_colleges"].add(c)
        campus = a.get("campus", "").strip()
        if campus:
            info["assign_campuses"].add(campus)
        term = a.get("term", "").strip()
        if term:
            info["assign_terms"].add(term)
        info["assign_count"] += 1

    for cname in courses:
        for key in ("assign_credits", "assign_teachers", "assign_majors", "assign_colleges",
                      "assign_campuses", "assign_terms"):
            courses[cname][key] = sorted(courses[cname][key])
    return courses


def load_curriculum_info() -> dict[str, dict[str, Any]]:
    """从 curriculum_templates.json 提取课程分类"""
    doc = load_json("curriculum_templates.json")
    course_category: dict[str, str] = {}
    course_credits: dict[str, float] = {}
    for c in doc.get("common_courses", []):
        name = c.get("name", "").strip()
        if name:
            course_category[name] = c.get("category", "")
            course_credits[name] = float(c.get("credits", 0))
    for tpl in doc.get("templates", {}).values():
        for section in ("required", "electives"):
            for c in tpl.get(section, []):
                name = c.get("name", "").strip()
                if name and name not in course_category:
                    course_category[name] = c.get("category", "")
                    course_credits[name] = float(c.get("credits", 0))
    for c in doc.get("general_electives", []):
        name = c.get("name", "").strip()
        if name and name not in course_category:
            course_category[name] = c.get("category", "")
            course_credits[name] = float(c.get("credits", 0))
    return {"category": course_category, "credits": course_credits}


def load_reviews() -> dict[str, list[dict[str, Any]]]:
    doc = load_json("course_reviews.json")
    reviews_by_course: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in doc.get("reviews", []):
        cname = r.get("course", "").strip()
        if cname:
            reviews_by_course[cname].append(r)
    return dict(reviews_by_course)


# ══════════════════════════════════════════════════════════════════════
# 第二部分：维度评分函数
# ══════════════════════════════════════════════════════════════════════

def clamp(val: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, val))


def score_credit_intensity(avg_credits: float) -> float:
    """
    学分强度评分（0-100）
    基于华侨大学实际学分分布做非线性映射：
      0-0.5cr → 超轻 (0-8)
      0.5-1cr → 很轻 (8-18)
      1-2cr   → 较轻 (18-35)
      2-3cr   → 中等 (35-55)
      3-4cr   → 较重 (55-72)
      4-6cr   → 很重 (72-90)
      6+cr    → 超重 (90-100)
    """
    def _map_linear(x: float, x1: float, y1: float, x2: float, y2: float) -> float:
        if x <= x1:
            return y1
        if x >= x2:
            return y2
        ratio = (x - x1) / (x2 - x1)
        return y1 + ratio * (y2 - y1)

    if avg_credits <= 0:
        return 0.0
    if avg_credits <= 0.5:
        return _map_linear(avg_credits, 0, 0, 0.5, 8)
    if avg_credits <= 1:
        return _map_linear(avg_credits, 0.5, 8, 1, 18)
    if avg_credits <= 2:
        return _map_linear(avg_credits, 1, 18, 2, 35)
    if avg_credits <= 3:
        return _map_linear(avg_credits, 2, 35, 3, 55)
    if avg_credits <= 4:
        return _map_linear(avg_credits, 3, 55, 4, 72)
    if avg_credits <= 6:
        return _map_linear(avg_credits, 4, 72, 6, 90)
    return _map_linear(avg_credits, 6, 90, 14, 100)


CATEGORY_DIFFICULTY_MAP: dict[str, float] = {
    "专业必修": 90.0,
    "学科基础": 80.0,
    "专业选修": 65.0,
    "实践与创新": 50.0,
    "通识必修": 35.0,
    "通识选修": 20.0,
}

# 从课程名推测类别的关键词规则
CATEGORY_GUESS_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"专业实习|毕业设计|毕业论文|社会实践|创新创业|劳动教育"), "实践与创新"),
    (re.compile(r"形势与政策|思政|军事理论|国防|大学英语|大学体育|心理健康"), "通识必修"),
    (re.compile(r"通识|公选|任选|全校选修|跨专业"), "通识选修"),
    (re.compile(r"导论|基础|原理(?!.*实践)|概论|入门|方法"), "学科基础"),
    (re.compile(r"高级|综合设计|专题|前沿|创新|研讨|seminar|实践"), "专业选修"),
]

# 知识复杂度关键词——从课程名识别高难度知识点
HIGH_COMPLEXITY_KW = [
    "机器学习", "深度学习", "算法", "数据挖掘", "人工智能", "计算机视觉",
    "自然语言", "神经网络", "量子", "密码学", "编译", "体系结构",
    "信号与系统", "数字信号", "通信原理", "嵌入式", "集成电路", "EDA",
    "控制工程", "机器人", "自动化", "飞行器", "航空航天",
    "理论力学", "材料力学", "结构力学", "流体力学", "热力学",
    "有机化学", "无机化学", "物理化学", "分析化学",
    "生化", "分子生物", "基因组", "药理", "药剂",
    "数学分析", "高等代数", "抽象代数", "拓扑", "实变", "复变", "泛函",
    "数理统计", "计量经济", "时间序列", "随机过程", "优化",
    "生物医学工程", "医学影像", "病理", "免疫", "神经科学",
    "金融工程", "金融数学", "衍生品",
]

LOW_COMPLEXITY_KW = [
    "导论", "入门", "基础(?!.*实践)", "概论", "通识", "欣赏",
    "体育", "游泳", "篮球", "足球", "瑜伽",
    "就业指导", "生涯规划", "心理健康", "安全教育",
    "英语听说", "英语阅读", "大学英语",
    "军事", "国防",
]


def score_category_difficulty(course_name: str, category_from_map: str | None = None) -> float:
    """课程类别难度评分"""
    if category_from_map and category_from_map in CATEGORY_DIFFICULTY_MAP:
        return CATEGORY_DIFFICULTY_MAP[category_from_map]
    for pattern, cat in CATEGORY_GUESS_RULES:
        if pattern.search(course_name):
            return CATEGORY_DIFFICULTY_MAP.get(cat, 50.0)
    # 含有"实习"、"实验"等词可能偏技能实践
    if re.search(r"实验|实习", course_name):
        return 55.0
    return 60.0  # 默认偏向中等偏上（多数专业课）


def score_knowledge_complexity(course_name: str) -> float:
    """
    知识复杂度评分（0-100）
    从课程名中出现的专业术语密度判断
    """
    name_lower = course_name.lower()
    high_hits = sum(1 for kw in HIGH_COMPLEXITY_KW if kw.lower() in name_lower)
    low_hits = sum(1 for kw in LOW_COMPLEXITY_KW if kw.lower() in name_lower)

    # 检查是否含英文/缩写 — 通常表示专业课程
    has_english = bool(re.search(r"[a-z]{2,}", name_lower))
    # 检查是否含数学符号
    has_math = bool(re.search(r"[×÷±∫∑∏√∞∩∪∈⊂⊃]", course_name))

    base = 50.0
    base += 12 * high_hits
    base -= 10 * low_hits
    if has_english:
        base += 8
    if has_math:
        base += 12

    return clamp(base)


def score_specialization(num_majors: int, num_colleges: int) -> float:
    """
    专业化程度评分（0-100）
    面向专业少且学院少 = 专精深 = 可能更难
    """
    if num_majors <= 0 and num_colleges <= 0:
        return 55.0

    # 综合专业数和学院数
    combined = max(num_majors, num_colleges)

    if combined == 1:
        return 88.0
    if combined <= 2:
        return 78.0
    if combined <= 4:
        return 66.0
    if combined <= 8:
        return 52.0
    if combined <= 15:
        return 38.0
    if combined <= 30:
        return 26.0
    return 16.0


def score_teaching_intensity(
    unique_teachers: int,
    total_assignments: int,
    unique_terms: int,
) -> float:
    """
    教学强度评分（0-100）
    教师少 + 开课频次高 + 跨度学期多 = 稳定核心课程 = 难度较高
    教师多 + 开课分散 = 通识普及课 = 难度较低
    """
    if total_assignments <= 0:
        return 50.0

    teacher_ratio = total_assignments / max(unique_teachers, 1)
    term_span_score = min(unique_terms * 8, 40)  # 最多开5学期得40

    if teacher_ratio >= 10:
        return clamp(65 + term_span_score * 0.5)
    if teacher_ratio >= 6:
        return clamp(55 + term_span_score * 0.4)
    if teacher_ratio >= 3:
        return clamp(42 + term_span_score * 0.3)
    if teacher_ratio >= 1.5:
        return clamp(30 + term_span_score * 0.2)
    return clamp(18 + term_span_score * 0.15)


def score_from_reviews(reviews: list[dict[str, Any]]) -> tuple[float, int]:
    """
    从评价文本计算难度感知（0-100）
    """
    if not reviews:
        return 50.0, 0

    high_markers = [
        "作业量偏大", "作业多", "实验多", "任务重", "很肝", "肝",
        "熬夜", "报告多", "周周", "代码题", "期末不简单",
        "硬核", "门槛高", "吃力", "难", "区分度大",
        "公式密集", "节奏快", "要求高", "项目有挑战",
        "干货很足", "干货非常足", "给分中等偏严", "给分低",
    ]
    low_markers = [
        "作业少", "轻松", "水", "负担小", "内容新",
        "作业量适中", "给分好", "给分友好", "不压分",
        "深度要靠自己", "友好",
    ]

    scores = []
    for r in reviews:
        text = r.get("text", "")
        rating = r.get("rating", 0)
        hits_high = sum(1 for m in high_markers if m in text)
        hits_low = sum(1 for m in low_markers if m in text)

        base = 50.0
        base += 14 * hits_high
        base -= 12 * hits_low

        # 数值评分映射到难度（评分越高→内容充实但可能更难）
        if 1 <= rating <= 5:
            rating_hardness = (6 - rating) * 10  # 1→50, 2→40, 3→30, 4→20, 5→10
            base = base * 0.6 + rating_hardness * 0.4

        scores.append(clamp(base))

    avg_score = sum(scores) / len(scores)
    # 有评价的课程，置信度更高
    confidence_bonus = min(len(scores) * 2, 10)
    if avg_score > 50:
        avg_score += confidence_bonus * 0.2
    else:
        avg_score -= confidence_bonus * 0.1

    return clamp(avg_score), len(scores)


# ══════════════════════════════════════════════════════════════════════
# 第三部分：综合计算与输出
# ══════════════════════════════════════════════════════════════════════

STAR_THRESHOLDS = [
    (5, 65.0, "非常硬核", "顶尖难度的专业核心课，需要投入大量精力"),
    (4, 55.0, "较难", "专业领域有区分度的课程，需要认真对待"),
    (3, 45.0, "中等难度", "正常课业负担，跟上节奏可获理想成绩"),
    (2, 35.0, "比较轻松", "内容基础或技能型，课业压力较小"),
    (1, 0.0, "非常轻松", "通识/讲座类课程，轻松愉快"),
]


def assign_star(score: float) -> dict[str, Any]:
    for stars, threshold, label, desc in STAR_THRESHOLDS:
        if score >= threshold:
            return {"stars": stars, "label": label, "description": desc}
    return {"stars": 1, "label": "非常轻松", "description": STAR_THRESHOLDS[-1][3]}


def compute_difficulty(merged: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """为所有课程计算难度评分"""
    results: dict[str, Any] = {}

    # 预计算所有课程的学分分布统计，用于相对打分
    all_credits = []
    for info in merged.values():
        pool = info.get("xlsx_credits", []) or info.get("assign_credits", [])
        if pool:
            all_credits.append(sum(pool) / len(pool))
    avg_all_credits = sum(all_credits) / len(all_credits) if all_credits else 2.0

    for cname, info in merged.items():
        # ── 1. 学分强度 ──
        credits_pool = info.get("xlsx_credits", []) or info.get("assign_credits", [])
        avg_credits = sum(credits_pool) / len(credits_pool) if credits_pool else avg_all_credits
        credit_score = score_credit_intensity(avg_credits)

        # ── 2. 类别难度 ──
        category = info.get("curriculum_category", "")
        cat_score = score_category_difficulty(cname, category if category else None)

        # ── 3. 知识复杂度 ──
        know_score = score_knowledge_complexity(cname)

        # ── 4. 专业化程度 ──
        all_majors = set(info.get("majors", []))
        all_majors.update(info.get("assign_majors", []))
        all_colleges = set(info.get("colleges_raw", []))
        all_colleges.update(info.get("assign_colleges", []))
        spec_score = score_specialization(len(all_majors), len(all_colleges))

        # ── 5. 教学强度 ──
        all_teachers = set(info.get("teachers", []))
        all_teachers.update(info.get("assign_teachers", []))
        total_count = info.get("xlsx_count", 0) + info.get("assign_count", 0)
        all_terms = set(info.get("terms_raw", []))
        all_terms.update(info.get("assign_terms", []))
        teach_score = score_teaching_intensity(
            len(all_teachers) if all_teachers else 1,
            max(total_count, 1),
            len(all_terms),
        )

        # ── 6. 评价得分 ──
        reviews = info.get("_reviews", [])
        review_score, review_count = score_from_reviews(reviews)

        # ── 加权综合 ──
        weights = {
            "credit_intensity": 0.15,
            "category": 0.30,
            "knowledge": 0.20,
            "specialization": 0.15,
            "teaching": 0.10,
            "review": 0.10,
        }
        composite = (
            credit_score * weights["credit_intensity"]
            + cat_score * weights["category"]
            + know_score * weights["knowledge"]
            + spec_score * weights["specialization"]
            + teach_score * weights["teaching"]
            + review_score * weights["review"]
        )
        composite = clamp(composite)

        star_info = assign_star(composite)

        results[cname] = {
            "name": cname,
            "difficulty_score": round(composite, 1),
            "stars": star_info["stars"],
            "star_label": star_info["label"],
            "star_description": star_info["description"],
            "dimensions": {
                "credit_intensity": round(credit_score, 1),
                "category_difficulty": round(cat_score, 1),
                "knowledge_complexity": round(know_score, 1),
                "specialization": round(spec_score, 1),
                "teaching_intensity": round(teach_score, 1),
                "review_score": round(review_score, 1),
            },
            "meta": {
                "avg_credits": round(avg_credits, 1),
                "unique_teachers": len(all_teachers),
                "unique_majors": len(all_majors),
                "assignments_count": total_count,
                "review_count": review_count,
                "category": category or "未分类",
            },
        }

    return results


def compute_distribution_stats(results: dict[str, Any]) -> dict[str, Any]:
    scores = [r["difficulty_score"] for r in results.values()]
    stars_dist = Counter(r["stars"] for r in results.values())

    if not scores:
        return {"min": 0, "max": 0, "avg": 0, "median": 0, "star_distribution": {}}

    sorted_scores = sorted(scores)
    n = len(sorted_scores)
    return {
        "total_courses": n,
        "min_score": round(sorted_scores[0], 1),
        "max_score": round(sorted_scores[-1], 1),
        "avg_score": round(sum(scores) / n, 1),
        "median_score": round(
            sorted_scores[n // 2] if n % 2 == 1
            else (sorted_scores[n // 2 - 1] + sorted_scores[n // 2]) / 2,
            1,
        ),
        "star_distribution": {str(k): v for k, v in sorted(stars_dist.items())},
    }


# ══════════════════════════════════════════════════════════════════════
# 第四部分：主流程
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    print("=" * 60)
    print("  课程难度分析引擎 v2.0")
    print("=" * 60)

    # 1. 加载数据
    print("\n[1/5] 加载教务 XLSX 数据...")
    xlsx_courses = load_xlsx_courses()
    print(f"       → {len(xlsx_courses)} 门课程")

    print("[2/5] 加载课程安排 JSON 数据...")
    assign_courses = load_assignments()
    print(f"       → {len(assign_courses)} 门课程")

    print("[3/5] 加载培养方案分类信息...")
    curric = load_curriculum_info()
    cat_map = curric["category"]
    print(f"       → {len(cat_map)} 门课程有分类标签")

    print("[4/5] 加载评价数据...")
    reviews_map = load_reviews()
    print(f"       → {len(reviews_map)} 门课程有评价")

    # 5. 融合数据
    print("[5/5] 融合数据并计算难度...")
    all_cnames = set(xlsx_courses.keys()) | set(assign_courses.keys())
    print(f"       → 共计 {len(all_cnames)} 门课程")

    merged: dict[str, dict[str, Any]] = {}
    for cname in sorted(all_cnames):
        entry: dict[str, Any] = {}
        if cname in xlsx_courses:
            entry.update(xlsx_courses[cname])
        if cname in assign_courses:
            ac = assign_courses[cname]
            for key in ("assign_credits", "assign_teachers", "assign_majors",
                          "assign_colleges", "assign_campuses", "assign_terms"):
                val = ac.get(key)
                if key not in entry or not entry.get(key):
                    entry[key] = val
                elif val:
                    existing = entry.get(key, [])
                    if isinstance(existing, list) and isinstance(val, list):
                        entry[key] = sorted(set(existing) | set(val))
        if cname in cat_map:
            entry["curriculum_category"] = cat_map[cname]
        if "xlsx_credits" not in entry or not entry.get("xlsx_credits"):
            if cname in curric["credits"]:
                entry["xlsx_credits"] = [curric["credits"][cname]]
        entry["_reviews"] = reviews_map.get(cname, [])
        merged[cname] = entry

    # 6. 计算难度
    results = compute_difficulty(merged)
    stats = compute_distribution_stats(results)

    # 7. 输出 JSON
    output = {
        "version": "2.0",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "data_sources": {
            "xlsx_courses": len(xlsx_courses),
            "json_assignments": len(assign_courses),
            "curriculum_categories": len(cat_map),
            "reviews_available": sum(1 for v in merged.values() if v.get("_reviews")),
        },
        "difficulty_model": {
            "description": "多维度加权难度评分 (0-100) — 基于教务系统数据 + 评价文本",
            "dimensions": {
                "credit_intensity": {"weight": "15%", "description": "学分越高课业负荷越重"},
                "category_difficulty": {"weight": "30%", "description": "专业必修/学科基础 > 通识选修"},
                "knowledge_complexity": {"weight": "20%", "description": "课程名中高密度专业术语"},
                "specialization": {"weight": "15%", "description": "面向专业越少 = 课程越专精"},
                "teaching_intensity": {"weight": "10%", "description": "师资集中度 + 开课频次"},
                "review_score": {"weight": "10%", "description": "来自真实评价的难度感知"},
            },
            "star_thresholds": [
                {"stars": 5, "min_score": 65, "label": "非常硬核", "description": "顶尖难度的专业核心课"},
                {"stars": 4, "min_score": 55, "label": "较难", "description": "专业领域有区分度的课程"},
                {"stars": 3, "min_score": 45, "label": "中等难度", "description": "正常课业负担"},
                {"stars": 2, "min_score": 35, "label": "比较轻松", "description": "内容基础或技能型"},
                {"stars": 1, "min_score": 0, "label": "非常轻松", "description": "通识/讲座类课程"},
            ],
        },
        "distribution": stats,
        "courses": list(results.values()),
    }

    output_path = DATA_DIR / "course_difficulty.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 难度数据已写入: {output_path}")
    print(f"   总计 {stats['total_courses']} 门课程")
    print(f"   难度分布: {stats['star_distribution']}")
    print(f"   平均分: {stats['avg_score']} | 中位数: {stats['median_score']}")
    print(f"   最高: {stats['max_score']} | 最低: {stats['min_score']}")

    # 各星级样例
    print("\n--- 各星级课程样例 ---")
    for stars in range(5, 0, -1):
        samples = [r for r in results.values() if r["stars"] == stars][:6]
        if samples:
            print(f"\n{'⭐' * stars} ({stars}星 - {samples[0]['star_label']}):")
            for s in samples:
                print(f"   · {s['name']:<30s} 难度:{s['difficulty_score']:>5.1f}  "
                      f"[学分:{s['meta']['avg_credits']}  教师:{s['meta']['unique_teachers']}  专业:{s['meta']['unique_majors']}]")


if __name__ == "__main__":
    main()
