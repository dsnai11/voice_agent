"""List the questions Ria could not answer (saved locally in calls/unanswered.jsonl), most frequent first.
Turn the useful ones into approved answers in knowledge/reply_bank.json.   python train/review_unanswered.py"""
import collections
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calls", "unanswered.jsonl")
if not os.path.exists(path):
    sys.exit("No unanswered questions saved yet.")
rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
counts = collections.Counter(r["question"].strip().lower() for r in rows)
print(f"{len(rows)} unanswered question(s), {len(counts)} different:\n")
for q, n in counts.most_common(50):
    print(f"{n:3d} x  {q}")
