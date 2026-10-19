"""
ft_merge_v3.py - unisce il training v2 (senza i vecchi join con alias casuali) e i dati nuovi v3.
Uso (da finetune\\):  ..\\venv\\Scripts\\python.exe .\\ft_merge_v3.py
Legge  out\\train_final.jsonl  e  out_v3\\train_final.jsonl ; scrive  out_v3\\train_final_v3.jsonl  (non tocca i file esistenti).
"""
import json, os, random
HERE = os.path.dirname(os.path.abspath(__file__))
old = [json.loads(l) for l in open(os.path.join(HERE, "out", "train_final.jsonl"), encoding="utf-8")]
new = [json.loads(l) for l in open(os.path.join(HERE, "out_v3", "train_final.jsonl"), encoding="utf-8")]
keep = [r for r in old if "JOIN OF COLLECTIONS" not in r["output"]]
print(f"v2: {len(old)} esempi, di cui join (rimossi): {len(old) - len(keep)} | v3 nuovi: {len(new)} "
      f"(di cui join: {sum('JOIN OF COLLECTIONS' in r['output'] for r in new)})")
allr = keep + new
random.Random(3).shuffle(allr)
out = os.path.join(HERE, "out_v3", "train_final_v3.jsonl")
with open(out, "w", encoding="utf-8") as f:
    for r in allr:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"scritto {out}: {len(allr)} esempi, lunghezza massima prompt (caratteri): {max(len(r['instruction']) for r in allr)}")
