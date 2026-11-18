"""Package Ria's code for Kaggle: python kaggle\\make_zip.py  ->  kaggle\\ria_app.zip

Contains only code, the web page, the FAKE demo customers, an empty data file and the Hindi Narrator voice.
No call records, no saved enquiries, no audio caches, no keys.
"""
import os
import zipfile

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "ria_app.zip")
EMPTY = os.path.join(HERE, "company_data_empty.xlsx")

wb = openpyxl.Workbook()
wb.active.title = "enquiries"
wb.save(EMPTY)

code = [f for f in os.listdir(ROOT) if f.endswith(".py")]
extra = ["crm_demo.xlsx", "Hindi_Narrator.omnivoice"]
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for f in code + extra:
        if os.path.exists(os.path.join(ROOT, f)):
            z.write(os.path.join(ROOT, f), f)
        else:
            print("missing (skipped):", f)
    for name in os.listdir(os.path.join(ROOT, "web")):
        z.write(os.path.join(ROOT, "web", name), "web/" + name)
    for folder in ("knowledge", "train"):                                   # approved facts for the prompt, and the fine-tuning files
        for name in os.listdir(os.path.join(ROOT, folder)):
            if name.endswith((".txt", ".jsonl", ".py", ".md", ".json")):
                z.write(os.path.join(ROOT, folder, name), f"{folder}/{name}")
    z.write(os.path.join(HERE, "gpu_server.py"), "gpu_server.py")           # the Kaggle start-up script travels with the app: no pasting
    z.write(EMPTY, "company_data.xlsx")
os.remove(EMPTY)
print(f"{OUT}: {os.path.getsize(OUT) // 1024} KB, {len(code)} code files")
