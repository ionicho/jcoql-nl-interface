"""
ft_verify_v4.py - verifica per ESECUZIONE del dataset v4 (stessa logica di ft_verify.py, piu' il controllo dei valori).

Per ogni famiglia prende un campione, carica i database sintetici in MongoDB, esegue la query tramite il backend
(POST /api/execute) e confronta:
  1. il numero di risultati con quello calcolato da Python alla generazione (campo 'expected');
  2. dove la famiglia lo prevede (meta.check), anche i VALORI dei campi nuovi nei documenti restituiti:
       values  - il campo nuovo vale quanto atteso (TRANSLATE, campo calcolato)
       equal   - il campo copiato e' uguale all'originale (ADD FIELDS)
       absent  - i campi tolti non compaiono (REMOVE FIELDS)
       rename  - il campo nuovo c'e', quello vecchio no
       present - i campi della proiezione ci sono
Esiti: ESATTO | VALORI (conteggio giusto, valori sbagliati) | DIVERSO (conteggio diverso) | ERRORE.
Il controllo dei valori usa i documenti restituiti dal backend: se l'API ne restituisce solo una parte, controlla quelli.

Uso (backend gia' avviato su localhost:8000, MongoDB su localhost:27017), da finetune\\ :
    ..\\venv\\Scripts\\python.exe .\\ft_verify_v4.py --per-family 12
    ..\\venv\\Scripts\\python.exe .\\ft_verify_v4.py --family join3 --per-family 30
"""
import argparse, collections, csv, json, os, random, re, time


def get_path(doc, path):
    for p in path.split("."):
        doc = doc.get(p) if isinstance(doc, dict) else None
    return doc


def same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) < 1e-6
    return a == b


def check_values(chk, docs):
    """None se tutto torna (o nulla da controllare), altrimenti una stringa col primo problema. Ritorna anche quanti documenti controllati."""
    if not chk or not docs:
        return None, 0
    n = 0
    k = chk["kind"]
    seen = set()                                        # campi visti in almeno un documento (i null non vengono restituiti)
    for d in docs:
        if not isinstance(d, dict):
            continue
        if k == "values":
            if d.get("_id") not in chk["map"]:
                continue
            n += 1
            got, want = get_path(d, chk["field"]), chk["map"][d["_id"]]
            if not same(got, want):
                return f"{chk['field']}: atteso {want!r}, ottenuto {got!r} (_id {d['_id']})", n
        elif k == "equal":
            for new, old in chk["pairs"]:
                if get_path(d, old) is None and old not in d:
                    continue
                n += 1
                if not same(get_path(d, new), get_path(d, old)):
                    return f"{new} != {old} ({get_path(d, new)!r} contro {get_path(d, old)!r})", n
        elif k == "absent":
            n += 1
            for f in chk["fields"]:
                if f in d:
                    return f"il campo {f} doveva essere tolto", n
        elif k == "rename":
            n += 1
            if chk["old"] in d:
                return f"il campo {chk['old']} doveva sparire", n
            if chk["new"] in d:
                seen.add(chk["new"])
        elif k == "present":
            n += 1
            seen.update(f for f in chk["fields"] if f in d)
    if k == "rename" and chk["new"] not in seen:
        return f"manca il campo nuovo {chk['new']}", n
    if k == "present":
        for f in chk["fields"]:
            if f not in seen:
                return f"manca il campo {f} in tutti i documenti", n
    return None, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--meta", default="out_v4/dataset_meta.jsonl")
    ap.add_argument("--dbs", default="out_v4/databases.json")
    ap.add_argument("--backend", default="http://localhost:8000")
    ap.add_argument("--mongo", default="mongodb://localhost:27017")
    ap.add_argument("--per-family", type=int, default=12)
    ap.add_argument("--family", default="", help="solo questa famiglia")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--out", default="out_v4/verify_results.csv")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(a.meta, encoding="utf-8")]
    by = collections.defaultdict(list)
    for r in rows:
        if not a.family or r["meta"]["family"] == a.family:
            by[r["meta"]["family"]].append(r)
    rng = random.Random(a.seed)
    sample = []
    for fam, xs in sorted(by.items()):
        sample += rng.sample(xs, min(a.per_family, len(xs)))
    print(f"{len(rows)} esempi, {len(by)} famiglie, campione di {len(sample)}")
    for fam, xs in sorted(by.items()):
        print(f"   {fam:16} {len(xs):5} esempi")
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

    res, tally = [], collections.defaultdict(collections.Counter)
    for k, r in enumerate(sample, 1):
        m, q, dbn = r["meta"], r["output"], r["meta"]["db"]
        for coll in re.findall(r"SAVE AS\s+(\w+)@", q):        # i SAVE AS non devono accumularsi tra un giro e l'altro
            mongo[dbn].drop_collection(coll)
        t0, ctrl = time.time(), ""
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
                if n != m["expected"]:
                    esito, det = "DIVERSO", f"attesi {m['expected']}, ottenuti {n}"
                else:
                    esito, det = "ESATTO", f"{n} risultati"
                    bad, nchk = check_values(m.get("check"), j.get("results") or [])
                    if bad:
                        esito, det = "VALORI", bad
                    ctrl = f"{nchk} documenti controllati" if m.get("check") else ""
        tally[m["family"]][esito] += 1
        res.append(dict(famiglia=m["family"], db=dbn, esito=esito, dettaglio=det, controllo=ctrl, atteso=m["expected"],
                        ottenuti=n, richiesta=m["nl"], query=q, secondi=round(time.time() - t0, 2)))
        print(f"[{k}/{len(sample)}] {m['family']:16} {esito:8} {det[:70]}")

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(res[0].keys())); w.writeheader(); w.writerows(res)
    print("\nRIEPILOGO per famiglia (ESATTO / VALORI / DIVERSO / ERRORE)")
    for fam, c in sorted(tally.items()):
        print(f"   {fam:16} {c['ESATTO']:3} / {c['VALORI']:3} / {c['DIVERSO']:3} / {c['ERRORE']:3}")
    bad = [x for x in res if x["esito"] != "ESATTO"]
    for x in bad[:12]:
        print(f"\n[{x['famiglia']}] {x['esito']}: {x['dettaglio']}\n   {x['richiesta']}\n   {x['query'][:260]}")
    print(f"\nscritto {a.out}  ({len(res) - len(bad)}/{len(res)} esatti)")


if __name__ == "__main__":
    main()
