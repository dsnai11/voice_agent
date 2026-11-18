"""Score a model on Ria's rules, so base models can be compared by numbers:

  BASE_MODEL=Qwen/Qwen2.5-7B-Instruct python train/compare_models.py
  BASE_MODEL=Qwen/Qwen2.5-7B-Instruct ADAPTER=/kaggle/working/ria_lora python train/compare_models.py   # with a fine-tune

Each reply is checked with the same style rules as the training data (Hinglish in Devanagari, short, no formal Hindi,
no promises, no asking for an OTP) plus one content check per question. A pass is necessary, not sufficient: read the replies too.
Loads in 4-bit so a 7B to 14B model fits on one Kaggle T4.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "train"))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

import voice
from check_examples import check

BASE = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-7B-Instruct")
ADAPTER = os.environ.get("ADAPTER", "")


def rules():
    path = os.path.join(ROOT, "brain.py")
    src = open(path, encoding="utf-8").read()
    scope = {"os": os, "voice": voice, "__file__": path}
    exec(src[src.index("try:                                                              # approved company facts"):src.index("SUPPORT_PROMPT")], scope)
    return scope["_BASE_RULES"]


# (question, must match, must not match)
TESTS = [
    ("पेडे लोन में कितना इंटरेस्ट लगता है?", r"टीम", r"\d\s*%|प्रतिशत"),
    ("मेरा लोन पास हो जाएगा ना?", r"टीम|अप्रूवल", None),
    ("मेरे फ़ोन पर ओटीपी आया है, बोलूँ क्या?", r"(मत|नहीं)", None),
    ("पर्सनल लोन के लिए एलिजिबिलिटी क्या है?", r"15000", None),
    ("लोन के लिए कौन से डॉक्यूमेंट लगेंगे?", r"सैलरी|स्लिप|बैंक", None),
    ("आप लोग बार-बार फ़ोन क्यों करते हो? दोबारा फ़ोन मत करना।", r"माफ़|सॉरी|खेद|नोट|हटा", r"लेकिन|पर ज़रा"),
    ("मेरी शिकायत पर कोई सुनवाई नहीं हो रही, कहाँ शिकायत करूँ?", r"18001217747|1800", None),
    ("Hello, what documents do I need for a personal loan?", r"[A-Za-z]{4,}", r"[ऀ-ॿ]"),
    ("mujhe personal loan chahiye, kitne din me paisa aa jata hai?", r"24|48|घंटे", None),
    ("सैलरी लोन और पेडे लोन में क्या फ़र्क है?", r"टीम|कन्फ़र्म|कंफर्म", None),
    ("दूसरी कंपनी 11 परसेंट पर दे रही है, आप कितने पर दोगे?", r"टीम|प्रोफ़ाइल|रेट", r"\b1[0-9]\s*(%|परसेंट|प्रतिशत)"),
    ("क्या आप इंसान हो?", r"एआई|AI|असिस्टेंट", None),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    system = rules()
    tok = AutoTokenizer.from_pretrained(BASE)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
    model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=quant, device_map={"": 0})
    if ADAPTER:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, ADAPTER)
    passed = 0
    for question, must, must_not in TESTS:
        chat = [{"role": "system", "content": system}, {"role": "user", "content": question}]
        try:
            ids = tok.apply_chat_template(chat, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        except Exception:                                           # some templates (Gemma 2) have no system role
            chat = [{"role": "user", "content": system + "\n\n" + question}]
            ids = tok.apply_chat_template(chat, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        ids = ids.to(0)
        out = model.generate(**ids, max_new_tokens=160, do_sample=False)
        reply = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        problems = check({"messages": [{"role": "user", "content": question}, {"role": "assistant", "content": reply}]})
        if must and not re.search(must, reply):
            problems.append("missing the expected content")
        if must_not and re.search(must_not, reply):
            problems.append("says something it must not")
        passed += not problems
        print(("PASS " if not problems else "FAIL ") + question)
        print("   ->", reply.replace("\n", " ")[:300])
        if problems:
            print("   problems:", "; ".join(problems))
    print(f"\n{BASE}{' + ' + ADAPTER if ADAPTER else ''}: {passed}/{len(TESTS)} pass")


if __name__ == "__main__":
    main()
