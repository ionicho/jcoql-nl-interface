"""
rerun_extended.py - round 1-3 (41 richieste) + 37 richieste nuove (22 comuni F + 15 difficili D) = 78 richieste,
con il prompt snello e/o completo per i modelli locali. Ogni richiesta: /api/generate -> /api/execute -> confronto con l'atteso.

Richiede nella stessa cartella: verify_execution.py, repeatability.py, rerun_rounds.py, extended_tests.py.
Il backend deve avere /api/set_local_prompt_mode (main.py aggiornato). Riprendibile: scrive ogni riga subito su extended_runs.csv.

ATTENZIONE: ogni chiamata a /api/generate scrive anche in test_campaign_log.csv.
    copy test_campaign_log.csv test_campaign_log_prima_extended.csv

Uso (backend avviato su localhost:8000):
    .\\venv\\Scripts\\python.exe .\\rerun_extended.py --models gemma4 --modes compact full
    .\\venv\\Scripts\\python.exe .\\rerun_extended.py --models llama llama32 --modes compact
    .\\venv\\Scripts\\python.exe .\\rerun_extended.py --models gemini
    .\\venv\\Scripts\\python.exe .\\rerun_extended.py --models llama --modes tuned   (LLAMACPP_URL + llama-server v3)
    .\\venv\\Scripts\\python.exe .\\rerun_extended.py --models gemma4 --modes compact full --runs 3
Opzioni: --groups R1 R2 R3 F D (default tutti), --runs N (giri per richiesta),
         --redo parola [parola ...]  rifà solo le richieste che contengono quelle parole, es. --redo tracking
Output: extended_runs.csv, extended_riepilogo.csv
"""
import argparse, csv, json, os, time
import requests
import verify_execution as V
import repeatability as R
import rerun_rounds as RR
import extended_tests as X

LOCAL = ("gemma4", "llama", "llama32", "gemma")
GROUPS = [(name, qs) for name, qs in RR.ROUNDS] + list(X.NEW_SETS)
OUT, OUT_SUM = "extended_runs.csv", "extended_riepilogo.csv"
FIELDS = ["modello", "modo_prompt", "gruppo", "n", "run", "query_nl", "valida", "tentativi", "tempo_gen_s",
          "query_jcoql", "esito", "dettaglio"]

def load_context():
    from pymongo import MongoClient
    db = MongoClient("mongodb://localhost:27017")[V.DB]
    C = {c: list(db[c].find({})) for c in ("products", "orders", "users")}
    C["category_translations"] = list(db["category_translations"].find({})) if "category_translations" in db.list_collection_names() else []
    return C

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gemma4"])
    ap.add_argument("--modes", nargs="+", default=["compact"], choices=["compact", "full", "tuned"])
    ap.add_argument("--groups", nargs="+", default=[g for g, _ in GROUPS])
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--redo", nargs="+", default=[], help="rifà le richieste il cui testo contiene una di queste parole (le righe vecchie restano nel file; vale l'ultima)")
    ap.add_argument("--gen-timeout", type=int, default=1500)
    ap.add_argument("--exec-timeout", type=int, default=600)
    ap.add_argument("--pause-gemini", type=int, default=20)
    ap.add_argument("--wait-rate-limit", type=int, default=70)
    ap.add_argument("--max-rate-retries", type=int, default=4)
    a = ap.parse_args()

    X.install()
    C = load_context()
    rows = list(csv.DictReader(open(OUT, encoding="utf-8-sig"))) if os.path.exists(OUT) else []
    redo = [x.lower() for x in a.redo]
    done = {(r["modello"], r["modo_prompt"], r["query_nl"], int(r["run"])) for r in rows
            if not any(x in r["query_nl"].lower() for x in redo)}
    new_file = not os.path.exists(OUT)
    fh = open(OUT, "a", newline="", encoding="utf-8-sig"); w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file: w.writeheader()
    sel = [(g, qs) for g, qs in GROUPS if g in a.groups]
    tot = sum(len(q) for _, q in sel) * a.runs
    try:
        for m in a.models:
            rr = requests.post(f"{V.BACKEND}/api/set_llm", params={"llm_type": m})
            if rr.status_code != 200:
                print(f"!! impossibile selezionare {m}"); continue
            for mode in (a.modes if m in LOCAL else ["n/a"]):
                if m in LOCAL:
                    r2 = requests.post(f"{V.BACKEND}/api/set_local_prompt_mode", params={"mode": mode})
                    if r2.status_code != 200:
                        print("!! il backend non ha /api/set_local_prompt_mode: aggiorna main.py e riavvia"); return
                print(f"=== {m} / prompt {mode} ===")
                k = 0
                for run in range(1, a.runs + 1):
                    for g, qs in sel:
                        for n, nl in enumerate(qs, 1):
                            k += 1
                            if (m, mode, nl, run) in done: continue
                            row = R.one_run(m, f"{g}-{n}", nl, run, C, a.gen_timeout, a.exec_timeout)
                            tries = 0
                            while R.is_rate_limited(row) and tries < a.max_rate_retries:
                                tries += 1; print(f"   quota/timeout: attendo {a.wait_rate_limit}s ({tries}/{a.max_rate_retries})")
                                time.sleep(a.wait_rate_limit)
                                row = R.one_run(m, f"{g}-{n}", nl, run, C, a.gen_timeout, a.exec_timeout)
                            if m == "gemini" and a.pause_gemini: time.sleep(a.pause_gemini)
                            out = {"modello": m, "modo_prompt": mode, "gruppo": g, "n": n, "run": run, "query_nl": nl,
                                   "valida": row["valida"], "tentativi": row["tentativi"], "tempo_gen_s": row["tempo_gen_s"],
                                   "query_jcoql": row["query_jcoql"], "esito": row["esito"], "dettaglio": row["dettaglio"]}
                            w.writerow(out); fh.flush(); rows.append(out)
                            print(f"[{m}/{mode} {k}/{tot}] {g}-{n:<2} {row['esito'][:26]:26} {row['tempo_gen_s']}s")
    finally:
        fh.close()
        try: requests.post(f"{V.BACKEND}/api/set_local_prompt_mode", params={"mode": "compact"})
        except Exception: pass

    last = {}
    for r in rows:   # per ogni (modello, prompt, richiesta, giro) vale l'ultima riga scritta
        last[(r["modello"], r["modo_prompt"], r["query_nl"], r["run"])] = r
    rows = list(last.values())
    summ = []
    keys = sorted({(r["modello"], r["modo_prompt"]) for r in rows})
    for m, mode in keys:
        for g in [x for x, _ in GROUPS] + ["TOT"]:
            rs = [r for r in rows if r["modello"] == m and r["modo_prompt"] == mode and (g == "TOT" or r["gruppo"] == g)]
            if not rs: continue
            tg = [float(r["tempo_gen_s"]) for r in rs if r["tempo_gen_s"] != ""]
            summ.append({"modello": m, "modo_prompt": mode, "gruppo": g, "righe": len(rs),
                         "valide": sum(r["valida"] == "SI" for r in rs),
                         "esatte": sum(r["esito"].startswith("ESATTO") for r in rs),
                         "tempo_medio_s": round(sum(tg) / len(tg), 1) if tg else ""})
    if summ:
        with open(OUT_SUM, "w", newline="", encoding="utf-8-sig") as f:
            sw = csv.DictWriter(f, fieldnames=list(summ[0])); sw.writeheader(); sw.writerows(summ)
    print("\nRIEPILOGO (esatte su righe)")
    for s in summ:
        print(f"{s['modello']:8} {s['modo_prompt']:8} {s['gruppo']:4} righe {s['righe']:>3}  valide {s['valide']:>3}  esatte {s['esatte']:>3}  tempo medio {s['tempo_medio_s']}s")
    print("scritti", OUT, "e", OUT_SUM)

if __name__ == "__main__":
    main()
