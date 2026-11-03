"""Step 0: find the saved files and report what is there. Reads only; stops (exit 1) if anything is missing."""
import collections
import csv
import json
import os
import sys

from common import RUNS, ROOT, load_model_rows, load_questions, raw_path, questions_path


def main():
    missing = []
    print("== Rotation pilot (pilot/output/*)")
    folders = sorted({f for _, f, _ in RUNS})
    ids = {}
    for folder in folders:
        for p in (raw_path(folder), questions_path(folder)):
            print(f"  {p.relative_to(ROOT)}  {'OK' if p.exists() else 'MISSING'}")
            if not p.exists():
                missing.append(str(p))
        if questions_path(folder).exists():
            q = load_questions(folder)
            ids[folder] = {(x["id"], json.dumps(x["truth"])) for s in q["scenes"] for x in s["questions"]}
            kinds = collections.Counter(x["type"] for s in q["scenes"] for x in s["questions"])
            print(f"    {len(q['scenes'])} frames, questions {dict(kinds)}, rotations {q['rotations']}")
    if len({frozenset(v) for v in ids.values()}) > 1:
        missing.append("the question sets in the different folders are NOT identical")
    else:
        print("  question ids and truths are identical across the folders")
    cols = list(json.loads(open(raw_path(folders[0])).readline()))
    print("  raw_responses.jsonl columns:", ", ".join(cols))
    for label, folder, model in RUNS:
        rows = load_model_rows(folder, model)
        kinds = collections.Counter(r["type"] for r in rows)
        unparsed = sum(r["answer"] is None for r in rows)
        print(f"  {label:14s} {model:20s} {len(rows)} usable rows {dict(kinds)}, unparsed {unparsed}, folder {folder}")
        if len(rows) != 216:
            missing.append(f"{label}: {len(rows)} rows, expected 216")

    print("\n== Depth comparison (depth_comparison/)")
    for name in ("unidepth", "moge2", "moge2aerial"):
        p = ROOT / "depth_comparison" / "output" / f"{name}_raw.csv"
        if not p.exists():
            missing.append(str(p))
            print(f"  {p.relative_to(ROOT)} MISSING")
            continue
        rows = list(csv.DictReader(open(p)))
        print(f"  {p.relative_to(ROOT)}: {len(rows)} rows, settings {sorted({r['setting'] for r in rows})}, "
              f"frames {len({r['frame'] for r in rows})}; columns {', '.join(rows[0])}")
    for name in ("clean_frames.csv", "da3_reference_clean.csv", "vehicle_counts.csv"):
        p = ROOT / "depth_comparison" / name
        print(f"  {p.relative_to(ROOT)}  {'OK' if p.exists() else 'MISSING'}")
        if not p.exists():
            missing.append(str(p))
    p = ROOT / "data_check" / "derived" / "20190829091111.json"
    print(f"  {p.relative_to(ROOT)} (poses for step 3): {'OK' if p.exists() else 'MISSING'}")
    if not p.exists():
        missing.append(str(p))

    print("\n== Step 4 precondition")
    print("  ANTHROPIC_API_KEY is", "set (value not shown)" if os.environ.get("ANTHROPIC_API_KEY") else "NOT set")

    if missing:
        print("\nSTOP: missing or inconsistent:", *missing, sep="\n  - ")
        return 1
    print("\nAll inputs present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
