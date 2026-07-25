from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def import_reviews(csv_path: Path) -> int:
    target = DATA / "course_reviews.json"
    doc = read_json(target)
    count = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("course") or not row.get("text"):
                continue
            doc["reviews"].append(
                {
                    "course": row["course"].strip(),
                    "source": row.get("source", "csv-import").strip() or "csv-import",
                    "text": row["text"].strip(),
                    "rating": int(row.get("rating") or 0),
                }
            )
            count += 1
    write_json(target, doc)
    return count


def import_professors(json_path: Path) -> int:
    target = DATA / "professors.json"
    doc = read_json(target)
    incoming = read_json(json_path)
    professors = incoming.get("professors", incoming if isinstance(incoming, list) else [])
    doc["professors"].extend(professors)
    write_json(target, doc)
    return len(professors)


def import_offerings(json_path: Path) -> int:
    target = DATA / "seat_inventory.json"
    doc = read_json(target)
    incoming = read_json(json_path)
    offerings = incoming.get("offerings", incoming if isinstance(incoming, list) else [])
    doc["offerings"].extend(offerings)
    write_json(target, doc)
    return len(offerings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import real data into Qinmian AI.")
    parser.add_argument("--reviews-csv", type=Path, help="CSV columns: course,text,rating,source")
    parser.add_argument("--professors-json", type=Path, help="JSON list or object with professors[]")
    parser.add_argument("--offerings-json", type=Path, help="JSON list or object with offerings[]")
    args = parser.parse_args()

    if args.reviews_csv:
        print(f"imported reviews: {import_reviews(args.reviews_csv)}")
    if args.professors_json:
        print(f"imported professors: {import_professors(args.professors_json)}")
    if args.offerings_json:
        print(f"imported offerings: {import_offerings(args.offerings_json)}")
    if not any([args.reviews_csv, args.professors_json, args.offerings_json]):
        parser.print_help()


if __name__ == "__main__":
    main()
