"""
stability.py - test di stabilita': la stessa richiesta ripetuta N volte (default 50) per ogni modello.

Per ogni (modello, richiesta, giro): /api/generate -> query JCoQL+. Ogni query DISTINTA (dopo normalizzazione
degli spazi) viene eseguita UNA sola volta e confrontata con l'atteso (oracolo di verify_execution.py /
extended_tests.py); le ripetizioni identiche riusano l'esito. Cosi' si misura sia quante query diverse produce
il modello, sia quante di quelle sono corrette, senza rieseguire 2500 volte il motore Java.

Richiede nella stessa cartella: verify_execution.py, repeatability.py, extended_tests.py.
Backend avviato su localhost:8000 (main.py aggiornato, con /api/set_local_prompt_mode).
Riprendibile: ogni riga viene scritta subito su stability_runs.csv; se lo interrompi e lo rilanci salta i giri gia' fatti.

ATTENZIONE: ogni chiamata a /api/generate viene registrata anche in test_campaign_log.csv. Prima di lanciare:
    copy test_campaign_log.csv test_campaign_log_prima_stabilita.csv

Uso:
    python stability.py --models llama32 gemma4 llama gemma
    python stability.py --models gemini --max-new 200       # Gemini a blocchi, per la quota giornaliera
    python stability.py --models llama --tuned               # Llama 3.1 con LoRA v3 (llama-server)
    python stability.py --summary-only                       # rigenera solo il riepilogo dai dati gia' raccolti
Opzioni: --runs N (default 50), --ids S1 S5 (solo alcune richieste), --max-new N (si ferma dopo N generazioni
         nuove in questa esecuzione), --no-clean (non cancella le collezioni temporanee in jcoql_test)
Output: stability_runs.csv (una riga per giro), stability_riepilogo.csv (una riga per modello e richiesta + totali)
"""
import argparse, collections, csv, os, re, sys, time
import requests
import verify_execution as V
import repeatability as R
import extended_tests as X

# Le 10 richieste: 3 comuni, 3 medie, 4 difficili (tutte con oracolo)
STAB_QUERIES = [
    ("S1",  "comune",    "Mostrami i prodotti con un prezzo compreso tra 200 e 700 euro"),
    ("S2",  "comune",    "Mostrami gli ordini senza numero di tracking"),
    ("S3",  "comune",    "Mostrami gli utenti attivi con l'email verificata"),
    ("S4",  "media",     "Raggruppa gli ordini per stato"),
    ("S5",  "media",     "Mostrami le recensioni dei prodotti con un voto uguale a 5"),
    ("S6",  "media",     "Collega ogni ordine ai prodotti acquistati"),
    ("S7",  "difficile", "Collega ogni ordine all'utente che lo ha effettuato e ai prodotti acquistati"),
    ("S8",  "difficile", "Unisci in un'unica collezione i prodotti food, electronics e books, senza duplicati"),
    ("S9",  "difficile", "Traduci la categoria di ogni prodotto usando il dizionario delle categorie"),
    ("S10", "difficile", "Mostrami i prodotti che sono sia biologici sia con un rating di almeno 4, usando l'intersezione"),
]
DEFAULT_MODELS = ["llama32", "gemma4", "llama", "gemma", "gemini"]   # dal piu' veloce; Gemini per ultimo (quota)
LOCAL = ("gemma4", "llama", "llama32", "gemma")
BASE_COLLECTIONS = {"products", "orders", "users", "category_translations"}
OUT, OUT_SUM = "stability_runs.csv", "stability_riepilogo.csv"
FIELDS = ["modello", "query_id", "livello", "query_nl", "run", "valida", "tentativi", "tempo_gen_s",
          "query_jcoql", "esito", "dettaglio", "versione"]
# "versione" = versione della pipeline con cui e' stata fatta la riga. Le righe nate prima della colonna sono
# "prima" (prima dei correttori JOIN-alias / MERGE-REMOVE-DUPLICATES / BETWEEN), tranne Gemma 1 S6-S10 ("dopo").
DEFAULT_VERSION = "dopo"


def load_rows():
    """Legge OUT; se manca la colonna 'versione' la aggiunge (una tantum) e riscrive il file."""
    if not os.path.exists(OUT):
        return []
    rows = list(csv.DictReader(open(OUT, encoding="utf-8-sig")))
    if rows and "versione" not in rows[0]:
        late = {f"S{i}" for i in range(6, 11)}
        for r in rows:
            r["versione"] = "dopo" if (r["modello"] == "gemma" and r["query_id"] in late) else "prima"
        with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
        print(f"(aggiunta la colonna 'versione' a {OUT}: {len(rows)} righe)")
    return rows


def current_view(rows, version=None):
    """version dato: solo quelle righe. Altrimenti, per ogni (modello, richiesta), le righe della versione
    piu' recente presente ('dopo' batte 'prima'): e' lo stato attuale dei dati."""
    if version:
        return [r for r in rows if r.get("versione") == version]
    rank = {"prima": 0}
    best = {}
    for r in rows:
        k = (r["modello"], r["query_id"])
        best[k] = max(best.get(k, -1), rank.get(r.get("versione"), 1))
    return [r for r in rows if rank.get(r.get("versione"), 1) == best[(r["modello"], r["query_id"])]]


def load_context():
    from pymongo import MongoClient
    db = MongoClient("mongodb://localhost:27017")[V.DB]
    C = {c: list(db[c].find({})) for c in ("products", "orders", "users")}
    C["category_translations"] = list(db["category_translations"].find({})) \
        if "category_translations" in db.list_collection_names() else []
    return C


def clean_extra_collections():
    """Cancella le collezioni temporanee lasciate da SAVE AS (entrano nello schema e inquinano i test)."""
    from pymongo import MongoClient
    db = MongoClient("mongodb://localhost:27017")[V.DB]
    extra = [c for c in db.list_collection_names() if c not in BASE_COLLECTIONS and not c.startswith("system.")]
    for c in extra:
        db.drop_collection(c)
    return extra


def generate(model, nl, gen_timeout):
    """Una sola generazione. Ritorna (riga_parziale, rate_limited)."""
    t0 = time.time()
    row = {"valida": "", "tentativi": "", "tempo_gen_s": "", "query_jcoql": "", "esito": "", "dettaglio": ""}
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


def judge(nl, q, C, exec_timeout):
    """Esegue la query e la confronta con l'atteso. Ritorna (esito, dettaglio)."""
    exp = V.expected(nl, C)
    try:
        j = requests.post(f"{V.BACKEND}/api/execute",
                          json={"jcoql_query": q, "database_name": V.DB, "timeout_seconds": exec_timeout},
                          timeout=exec_timeout + 30).json()
    except Exception as ex:
        return "ERRORE ESECUZIONE", str(ex)[:200]
    if not j.get("success"):
        return "ERRORE ESECUZIONE", str(j.get("error") or j.get("detail"))[:200]
    return V.compare(exp, j)


def summarize(rows):
    """rows: righe di stability_runs.csv. Ritorna la lista di righe di riepilogo."""
    out = []
    keyfun = lambda r: (r["modello"], r["query_id"])
    models = []
    for r in rows:
        if r["modello"] not in models:
            models.append(r["modello"])
    levels = {qid: lv for qid, lv, _ in STAB_QUERIES}

    def stats(rs, label_id, label_lv, label_nl, model):
        n = len(rs)
        valid = [r for r in rs if r["valida"] == "SI"]
        norms = [R.norm(r["query_jcoql"]) for r in rs if r["query_jcoql"]]
        cnt = collections.Counter(norms)
        exact_norm = {R.norm(r["query_jcoql"]) for r in rs if r["esito"].startswith("ESATTO")}
        wrong_norm = {R.norm(r["query_jcoql"]) for r in rs
                      if r["query_jcoql"] and r["valida"] == "SI" and not r["esito"].startswith("ESATTO")}
        att = [float(r["tentativi"]) for r in rs if str(r["tentativi"]).strip() != ""]
        tg = [float(r["tempo_gen_s"]) for r in rs if str(r["tempo_gen_s"]).strip() != ""]
        exact_runs = sum(r["esito"].startswith("ESATTO") for r in rs)
        top = cnt.most_common(1)[0][1] if cnt else 0
        return {"modello": model, "query_id": label_id, "livello": label_lv, "query_nl": label_nl, "giri": n,
                "valide": len(valid), "valide_pct": round(100 * len(valid) / n, 1) if n else "",
                "query_distinte": len(cnt),
                "query_piu_frequente_pct": round(100 * top / n, 1) if n else "",
                "identiche_tutti_i_giri": "SI" if n and len(cnt) == 1 and len(norms) == n else "NO",
                "giri_esatti": exact_runs, "esatti_pct": round(100 * exact_runs / n, 1) if n else "",
                "distinte_esatte": len(exact_norm), "distinte_sbagliate": len(wrong_norm),
                "tentativi_medi": round(sum(att) / len(att), 2) if att else "",
                "tempo_medio_s": round(sum(tg) / len(tg), 1) if tg else ""}

    def aggregate(per, label_id, label_lv, model):
        """Riga di totale dalle righe per-richiesta: i conteggi si sommano, le query distinte sono per richiesta
        (la media), perche' mescolare richieste diverse in un unico conteggio non avrebbe senso."""
        n = sum(p["giri"] for p in per)
        num = lambda k: [float(p[k]) for p in per if str(p[k]).strip() != ""]
        w = lambda k: round(sum(float(p[k]) * p["giri"] for p in per if str(p[k]).strip() != "") / n, 2) if n else ""
        return {"modello": model, "query_id": label_id, "livello": label_lv, "query_nl": f"{len(per)} richieste",
                "giri": n, "valide": sum(p["valide"] for p in per),
                "valide_pct": round(100 * sum(p["valide"] for p in per) / n, 1) if n else "",
                "query_distinte": round(sum(num("query_distinte")) / len(per), 1),
                "query_piu_frequente_pct": round(sum(num("query_piu_frequente_pct")) / len(per), 1),
                "identiche_tutti_i_giri": f"{sum(p['identiche_tutti_i_giri'] == 'SI' for p in per)}/{len(per)} richieste",
                "giri_esatti": sum(p["giri_esatti"] for p in per),
                "esatti_pct": round(100 * sum(p["giri_esatti"] for p in per) / n, 1) if n else "",
                "distinte_esatte": sum(p["distinte_esatte"] for p in per),
                "distinte_sbagliate": sum(p["distinte_sbagliate"] for p in per),
                "tentativi_medi": w("tentativi_medi"), "tempo_medio_s": w("tempo_medio_s")}

    for m in models:
        mrows = [r for r in rows if r["modello"] == m]
        per = []
        for qid, lv, nl in STAB_QUERIES:
            rs = [r for r in mrows if r["query_id"] == qid]
            if rs:
                per.append(stats(rs, qid, lv, nl, m))
        out.extend(per)
        for lv in ("comune", "media", "difficile"):
            sub = [p for p in per if p["livello"] == lv]
            if sub:
                out.append(aggregate(sub, f"TOT-{lv}", lv, m))
        if per:
            out.append(aggregate(per, "TOT", "tutte", m))
    return out


def write_summary(rows, version=None):
    rows = current_view(rows, version)
    summ = summarize(rows)
    if not summ:
        return summ
    out_sum = OUT_SUM if not version else OUT_SUM.replace(".csv", f"_{version}.csv")
    with open(out_sum, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0])); w.writeheader(); w.writerows(summ)
    print("\nRIEPILOGO (query distinte / giri, esatte %)")
    for s in summ:
        if s["query_id"].startswith("TOT") or s["query_id"].startswith("S"):
            print(f"{s['modello']:8} {s['query_id']:12} giri {s['giri']:>3}  valide {s['valide_pct']:>5}%  "
                  f"distinte {s['query_distinte']:>3}  piu' frequente {s['query_piu_frequente_pct']:>5}%  "
                  f"esatte {s['esatti_pct']:>5}%  tempo {s['tempo_medio_s']}s")
    print("scritto", out_sum)
    return summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--runs", type=int, default=50)
    ap.add_argument("--ids", nargs="+", default=[q for q, _, _ in STAB_QUERIES])
    ap.add_argument("--max-new", type=int, default=0, help="si ferma dopo N generazioni nuove (0 = nessun limite)")
    ap.add_argument("--versione", default=None,
                    help=f"etichetta delle righe NUOVE (default '{DEFAULT_VERSION}'); con --summary-only filtra il riepilogo")
    ap.add_argument("--no-clean", action="store_true")
    ap.add_argument("--tuned", action="store_true", help="prompt tuned (llama-server v3); le righe sono salvate come <modello>-tuned")
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--gen-timeout", type=int, default=1500)
    ap.add_argument("--exec-timeout", type=int, default=600)
    ap.add_argument("--pause-gemini", type=int, default=10)
    ap.add_argument("--wait-rate-limit", type=int, default=70)
    ap.add_argument("--max-rate-retries", type=int, default=4)
    a = ap.parse_args()

    rows = load_rows()
    if a.summary_only:
        write_summary(rows, a.versione); return
    ver = a.versione or DEFAULT_VERSION

    X.install()
    C = load_context()
    # i giri gia' fatti contano solo se della stessa versione: con una versione nuova si rifanno da capo
    done = {(r["modello"], r["query_id"], int(r["run"])) for r in rows if r.get("versione") == ver}
    # esiti gia' noti per (query_nl, query normalizzata): evita di rieseguire dopo un'interruzione
    verdict = {(r["query_nl"], R.norm(r["query_jcoql"])): (r["esito"], r["dettaglio"])
               for r in rows if r["query_jcoql"] and r["esito"] and not r["esito"].startswith("ERRORE")}
    new_file = not os.path.exists(OUT)
    fh = open(OUT, "a", newline="", encoding="utf-8-sig"); w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file: w.writeheader()
    sel = [(qid, lv, nl) for qid, lv, nl in STAB_QUERIES if qid in a.ids]
    new_count = 0
    stop = False
    try:
        for m in a.models:
            if stop: break
            lab = m + "-tuned" if a.tuned else m
            rr = requests.post(f"{V.BACKEND}/api/set_llm", params={"llm_type": m})
            if rr.status_code != 200:
                print(f"!! impossibile selezionare {m}"); continue
            if m in LOCAL:
                r2 = requests.post(f"{V.BACKEND}/api/set_local_prompt_mode", params={"mode": "tuned" if a.tuned else "compact"})
                if r2.status_code != 200:
                    print("!! il backend non ha /api/set_local_prompt_mode: aggiorna main.py e riavvia"); return
            print(f"=== {lab}{(' / prompt ' + ('tuned' if a.tuned else 'compact')) if m in LOCAL else ''} ===")
            for qid, lv, nl in sel:
                if stop: break
                if not a.no_clean:
                    extra = clean_extra_collections()
                    if extra: print(f"   (cancellate {len(extra)} collezioni temporanee)")
                for run in range(1, a.runs + 1):
                    if (lab, qid, run) in done: continue
                    if a.max_new and new_count >= a.max_new:
                        print(f"\nlimite --max-new {a.max_new} raggiunto: rilancia per proseguire"); stop = True; break
                    row = generate(m, nl, a.gen_timeout)
                    tries = 0
                    while R.is_rate_limited(row) and tries < a.max_rate_retries:
                        tries += 1
                        print(f"   quota/timeout: attendo {a.wait_rate_limit}s ({tries}/{a.max_rate_retries})")
                        time.sleep(a.wait_rate_limit)
                        row = generate(m, nl, a.gen_timeout)
                    if R.is_rate_limited(row):
                        print("\nquota ancora esaurita: giro NON salvato, mi fermo. Rilancia piu' tardi (riprende da qui).")
                        stop = True; break
                    q = row["query_jcoql"]
                    if row["valida"] == "SI" and q:
                        key = (nl, R.norm(q))
                        if key not in verdict:
                            verdict[key] = judge(nl, q, C, a.exec_timeout)
                        row["esito"], row["dettaglio"] = verdict[key]
                    out = {"modello": lab, "query_id": qid, "livello": lv, "query_nl": nl, "run": run, **row, "versione": ver}
                    w.writerow(out); fh.flush(); rows.append(out); new_count += 1
                    print(f"[{lab} {qid} {run}/{a.runs}] {row['esito'][:26]:26} {row['tempo_gen_s']}s")
                    if m == "gemini" and a.pause_gemini: time.sleep(a.pause_gemini)
    finally:
        fh.close()
        try: requests.post(f"{V.BACKEND}/api/set_local_prompt_mode", params={"mode": "compact"})
        except Exception: pass
    write_summary(rows, a.versione)


if __name__ == "__main__":
    main()
