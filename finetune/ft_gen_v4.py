"""
ft_gen_v4.py - dati NUOVI per v4. Non modifica ne' sostituisce ft_gen.py / ft_gen_v3.py: li importa e scrive in una cartella a parte.

Famiglie nuove rispetto a v1-v3 (tutte dalla grammatica ufficiale JCoQL.g, nessuno schema scritto a mano):
  join3          join a tre collezioni: JOIN, SAVE AS chaintemp1, JOIN con la terza (alias posizionali x/y come in v3)
  translate      GET DICTIONARY + TRANSLATE dentro FILTER GENERATE ADD FIELDS (dizionario = collezione con campi key/value,
                 costruita dai dati: valori distinti di un campo enum, oppure _id -> campo testo di una collezione referenziata)
  add_copy, add_calc, remove, rename   ADD FIELDS / REMOVE FIELDS in FILTER GENERATE (con o senza CASE WHERE)
  group_order, group_drop, group_two   GROUP con ORDER BY .campo TYPE <T> [ASC|DESC], DROP GROUPING FIELDS, BY con due campi
  filter_project FILTER CASE WHERE ... GENERATE BUILD { ... }
  join_add       JOIN ... CASE WHERE ... GENERATE ADD FIELDS { ... }
  expand_cond, expand_two   EXPAND con condizione su UNPACK, due EXPAND in sequenza su due array
  derived        FILTER sulla collezione derivata ({a}_with_{b}, documenti {o: ..., u: ...}) con percorsi .o.campo
  review         ripasso delle famiglie piu' deboli di v3 (join_array, group_filter, not)
Non usati di proposito: KEEP/DROP OTHERS e CASES con piu' WHERE (default del motore = DROP), PARTITION multiple (la prima
condizione vera vince), funzioni fuzzy, traiettorie, funzioni definite dall'utente, LOOKUP/GET da web o file, USE DB.

Le richieste sono costruite da modelli programmatici con piu' formulazioni (nessuna parafrasi Gemini): il risultato atteso
(conteggio e, dove possibile, i valori dei campi nuovi) e' calcolato in Python sui dati e verificato per ESECUZIONE.

Uso (venv del backend, da finetune\\):
    ..\\venv\\Scripts\\python.exe .\\ft_gen_v4.py --v4-dbs 60 --eval-dbs 6 --seed 11 --out out_v4
Scrive in out_v4: dataset_meta.jsonl, dataset_train.jsonl, databases.json (stesso formato di v3).
"""
import argparse, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ft_gen as g
import ft_gen_v3 as g3
from ft_prompt import build_tuned_prompt

MAX_PROMPT_CHARS = 2800          # come v3 (max_length 1280)
VERBS = g.JOIN_VERBS2
OPEN = g.OPENERS

# quanti esempi di training per famiglia (circa 1000 in tutto); le famiglie senza dati adatti ne producono meno
TARGET = {"join3": 200, "translate": 130, "add_copy": 40, "add_calc": 25, "remove": 35, "rename": 30,
          "group_order": 50, "group_drop": 30, "group_two": 40, "filter_project": 80, "join_add": 70,
          "expand_cond": 30, "expand_two": 20, "derived": 120, "review": 100}
EVAL_PER_FAMILY = 8              # esempi di sola valutazione per famiglia (database tenuti fuori)


def _last(path):
    return path.split(".")[-1]


def _pl(db, c):
    return db["collections"][c]["entity_it"]


def _real(db):
    return [c for c, v in db["collections"].items() if v["specs"]]


# ----------------------------------------------------------------------------- database
def add_dictionaries(rng, db):
    """Aggiunge 1-2 collezioni dizionario {_id, key, value} costruite dai dati del database."""
    style, cols, dbn = db["style"], db["collections"], db["name"]
    made = 0
    # (a) valori distinti di un campo enum/testo -> etichetta maiuscola
    cands = []
    for c in _real(db):
        for f in g.leaf_fields(cols[c]):
            if f[2] not in ("enum", "text"):
                continue
            vals = {g.get_path(d, f[0]) for d in cols[c]["docs"]}
            if None in vals or not all(isinstance(v, str) for v in vals) or not 2 <= len(vals) <= 12:
                continue
            cands.append((c, f, sorted(vals)))
    rng.shuffle(cands)
    for c, f, vals in cands[:rng.choice([0, 1, 1])]:
        leaf = _last(f[0])
        name = f"{leaf}_dictionary" if style == "en" else f"dizionario_{leaf}"
        if name in cols:
            continue
        mp = {v: v.upper() for v in vals}
        cols[name] = {"entity_it": "dizionario", "entity_en": "dictionary", "specs": [], "dictionary": True,
                      "docs": [{"_id": f"dz_{i:03d}", "key": k, "value": v} for i, (k, v) in enumerate(mp.items(), 1)],
                      "dict": dict(kind="enum", source=c, path=f[0], it=f[1], map=mp,
                                   newname=f"{leaf}_translated" if style == "en" else f"{leaf}_tradotto")}
        made += 1
    # (b) _id di una collezione referenziata -> un suo campo testo (la FK viene tradotta in un nome)
    refs = [r for r in db["rels"] if r[2] == "ref"]
    rng.shuffle(refs)
    for a, b, _, fk in refs[:rng.choice([0, 1, 1])]:
        txt = [f for f in cols[b]["specs"] if f[2] in ("text", "enum") and all(isinstance(d.get(f[0]), str) for d in cols[b]["docs"])]
        if not txt:
            continue
        tf = rng.choice(txt)
        name = f"{cols[b]['entity_en']}_names" if style == "en" else f"nomi_{b}"
        if name in cols:
            continue
        mp = {d["_id"]: d[tf[0]] for d in cols[b]["docs"]}
        cols[name] = {"entity_it": "dizionario", "entity_en": "dictionary", "specs": [], "dictionary": True,
                      "docs": [{"_id": f"dz_{i:03d}", "key": k, "value": v} for i, (k, v) in enumerate(mp.items(), 1)],
                      "dict": dict(kind="fk", source=a, path=fk, it=f"{fk}", map=mp, target=b, tf=tf[1],
                                   newname=f"{cols[b]['entity_en']}_{tf[0]}" if style == "en" else f"{tf[0]}_{b}")}
        made += 1
    return made


def make_database_v4(rng, idx, style):
    db = g3.make_database_v3(rng, idx, style)
    add_dictionaries(rng, db)
    return db


# ----------------------------------------------------------------------------- join a tre collezioni
def _pair_rel_count(db, x, y):
    return sum(1 for r in db["rels"] if {r[0], r[1]} == {x, y})


def chain_candidates(db):
    refs = [r for r in db["rels"] if r[2] == "ref"]
    out = []
    for r1 in refs:
        for r2 in refs:
            if r1 is r2:
                continue
            shared = {r1[0], r1[1]} & {r2[0], r2[1]}
            allc = {r1[0], r1[1], r2[0], r2[1]}
            if len(shared) != 1 or len(allc) != 3:
                continue
            s = next(iter(shared))
            z = next(iter(allc - {r1[0], r1[1]}))
            other = next(iter({r1[0], r1[1]} - {s}))
            # nessuna ambiguita': una sola relazione per coppia, e la terza collezione non e' collegata anche all'altra
            if _pair_rel_count(db, r1[0], r1[1]) != 1 or _pair_rel_count(db, r2[0], r2[1]) != 1 or _pair_rel_count(db, z, other):
                continue
            out.append((r1, r2, s, z))
    return out


def gen_join3(rng, db, want=None):
    cands = chain_candidates(db)
    if not cands:
        return None
    r1, r2, s, z = rng.choice(cands)
    cols, dbn = db["collections"], db["name"]
    h1, t1, _, fk1 = r1
    h2, t2, _, fk2 = r2
    swap1 = rng.random() < 0.5
    first, second = (t1, h1) if swap1 else (h1, t1)
    al = {first: "x", second: "y"}
    swap2 = rng.random() < 0.5
    cc, cz = ("y", "x") if swap2 else ("x", "y")          # alias della collezione intermedia e della terza
    left = f"{z}@{dbn} AS x, chaintemp1@{dbn} AS y" if swap2 else f"chaintemp1@{dbn} AS x, {z}@{dbn} AS y"
    if h2 == z:
        cond2 = f".{cz}.{fk2} = .{cc}.{al[s]}._id"
    else:
        cond2 = f".{cc}.{al[s]}.{fk2} = .{cz}._id"
    q = (f"JOIN OF COLLECTIONS {first}@{dbn} AS x, {second}@{dbn} AS y CASE WHERE .{al[h1]}.{fk1} = .{al[t1]}._id; "
         f"SAVE AS chaintemp1@{dbn}; GET COLLECTION chaintemp1; "
         f"JOIN OF COLLECTIONS {left} CASE WHERE {cond2};")
    # risultato atteso, calcolato sui dati
    D = {c: {d["_id"]: d for d in cols[c]["docs"]} for c in (h1, t1, h2, t2)}
    pairs = [(d, D[t1][d[fk1]]) for d in cols[h1]["docs"] if d[fk1] in D[t1]]
    n = 0
    for dh, dt in pairs:
        sd = dh if s == h1 else dt
        if h2 == z:
            n += sum(1 for dz in cols[z]["docs"] if dz[fk2] == sd["_id"])
        else:
            n += 1 if sd[fk2] in D[t2] else 0
    if n == 0:
        return None
    verb = rng.choice(VERBS)
    pf, ps, pz = _pl(db, first), _pl(db, second), _pl(db, z)
    nl = rng.choice([f"{verb} {pf}, {ps} e {pz}", f"{verb} {pf} con {ps} e con {pz}",
                     f"{verb} {pf} con {ps} e poi anche con {pz}", f"{verb} i dati di {pf}, di {ps} e di {pz}",
                     f"{verb} {pf} e {ps}, aggiungendo anche {pz}"])
    return dict(family="join3", coll=h1, nl=nl, query=q, expected=n)


# ----------------------------------------------------------------------------- TRANSLATE
def gen_translate(rng, db, want=None):
    dicts = [(c, v["dict"]) for c, v in db["collections"].items() if v.get("dictionary")]
    if not dicts:
        return None
    dname, info = rng.choice(dicts)
    cols, dbn = db["collections"], db["name"]
    src = cols[info["source"]]
    newf, path = info["newname"], info["path"]
    cond = None
    docs = src["docs"]
    if rng.random() < 0.3:
        fields = [f for f in g.leaf_fields(src) if f[0] != path]
        if fields:
            cond = g.make_cond(rng, src, rng.choice(fields))
            docs = [d for d in docs if cond["f"](d)]
            if not docs or len(docs) == len(src["docs"]):
                cond, docs = None, src["docs"]
    flt = f"FILTER CASE WHERE {cond['q']}; " if cond else ""
    q = (f"GET DICTIONARY {dname}@{dbn} AS dict; GET COLLECTION {info['source']}; {flt}"
         f"FILTER GENERATE ADD FIELDS {{ .{newf}: TRANSLATE(.{path}, dict) }};")
    op = rng.choice(OPEN)
    tail = f" {cond['nl'][0]} {cond['nl'][1]}" if cond else ""
    if info["kind"] == "enum":
        nl = rng.choice([f"{op} {src['entity_it']}{tail} con {info['it']} tradotto tramite il dizionario",
                         f"{op} {src['entity_it']}{tail}, traducendo {info['it']} con il dizionario",
                         f"{op} {src['entity_it']}{tail} aggiungendo {info['it']} tradotto con il suo dizionario"])
    else:
        pt = cols[info["target"]]["entity_it"]
        nl = rng.choice([f"{op} {src['entity_it']}{tail} sostituendo il riferimento a {pt} con il suo nome, usando il dizionario",
                         f"{op} {src['entity_it']}{tail} aggiungendo {info['tf']} di {pt} tramite il dizionario",
                         f"{op} {src['entity_it']}{tail} traducendo {path} in {info['tf']} con il dizionario"])
    chk = dict(kind="values", field=newf, map={d["_id"]: info["map"][g.get_path(d, path)] for d in docs})
    return dict(family="translate", coll=info["source"], nl=nl, query=q, expected=len(docs), check=chk)


# ----------------------------------------------------------------------------- ADD FIELDS / REMOVE FIELDS
def _scope(rng, src):
    """Condizione opzionale: (testo query 'CASE WHERE ... ', testo nl, documenti)."""
    if rng.random() < 0.4:
        c = g.make_cond(rng, src, rng.choice(g.leaf_fields(src)))
        docs = [d for d in src["docs"] if c["f"](d)]
        if 0 < len(docs) < len(src["docs"]):
            return c, docs
    return None, src["docs"]


def gen_fields(rng, db, want=None):
    cols = db["collections"]
    c = rng.choice(_real(db))
    src = cols[c]
    simple = [s for s in src["specs"] if s[2] in ("num", "enum", "text", "bool", "null")]
    if len(simple) < 3:
        return None
    cond, docs = _scope(rng, src)
    head = f"FILTER CASE WHERE {cond['q']} GENERATE" if cond else "FILTER GENERATE"
    tail = f" {cond['nl'][0]} {cond['nl'][1]}" if cond else ""
    op, pl, style = rng.choice(OPEN), src["entity_it"], db["style"]
    fam = want or rng.choices(["add_copy", "add_calc", "remove", "rename"], weights=[4, 2, 3, 3])[0]
    if fam == "add_copy":
        s = rng.choice(simple)
        new = f"{s[0]}_copy" if style == "en" else f"{s[0]}_copia"
        q = f"GET COLLECTION {c}; {head} ADD FIELDS {{ .{new}: .{s[0]} }};"
        nl = rng.choice([f"{op} {pl}{tail} aggiungendo un campo {new} con il valore di {s[1]}",
                         f"{op} {pl}{tail} con in più il campo {new} uguale a {s[1]}"])
        chk = dict(kind="equal", pairs=[[new, s[0]]])
    elif fam == "add_calc":
        nums = [s for s in simple if s[2] == "num"]
        if not nums:
            return None
        s = rng.choice(nums)
        k = rng.choice([2, 10, 100, 0.5])
        new = f"{s[0]}_x{str(k).replace('.', '_')}"
        q = f"GET COLLECTION {c}; {head} ADD FIELDS {{ .{new}: (.{s[0]} * {k}) }};"
        nl = rng.choice([f"{op} {pl}{tail} aggiungendo il campo {new} pari a {s[1]} moltiplicato per {k}",
                         f"{op} {pl}{tail} con in più {new}, cioe' {s[1]} per {k}"])
        chk = dict(kind="values", field=new, map={d["_id"]: d[s[0]] * k for d in docs if d.get(s[0]) is not None})
    elif fam == "remove":
        gone = rng.sample(simple, rng.choice([1, 2]))
        q = f"GET COLLECTION {c}; {head} REMOVE FIELDS {{ " + ", ".join(f".{s[0]}" for s in gone) + " };"
        lst = " e ".join(s[1] for s in gone)
        nl = rng.choice([f"{op} {pl}{tail} senza il campo {lst}" if len(gone) == 1 else f"{op} {pl}{tail} senza i campi {lst}",
                         f"{op} {pl}{tail} togliendo {lst}"])
        chk = dict(kind="absent", fields=[s[0] for s in gone])
    else:
        s = rng.choice(simple)
        new = f"{s[0]}_new" if style == "en" else f"{s[0]}_nuovo"
        q = f"GET COLLECTION {c}; {head} ADD FIELDS {{ .{new}: .{s[0]} }} REMOVE FIELDS {{ .{s[0]} }};"
        nl = rng.choice([f"{op} {pl}{tail} rinominando il campo {s[1]} in {new}",
                         f"{op} {pl}{tail} con {s[1]} rinominato come {new}"])
        chk = dict(kind="rename", new=new, old=s[0])
    return dict(family=fam, coll=c, nl=nl, query=q, expected=len(docs), check=chk)


# ----------------------------------------------------------------------------- GROUP avanzato
def gen_group_adv(rng, db, want=None):
    cols = db["collections"]
    c = rng.choice(_real(db))
    src = cols[c]
    fields = g.leaf_fields(src)
    gf = [f for f in fields if f[2] in ("enum", "text", "bool")]
    if not gf:
        return None
    fam = want or rng.choices(["group_order", "group_drop", "group_two"], weights=[5, 3, 4])[0]
    op, pl = rng.choice(["Raggruppa", "Raggruppa", "Dividi in gruppi"]), src["entity_it"]
    f1 = rng.choice(gf)
    by, nlby = [f1], f"per {f1[1]}"
    if fam == "group_two":
        rest = [f for f in gf if f[0] != f1[0]]
        if not rest:
            return None
        f2 = rng.choice(rest)
        by, nlby = [f1, f2], f"per {f1[1]} e {f2[1]}"
    keys = {tuple(g.get_path(d, f[0]) for f in by) for d in src["docs"]}
    if any(None in k for k in keys) or not 2 <= len(keys) <= 20:
        return None
    into = g._camel(c) + "By" + "".join(g._camel(f[0]) for f in by)
    into = into[0].lower() + into[1:]
    q = f"GET COLLECTION {c}; GROUP PARTITION TRUE BY " + ", ".join(f".{f[0]}" for f in by) + f" INTO .{into}"
    extra = ""
    if fam == "group_drop":
        q += " DROP GROUPING FIELDS"
        extra = rng.choice([", senza ripetere il campo di raggruppamento", ", togliendo il campo usato per raggruppare"])
    elif fam == "group_order":
        ords = [f for f in fields if f[2] in ("num", "enum", "text") and f[0] != f1[0]]
        if not ords:
            return None
        o = rng.choice(ords)
        typ = "NUMERIC" if o[2] == "num" else "STRING"
        way = rng.choice(["ASC", "DESC", ""])
        q += f" ORDER BY .{o[0]} TYPE {typ}" + (f" {way}" if way else "")
        words = {"ASC": "in ordine crescente", "DESC": "in ordine decrescente", "": ""}[way]
        extra = f", ordinando gli elementi di ogni gruppo per {o[1]} {words}".rstrip()
    q += ";"
    nl = f"{op} {pl} {nlby}{extra}"
    return dict(family=fam, coll=c, nl=nl, query=q, expected=len(keys))


# ----------------------------------------------------------------------------- proiezione dopo filtro, JOIN con campi aggiunti
def gen_filter_project(rng, db, want=None):
    cols = db["collections"]
    c = rng.choice(_real(db))
    src = cols[c]
    simple = [s for s in src["specs"] if s[2] in ("num", "enum", "text", "bool", "null")]
    if len(simple) < 3:
        return None
    cond = g.make_cond(rng, src, rng.choice(g.leaf_fields(src)))
    docs = [d for d in src["docs"] if cond["f"](d)]
    if not 0 < len(docs) < len(src["docs"]):
        return None
    pick = rng.sample(simple, rng.choice([1, 2, 2, 3]))
    build = ", ".join(f".{s[0]}: .{s[0]}" for s in pick)
    q = f"GET COLLECTION {c}; FILTER CASE WHERE {cond['q']} GENERATE BUILD {{ {build} }};"
    lst = ", ".join(s[1] for s in pick[:-1]) + (" e " if len(pick) > 1 else "") + pick[-1][1]
    pl = src["entity_it"]
    nl = rng.choice([f"{rng.choice(OPEN)} {lst} di {pl} {cond['nl'][0]} {cond['nl'][1]}",
                     f"{rng.choice(OPEN)} {pl} {cond['nl'][0]} {cond['nl'][1]}, mostrando soltanto {lst}"])
    return dict(family="filter_project", coll=c, nl=nl, query=q, expected=len(docs), check=dict(kind="present", fields=[s[0] for s in pick]))


def gen_join_add(rng, db, want=None):
    refs = [r for r in db["rels"] if r[2] == "ref"]
    if not refs:
        return None
    a, b, _, fk = rng.choice(refs)
    cols, dbn = db["collections"], db["name"]
    if _pair_rel_count(db, a, b) != 1:
        return None
    txt = [s for s in cols[b]["specs"] if s[2] in ("text", "enum", "num", "bool")]
    if not txt:
        return None
    s = rng.choice(txt)
    swap = rng.random() < 0.5
    first, second = (b, a) if swap else (a, b)
    ha, oa = ("y", "x") if swap else ("x", "y")
    new = f"{cols[b]['entity_en']}_{s[0]}" if db["style"] == "en" else f"{s[0]}_{b}"
    q = (f"JOIN OF COLLECTIONS {first}@{dbn} AS x, {second}@{dbn} AS y CASE WHERE .{ha}.{fk} = .{oa}._id "
         f"GENERATE ADD FIELDS {{ .{new}: .{oa}.{s[0]} }};")
    ids_b = {d["_id"] for d in cols[b]["docs"]}
    n = sum(1 for d in cols[a]["docs"] if d[fk] in ids_b)
    pa, pb, verb = _pl(db, a), _pl(db, b), rng.choice(VERBS)
    first_it, second_it = _pl(db, first), _pl(db, second)
    nl = rng.choice([f"{verb} {first_it} con {second_it}, aggiungendo il campo {new} con {s[1]} di {pb}",
                     f"{verb} {first_it} e {second_it} e aggiungi {new} uguale a {s[1]} di {pb}"])
    return dict(family="join_add", coll=a, nl=nl, query=q, expected=n)


# ----------------------------------------------------------------------------- EXPAND avanzato
def gen_expand_adv(rng, db, want=None):
    cols = db["collections"]
    arrs = [(c, [s for s in cols[c]["specs"] if s[2] in ("arr_obj", "arr_scalar")]) for c in _real(db)]
    arrs = [(c, a) for c, a in arrs if a]
    if not arrs:
        return None
    c, al = rng.choice(arrs)
    src = cols[c]
    pl, op = src["entity_it"], rng.choice(OPEN)
    if want == "expand_two" or (want is None and len(al) >= 2 and rng.random() < 0.4):
        if len(al) < 2:
            return None
        a1, a2 = rng.sample(al, 2)
        e1, e2 = rng.sample(g.ALIASES, 2)
        n = sum(len(d[a1[0]]) * len(d[a2[0]]) for d in src["docs"])
        if n == 0:
            return None
        q = f"GET COLLECTION {c}; EXPAND UNPACK TRUE ARRAY .{a1[0]} TO .{e1}; EXPAND UNPACK TRUE ARRAY .{a2[0]} TO .{e2};"
        nl = rng.choice([f"{op} {pl} espandendo sia {a1[1]} sia {a2[1]}, una riga per ogni combinazione",
                         f"Espandi {a1[1]} e anche {a2[1]} di {pl} in righe separate"])
        return dict(family="expand_two", coll=c, nl=nl, query=q, expected=n)
    a = rng.choice(al)
    e = rng.choice(g.ALIASES)
    cond = g.make_cond(rng, src, rng.choice(g.leaf_fields(src)))
    hit = [d for d in src["docs"] if cond["f"](d)]
    n = sum(len(d[a[0]]) for d in hit)
    if not 0 < len(hit) < len(src["docs"]) or n == 0:
        return None
    q = f"GET COLLECTION {c}; EXPAND UNPACK {cond['q']} ARRAY .{a[0]} TO .{e};"
    nl = rng.choice([f"Espandi {a[1]} di {pl} {cond['nl'][0]} {cond['nl'][1]} in righe separate",
                     f"{op} una riga per ogni elemento di {a[1]} di {pl} {cond['nl'][0]} {cond['nl'][1]}"])
    return dict(family="expand_cond", coll=c, nl=nl, query=q, expected=n)


# ----------------------------------------------------------------------------- collezioni derivate
def gen_derived(rng, db, want=None):
    ders = [(c, v) for c, v in db["collections"].items() if v.get("derived")]
    if not ders:
        return None
    dname, dv = rng.choice(ders)
    a, b = dname.split("_with_")
    cols = db["collections"]
    d0 = dv["docs"][0]
    ka, kb = [k for k in d0 if k != "_id"]
    side = rng.choice([(a, ka), (b, kb)])
    base, key = side
    fields = g.leaf_fields(cols[base])
    if not fields:
        return None
    fld = rng.choice(fields)
    sub = [d[key] for d in dv["docs"]]
    cond = g.make_cond(rng, {"docs": sub}, fld)
    hit = [d for d in dv["docs"] if cond["f"](d[key])]
    if not 0 < len(hit) < len(dv["docs"]):
        return None
    path = fld[0]
    q = f"GET COLLECTION {dname}; FILTER CASE WHERE " + cond["q"].replace(f".{path}", f".{key}.{path}", 1) + ";"
    pa, pb, op = _pl(db, a), _pl(db, b), rng.choice(OPEN)
    cl = f"{cond['nl'][0]} {cond['nl'][1]}"
    nl = rng.choice([f"Tra i risultati già uniti di {pa} e {pb}, {op.lower()} quelli di {_pl(db, base)} {cl}",
                     f"Dalla collezione {dname}, {op.lower()} i documenti di {_pl(db, base)} {cl}"])
    return dict(family="derived", coll=dname, nl=nl, query=q, expected=len(hit))


# ----------------------------------------------------------------------------- ripasso famiglie deboli di v3
def gen_review(rng, db, want=None):
    sub = {"name": db["name"], "collections": {c: db["collections"][c] for c in _real(db)}}
    r = rng.choices(["join_array", "group_filter", "not"], weights=[4, 3, 2])[0]
    if r == "join_array":
        return g3.gen_join_v3(rng, db, "array")
    if r == "group_filter":
        return g.gen_group_example(rng, sub, force_cond=True)
    for _ in range(40):                       # la famiglia 'not' esce di rado da gen_filter_example
        ex = g.gen_filter_example(rng, sub)
        if ex and ex["family"] == "not":
            ex["family"] = "review_not"
            return ex
    return None


GENS = {"join3": gen_join3, "translate": gen_translate, "add_copy": gen_fields, "add_calc": gen_fields, "remove": gen_fields,
        "rename": gen_fields, "group_order": gen_group_adv, "group_drop": gen_group_adv, "group_two": gen_group_adv,
        "filter_project": gen_filter_project, "join_add": gen_join_add, "expand_cond": gen_expand_adv,
        "expand_two": gen_expand_adv, "derived": gen_derived, "review": gen_review}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v4-dbs", type=int, default=60)
    ap.add_argument("--eval-dbs", type=int, default=6, help="database di sola valutazione (split heldout): le famiglie nuove si misurano qui")
    ap.add_argument("--eval-per-family", type=int, default=EVAL_PER_FAMILY)
    ap.add_argument("--scale", type=float, default=1.0, help="moltiplica gli obiettivi per famiglia (1.0 = circa 1000 esempi)")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default="out_v4")
    ap.add_argument("--backend-dir", default=os.path.join(HERE, "..", "backend", "database"))
    a = ap.parse_args()
    rng = random.Random(a.seed + 4000)
    os.makedirs(a.out, exist_ok=True)
    dbs = []
    for i in range(a.v4_dbs + a.eval_dbs):
        split = "train" if i < a.v4_dbs else "heldout"
        for _ in range(60):
            db = make_database_v4(rng, 900 + i, "en" if i % 2 == 0 else "it")
            db["schema"] = {c: g.discover(v["docs"], a.backend_dir) for c, v in db["collections"].items()}
            if len(build_tuned_prompt(db["name"], db["schema"], "y" * 150)) <= MAX_PROMPT_CHARS:
                break
        else:
            continue
        db["split"] = split
        dbs.append(db)
    f_tr = open(os.path.join(a.out, "dataset_train.jsonl"), "w", encoding="utf-8")
    f_me = open(os.path.join(a.out, "dataset_meta.jsonl"), "w", encoding="utf-8")
    seen, stats, longest = set(), {}, 0

    def emit(db, ex, fam):
        nonlocal longest
        if ex is None or (fam != "review" and ex["family"] != fam):
            return False
        if (db["name"], ex["nl"], ex["query"]) in seen:
            return False
        prompt = build_tuned_prompt(db["name"], db["schema"], ex["nl"])
        if len(prompt) > MAX_PROMPT_CHARS:
            return False
        seen.add((db["name"], ex["nl"], ex["query"]))
        longest = max(longest, len(prompt))
        meta = dict(db=db["name"], split=db["split"], **ex)
        f_me.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"], meta=meta), ensure_ascii=False) + "\n")
        if db["split"] == "train":
            f_tr.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"]), ensure_ascii=False) + "\n")
        key = (ex["family"], db["split"])
        stats[key] = stats.get(key, 0) + 1
        return True

    for fam, gen in GENS.items():
        for split, quota in (("train", round(TARGET[fam] * a.scale)), ("heldout", a.eval_per_family if fam != "review" else 0)):
            pool = [d for d in dbs if d["split"] == split]
            got = tries = 0
            while pool and got < quota and tries < quota * 80:
                tries += 1
                db = rng.choice(pool)
                got += emit(db, gen(rng, db, fam), fam)
    f_tr.close(); f_me.close()
    json.dump([{"name": d["name"], "style": d["style"], "split": d["split"],
                "collections": {c: v["docs"] for c, v in d["collections"].items()}} for d in dbs],
              open(os.path.join(a.out, "databases.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("esempi per famiglia (training / valutazione):")
    for fam in sorted({k[0] for k in stats}):
        print(f"   {fam:16} {stats.get((fam, 'train'), 0):5} / {stats.get((fam, 'heldout'), 0):3}")
    print("totale training:", sum(v for k, v in stats.items() if k[1] == "train"),
          "| prompt piu' lungo (caratteri):", longest, "| database:", len(dbs))


if __name__ == "__main__":
    main()
