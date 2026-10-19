"""
ft_vocab_expand.py - amplia il vocabolario degli schemi sintetici con Gemini (nessun dominio scritto a mano).

Gemini inventa nuovi domini (entita', campi, valori) nello STESSO formato di ft_vocab.json; ogni voce
viene validata in modo rigido prima di essere accettata. Le voci accettate vanno in ft_vocab_extra.json,
che ft_gen.py carica insieme a ft_vocab.json. Si puo' rilanciare piu' volte: aggiunge senza duplicare.

Uso (dalla cartella finetune, con la chiave in .env come per il backend):
    ..\\venv\\Scripts\\python.exe .\\ft_vocab_expand.py --domains 8 --rounds 3
    ..\\venv\\Scripts\\python.exe .\\ft_vocab_expand.py --selftest      # controlla solo il validatore, senza Gemini
"""
import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "ft_vocab.json")
EXTRA = os.path.join(HERE, "ft_vocab_extra.json")
SCALAR = ("num", "enum", "text", "null", "bool")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
# domini tenuti fuori: sono quelli dei database di prova (e-commerce) e dei dataset reali di test
BANNED = ("product", "order", "user", "movie", "film", "restaurant", "listing", "airbnb", "comment", "theater")
BAD_CHARS = re.compile(r"""['"\;{}\[\]]""")


def _ok_value(v):
    return isinstance(v, str) and 0 < len(v) <= 24 and not BAD_CHARS.search(v)


def _clean_values(vals):
    """Tiene i valori validi e distinti (max 8); None se ne restano meno di 2."""
    if not isinstance(vals, list):
        return None
    out = []
    for v in vals:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v = str(v)
        if _ok_value(v) and v not in out:
            out.append(v)
    return out[:8] if len(out) >= 2 else None


def _repair_field(f, nested=False):
    """Ripara un campo SENZA cambiarne il significato; se non e' riparabile lo lascia com'e' (lo scartera' il validatore)."""
    if not (isinstance(f, list) and len(f) == 4):
        return f
    name, it, kind, extra = f
    if isinstance(it, str):
        it = re.sub(r"\s+", " ", it.replace("_", " ")).strip()
    if kind in ("enum", "text", "null", "arr_scalar"):
        c = _clean_values(extra)
        extra = c if c else extra
    elif kind == "bool":
        extra = None
    elif kind in ("obj", "arr_obj") and isinstance(extra, list) and not nested:
        extra = [_repair_field(x, nested=True) for x in extra]
    return [name, it, kind, extra]


def repair_entity(e):
    if not isinstance(e, dict):
        return e
    e = dict(e)
    if isinstance(e.get("it"), str):
        e["it"] = re.sub(r"\s+", " ", e["it"].replace("_", " ")).strip().lower()
    if isinstance(e.get("fields"), list):
        e["fields"] = [_repair_field(f) for f in e["fields"]]
    return e


def validate_field(f, allow_nested=True):
    if not (isinstance(f, list) and len(f) == 4):
        return "campo non e' una lista di 4 elementi"
    name, it, kind, extra = f
    if not (isinstance(name, str) and NAME_RE.match(name)):
        return f"nome campo non valido: {name!r}"
    if not (isinstance(it, str) and 0 < len(it) <= 40 and not BAD_CHARS.search(it)):
        return f"etichetta italiana non valida: {it!r}"
    if kind == "num":
        if not (isinstance(extra, list) and len(extra) == 3 and extra[2] in ("int", "float")
                and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in extra[:2]) and extra[0] < extra[1]):
            return f"extra num non valido: {extra!r}"
    elif kind in ("enum", "text", "null"):
        if not (isinstance(extra, list) and 2 <= len(extra) <= 8 and all(_ok_value(v) for v in extra) and len(set(extra)) == len(extra)):
            return f"valori non validi per {name}: {extra!r}"
    elif kind == "bool":
        if extra is not None:
            return "extra di bool deve essere null"
    elif kind in ("obj", "arr_obj") and allow_nested:
        if not (isinstance(extra, list) and 2 <= len(extra) <= 3):
            return f"sottocampi non validi per {name}"
        subs = set()
        for s in extra:
            if not isinstance(s, list) or len(s) != 4 or s[2] not in SCALAR:
                return f"sottocampo non valido in {name}: {s!r}"
            e = validate_field(s, allow_nested=False)
            if e:
                return e
            if s[0] in subs:
                return f"sottocampo duplicato {s[0]}"
            subs.add(s[0])
    elif kind == "arr_scalar":
        if not (isinstance(extra, list) and 3 <= len(extra) <= 8 and all(_ok_value(v) for v in extra) and len(set(extra)) == len(extra)):
            return f"valori non validi per array {name}: {extra!r}"
    else:
        return f"tipo non ammesso: {kind!r}"
    return None


def validate_entity(e, taken_names):
    if not isinstance(e, dict):
        return "entita' non e' un oggetto"
    for k in ("en", "plural_en", "it", "fields"):
        if k not in e:
            return f"manca {k}"
    for k in ("en", "plural_en"):
        if not (isinstance(e[k], str) and NAME_RE.match(e[k])):
            return f"{k} non valido: {e[k]!r}"
    if not (isinstance(e["it"], str) and re.match(r"^[a-zà-ú ]{3,30}$", e["it"])):
        return f"plurale italiano non valido: {e['it']!r}"
    if any(b in e["en"] or b in e["plural_en"] for b in BANNED):
        return f"entita' esclusa ({e['en']})"
    if e["plural_en"] in taken_names or e["en"] in taken_names:
        return f"entita' duplicata ({e['en']})"
    fields = e["fields"]
    if not (isinstance(fields, list) and 5 <= len(fields) <= 10):
        return "servono da 5 a 10 campi"
    names, its = set(), set()
    for f in fields:
        err = validate_field(f)
        if err:
            return err
        if f[0] in names or f[1] in its or f[0] == "_id":
            return f"campo duplicato o riservato: {f[0]}"
        names.add(f[0]); its.add(f[1])
    kinds = [f[2] for f in fields]
    if sum(k == "num" for k in kinds) < 1 or not any(k in ("enum", "text") for k in kinds) or not any(k in ("bool", "null") for k in kinds):
        return "servono almeno 1 campo num, 1 enum/text e 1 bool/null"
    return None


def validate_domain(name, ents, taken):
    if not (isinstance(name, str) and NAME_RE.match(name)):
        return f"nome dominio non valido: {name!r}"
    if not (isinstance(ents, list) and 2 <= len(ents) <= 3):
        return "servono 2 o 3 entita' per dominio"
    local = set(taken)
    for e in ents:
        err = validate_entity(e, local)
        if err:
            return err
        local.update((e["en"], e["plural_en"]))
    return None


def load_vocab():
    out = {}
    for p in (BASE, EXTRA):
        if os.path.exists(p):
            out.update(json.load(open(p, encoding="utf-8"))["domains"])
    return out


EXAMPLE = {"en": "member", "plural_en": "members", "it": "iscritti", "fields": [
    ["name", "nome", "text", ["Anna", "Luca", "Marta", "Paolo"]],
    ["age", "età", "num", [14, 85, "int"]],
    ["city", "città", "enum", ["Milano", "Roma", "Torino"]],
    ["active", "attivo", "bool", None],
    ["email", "email", "null", ["a@mail.it", "b@mail.it", "c@mail.it"]],
    ["interests", "interessi", "arr_scalar", ["sport", "musica", "viaggi"]],
    ["address", "indirizzo", "obj", [["street", "via", "text", ["Via Roma", "Via Dante"]], ["zip", "cap", "num", [10000, 99999, "int"]]]],
    ["loans", "prestiti", "arr_obj", [["title", "titolo", "text", ["Il faro", "Mare nero", "Terra rossa"]], ["days", "giorni", "num", [1, 30, "int"]]]]]}


def make_prompt(n, existing):
    return f"""Genera {n} NUOVI domini per schemi di database di prova. Rispondi SOLO con JSON valido: un oggetto
{{"<nome_dominio>": [ <entita'>, <entita'> ]}} con 2 o 3 entita' per dominio.

Formato di UNA entita' (esempio, da NON ricopiare):
{json.dumps(EXAMPLE, ensure_ascii=False)}

Regole del formato:
- "en" singolare e "plural_en" plurale inglese, minuscoli, solo a-z, cifre e underscore; "it" plurale italiano minuscolo.
- ogni campo e' [nome_en, etichetta_italiana, tipo, extra]; nome_en minuscolo con underscore (mai "_id").
- tipi: "num" con extra [min, max, "int" oppure "float"]; "enum" e "text" e "null" (stringa che puo' mancare) con 3-8 valori
  stringa distinti, brevi (max 24 caratteri), senza apici, virgolette, punto e virgola, parentesi; "bool" con extra null;
  "arr_scalar" con 3-8 valori stringa; "obj" e "arr_obj" con 2-3 sottocampi [nome, etichetta, tipo scalare, extra] (un solo livello).
- ogni entita' ha 5-10 campi, di cui almeno 2 "num" (meglio), almeno 1 "enum" o "text", almeno 1 "bool" o "null"; includi un "arr_scalar",
  "obj" o "arr_obj" in circa meta' delle entita'.
- etichette italiane naturali (parole separate da spazi, mai underscore) e diverse tra loro, valori realistici in italiano.
- VARIA la forma delle entita': numero di campi diverso (da 5 a 10), non sempre la stessa sequenza di tipi; usa spesso piu' campi
  "num" (3-4) e piu' "enum"; includi campi "null" (valori che possono mancare) e "obj" annidati in almeno un terzo delle entita'.
Varieta': domini lontani tra loro (industria, agricoltura, trasporti, banca, turismo, musica, energia, scuola, telefonia, ecc.).
NON usare questi domini gia' presenti: {", ".join(sorted(existing))}.
NON usare e-commerce (prodotti, ordini, utenti), film, ristoranti, alloggi in affitto, recensioni."""


def call_gemini(prompt, temperature=0.9):
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(HERE, "..", ".env")); load_dotenv()
    except Exception:
        pass
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    m = genai.GenerativeModel("gemini-3.1-flash-lite-preview",
                              generation_config=genai.GenerationConfig(temperature=temperature, response_mime_type="application/json"))
    return m.generate_content(prompt).text


def merge_extra(new_domains):
    cur = json.load(open(EXTRA, encoding="utf-8"))["domains"] if os.path.exists(EXTRA) else {}
    cur.update(new_domains)
    json.dump({"_nota": "Generato da ft_vocab_expand.py (Gemini) e validato.", "domains": cur},
              open(EXTRA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return len(cur)


# ----------------------------------------------------------------------------- arricchimento
def make_enrich_prompt(batch):
    items = []
    for e in batch:
        have = [[f[0], f[2]] for f in e["fields"]]
        miss = [k for k, kk in (("null", ("null",)), ("enum", ("enum",)), ("obj", ("obj", "arr_obj"))) if not any(f[2] in kk for f in e["fields"])]
        items.append({"en": e["en"], "it": e["it"], "campi_esistenti": have, "tipi_che_mancano": miss})
    return f"""Per ciascuna entita' di un database di prova aggiungi da 2 a 3 NUOVI campi plausibili, coerenti con l'entita'.
Rispondi SOLO con JSON: {{"<en>": [ <campo>, <campo>, ... ]}} una chiave per entita'.
Ogni campo e' [nome_en, etichetta_italiana, tipo, extra] (nome_en minuscolo con underscore, mai "_id", diverso dagli esistenti).
Tipi: "num" extra [min, max, "int"|"float"]; "enum" o "text" o "null" con 3-8 valori stringa distinti, brevi, senza apici/virgolette/;/parentesi
("null" = stringa che puo' mancare, es. note, telefono, data di chiusura); "bool" con extra null;
"obj" con 2-3 sottocampi [nome, etichetta, tipo scalare, extra] (un solo livello).
Includi SEMPRE i tipi indicati in "tipi_che_mancano" (se la lista e' vuota, scegli liberamente). Etichette italiane naturali con spazi, mai underscore.
Entita':
{json.dumps(items, ensure_ascii=False)}"""


def apply_enrichment(e, new_fields, max_fields=10):
    """Aggiunge a e['fields'] i campi nuovi validi (nome ed etichetta non gia' usati). Ritorna quanti ne ha aggiunti."""
    names = {f[0] for f in e["fields"]}
    its = {f[1] for f in e["fields"]}
    added = 0
    for f in new_fields if isinstance(new_fields, list) else []:
        f = _repair_field(f)
        if len(e["fields"]) >= max_fields or added >= 3:
            break
        if validate_field(f) or f[0] in names or f[1] in its or f[0] == "_id":
            continue
        e["fields"].append(f); names.add(f[0]); its.add(f[1]); added += 1
    return added


def enrich_all(batch_size, pause, only_short):
    cur = json.load(open(EXTRA, encoding="utf-8"))["domains"]
    ents = [e for v in cur.values() for e in v]
    todo = [e for e in ents if not only_short or len(e["fields"]) < 8]
    print(f"entita' da arricchire: {len(todo)} su {len(ents)}")
    tot = 0
    for i in range(0, len(todo), batch_size):
        batch = todo[i:i + batch_size]
        try:
            data = json.loads(call_gemini(make_enrich_prompt(batch), temperature=0.7))
        except Exception as ex:
            print(f"   batch {i // batch_size + 1}: errore {ex!r}"); time.sleep(pause); continue
        n = sum(apply_enrichment(e, data.get(e["en"], [])) for e in batch)
        tot += n
        print(f"   batch {i // batch_size + 1}: +{n} campi su {len(batch)} entita'")
        json.dump({"_nota": "Generato da ft_vocab_expand.py (Gemini) e validato.", "domains": cur},
                  open(EXTRA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        time.sleep(pause)
    print(f"aggiunti {tot} campi in totale")


def selftest():
    base = json.load(open(BASE, encoding="utf-8"))["domains"]
    bad = 0
    for dname, ents in base.items():
        err = validate_domain(dname, ents, taken=set())
        print(f"{dname:12} {'OK' if not err else 'NO: ' + err}")
        bad += bool(err)
    print("--- casi che il validatore deve RIFIUTARE:")
    neg = [("prodotti", [{"en": "product", "plural_en": "products", "it": "prodotti", "fields": []}] * 2),
           ("x1", [dict(base["hotel"][0], fields=[[f"c{i}", f"c{i}", "num", [5, 1, "int"]] for i in range(5)])] * 2),
           ("x2", [dict(base["hotel"][0], fields=[[f"c{i}", f"c{i}", "enum", ["a'b", "c", "d"]] for i in range(5)])] * 2),
           ("x3", [dict(base["hotel"][0], fields=[["_id", "id", "num", [1, 5, "int"]]] + base["hotel"][0]["fields"][:4])] * 2),
           ("x4", [dict(base["hotel"][0], fields=[[f"c{i}", f"c{i}", "enum", ["a", "b"]] for i in range(5)])] * 2)]
    for n, e in neg:
        print(f"{n:12} rifiutato: {validate_domain(n, e, set())}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--domains", type=int, default=8, help="domini richiesti per chiamata")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--pause", type=float, default=6)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--enrich", action="store_true", help="aggiunge 2-3 campi (nulli, enum, oggetti) alle entita' di ft_vocab_extra.json")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--all", action="store_true", help="con --enrich: anche le entita' che hanno gia' 8+ campi")
    a = ap.parse_args()
    if a.enrich:
        enrich_all(a.batch, a.pause, only_short=not a.all)
        return
    if a.selftest:
        sys.exit(1 if selftest() else 0)
    for r in range(1, a.rounds + 1):
        vocab = load_vocab()
        taken = {x for ents in vocab.values() for e in ents for x in (e["en"], e["plural_en"])}
        try:
            data = json.loads(call_gemini(make_prompt(a.domains, vocab)))
        except Exception as ex:
            print(f"giro {r}: errore {ex!r}"); time.sleep(a.pause); continue
        ok, ko = {}, 0
        for dname, ents in (data.items() if isinstance(data, dict) else []):
            if dname in vocab or dname in ok:
                ko += 1; continue
            ents = [repair_entity(e) for e in ents] if isinstance(ents, list) else ents
            err = validate_domain(dname, ents, taken)
            if err:
                ko += 1; print(f"   scartato {dname}: {err}"); continue
            ok[dname] = ents
            taken.update(x for e in ents for x in (e["en"], e["plural_en"]))
        tot = merge_extra(ok) if ok else len(json.load(open(EXTRA))["domains"]) if os.path.exists(EXTRA) else 0
        print(f"giro {r}/{a.rounds}: accettati {len(ok)}, scartati {ko}; domini extra totali {tot}")
        time.sleep(a.pause)


if __name__ == "__main__":
    main()
