"""
verify_execution.py - verifica per ESECUZIONE della campagna di test JCoQL.

Per ogni riga valida di test_campaign_log.csv:
  1. esegue la query JCoQL+ generata tramite il backend (POST /api/execute)
  2. calcola il risultato ATTESO direttamente dai dati MongoDB (oracolo indipendente)
  3. confronta e scrive verification_results.csv

Uso (dalla cartella del progetto, backend gia' avviato su localhost:8000):
    pip install requests pymongo
    python verify_execution.py                # tutte le righe
    python verify_execution.py --only gemini  # solo un modello
    python verify_execution.py --selftest     # prova gli oracoli sui JSON seed, senza backend
"""
import argparse, csv, json, re, sys, time

BACKEND = "http://localhost:8000"
DB = "jcoql_test"
CSV_IN = "test_campaign_log.csv"
CSV_OUT = "verification_results.csv"


# --------------------------------------------------------------------------
# Oracoli: ritornano dict con
#   kind: "ids" (insieme di _id), "count" (solo conteggio), "custom"
#   n: conteggio atteso; ids: set di _id attesi (se kind == ids)
#   check: funzione(docs)->(bool, str) per kind custom
# --------------------------------------------------------------------------
def _ids(docs):
    return {str(d["_id"]) for d in docs}

def sel(docs, f):
    out = [d for d in docs if f(d)]
    return {"kind": "ids", "n": len(out), "ids": _ids(out)}

def cnt(n, note=""):
    return {"kind": "count", "n": n, "note": note}

def organic(d):  return d.get("organic") is True
def disc(d):     return d.get("discount") or 0
def rate(d):     return d.get("rating")

def expected(nl, C):
    P, O, U = C["products"], C["orders"], C["users"]
    t = nl.strip().rstrip(".").strip().lower()
    uid = {str(u["_id"]) for u in U}
    pid = {str(p["_id"]) for p in P}
    revs = [(p, r) for p in P for r in (p.get("reviews") or [])]
    items = [(o, i) for o in O for i in (o.get("items") or [])]

    rules = [
        (r"^mostrami tutti gli utenti$", lambda: sel(U, lambda d: True)),
        (r"^mostrami i prodotti con uno sconto maggiore del 20%$", lambda: sel(P, lambda d: disc(d) > 20)),
        (r"^mostrami i prodotti biologici con un rating di almeno 4$", lambda: sel(P, lambda d: organic(d) and rate(d) >= 4)),
        (r"^mostrami i prodotti biologici oppure quelli con uno sconto superiore al 30%$", lambda: sel(P, lambda d: organic(d) or disc(d) > 30)),
        (r"^espandi le recensioni dei prodotti in righe separate$", lambda: cnt(len(revs))),
        (r"^collega ogni ordine all'utente che lo ha effettuato$", lambda: cnt(sum(1 for o in O if str(o.get("user_id")) in uid))),
        (r"^raggruppa i prodotti per categoria$", lambda: cnt(len({p.get("category") for p in P}), "n gruppi")),
        (r"^unisci i prodotti biologici e quelli scontati in un'unica collezione, senza duplicati$",
            lambda: sel(P, lambda d: organic(d) or disc(d) > 0)),
        (r"^mostrami i prodotti che non sono biologici$", lambda: sel(P, lambda d: not organic(d))),
        (r"^mostrami i prodotti biologici con un rating di almeno 4, oppure quelli con uno sconto superiore al 50%$",
            lambda: sel(P, lambda d: (organic(d) and rate(d) >= 4) or disc(d) > 50)),
        (r"^mostrami gli ordini superiori a 100 euro insieme all'utente che li ha effettuati$",
            lambda: cnt(sum(1 for o in O if o["total"] > 100 and str(o.get("user_id")) in uid))),
        (r"^mostrami le recensioni dei prodotti con un voto superiore a 4$", lambda: cnt(sum(1 for p, r in revs if r["rating"] > 4))),
        (r"^conta quanti prodotti ci sono per categoria$", lambda: cnt(len({p.get("category") for p in P}), "n gruppi")),
        (r"^mostrami i prodotti con un rating compreso tra 3 e 4\.5$", lambda: sel(P, lambda d: 3 <= rate(d) <= 4.5)),
        (r"^mostrami i prodotti con uno sconto compreso tra il 10% e il 30%$", lambda: sel(P, lambda d: 10 <= disc(d) <= 30)),
        (r"^mostrami i prodotti senza nessuno sconto$", lambda: sel(P, lambda d: disc(d) == 0)),
        (r"^mostrami i prodotti con un rating inferiore a 3$", lambda: sel(P, lambda d: rate(d) < 3)),
        (r"^mostrami i prodotti biologici con uno sconto maggiore del 20%$", lambda: sel(P, lambda d: organic(d) and disc(d) > 20)),
        (r"^mostrami i prodotti non biologici con un rating di almeno 4$", lambda: sel(P, lambda d: not organic(d) and rate(d) >= 4)),
        (r"^mostrami i prodotti che non sono biologici e non hanno nessuno sconto$", lambda: sel(P, lambda d: not organic(d) and disc(d) == 0)),
        (r"^mostrami i prodotti biologici oppure quelli con un rating di almeno 4\.5$", lambda: sel(P, lambda d: organic(d) or rate(d) >= 4.5)),
        (r"^mostrami i prodotti con uno sconto superiore al 40%, oppure con un rating inferiore a 2$", lambda: sel(P, lambda d: disc(d) > 40 or rate(d) < 2)),
        (r"^mostrami i prodotti biologici con uno sconto superiore al 10%, oppure quelli con un rating di almeno 4\.5$",
            lambda: sel(P, lambda d: (organic(d) and disc(d) > 10) or rate(d) >= 4.5)),
        (r"^mostrami i prodotti non biologici oppure quelli con uno sconto superiore al 50%$", lambda: sel(P, lambda d: not organic(d) or disc(d) > 50)),
        (r"^mostrami le recensioni dei prodotti con un voto uguale a 5$", lambda: cnt(sum(1 for p, r in revs if r["rating"] == 5))),
        (r"^mostrami le recensioni dei prodotti con un voto inferiore a 3$", lambda: cnt(sum(1 for p, r in revs if r["rating"] < 3))),
        (r"^mostrami le recensioni dei soli prodotti biologici$", lambda: cnt(sum(1 for p, r in revs if organic(p)))),
        (r"^espandi gli articoli degli ordini in righe separate$", lambda: cnt(len(items))),
        (r"^collega ogni recensione all'utente che l'ha scritta$", lambda: cnt(sum(1 for p, r in revs if str(r.get("user")) in uid))),
        (r"^mostrami gli ordini inferiori a 50 euro insieme all'utente che li ha effettuati$",
            lambda: cnt(sum(1 for o in O if o["total"] < 50 and str(o.get("user_id")) in uid))),
        (r"^collega ogni ordine ai prodotti acquistati$", lambda: cnt(sum(1 for o, i in items if str(i["product_id"]) in pid))),
        (r"^collega ogni utente ai suoi ordini$", lambda: cnt(sum(1 for o in O if str(o.get("user_id")) in uid))),
        (r"^raggruppa gli ordini per utente$", lambda: cnt(len({o.get("user_id") for o in O}), "n gruppi")),
        (r"^raggruppa i prodotti biologici per categoria$", lambda: cnt(len({p.get("category") for p in P if organic(p)}), "n gruppi")),
        (r"^raggruppa i prodotti in biologici e non biologici$", lambda: cnt(len({organic(p) for p in P}), "n gruppi")),
        (r"^unisci i prodotti con un rating di almeno 4 e quelli con uno sconto superiore al 30% in un'unica collezione, senza duplicati$",
            lambda: sel(P, lambda d: rate(d) >= 4 or disc(d) > 30)),
        (r"^unisci i prodotti biologici e quelli senza sconto in un'unica collezione, mantenendo i duplicati$",
            lambda: cnt(sum(1 for p in P if organic(p)) + sum(1 for p in P if disc(p) == 0), "con duplicati = |A|+|B|")),
        (r"^unisci gli ordini superiori a 100 euro e quelli inferiori a 20 euro in un'unica collezione$",
            lambda: sel(O, lambda d: d["total"] > 100 or d["total"] < 20)),
        (r"^aggiungi a ogni ordine un campo con il totale maggiorato dell'iva al 22%$",
            lambda: {"kind": "custom", "n": len(O), "check": lambda docs: _check_arith(docs, O, "total", lambda v: v * 1.22)}),
        (r"^aggiungi a ogni prodotto un campo con la differenza tra 5 e il rating$",
            lambda: {"kind": "custom", "n": len(P), "check": lambda docs: _check_arith(docs, P, "rating", lambda v: 5 - v)}),
        (r"^mostrami solo la categoria e il rating di ogni prodotto$",
            lambda: {"kind": "custom", "n": len(P), "check": _check_projection}),
    ]
    for pat, fn in rules:
        if re.match(pat, t):
            return fn()
    return None


def _flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        else:
            out[key] = v
    return out

def _check_arith(docs, source, field, fn):
    """Esiste in ogni documento un campo numerico NUOVO con il valore calcolato?"""
    src = {str(s["_id"]): s for s in source}
    ok = 0
    for d in docs:
        s = src.get(str(d.get("_id")))
        if s is None:
            continue
        want = fn(s[field])
        flat = _flat(d)
        if any(isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v - want) < 0.01
               and k.split(".")[-1] != field for k, v in flat.items()):
            ok += 1
    return (ok == len(src) and len(docs) == len(src), f"{ok}/{len(src)} documenti con valore calcolato corretto")

def _check_projection(docs):
    bad = 0
    for d in docs:
        keys = {k.split(".")[-1] for k in _flat(d)} - {"_id"}
        if keys != {"category", "rating"}:
            bad += 1
    return (bad == 0, f"{bad} documenti con campi diversi da {{category, rating}}")


# --------------------------------------------------------------------------
def doc_id(d):
    v = d.get("_id")
    if isinstance(v, dict) and "$oid" in v:
        v = v["$oid"]
    return None if v is None else str(v)

def compare(exp, res):
    docs = res.get("results") or []
    n = res.get("count", len(docs))
    if exp["kind"] == "ids":
        if n != exp["n"]:
            return "DIVERSO", f"attesi {exp['n']} documenti, ottenuti {n}"
        got = {doc_id(d) for d in docs}
        if None in got:
            return "ESATTO (solo conteggio)", f"{n} documenti (senza _id nel risultato)"
        if got == exp["ids"]:
            return "ESATTO", f"{n} documenti, stesso insieme di _id"
        return "DIVERSO", f"stesso conteggio {n} ma _id diversi (mancanti {len(exp['ids']-got)}, extra {len(got-exp['ids'])})"
    if exp["kind"] == "count":
        if n == exp["n"]:
            return "ESATTO (solo conteggio)", f"{n} {exp.get('note','')}".strip()
        return "DIVERSO", f"attesi {exp['n']} {exp.get('note','')}, ottenuti {n}".strip()
    ok, msg = exp["check"](docs)
    return ("ESATTO" if ok else "DIVERSO"), f"{msg}; n={n}, atteso {exp['n']}"


def load_collections_mongo():
    from pymongo import MongoClient
    db = MongoClient("mongodb://localhost:27017")[DB]
    return {c: list(db[c].find({})) for c in ("products", "orders", "users")}

def load_collections_seed(base):
    out = {}
    for c in ("products", "orders", "users"):
        d = json.load(open(f"{base}/data_{c}.json", encoding="utf-8"))
        out[c] = d if isinstance(d, list) else list(d.values())[0]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--seed-dir", default="backend/database")
    ap.add_argument("--timeout", type=int, default=120)
    a = ap.parse_args()

    rows = list(csv.DictReader(open(CSV_IN, encoding="utf-8-sig")))
    if a.selftest:
        C = load_collections_seed(a.seed_dir)
        for nl in dict.fromkeys(r["query_nl"].strip() for r in rows):
            e = expected(nl, C)
            print(("OK  " if e else "??? "), nl[:80], "->", (e or {}).get("n"))
        return

    import requests
    C = load_collections_mongo()
    out = []
    for i, r in enumerate(rows, 1):
        if a.only and r["modello"] != a.only:
            continue
        q = (r["query_jcoql"] or "").strip()
        base = {"timestamp": r["timestamp"], "modello": r["modello"],
                "query_nl": r["query_nl"].strip(), "query_jcoql": q}
        exp = expected(r["query_nl"], C)
        if r["valida"] != "SI" or not q or not re.match(r"^[A-Z]", q) or exp is None:
            motivo = ("oracolo mancante" if exp is None and r["valida"] == "SI" and q
                      else "query non valida/vuota")
            out.append({**base, "esito": "NON ESEGUITA", "dettaglio": motivo, "tempo_exec_s": ""})
            continue
        t0 = time.time()
        try:
            resp = requests.post(f"{BACKEND}/api/execute",
                                 json={"jcoql_query": q, "database_name": DB,
                                       "timeout_seconds": a.timeout},
                                 timeout=a.timeout + 30)
            j = resp.json()
        except Exception as ex:
            out.append({**base, "esito": "ERRORE", "dettaglio": f"richiesta fallita: {ex}",
                        "tempo_exec_s": round(time.time() - t0, 2)})
            continue
        dt = round(time.time() - t0, 2)
        if not j.get("success"):
            out.append({**base, "esito": "ERRORE", "dettaglio": str(j.get("error") or j.get("detail"))[:300],
                        "tempo_exec_s": dt})
        else:
            esito, det = compare(exp, j)
            out.append({**base, "esito": esito, "dettaglio": det, "tempo_exec_s": dt})
        print(f"[{i}/{len(rows)}] {r['modello']:8} {out[-1]['esito']:24} {base['query_nl'][:60]}")

    with open(CSV_OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["timestamp", "modello", "query_nl", "query_jcoql",
                                          "esito", "dettaglio", "tempo_exec_s"])
        w.writeheader(); w.writerows(out)
    print("scritto", CSV_OUT)


if __name__ == "__main__":
    main()
