"""
ft_translate_train_v4.py - traduce in INGLESE la richiesta di ogni esempio del training v4 (out_v4\\train_final_v4.jsonl), cosi' il modello
si addestra su italiano E inglese. Cambia solo il testo tra le virgolette di RICHIESTA: schema, template del prompt (italiano), query di
riferimento restano identici. Quindi l'etichetta (la query) resta quella verificata per esecuzione: la traduzione della richiesta non puo'
renderla sbagliata, puo' al piu' tradire il significato della richiesta; per questo ogni traduzione e' controllata.

Controlli (gli stessi di ft_translate_eval.py, piu' un giudice in batch):
  1. numeri identici;  2. valori d'esempio dello schema e valori testuali della query di riferimento, presenti nella richiesta italiana,
  identici nella traduzione;  3. Gemini (temperatura 0) conferma che le due frasi chiedono la stessa cosa.
Riprendibile: ogni risultato e' scritto subito in out_v4\\train_en_cache.jsonl; se si ferma (quota, rete) basta rilanciare.
Una traduzione scartata viene ritentata nei lanci successivi (fino a 3 volte), poi esclusa.

Uso (da finetune\\, GEMINI_API_KEY nel .env):
    ..\\venv\\Scripts\\python.exe .\\ft_translate_train_v4.py --probe          # prova la quota con una chiamata
    ..\\venv\\Scripts\\python.exe .\\ft_translate_train_v4.py --limit 45        # prova su 45 esempi, poi guarda il cache
    ..\\venv\\Scripts\\python.exe .\\ft_translate_train_v4.py                   # tutto (circa 800 chiamate)
    ..\\venv\\Scripts\\python.exe .\\ft_translate_train_v4.py --build           # scrive out_v4\\train_final_v4_bi.jsonl (italiano + inglese)
"""
import argparse, json, os, random, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ft_translate_eval as T

IN = os.path.join(HERE, "out_v4", "train_final_v4.jsonl")
CACHE = os.path.join(HERE, "out_v4", "train_en_cache.jsonl")
OUT = os.path.join(HERE, "out_v4", "train_final_v4_bi.jsonl")

BATCH_JUDGE = """For each numbered pair, decide whether the Italian and the English request ask a database for exactly the same thing: same conditions, same comparison operators and directions (more than / at least / less than / between / different from), same logical connectors (and / or / not), same collections and fields. Ignore language and wording.
Return ONLY JSON: {{"different": [<ids of the pairs that are NOT equivalent>]}}  (empty list if all are equivalent).

{items}
"""


EXTRA = """
STRICT: the output must be entirely English except for the data values (kept as written). Every other Italian word, including the names of collections and fields (e.g. "previsioni" -> "forecasts", "alberi" -> "trees", "livello confidenza" -> "confidence level", "atmosfera falso" -> "atmosphere false"), must be translated into the natural English word, even when it looks like an identifier. Names written with underscores (new_field_name) stay as written.
Examples: "Elenca le previsioni con livello confidenza inferiore a 3" -> "List the forecasts with a confidence level below 3"; "Collega i campi agli abbonamenti" -> "Link the fields to the subscriptions".
"""

# parole che restano uguali in italiano e inglese (o nomi propri/sigle): non sono errori
SAME_OK = {"database", "query", "totale", "tipo", "area", "area", "video", "audio", "menu", "data", "radio", "email", "mail", "hotel",
           "club", "sport", "team", "film", "bar", "originale", "normale", "locale", "personale", "manual", "manuale", "finale", "digitale",
           "capitale", "minimo", "massimo", "media", "medio", "totali", "stazione", "gas", "pizza", "software", "hardware", "online", "offline",
           "volume", "firewall", "items", "false", "lorawan", "protocol", "sensor", "robot", "motor", "separate", "badge", "budget", "fragile", "credit", "ratio", "tablet", "extra", "manager", "premium", "server", "classic", "timestamp"}


_QUOTED = re.compile(r"'([^']+)'|\"([^\"]+)\"")


def _quoted_words(ctx):
    """parole (>=5 lettere) che compaiono tra virgolette nello schema/query dell'esempio: sono valori dei dati e restano come scritti."""
    out = set()
    for a, b in _QUOTED.findall(ctx or ""):
        out |= {w.lower() for w in re.findall(r"[^\W\d_]{5,}", a or b)}
    return out


def leftover_italian(it, en, ctx=""):
    """parole italiane rimaste nella traduzione: tokens della richiesta italiana (>=5 lettere) ricomparsi identici fuori da virgolette e identificatori."""
    en_clean = re.sub(r"(?<!\w)'[^']+'(?!\w)|\"[^\"]+\"|\b\w+_\w+\b", " ", en)
    it_clean = re.sub(r"(?<!\w)'[^']+'(?!\w)|\"[^\"]+\"|\b\w+_\w+\b", " ", it)
    it_w = {w.lower() for w in re.findall(r"[^\W\d_]{5,}", it_clean)}
    en_w = {w.lower() for w in re.findall(r"[^\W\d_]{5,}", en_clean)}
    # un valore di dato scritto senza virgolette (es. Parcheggio, La vita) e' lecito: lo accetto solo se maiuscolo nell'originale
    caps = {w.lower() for w in re.findall(r"(?<![\.\"] )(?<!^)\b[A-Z][a-zà-ù]{4,}", it)}
    return sorted((it_w & en_w) - SAME_OK - caps - _quoted_words(ctx))


class DailyQuota(Exception):
    pass


def gem(prompt, temperature, retries=6):
    for k in range(retries):
        try:
            return T.gem(prompt, temperature)
        except json.JSONDecodeError:
            time.sleep(2)
        except Exception as ex:
            msg = str(ex)
            if "429" in msg or "quota" in msg.lower():
                if "PerDay" in msg or "per day" in msg.lower():
                    raise DailyQuota(msg[:200])
                print(f"   limite al minuto: attendo 70 s ({k + 1}/{retries})", flush=True)
                time.sleep(70)
            else:
                print("   errore Gemini:", msg[:120], flush=True)
                time.sleep(5)
    raise RuntimeError("Gemini non risponde")


def load_cache():
    c = {}
    if os.path.exists(CACHE):
        for l in open(CACHE, encoding="utf-8"):
            r = json.loads(l)
            c[r["i"]] = r
    return c


def save(f, rec):
    f.write(json.dumps(rec, ensure_ascii=False) + "\n"); f.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=15)
    ap.add_argument("--max-tries", type=int, default=3)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args()

    if a.probe:
        try:
            print(gem('Return ONLY JSON: {"ok": true}', 0.0)); print("quota disponibile")
        except DailyQuota as q:
            print("quota giornaliera esaurita:", q)
        return

    rows = [json.loads(l) for l in open(IN, encoding="utf-8")]
    for i, r in enumerate(rows):
        r["_it"] = T.REQ.search(r["instruction"]).group(1)
    cache = load_cache()
    stale = [i for i, c in cache.items() if c.get("en") and leftover_italian(rows[i]["_it"], c["en"], rows[i]["instruction"] + " " + rows[i]["output"])]
    for i in stale:                                    # vecchie traduzioni con parole italiane rimaste: da rifare
        del cache[i]
    if stale:
        print(f"{len(stale)} traduzioni gia' in cache hanno parole italiane rimaste: le rifaccio", flush=True)

    if a.build:
        return build(rows, cache)

    todo = [i for i in range(len(rows)) if not (i in cache and (cache[i].get("en") or cache[i].get("tries", 0) >= a.max_tries))]
    if a.limit:
        todo = todo[:a.limit]
    print(f"{len(rows)} esempi | gia' tradotti: {sum(1 for c in cache.values() if c.get('en'))} | da fare in questo lancio: {len(todo)}", flush=True)
    f = open(CACHE, "a", encoding="utf-8")
    t0 = time.time(); done = 0
    try:
        for s in range(0, len(todo), a.batch):
            chunk = todo[s:s + a.batch]
            temp = 0.2 if all(cache.get(i, {}).get("tries", 0) == 0 for i in chunk) else 0.6
            items = "\n".join(f'{i}: {rows[i]["_it"]}' for i in chunk)
            out = gem(T.TR_PROMPT.format(items=items) + EXTRA, temp)
            got = {int(o["id"]): (o.get("en") or "").strip() for o in out if isinstance(o, dict) and "id" in o}
            cand, why = {}, {}
            for i in chunk:
                en = got.get(i, "")
                w = T.check(rows[i]["_it"], en, rows[i]["instruction"], rows[i]["output"])
                if w is None and (left := leftover_italian(rows[i]["_it"], en, rows[i]["instruction"] + " " + rows[i]["output"])):
                    w = "parole italiane rimaste: " + ", ".join(left)
                if w is None:
                    cand[i] = en
                else:
                    why[i] = w
            if cand:                                   # giudice in batch sulle candidate
                items = "\n".join(f'{i}) Italian: {rows[i]["_it"]}\n   English: {en}' for i, en in cand.items())
                j = gem(BATCH_JUDGE.format(items=items), 0.0)
                bad = {int(x) for x in (j.get("different") or [])}
                for i in list(cand):
                    if i in bad:
                        why[i] = "giudice: significato diverso"; cand.pop(i)
            for i in chunk:
                tries = cache.get(i, {}).get("tries", 0) + 1
                rec = {"i": i, "en": cand[i]} if i in cand else {"i": i, "tries": tries, "why": why.get(i, "mai tradotta")}
                cache[i] = rec; save(f, rec)
            done += len(chunk)
            ok = sum(1 for c in cache.values() if c.get("en"))
            el = time.time() - t0
            print(f"   {done}/{len(todo)}   tradotti in totale {ok}/{len(rows)}   ({el / 60:.1f} min, resto ~{el / done * (len(todo) - done) / 60:.0f} min)", flush=True)
    except DailyQuota as q:
        print("\nQUOTA GIORNALIERA ESAURITA:", q, "\nI risultati sono salvati: rilancia domani lo stesso comando, riprende da qui.")
    finally:
        f.close()
    ok = sum(1 for c in cache.values() if c.get("en"))
    fail = sum(1 for c in cache.values() if not c.get("en") and c.get("tries", 0) >= a.max_tries)
    print(f"\nrichieste tradotte e controllate: {ok}/{len(rows)}   scartate definitivamente: {fail}")


def build(rows, cache):
    out = [{k: r[k] for k in ("instruction", "input", "output")} for r in rows]
    n = 0
    for i, r in enumerate(rows):
        c = cache.get(i)
        if c and c.get("en"):
            new = dict(instruction=r["instruction"].replace(f'RICHIESTA: "{r["_it"]}"', f'RICHIESTA: "{c["en"]}"'), input=r["input"], output=r["output"])
            if new["instruction"] != r["instruction"]:
                out.append(new); n += 1
    random.Random(5).shuffle(out)
    with open(OUT, "w", encoding="utf-8") as f:
        for o in out:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    print(f"italiano: {len(rows)} | inglese aggiunti: {n} | totale: {len(out)}   -> {OUT}")
    print(f"lunghezza massima prompt (caratteri): {max(len(o['instruction']) for o in out)} (limite del training: max_length 1280 token)")
    print(f"passi di addestramento a 1 epoca, batch effettivo 8, dopo il 5% di validazione: circa {int(len(out) * 0.95 / 8)}")


if __name__ == "__main__":
    main()
