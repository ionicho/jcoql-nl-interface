"""Come ft_train_recall_raw.py ma contro llama-server (llama.cpp) invece che Ollama. Stessi 30 esempi (seed 7).
Uso, da finetune\\soup:  python ft_recall_llamacpp.py --n 30 [--url http://localhost:8081]"""
import argparse, json, random, re, time, requests
from transformers import AutoTokenizer
ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:8081"); ap.add_argument("--n", type=int, default=30)
a = ap.parse_args()
tok = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B-Instruct")
for _ in range(120):
    try:
        if requests.get(a.url + "/health", timeout=3).json().get("status") == "ok": break
    except Exception: pass
    time.sleep(2)
else: raise SystemExit("server non pronto")
rows = [json.loads(l) for l in open('../out/train_final.jsonl', encoding='utf-8')]
fg = [x for x in rows if re.search(r'FILTER.*GROUP PARTITION', x['output'], re.S)]
random.seed(7); sample = random.sample(fg, min(a.n, len(fg)))
norm = lambda q: re.sub(r"\s+", " ", q).strip().rstrip(";").strip()
ident = true_ok = 0
for k, x in enumerate(sample, 1):
    p = tok.apply_chat_template([{"role": "user", "content": x["instruction"]}], tokenize=False, add_generation_prompt=True).replace("<|begin_of_text|>", "", 1)
    g = requests.post(a.url + "/completion", json={"prompt": p, "n_predict": 300, "temperature": 0, "stop": ["<|eot_id|>"], "cache_prompt": False}, timeout=900).json()["content"].strip()
    same = norm(g) == norm(x["output"]); t = "GROUP PARTITION TRUE BY" in g
    ident += same; true_ok += t
    if not t: print("SBAGLIATA:", g)
    print(f"[{k}/{len(sample)}] identica={same} PARTITION TRUE BY={t}", flush=True)
print(f"\nidentiche {ident}/{len(sample)}  |  con 'GROUP PARTITION TRUE BY' {true_ok}/{len(sample)}")
