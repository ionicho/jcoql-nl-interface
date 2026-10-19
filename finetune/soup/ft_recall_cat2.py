"""Il modello (llama-server + LoRA) riproduce gli esempi di training di una categoria? Solo testo (identica al riferimento).
Uso, da finetune\\soup, con llama-server attivo:  python ft_recall_cat.py --cat joindirect --n 30
Categorie: joindirect (solo JOIN), joinarray (con EXPAND e JOIN), filtergroup, group, expand, setop, altro"""
import argparse, json, random, re, time, requests
from transformers import AutoTokenizer
ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:8081"); ap.add_argument("--n", type=int, default=30)
ap.add_argument("--cat", default="joindirect")
a = ap.parse_args()
def cat(o):
    if "JOIN OF" in o: return "joinarray" if "EXPAND" in o else "joindirect"
    if "EXPAND" in o: return "expand"
    if re.search(r"FILTER.*GROUP PARTITION", o, re.S): return "filtergroup"
    if "GROUP PARTITION" in o: return "group"
    if re.search(r"MERGE|SUBTRACT|INTERSECT", o): return "setop"
    return "altro"
tok = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B-Instruct")
for _ in range(60):
    try:
        if requests.get(a.url + "/health", timeout=3).json().get("status") == "ok": break
    except Exception: pass
    time.sleep(2)
else: raise SystemExit("server non pronto")
rows = [json.loads(l) for l in open('../out/train_final.jsonl', encoding='utf-8')]
pool = [x for x in rows if cat(x['output']) == a.cat]
random.seed(7); sample = random.sample(pool, min(a.n, len(pool)))
print(f"categoria {a.cat}: {len(pool)} esempi nel training, provo {len(sample)}")
norm = lambda q: re.sub(r"\s+", " ", q).strip().rstrip(";").strip()
def canon(q):
    """alias rinominati per ordine di dichiarazione (A0, A1, ...): confronta la struttura, non le lettere scelte a caso"""
    q = norm(q); al = []
    for m in re.finditer(r"\bAS\s+(\w+)", q):
        if m.group(1) not in al: al.append(m.group(1))
    for i, n in enumerate(al):
        q = re.sub(r"\bAS\s+" + re.escape(n) + r"\b", f"AS @{i}", q)
        q = re.sub(r"\." + re.escape(n) + r"\.", f".@{i}.", q)
    return q
ident = ident_c = 0
for k, x in enumerate(sample, 1):
    p = tok.apply_chat_template([{"role": "user", "content": x["instruction"]}], tokenize=False, add_generation_prompt=True).replace("<|begin_of_text|>", "", 1)
    g = requests.post(a.url + "/completion", json={"prompt": p, "n_predict": 400, "temperature": 0, "stop": ["<|eot_id|>"], "cache_prompt": False}, timeout=900).json()["content"].strip()
    same = norm(g) == norm(x["output"]); ident += same; same_c = canon(g) == canon(x["output"]); ident_c += same_c
    if not same_c and k <= 40: print("GEN:", g, "\nREF:", x["output"], "\n")
print(f"identiche al carattere: {ident}/{len(sample)}  |  identiche con alias normalizzati: {ident_c}/{len(sample)}")
