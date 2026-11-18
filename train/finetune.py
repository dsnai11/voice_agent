"""Fine-tune a small model on Ria's conversations (QLoRA) on a Kaggle GPU.

  python train/finetune.py            # train, then save the adapter and a merged model
Settings (environment): BASE_MODEL (default Qwen/Qwen2.5-3B-Instruct), DATA (default train/seed_conversations.jsonl),
EPOCHS (4), OUT (/kaggle/working/ria_lora), MERGED (/kaggle/working/ria_merged).

Needs: pip install -q peft bitsandbytes accelerate   (transformers and torch are on Kaggle already)
Training uses ONLY the files you give it. It never sees real customer data unless you add such conversations.
The model learns the style and the behaviour (hand over, no promises); facts come from knowledge/ria_facts.txt in the prompt.
"""
import json
import os
import random

import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, Trainer, TrainingArguments

import voice

BASE = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-3B-Instruct")
DATA = os.environ.get("DATA", "train/seed_conversations.jsonl")
EPOCHS = float(os.environ.get("EPOCHS", "4"))
OUT = os.environ.get("OUT", "/kaggle/working/ria_lora")
MERGED = os.environ.get("MERGED", "/kaggle/working/ria_merged")
MAX_LEN = 1536                                                     # the facts block is about 600 tokens

def _live_rules():
    """The exact rules and facts the live agent gets: run the rules section of brain.py without importing the whole app."""
    path = os.path.join(ROOT, "brain.py")
    src = open(path, encoding="utf-8").read()
    section = src[src.index("try:                                                              # approved company facts"):src.index("SUPPORT_PROMPT")]
    scope = {"os": os, "voice": voice, "__file__": path}
    exec(section, scope)
    return scope["_BASE_RULES"]


SYSTEM = _live_rules()


def load_examples():
    with open(DATA, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return rows


def _ids(tok, chat, generation_prompt):
    text = tok.apply_chat_template(chat, tokenize=False, add_generation_prompt=generation_prompt)
    return tok(text, add_special_tokens=False)["input_ids"]


def encode(tok, messages):
    """Token ids and labels where only Ria's own turns count toward the loss."""
    chat = [{"role": "system", "content": SYSTEM}] + messages
    ids = _ids(tok, chat, False)
    labels = [-100] * len(ids)
    for i, m in enumerate(chat):
        if m["role"] != "assistant":
            continue
        start = len(_ids(tok, chat[:i], True))
        end = len(_ids(tok, chat[:i + 1], False))
        labels[start:end] = ids[start:end]
    return {"input_ids": ids[:MAX_LEN], "labels": labels[:MAX_LEN]}


class Rows(torch.utils.data.Dataset):
    def __init__(self, items):
        self.items = items

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        return self.items[i]


def collate(batch, pad_id):
    n = max(len(b["input_ids"]) for b in batch)
    ids = torch.tensor([b["input_ids"] + [pad_id] * (n - len(b["input_ids"])) for b in batch])
    lab = torch.tensor([b["labels"] + [-100] * (n - len(b["labels"])) for b in batch])
    return {"input_ids": ids, "labels": lab, "attention_mask": (torch.arange(n)[None, :] < torch.tensor([len(b["input_ids"]) for b in batch])[:, None]).long()}


def main():
    random.seed(7)
    tok = AutoTokenizer.from_pretrained(BASE)
    rows = load_examples()
    items = [encode(tok, r["messages"]) for r in rows]
    trained = sum(sum(1 for x in it["labels"] if x != -100) for it in items)
    print(f"{len(items)} conversations, {trained} tokens of Ria's own speech to learn from", flush=True)

    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True)
    model = AutoModelForCausalLM.from_pretrained(BASE, quantization_config=quant, device_map={"": 0})
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(model, LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                                             target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    model.print_trainable_parameters()

    args = TrainingArguments(output_dir=OUT, num_train_epochs=EPOCHS, per_device_train_batch_size=1, gradient_accumulation_steps=8,
                             learning_rate=2e-4, lr_scheduler_type="cosine", warmup_steps=1, fp16=True, logging_steps=1,
                             save_strategy="no", report_to=[], gradient_checkpointing=True, remove_unused_columns=False)
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    Trainer(model=model, args=args, train_dataset=Rows(items), data_collator=lambda b: collate(b, pad)).train()

    model.save_pretrained(OUT)
    tok.save_pretrained(OUT)
    print("adapter saved:", OUT, flush=True)

    del model
    torch.cuda.empty_cache()
    from peft import PeftModel
    base = AutoModelForCausalLM.from_pretrained(BASE, torch_dtype=torch.float16, device_map={"": 0})
    PeftModel.from_pretrained(base, OUT).merge_and_unload().save_pretrained(MERGED, safe_serialization=True)
    tok.save_pretrained(MERGED)
    print("merged model saved:", MERGED, flush=True)


if __name__ == "__main__":
    main()
