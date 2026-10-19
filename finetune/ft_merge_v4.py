"""
ft_merge_v4.py - unisce il training v3 e i dati nuovi v4 (non tocca i file esistenti).
Uso (da finetune\\):  ..\\venv\\Scripts\\python.exe .\\ft_merge_v4.py            # con le parafrasi (out_v4\\train_final.jsonl)
                     ..\\venv\\Scripts\\python.exe .\\ft_merge_v4.py --no-paraphrase   # solo le richieste originali (out_v4\\dataset_train.jsonl)
Legge  out_v3\\train_final_v3.jsonl  e i dati v4 ; scrive  out_v4\\train_final_v4.jsonl.
"""
import json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
src_new = "dataset_train.jsonl" if "--no-paraphrase" in sys.argv else "train_final.jsonl"
old = [json.loads(l) for l in open(os.path.join(HERE, "out_v3", "train_final_v3.jsonl"), encoding="utf-8")]
new = [json.loads(l) for l in open(os.path.join(HERE, "out_v4", src_new), encoding="utf-8")]
allr = old + new
random.Random(4).shuffle(allr)
out = os.path.join(HERE, "out_v4", "train_final_v4.jsonl")
with open(out, "w", encoding="utf-8") as f:
    for r in allr:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"v3: {len(old)} esempi | v4 nuovi ({src_new}): {len(new)} | totale: {len(allr)}")
print(f"scritto {out}; lunghezza massima prompt (caratteri): {max(len(r['instruction']) for r in allr)} (limite del training: max_length 1280 token)")
