"""Il modello riproduce gli esempi FILTER+GROUP che ha visto in addestramento? (solo testo, niente esecuzione)
Uso, da finetune\\soup:  python ft_train_recall.py --model llama3.1-jcoql-v2 --n 30"""
import argparse, json, random, re, requests
ap = argparse.ArgumentParser()
ap.add_argument("--model", default="llama3.1-jcoql-v2")
ap.add_argument("--n", type=int, default=30)
ap.add_argument("--ollama", default="http://localhost:11434")
a = ap.parse_args()
rows = [json.loads(l) for l in open('../out/train_final.jsonl', encoding='utf-8')]
fg = [x for x in rows if re.search(r'FILTER.*GROUP PARTITION', x['output'], re.S)]
random.seed(7); sample = random.sample(fg, min(a.n, len(fg)))
norm = lambda q: re.sub(r"\s+", " ", q).strip().rstrip(";").strip()
ident = true_ok = 0
for k, x in enumerate(sample, 1):
    g = requests.post(f"{a.ollama}/api/generate", json={"model": a.model, "prompt": x["instruction"], "stream": False,
        "options": {"temperature": 0, "num_predict": 600, "num_ctx": 4096}}, timeout=600).json()["response"].strip()
    same = norm(g) == norm(x["output"]); t = "GROUP PARTITION TRUE BY" in g
    ident += same; true_ok += t
    if not t: print("SBAGLIATA:", g)
    print(f"[{k}/{len(sample)}] identica={same} PARTITION TRUE BY={t}")
print(f"\nidentiche {ident}/{len(sample)}  |  con 'GROUP PARTITION TRUE BY' {true_ok}/{len(sample)}")
