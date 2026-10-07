"""
repeatability.py - test di ripetibilita': la stessa richiesta, N volte, per ogni modello.

Per ogni modello e per ognuna delle 5 richieste esegue N volte (default 5):
  /api/generate -> query JCoQL+  ->  /api/execute  ->  confronto con l'atteso (oracolo
  di verify_execution.py, che deve stare nella stessa cartella).
Scrive ogni run subito su repeatability_runs.csv (riprendibile: se lo interrompi e lo
rilanci salta i run gia' fatti) e alla fine repeatability_summary.csv.

ATTENZIONE: ogni chiamata a /api/generate viene registrata anche in test_campaign_log.csv
(il logger e' automatico). Prima di lanciare fai una copia di quel file:
    copy test_campaign_log.csv test_campaign_log_prima_ripetibilita.csv

Uso (backend avviato su localhost:8000):
    python repeatability.py                              # tutti i modelli, 5 run
    python repeatability.py --models gemini gemma4       # solo alcuni
    python repeatability.py --models llama --runs 3
"""
import argparse, collections, csv, os, re, time
import requests
import verify_execution as V

QUERIES = [
    ("A range",      "Mostrami i prodotti con un rating compreso tra 3 e 4.5"),
    ("B OR",         "Mostrami i prodotti biologici oppure quelli con un rating di almeno 4.5"),
    ("C EXPAND",     "Mostrami le recensioni dei prodotti con un voto uguale a 5"),
    ("D JOIN",       "Collega ogni ordine ai prodotti acquistati"),
    ("E GROUP",      "Raggruppa i prodotti biologici per categoria"),
]
DEFAULT_MODELS = ["gemini", "llama32", "gemma4", "llama"]   # dal piu' veloce al piu' lento
OUT_RUNS = "repeatability_runs.csv"
OUT_SUM = "repeatability_summary.csv"
FIELDS = ["modello", "query_id", "query_nl", "run", "valida", "tentativi", "tempo_gen_s",
          "query_jcoql", "esito", "dettaglio"]

def norm(q):
    return re.sub(r"\s+", " ", (q or "").strip())

def load_done():
    if not os.path.exists(OUT_RUNS):
        return [], set()
    rows = list(csv.DictReader(open(OUT_RUNS, encoding="utf-8-sig")))
    return rows, {(r["modello"], r["query_id"], int(r["run"])) for r in rows}

RATE_PAT = re.compile(r"429|quota|rate.?limit|resource.?exhausted|too many requests|timed? ?out|deadline", re.I)

def is_rate_limited(row):
    """Run fallito per limite di quota/timeout del servizio cloud, non per un errore del modello."""
    return row["esito"] in ("NON VALIDA", "ERRORE GENERAZIONE") and bool(RATE_PAT.search(row["dettaglio"] or ""))

def one_run(model, qid, nl, run, C, gen_timeout, exec_timeout):
    t0 = time.time()
    row = {"modello": model, "query_id": qid, "query_nl": nl, "run": run,
           "valida": "", "tentativi": "", "tempo_gen_s": "", "query_jcoql": "", "esito": "", "dettaglio": ""}
    try:
        g = requests.post(f"{V.BACKEND}/api/generate",
                          json={"nl_query": nl, "database": V.DB, "databases": [V.DB], "max_retries": 3},
                          timeout=gen_timeout).json()
    except Exception as ex:
        row.update(esito="ERRORE GENERAZIONE", dettaglio=str(ex)[:200], tempo_gen_s=round(time.time() - t0, 1))
        return row
    row["tempo_gen_s"] = round(time.time() - t0, 1)
    q = (g.get("jcoql_query") or "").strip()
    row.update(valida="SI" if g.get("is_valid") else "NO", tentativi=g.get("attempts", ""), query_jcoql=q)
    if not g.get("is_valid") or not q:
        row["esito"] = "NON VALIDA"
        row["dettaglio"] = str(g.get("validation_errors") or g.get("error") or g.get("detail") or "")[:300]
        return row
    exp = V.expected(nl, C)
    try:
        j = requests.post(f"{V.BACKEND}/api/execute",
                          json={"jcoql_query": q, "database_name": V.DB, "timeout_seconds": exec_timeout},
                          timeout=exec_timeout + 30).json()
    except Exception as ex:
        row.update(esito="ERRORE ESECUZIONE", dettaglio=str(ex)[:200]); return row
    if not j.get("success"):
        row.update(esito="ERRORE ESECUZIONE", dettaglio=str(j.get("error") or j.get("detail"))[:200]); return row
    esito, det = V.compare(exp, j)
    row.update(esito=esito, dettaglio=det)
    return row

def summarize(rows):
    out = []
    keys = sorted({(r["modello"], r["query_id"]) for r in rows},
                  key=lambda k: (DEFAULT_MODELS.index(k[0]) if k[0] in DEFAULT_MODELS else 99, k[1]))
    for m, qid in keys:
        rs = [r for r in rows if r["modello"] == m and r["query_id"] == qid]
        n = len(rs)
        qs = collections.Counter(norm(r["query_jcoql"]) for r in rs)
        top = qs.most_common(1)[0][1] if qs else 0
        ok = sum(r["esito"].startswith("ESATTO") for r in rs)
        valid = sum(r["valida"] == "SI" for r in rs)
        tg = [float(r["tempo_gen_s"]) for r in rs if r["tempo_gen_s"] != ""]
        out.append({"modello": m, "query_id": qid, "run": n, "query_distinte": len(qs),
                    "stessa_query_%": round(100 * top / n) if n else 0,
                    "valide": f"{valid}/{n}", "corrette": f"{ok}/{n}",
                    "esiti_distinti": len({r['esito'].split(' (')[0] for r in rs}),
                    "tempo_medio_s": round(sum(tg) / len(tg), 1) if tg else ""})
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--gen-timeout", type=int, default=1500)
    ap.add_argument("--exec-timeout", type=int, default=120)
    ap.add_argument("--pause-gemini", type=int, default=20,
                    help="secondi di pausa dopo ogni chiamata a Gemini (limite di token/minuto)")
    ap.add_argument("--wait-rate-limit", type=int, default=70,
                    help="secondi di attesa prima di rifare un run fallito per quota")
    ap.add_argument("--max-rate-retries", type=int, default=4)
    ap.add_argument("--redo-invalid", action="store_true",
                    help="elimina dal file i run NON VALIDA / ERRORE dei modelli indicati e li rifa")
    a = ap.parse_args()

    C = V.load_collections_mongo()
    rows, done = load_done()
    if a.redo_invalid and rows:
        keep = [r for r in rows if not (r["modello"] in a.models and r["esito"] in ("NON VALIDA", "ERRORE GENERAZIONE", "ERRORE ESECUZIONE"))]
        print(f"--redo-invalid: eliminati {len(rows) - len(keep)} run da rifare")
        with open(OUT_RUNS, "w", newline="", encoding="utf-8-sig") as f0:
            w0 = csv.DictWriter(f0, fieldnames=FIELDS); w0.writeheader(); w0.writerows(keep)
        rows = keep; done = {(r["modello"], r["query_id"], int(r["run"])) for r in rows}
    new_file = not os.path.exists(OUT_RUNS)
    fh = open(OUT_RUNS, "a", newline="", encoding="utf-8-sig")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file:
        w.writeheader()
    for m in a.models:
        r = requests.post(f"{V.BACKEND}/api/set_llm", params={"llm_type": m})
        if r.status_code != 200:
            print(f"!! impossibile selezionare {m}: {r.text[:100]}"); continue
        print(f"=== modello {m} ===")
        for run in range(1, a.runs + 1):            # round-robin: una passata su tutte le query per run
            for qid, nl in QUERIES:
                if (m, qid, run) in done:
                    continue
                row = one_run(m, qid, nl, run, C, a.gen_timeout, a.exec_timeout)
                tries = 0
                while is_rate_limited(row) and tries < a.max_rate_retries:
                    tries += 1
                    print(f"   quota/timeout ({row['dettaglio'][:60]!r}): attendo {a.wait_rate_limit}s e rifaccio ({tries}/{a.max_rate_retries})")
                    time.sleep(a.wait_rate_limit)
                    row = one_run(m, qid, nl, run, C, a.gen_timeout, a.exec_timeout)
                if m == "gemini" and a.pause_gemini:
                    time.sleep(a.pause_gemini)
                w.writerow(row); fh.flush(); rows.append(row)
                print(f"[{m} run {run}/{a.runs}] {qid:9} {row['esito']:24} {row['tempo_gen_s']}s  tent={row['tentativi']}")
    fh.close()
    summ = summarize(rows)
    with open(OUT_SUM, "w", newline="", encoding="utf-8-sig") as f:
        sw = csv.DictWriter(f, fieldnames=list(summ[0])); sw.writeheader(); sw.writerows(summ)
    print("\nRIEPILOGO");
    for s in summ:
        print(f"{s['modello']:8} {s['query_id']:9} stessa query {s['stessa_query_%']:>3}%  distinte={s['query_distinte']}  valide {s['valide']}  corrette {s['corrette']}")
    print("scritti", OUT_RUNS, "e", OUT_SUM)

if __name__ == "__main__":
    main()
