"""ft_sample.py - mostra a campione richiesta -> query da train_final.jsonl.
Uso:  ..\\venv\\Scripts\\python.exe .\\ft_sample.py [--file out\\train_final.jsonl] [--n 30] [--seed 1]
"""
import argparse, json, random, re

ap = argparse.ArgumentParser()
ap.add_argument("--file", default="out/train_final.jsonl")
ap.add_argument("--n", type=int, default=30)
ap.add_argument("--seed", type=int, default=1)
a = ap.parse_args()

rows = [json.loads(l) for l in open(a.file, encoding="utf-8")]
random.seed(a.seed)
for k, x in enumerate(random.sample(rows, min(a.n, len(rows))), 1):
    m = re.search(r'RICHIESTA: "(.*)"', x["instruction"])
    print(f"{k}. {m.group(1) if m else '?'}")
    print("   -> " + x["output"].replace("\n", " | "))
    print()
