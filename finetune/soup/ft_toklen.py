"""ft_toklen.py - lunghezza ESATTA in token (tokenizer Llama 3.1) degli esempi di addestramento.
Uso (con l'ambiente di Soup attivo):  python ft_toklen.py ..\\out\\train_final.jsonl
"""
import json, sys
from transformers import AutoTokenizer

path = sys.argv[1] if len(sys.argv) > 1 else "../out/train_final.jsonl"
tok = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B-Instruct")
rows = [json.loads(l) for l in open(path, encoding="utf-8")]
n = sorted(len(tok(r["instruction"] + "\n" + r["output"])["input_ids"]) + 12 for r in rows)   # +12: token speciali del template
q = lambda p: n[min(len(n) - 1, int(len(n) * p))]
print(f"{len(n)} esempi | media {sum(n)//len(n)} | p50 {q(.5)} | p95 {q(.95)} | p99 {q(.99)} | max {n[-1]}")
for lim in (512, 640, 768, 1024):
    print(f"   oltre {lim:4}: {sum(x > lim for x in n)} esempi")
print(f"token totali per epoca: {sum(n)}")
