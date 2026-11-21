"""Summary of the saved calls: how many, how they ended, how fast Ria answers, what callers ask that she could not answer.
    python train/call_report.py [folder with the call json files]
"""
import glob, json, os, statistics, sys
sys.stdout.reconfigure(encoding="utf-8")
folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "testdata", "calls")
calls = [json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(folder, "*.json"))]
print(f"calls saved: {len(calls)}   submitted: {sum(c.get('status') == 'submitted' for c in calls)}   partial: {sum(c.get('status') == 'partial' for c in calls)}")
rows = [r for c in calls for r in c.get("turn_metrics", [])]
if rows:
    def line(key, label):
        v = sorted(r[key] for r in rows if key in r)
        if v:
            print(f"  {label:34s} median {statistics.median(v):5.2f}s   90th percentile {v[int(0.9 * (len(v) - 1))]:5.2f}s   worst {v[-1]:5.2f}s")
    print(f"turns timed: {len(rows)}")
    line("stt_s", "listening (speech to text)")
    line("reply_s", "thinking (reply written)")
    line("first_audio_s", "caller stops -> first sound")
    line("total_s", "caller stops -> reply sent")
    slow = [r for r in rows if r.get("first_audio_s", 0) > 3]
    print(f"  turns slower than 3 s: {len(slow)}")
    for r in slow[:5]:
        print(f"    turn {r['turn']}: {r.get('heard', '')[:50]!r} first sound after {r['first_audio_s']}s (listening {r.get('stt_s')}s, reply {r.get('reply_s')}s)")
else:
    print("no timed turns yet (calls made before 21 Nov 2026 carry no timing)")
un = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "calls", "unanswered.jsonl")
if os.path.exists(un):
    qs = [json.loads(l).get("text", "") for l in open(un, encoding="utf-8") if l.strip()]
    print(f"questions Ria could not answer so far: {len(qs)} (python train/review_unanswered.py groups them)")
