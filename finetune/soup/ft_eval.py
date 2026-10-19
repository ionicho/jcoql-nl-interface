"""
ft_eval.py - valuta un modello Ollama sugli esempi tenuti fuori (database MAI visti in addestramento).

Per ogni richiesta: il modello genera la query -> si esegue con il backend (POST /api/execute) ->
si confronta il numero di risultati con quello atteso (calcolato da Python). Si riporta anche l'uguaglianza
testuale con la query di riferimento (metrica piu' severa: query equivalenti ma scritte in modo diverso
non contano come esatte).

Uso (backend e MongoDB avviati, Ollama attivo), da finetune\\soup:
    python ft_eval.py --model llama3.1-jcoql --per-family 10
    python ft_eval.py --model llama3.1:8b-instruct-q4_K_M --per-family 10     # modello base, prompt breve (NON equo)
    python ft_eval.py --model llama3.1:8b-instruct-q4_K_M --prompt compact    # modello base, prompt del progetto (regole + RAG)

--prompt tuned   (default) il prompt breve dell'addestramento, preso dal file degli esempi;
--prompt compact il prompt "compatto" del backend (regole + schema + 7 esempi RAG), costruito dal
                 backend (POST /api/eval/build_prompt): e' il confronto equo per il modello base.
In entrambi i casi: UN solo tentativo, nessuna correzione automatica, stessa esecuzione e stesso oracolo.
"""
import argparse, collections, csv, json, os, random, re, time


def clean(txt):
    t = txt.strip()
    t = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", t).strip()
    return t


def norm(q):
    return re.sub(r"\s+", " ", q).strip().rstrip(";").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--eval", default="../out/eval_heldout.jsonl")
    ap.add_argument("--dbs", default="../out/databases.json")
    ap.add_argument("--per-family", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--backend", default="http://localhost:8000")
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--mongo", default="mongodb://localhost:27017")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--no-seed", action="store_true", help="non ricaricare i database in MongoDB")
    ap.add_argument("--prompt", choices=["tuned", "compact"], default="tuned")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    import requests
    rows = [json.loads(l) for l in open(a.eval, encoding="utf-8")]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["meta"]["family"]].append(r)
    rng = random.Random(a.seed)
    sample = [x for fam in sorted(by) for x in rng.sample(by[fam], min(a.per_family, len(by[fam])))]
    print(f"modello {a.model}: {len(rows)} esempi tenuti fuori, campione di {len(sample)} su {len(by)} famiglie")

    mongo = None
    if not a.no_seed:
        from pymongo import MongoClient
        mongo = MongoClient(a.mongo, serverSelectionTimeoutMS=4000); mongo.admin.command("ping")
        dbs = {d["name"]: d for d in json.load(open(a.dbs, encoding="utf-8"))}
        for name in sorted({r["meta"]["db"] for r in sample}):
            mongo.drop_database(name)
            for coll, docs in dbs[name]["collections"].items():
                if docs:
                    mongo[name][coll].insert_many([dict(d) for d in docs])
        print("database sintetici caricati in MongoDB")

    res, tally = [], collections.defaultdict(collections.Counter)
    for k, r in enumerate(sample, 1):
        m, ref, dbn = r["meta"], r["output"], r["meta"]["db"]
        t0 = time.time()
        gen = ""
        prompt = r["instruction"]
        if a.prompt == "compact":
            nl = re.search(r'RICHIESTA: "(.*)"', r["instruction"]).group(1)
            prompt = requests.post(f"{a.backend}/api/eval/build_prompt", params={
                "database_name": dbn, "nl_query": nl, "mode": "compact"}, timeout=120).json()["prompt"]
        try:
            g = requests.post(f"{a.ollama}/api/generate", json={
                "model": a.model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0, "num_predict": 600,
                            "num_ctx": 4096 if a.prompt == "tuned" else 8192}}, timeout=600).json()
            gen = clean(g.get("response", ""))
        except Exception as ex:
            esito, det = "ERRORE_MODELLO", str(ex)[:150]
        else:
            if mongo is not None:
                for coll in re.findall(r"SAVE AS\s+(\w+)@", gen):
                    mongo[dbn].drop_collection(coll)
            try:
                j = requests.post(f"{a.backend}/api/execute", json={"jcoql_query": gen, "database_name": dbn,
                                  "timeout_seconds": a.timeout}, timeout=a.timeout + 30).json()
            except Exception as ex:
                esito, det = "ERRORE_BACKEND", str(ex)[:150]
            else:
                if not j.get("success"):
                    esito, det = "ERRORE_QUERY", str(j.get("error") or j.get("detail"))[:150]
                else:
                    n = j.get("count", len(j.get("results") or []))
                    esito, det = ("ESATTO", f"{n} risultati") if n == m["expected"] else ("DIVERSO", f"attesi {m['expected']}, ottenuti {n}")
        same = norm(gen) == norm(ref)
        tally[m["family"]][esito] += 1
        tally[m["family"]]["identica"] += same
        res.append(dict(famiglia=m["family"], db=dbn, esito=esito, identica=same, dettaglio=det,
                        richiesta=m.get("nl_variant", m["nl"]), generata=gen, riferimento=ref, secondi=round(time.time() - t0, 1)))
        print(f"[{k}/{len(sample)}] {m['family']:16} {esito:14} {'=' if same else ' '} {det[:60]}")

    suffix = "" if a.prompt == "tuned" else f"_{a.prompt}"
    out = a.out or f"eval_{re.sub(r'[^A-Za-z0-9]+', '_', a.model)}{suffix}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    tot = collections.Counter()
    print(f"\nRIEPILOGO {a.model}  (esatti per esecuzione / query identica al riferimento / totale)")
    for fam, c in sorted(tally.items()):
        n = sum(v for kk, v in c.items() if kk != "identica")
        print(f"   {fam:18} {c['ESATTO']:3} / {c['identica']:3} / {n:3}")
        tot["e"] += c["ESATTO"]; tot["i"] += c["identica"]; tot["n"] += n
    print(f"   {'TOTALE':18} {tot['e']:3} / {tot['i']:3} / {tot['n']:3}   -> {100*tot['e']/max(1,tot['n']):.1f}% esatti per esecuzione")
    print(f"\nscritto {out}")


if __name__ == "__main__":
    main()
