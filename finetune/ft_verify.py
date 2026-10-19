"""
ft_verify.py - verifica per ESECUZIONE del dataset sintetico.

Per ogni famiglia di query prende un campione di esempi, carica i database sintetici in MongoDB,
esegue la query tramite il backend (POST /api/execute) e confronta il numero di risultati con
quello calcolato da Python al momento della generazione (campo 'expected').
Se tutte le famiglie tornano, le etichette del dataset sono corrette per esecuzione, non solo per sintassi.

Uso (backend gia' avviato su localhost:8000, MongoDB su localhost:27017), dalla cartella finetune:
    ..\\venv\\Scripts\\python.exe .\\ft_verify.py --per-family 10
    ..\\venv\\Scripts\\python.exe .\\ft_verify.py --per-family 10 --dry      # solo il piano, senza eseguire
"""
import argparse, collections, json, os, random, re, time


def bson_ready(doc):
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", default="out/dataset_meta.jsonl")
    ap.add_argument("--dbs", default="out/databases.json")
    ap.add_argument("--backend", default="http://localhost:8000")
    ap.add_argument("--mongo", default="mongodb://localhost:27017")
    ap.add_argument("--per-family", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--out", default="out/verify_results.csv")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--from-index", type=int, default=0, help="usa solo le righe di dataset_meta da questo indice (v2: 1600 = solo gli esempi nuovi)")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.meta, encoding="utf-8")]
    rows = rows[a.from_index:]
    by = collections.defaultdict(list)
    for r in rows:
        by[r["meta"]["family"]].append(r)
    rng = random.Random(a.seed)
    sample = []
    for fam, xs in sorted(by.items()):
        sample += rng.sample(xs, min(a.per_family, len(xs)))
    print(f"{len(rows)} esempi, {len(by)} famiglie, campione di {len(sample)}")
    for fam, xs in sorted(by.items()):
        print(f"   {fam:18} {len(xs):5} esempi")
    if a.dry:
        return

    import requests
    from pymongo import MongoClient
    mongo = MongoClient(a.mongo, serverSelectionTimeoutMS=4000)
    mongo.admin.command("ping")
    dbs = {d["name"]: d for d in json.load(open(a.dbs, encoding="utf-8"))}
    need = sorted({r["meta"]["db"] for r in sample})
    for name in need:                                   # database sintetici: ricaricati puliti
        mongo.drop_database(name)
        for coll, docs in dbs[name]["collections"].items():
            if docs:
                mongo[name][coll].insert_many([dict(d) for d in docs])
    print(f"caricati {len(need)} database sintetici in MongoDB")

    res, tally = [], collections.defaultdict(lambda: collections.Counter())
    for k, r in enumerate(sample, 1):
        m, q, dbn = r["meta"], r["output"], r["meta"]["db"]
        for coll in re.findall(r"SAVE AS\s+(\w+)@", q):        # i SAVE AS non devono accumularsi tra un giro e l'altro
            mongo[dbn].drop_collection(coll)
        t0 = time.time()
        try:
            j = requests.post(f"{a.backend}/api/execute",
                              json={"jcoql_query": q, "database_name": dbn, "timeout_seconds": a.timeout},
                              timeout=a.timeout + 30).json()
        except Exception as ex:
            esito, det, n = "ERRORE", f"richiesta fallita: {ex}", ""
        else:
            if not j.get("success"):
                esito, det, n = "ERRORE", str(j.get("error") or j.get("detail"))[:200], ""
            else:
                n = j.get("count", len(j.get("results") or []))
                esito, det = ("ESATTO", f"{n} risultati") if n == m["expected"] else ("DIVERSO", f"attesi {m['expected']}, ottenuti {n}")
        tally[m["family"]][esito] += 1
        res.append(dict(famiglia=m["family"], db=dbn, esito=esito, dettaglio=det, atteso=m["expected"], ottenuti=n,
                        richiesta=m["nl"], query=q, secondi=round(time.time() - t0, 2)))
        print(f"[{k}/{len(sample)}] {m['family']:16} {esito:8} {det[:70]}")

    import csv
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    print("\nRIEPILOGO per famiglia (ESATTO / DIVERSO / ERRORE)")
    for fam, c in sorted(tally.items()):
        print(f"   {fam:18} {c['ESATTO']:3} / {c['DIVERSO']:3} / {c['ERRORE']:3}")
    bad = [x for x in res if x["esito"] != "ESATTO"]
    for x in bad[:12]:
        print(f"\n[{x['famiglia']}] {x['esito']}: {x['dettaglio']}\n   {x["richiesta"]}\n   {x['query'][:260]}")
    print(f"\nscritto {a.out}  ({len(res) - len(bad)}/{len(res)} esatti)")


if __name__ == "__main__":
    main()
