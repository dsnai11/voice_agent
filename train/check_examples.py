"""Check training conversations before they are used for fine-tuning:  python train\\check_examples.py [file.jsonl]

Mirrors the rules in brain.py and llm_eval.py: Hinglish in Devanagari, short replies, no formal Hindi,
no promises, no OTP requests. English replies are allowed only when the caller wrote fully in English.
A passing file still needs a person to read it: this catches style slips, not wrong facts.
"""
import json
import re
import sys

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN_WORD = re.compile(r"[A-Za-z]{4,}")
ALLOWED_LATIN = re.compile(r"\b(EMI|AI|OTP|PAN|KYC|CIBIL|NACH|ECS|GST)\b")
FORMAL = ("ऋण", "वेतन", "दस्तावेज", "आवेदन", "ब्याज दर", "किस्त", "अनुमोदन")
PROMISE = re.compile(r"(पक्का\s+(पास|अप्रूव)|ज़रूर\s+(पास|अप्रूव)|गारंटी|100\s*%|पास हो जाएगा|अप्रूव हो जाएगा)")
ASKS_SECRET = re.compile(r"(ओटीपी|OTP|पिन|पासवर्ड|CVV).{0,20}(बताइए|बताओ|बोलिए|भेजिए|दीजिए)")
GOODBYE = re.compile(r"(अलविदा|बाय|गुड\s?बाय|goodbye)", re.I)


def english_caller(messages):
    users = [m["content"] for m in messages if m["role"] == "user"]
    return bool(users) and not any(DEVANAGARI.search(u) for u in users) and not re.search(r"\b(mujhe|kitne|kaun|chahiye|hai|me)\b", " ".join(users), re.I)


def check(example):
    problems = []
    msgs = example["messages"]
    if not msgs or msgs[-1]["role"] != "assistant":
        problems.append("must end with an assistant turn")
    for a, b in zip(msgs, msgs[1:]):
        if a["role"] == b["role"]:
            problems.append("roles must alternate")
            break
    english = english_caller(msgs)
    for m in msgs:
        if m["role"] != "assistant":
            continue
        text = m["content"]
        plain = ALLOWED_LATIN.sub("", text)
        if not english and (not DEVANAGARI.search(text) or LATIN_WORD.search(plain)):
            problems.append(f"not Devanagari Hinglish: {text[:40]}")
        if len(re.findall(r"[।.?!](\s|$)", text)) > 3 or len(text) > 260:
            problems.append(f"too long: {text[:40]}")
        for w in FORMAL:
            if w in text:
                problems.append(f"formal word {w}")
        if PROMISE.search(text):
            problems.append(f"promise: {text[:40]}")
        secret = ASKS_SECRET.search(text)
        if secret and not re.search(r"(मत|नहीं|कभी)", text[max(0, secret.start() - 15):secret.end() + 12]):
            problems.append(f"asks for a secret: {text[:40]}")
        if GOODBYE.search(text):
            problems.append(f"goodbye: {text[:40]}")
        if "*" in text or "#" in text:
            problems.append("markdown symbols")
    return problems


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    path = sys.argv[1] if len(sys.argv) > 1 else "train/seed_conversations.jsonl"
    bad = total = 0
    seen = set()
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            total += 1
            try:
                ex = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"line {n}: invalid JSON ({e})")
                bad += 1
                continue
            issues = check(ex)
            if ex.get("id") in seen:
                issues.append("duplicate id")
            seen.add(ex.get("id"))
            if issues:
                bad += 1
                print(f"{ex.get('id', n)}: " + "; ".join(issues))
    print(f"{total - bad}/{total} conversations pass")


if __name__ == "__main__":
    main()
