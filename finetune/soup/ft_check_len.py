"""Quanti esempi di training superano max_length (768 token) e dove cade il taglio?
Uso, da finetune\\soup con l'ambiente di Soup:  python ft_check_len.py"""
import json, re, collections, statistics
MAXLEN = 768
try:
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B-Instruct")
    ntok = lambda s: len(tok(s)["input_ids"])
    print("tokenizer Llama 3.1 caricato")
except Exception as ex:
    print("tokenizer non disponibile (", str(ex)[:80], ") -> stima caratteri/3")
    ntok = lambda s: len(s) // 3
def cat(o):
    if "JOIN OF" in o: return "join"
    if "EXPAND" in o: return "expand"
    if re.search(r"FILTER.*GROUP PARTITION", o, re.S): return "filter+group"
    if "GROUP PARTITION" in o: return "group"
    if "MERGE" in o or "SUBTRACT" in o or "INTERSECT" in o: return "setop"
    return "altro"
L = collections.defaultdict(list); over = collections.Counter(); cut_out = collections.Counter()
for l in open("../out/train_final.jsonl", encoding="utf-8"):
    x = json.loads(l); c = cat(x["output"])
    tp, to = ntok(x["instruction"]), ntok(x["output"])
    tot = tp + to + 40   # ~ template alpaca/chat
    L[c].append(tot)
    if tot > MAXLEN:
        over[c] += 1
        if tp + 40 >= MAXLEN: cut_out[c] += 1   # tutto l'output tagliato
print(f"\n{'categoria':14} {'n':>5} {'mediana':>8} {'max':>6} {'>768':>6} {'%':>6}")
for c, v in sorted(L.items()):
    print(f"{c:14} {len(v):5} {int(statistics.median(v)):8} {max(v):6} {over[c]:6} {100*over[c]/len(v):5.0f}%")
print("\ntotale oltre il limite:", sum(over.values()), "su", sum(len(v) for v in L.values()))
