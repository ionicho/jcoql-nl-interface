"""
ft_gen.py - generatore di dataset NL -> JCoQL+ per il fine-tuning (nessuno schema scritto a mano).

Come funziona
  1. costruisce database SINTETICI (collezioni, campi annidati, nulli, booleani...) dal vocabolario
     ft_vocab.json, con nomi in inglese o in italiano (il modello deve leggere lo schema, non ricordarlo);
  2. ne ricava lo schema col MongoSchemaDiscoverer VERO del sistema (stessa funzione _extract_fields);
  3. genera coppie (richiesta in italiano, query JCoQL+) con modelli programmatici: la query e' giusta
     per costruzione e il risultato atteso (conteggio) e' calcolato in Python sui dati;
  4. salva dataset_train.jsonl (solo istruzione/risposta), dataset_meta.jsonl (con tutti i metadati)
     e i dati dei database, per la verifica per esecuzione.
Uso:
    python ft_gen.py --dbs 40 --per-db 25 --seed 1 --out out --backend-dir <progetto>/backend/database
"""
import argparse, json, os, random, re, sys, unicodedata
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ft_prompt import build_tuned_prompt

VOCAB = json.load(open(os.path.join(HERE, "ft_vocab.json"), encoding="utf-8"))["domains"]
_EXTRA = os.path.join(HERE, "ft_vocab_extra.json")      # generato da ft_vocab_expand.py (Gemini), opzionale
if os.path.exists(_EXTRA):
    VOCAB.update(json.load(open(_EXTRA, encoding="utf-8"))["domains"])


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ----------------------------------------------------------------------------- schemi e dati
def _gen_value(rng, kind, extra):
    if kind == "num":
        lo, hi, t = extra
        return rng.randint(lo, hi) if t == "int" else round(rng.uniform(lo, hi), 1)
    if kind in ("enum", "text"):
        return rng.choice(extra)
    if kind == "null":
        return None if rng.random() < 0.35 else rng.choice(extra)
    if kind == "bool":
        return rng.random() < 0.5
    raise ValueError(kind)


def _style_field(f, style):
    name, it, kind, extra = f
    if kind in ("obj", "arr_obj"):
        extra = [_style_field(x, style) for x in extra]
    return (name if style == "en" else slug(it)), it, kind, extra


def _gen_field(rng, spec, ids):
    n, it, kind, extra = spec
    if kind == "obj":
        return {sn: _gen_value(rng, sk, sx) for sn, sit, sk, sx in extra}
    if kind == "arr_obj":
        return [{sn: _gen_value(rng, sk, sx) for sn, sit, sk, sx in extra} for _ in range(rng.randint(0, 4))]
    if kind == "arr_scalar":
        return rng.sample(extra, k=rng.randint(0, min(3, len(extra))))
    if kind == "ref":
        return rng.choice(ids[extra])
    if kind == "arr_ref":
        target, refsub, qtysub = extra
        return [{refsub: rng.choice(ids[target]), qtysub: rng.randint(1, 5)} for _ in range(rng.randint(1, 3))]
    return _gen_value(rng, kind, extra)


def make_database(rng, idx, style, null_rate=0.25):
    """Ritorna dict {name, style, collections:{nome: {entity_it, entity_en, specs, docs}}}."""
    domains = rng.sample(list(VOCAB), k=rng.choice([1, 2]))
    ents = []
    for d in domains:
        ents += [e for e in VOCAB[d]]
    rng.shuffle(ents)
    ents = ents[:rng.choice([2, 3, 4])]
    plan = {}
    for e in ents:
        cname = e["plural_en"] if style == "en" else slug(e["it"])
        if cname in plan:
            continue
        fields = list(e["fields"])
        drop = rng.sample(range(len(fields)), k=rng.choice([0, 0, 1, 2]))
        kept = [f for i, f in enumerate(fields) if i not in drop]
        specs = [_style_field(f, style) for f in (kept if len(kept) >= 4 else fields)]
        # nei database veri molti campi di testo sono opzionali: a volte un campo text/enum diventa "nullable"
        specs = [(n, it, "null", ex) if k in ("text", "enum") and rng.random() < null_rate else (n, it, k, ex)
                 for n, it, k, ex in specs]
        plan[cname] = {"entity_it": e["it"], "entity_en": e["en"], "specs": specs,
                       "n": rng.randint(25, 40), "prefix": slug(e["en"])[:4]}
    ids = {c: [f"{p['prefix']}_{i:03d}" for i in range(1, p["n"] + 1)] for c, p in plan.items()}
    # relazioni tra collezioni: al massimo UNA per coppia (cosi' "collega A e B" non e' ambiguo)
    names = list(plan)
    used = set()
    if len(names) >= 2:
        for a in names:
            if rng.random() < 0.75:
                b = rng.choice([x for x in names if x != a])
                if frozenset((a, b)) in used:
                    continue
                used.add(frozenset((a, b)))
                if rng.random() < 0.5:
                    nm = f"{plan[b]['entity_en']}_id" if style == "en" else f"id_{b}"
                    plan[a]["specs"].append((nm, "riferimento", "ref", b))
                else:
                    refsub = f"{plan[b]['entity_en']}_id" if style == "en" else f"id_{b}"
                    qtysub = "quantity" if style == "en" else "quantita"
                    arrn = "items" if style == "en" else "righe"
                    plan[a]["specs"].append((arrn, "elementi", "arr_ref", (b, refsub, qtysub)))
    colls = {}
    for cname, p in plan.items():
        docs = []
        for i, _id in enumerate(ids[cname]):
            d = {"_id": _id}
            for spec in p["specs"]:
                d[spec[0]] = _gen_field(rng, spec, ids)
            docs.append(d)
        colls[cname] = {"entity_it": p["entity_it"], "entity_en": p["entity_en"], "specs": p["specs"], "docs": docs}
    return {"name": f"ft_{style}_{idx:03d}", "style": style, "collections": colls}


_DISC = None
def discover(docs, backend_dir):
    """Schema nello stesso formato di MongoSchemaDiscoverer.discover_collection_schema (senza MongoDB)."""
    global _DISC
    if _DISC is None:
        sys.path.insert(0, backend_dir)
        from schema_discovery import MongoSchemaDiscoverer
        _DISC = MongoSchemaDiscoverer.__new__(MongoSchemaDiscoverer)
    info = defaultdict(lambda: {"types": set(), "count": 0, "examples": []})
    sample = docs[:100]
    for doc in sample:
        _DISC._extract_fields(doc, info)
    fields = {p: {"types": list(i["types"]), "frequency": i["count"] / len(sample), "examples": i["examples"][:3]}
              for p, i in info.items()}
    return {"total_documents": len(docs), "sampled_documents": len(sample), "fields": fields}


# ----------------------------------------------------------------------------- condizioni
def leaf_fields(coll):
    """Campi 'foglia' usabili in un filtro: (percorso, etichetta_it, tipo, extra)."""
    out = []
    for n, it, kind, extra in coll["specs"]:
        if kind == "obj":
            for sn, sit, sk, sx in extra:
                out.append((f"{n}.{sn}", sit, sk, sx))
        elif kind in ("num", "enum", "text", "null", "bool"):
            out.append((n, it, kind, extra))
    return out


def get_path(doc, path):
    for p in path.split("."):
        doc = doc.get(p) if isinstance(doc, dict) else None
    return doc


def lit(v):
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, str):
        return "'" + v + "'"
    return repr(v)


OPS_NL = {">": "maggiore di", ">=": "di almeno", "<": "inferiore a", "<=": "non superiore a",
          "=": "uguale a", "!=": "diverso da"}
PY = {">": lambda a, b: a > b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
      "<=": lambda a, b: a <= b, "=": lambda a, b: a == b, "!=": lambda a, b: a != b}


def make_cond(rng, coll, field, allow_not=False):
    """Una condizione: dict(q=testo JCoQL+, nl=(prefisso, corpo), f=funzione di valutazione, neg=bool)."""
    path, it, kind, extra = field
    vals = [v for v in (get_path(d, path) for d in coll["docs"]) if v is not None]
    if kind == "num":
        r = rng.random()
        if r < 0.2 and len(set(vals)) > 3:
            a, b = sorted(rng.sample(sorted(set(vals)), 2))
            return dict(q=f".{path} IN_RANGE [{lit(a)}, {lit(b)}]", nl=("con", f"{it} tra {a} e {b}"),
                        f=lambda d, p=path, a=a, b=b: (lambda x: x is not None and a <= x <= b)(get_path(d, p)))
        op = rng.choice(list(OPS_NL))
        v = rng.choice(vals)
        return dict(q=f".{path} {op} {lit(v)}", nl=("con", f"{it} {OPS_NL[op]} {v}"),
                    f=lambda d, p=path, op=op, v=v: (lambda x: x is not None and PY[op](x, v))(get_path(d, p)))
    if kind in ("enum", "text"):
        v = rng.choice(vals)
        if allow_not and rng.random() < 0.5:
            return dict(q=f"NOT (.{path} = {lit(v)})", nl=("che non hanno", f"{it} uguale a {v}"),
                        f=lambda d, p=path, v=v: get_path(d, p) != v)
        op = rng.choice(["=", "=", "!="])
        return dict(q=f".{path} {op} {lit(v)}", nl=("con", f"{it} {OPS_NL[op]} {v}"),
                    f=lambda d, p=path, op=op, v=v: PY[op](get_path(d, p), v))
    if kind == "bool":
        v = rng.random() < 0.5
        return dict(q=f".{path} = {lit(v)}", nl=("con", f"{it} {'vero' if v else 'falso'}"),
                    f=lambda d, p=path, v=v: get_path(d, p) is v)
    if kind == "null":
        isnull = rng.random() < 0.5
        return dict(q=f"FIELD .{path} {'IS NULL' if isnull else 'IS NOT NULL'}",
                    nl=("senza", it) if isnull else ("con", f"{it} assegnato"),
                    f=lambda d, p=path, n=isnull: (get_path(d, p) is None) == n)
    raise ValueError(kind)


OPENERS = ["Mostrami", "Dammi", "Elenca", "Trova", "Voglio vedere", "Fammi vedere"]


def gen_filter_example(rng, db):
    cname = rng.choice(list(db["collections"]))
    coll = db["collections"][cname]
    n = len(coll["docs"])
    plural = coll["entity_it"]
    fam = rng.choices(["get_all", "single", "and", "or", "not"], weights=[1, 4, 3, 2, 1])[0]
    if fam == "get_all":
        nl = f"{rng.choice(OPENERS)} {plural}"
        return dict(family=fam, coll=cname, nl=nl, query=f"GET COLLECTION {cname};", expected=n)
    fields = leaf_fields(coll)
    k = 1 if fam in ("single", "not") else rng.choice([2, 2, 3])
    for _ in range(30):
        chosen = rng.sample(fields, k=min(k, len(fields)))
        conds = [make_cond(rng, coll, f, allow_not=(fam == "not" and i == len(chosen) - 1)) for i, f in enumerate(chosen)]
        if fam == "not" and not conds[0]["q"].startswith("NOT"):
            continue
        joiner = " OR " if fam == "or" else " AND "
        hit = [d for d in coll["docs"] if (any if fam == "or" else all)(c["f"](d) for c in conds)]
        if 0 < len(hit) < n:
            nlj = " oppure " if fam == "or" else " e "
            nl = f"{rng.choice(OPENERS)} {plural} " + nlj.join(f"{c['nl'][0]} {c['nl'][1]}" for c in conds)
            q = f"GET COLLECTION {cname}; FILTER CASE WHERE " + joiner.join(c["q"] for c in conds) + ";"
            return dict(family=fam if k > 1 or fam == "not" else "single", coll=cname, nl=nl, query=q, expected=len(hit))
    return None


# ----------------------------------------------------------------------------- array e JOIN
ALIASES = ["e", "el", "x", "r", "elem"]
JOIN_ALIASES = [("a", "b"), ("x", "y"), ("p", "q"), ("o", "u")]


def _rewrite_path(q, sub, alias):
    new, n = re.subn(r"\.%s\b" % re.escape(sub), f".{alias}.item.{sub}", q, count=1)
    assert n == 1, (q, sub)
    return new


def gen_array_example(rng, db):
    cands = [(c, sp) for c, v in db["collections"].items() for sp in v["specs"] if sp[2] in ("arr_obj", "arr_scalar")]
    if not cands:
        return None
    cname, (arr, arr_it, kind, extra) = rng.choice(cands)
    coll = db["collections"][cname]
    pl = coll["entity_it"]
    e = rng.choice(ALIASES)
    elems = [x for d in coll["docs"] for x in d[arr]]
    head = f"GET COLLECTION {cname}; EXPAND UNPACK TRUE ARRAY .{arr} TO .{e};"
    fam = rng.choices(["array_expand", "array_filter"], weights=[1, 4])[0]
    if fam == "array_expand":
        nl = rng.choice([f"Espandi {arr_it} di {pl} in righe separate",
                         f"{rng.choice(OPENERS)} una riga per ogni elemento di {arr_it} di {pl}"])
        return dict(family=fam, coll=cname, nl=nl, query=head, expected=len(elems))
    if kind == "arr_scalar":
        v = rng.choice([x for x in elems])
        hit = [x for x in elems if x == v]
        nl = f"{rng.choice(OPENERS)} {arr_it} di {pl} uguali a {v}"
        return dict(family=fam, coll=cname, nl=nl, query=f"{head} FILTER CASE WHERE .{e}.item = {lit(v)};", expected=len(hit))
    pseudo = {"docs": elems}
    for _ in range(30):
        sub = rng.choice(extra)
        c = make_cond(rng, pseudo, (sub[0], sub[1], sub[2], sub[3]))
        hit = [x for x in elems if c["f"](x)]
        if 0 < len(hit) < len(elems):
            q = f"{head} FILTER CASE WHERE {_rewrite_path(c['q'], sub[0], e)};"
            nl = f"{rng.choice(OPENERS)} {arr_it} di {pl} {c['nl'][0]} {c['nl'][1]}"
            return dict(family=fam, coll=cname, nl=nl, query=q, expected=len(hit))
    return None


def gen_join_example(rng, db):
    rels = [(c, sp) for c, v in db["collections"].items() for sp in v["specs"] if sp[2] in ("ref", "arr_ref")]
    if not rels:
        return None
    a, sp = rng.choice(rels)
    name, _, kind, extra = sp
    b = extra if kind == "ref" else extra[0]
    A, B = db["collections"][a], db["collections"][b]
    x, y = rng.choice(JOIN_ALIASES)
    ids_b = {d["_id"] for d in B["docs"]}
    swap = rng.random() < 0.3
    first, second = (b, a) if swap else (a, b)
    fx, fy = (y, x) if swap else (x, y)         # alias del primo/secondo
    ax, bx = (fy, fx) if swap else (fx, fy)     # alias di A e di B
    verb = rng.choice(["Collega", "Metti in relazione", "Incrocia"])
    pa, pb = A["entity_it"], B["entity_it"]
    nl = f"{verb} {db['collections'][first]['entity_it']} e {db['collections'][second]['entity_it']}" if rng.random() < .5 else \
         f"{verb} {db['collections'][first]['entity_it']} con {db['collections'][second]['entity_it']}"
    if kind == "ref":
        q = f"JOIN OF COLLECTIONS {first}@{db['name']} AS {fx}, {second}@{db['name']} AS {fy} CASE WHERE .{ax}.{name} = .{bx}._id;"
        n = sum(1 for d in A["docs"] if d[name] in ids_b)
        return dict(family="join_direct", coll=a, nl=nl, query=q, expected=n)
    refsub = extra[1]
    e = rng.choice(ALIASES)
    k = rng.choice([1, 2, 3])
    tmp = f"chaintemp{k}"
    q = (f"GET COLLECTION {a}; EXPAND UNPACK TRUE ARRAY .{name} TO .{e}; SAVE AS {tmp}@{db['name']}; "
         f"GET COLLECTION {tmp}; JOIN OF COLLECTIONS {tmp}@{db['name']} AS {x}, {b}@{db['name']} AS {y} "
         f"CASE WHERE .{x}.{e}.item.{refsub} = .{y}._id;")
    n = sum(1 for d in A["docs"] for it_ in d[name] if it_[refsub] in ids_b)
    nl = f"{verb} {pa} con {pb}" if rng.random() < .5 else f"{verb} {pa} e {pb}"
    return dict(family="join_array", coll=a, nl=nl, query=q, expected=n)


def gen_example(rng, db):
    group = rng.choices(["filter", "array", "join"], weights=[10, 4, 4])[0]
    for _ in range(5):
        ex = {"filter": gen_filter_example, "array": gen_array_example, "join": gen_join_example}[group](rng, db)
        if ex:
            return ex
    return gen_filter_example(rng, db)


# ----------------------------------------------------------------------------- GROUP, operazioni insiemistiche, proiezioni
def _camel(s):
    return "".join(p.capitalize() for p in re.split(r"[^A-Za-z0-9]+", s) if p)


def gen_group_example(rng, db, force_cond=False):
    cname = rng.choice(list(db["collections"]))
    coll = db["collections"][cname]
    fields = leaf_fields(coll)
    gf = [f for f in fields if f[2] in ("enum", "text", "bool")]
    if not gf:
        return None
    path, it = rng.choice(gf)[:2]
    cond, docs = None, coll["docs"]
    if rng.random() < 0.4 or force_cond:
        others = [f for f in fields if f[0] != path]
        if not others:
            return None
        cond = make_cond(rng, coll, rng.choice(others))
        docs = [d for d in docs if cond["f"](d)]
    vals = {get_path(d, path) for d in docs if get_path(d, path) is not None}
    if not 2 <= len(vals) <= 12:
        return None
    into = _camel(cname) + "By" + _camel(path)
    into = into[0].lower() + into[1:]
    q = f"GET COLLECTION {cname}; " + (f"FILTER CASE WHERE {cond['q']}; " if cond else "") + f"GROUP PARTITION TRUE BY .{path} INTO .{into};"
    nl = f"{rng.choice(['Raggruppa', 'Raggruppa', 'Dividi in gruppi'])} {coll['entity_it']}" + \
         (f" {cond['nl'][0]} {cond['nl'][1]}" if cond else "") + f" per {it}"
    return dict(family="group_filter" if cond else "group", coll=cname, nl=nl, query=q, expected=len(vals))


def gen_setop_example(rng, db, force_op=None, null_first=False):
    cname = rng.choice(list(db["collections"]))
    coll = db["collections"][cname]
    fields = leaf_fields(coll)
    if len(fields) < 2:
        return None
    if null_first:
        nulls = [f for f in fields if f[2] == "null"]
        if not nulls:
            return None
        fa = rng.choice(nulls)
        fb = rng.choice([f for f in fields if f[0] != fa[0]])
        if rng.random() < 0.5:
            fa, fb = fb, fa
    else:
        fa, fb = rng.sample(fields, 2)
    ca, cb = make_cond(rng, coll, fa), make_cond(rng, coll, fb)
    A = {i for i, d in enumerate(coll["docs"]) if ca["f"](d)}
    B = {i for i, d in enumerate(coll["docs"]) if cb["f"](d)}
    op = rng.choice(["MERGE", "INTERSECT", "SUBTRACT"])
    op = force_op or op
    if not A or not B or not (A & B):
        return None
    res = {"MERGE": A | B, "INTERSECT": A & B, "SUBTRACT": A - B}[op]
    if not res or res == A and op != "MERGE" or (op == "MERGE" and len(res) <= max(len(A), len(B))):
        return None
    dbn = db["name"]
    q = (f"GET COLLECTION {cname}; FILTER CASE WHERE {ca['q']}; SAVE AS selA@{dbn}; "
         f"GET COLLECTION {cname}; FILTER CASE WHERE {cb['q']}; SAVE AS selB@{dbn}; "
         f"{op} COLLECTIONS selA@{dbn}, selB@{dbn}" + (" REMOVE DUPLICATES;" if op == "MERGE" else ";"))
    a_t, b_t = f"{ca['nl'][0]} {ca['nl'][1]}", f"{cb['nl'][0]} {cb['nl'][1]}"
    pl, op_nl = coll["entity_it"], rng.choice(OPENERS)
    if op == "INTERSECT":
        nl = f"{op_nl} {pl} {a_t} e {b_t}, usando l'intersezione tra i due insiemi"
    elif op == "SUBTRACT":
        nl = f"{op_nl} {pl} {a_t}, escludendo quelli {b_t}, usando la differenza tra insiemi"
    else:
        nl = f"{op_nl} {pl} {a_t} oppure {b_t}, unendo i due insiemi senza duplicati"
    return dict(family="setop_" + op.lower(), coll=cname, nl=nl, query=q, expected=len(res))


def gen_project_example(rng, db):
    cname = rng.choice(list(db["collections"]))
    coll = db["collections"][cname]
    simple = [(n, it) for n, it, kind, _ in coll["specs"] if kind in ("num", "enum", "text", "bool", "null")]
    if not simple:
        return None
    pick = rng.sample(simple, min(rng.choice([1, 2, 2, 3]), len(simple)))
    lst = ", ".join(it for _, it in pick[:-1]) + (" e " if len(pick) > 1 else "") + pick[-1][1]
    build = ", ".join(f".{n}: .{n}" for n, _ in pick)
    q = f"GET COLLECTION {cname}; FILTER GENERATE BUILD {{ {build} }};"
    nl = rng.choice([f"{rng.choice(OPENERS)} {coll['entity_it']} con solo {lst}",
                     f"{rng.choice(OPENERS)} {coll['entity_it']} mostrando soltanto {lst}"])
    return dict(family="project", coll=cname, nl=nl, query=q, expected=len(coll["docs"]), fields=[n for n, _ in pick])


def gen_extra_example(rng, db):
    g = rng.choices(["group", "setop", "project"], weights=[4, 4, 3])[0]
    return {"group": gen_group_example, "setop": gen_setop_example, "project": gen_project_example}[g](rng, db)


# ----------------------------------------------------------------------------- v2: esempi mirati (join, NULL, group_filter, merge)
JOIN_VERBS2 = ["Collega", "Metti in relazione", "Incrocia", "Associa", "Abbina", "Combina", "Mostrami", "Visualizza"]
JOIN_ALIASES2 = JOIN_ALIASES + [("c", "d"), ("m", "n"), ("l", "r"), ("s", "t")]
ALIASES2 = ALIASES + ["i", "it", "k"]


def gen_join_example2(rng, db):
    """Come gen_join_example, ma con piu' verbi, piu' formulazioni e piu' coppie di alias (stessa sintassi di uscita)."""
    rels = [(c, sp) for c, v in db["collections"].items() for sp in v["specs"] if sp[2] in ("ref", "arr_ref")]
    if not rels:
        return None
    a, sp = rng.choice(rels)
    name, _, kind, extra = sp
    b = extra if kind == "ref" else extra[0]
    A, B = db["collections"][a], db["collections"][b]
    x, y = rng.choice(JOIN_ALIASES2)
    ids_b = {d["_id"] for d in B["docs"]}
    verb = rng.choice(JOIN_VERBS2)
    pa, pb = A["entity_it"], B["entity_it"]
    if kind == "ref":
        swap = rng.random() < 0.4
        first, second = (b, a) if swap else (a, b)
        fx, fy = (y, x) if swap else (x, y)
        ax, bx = (fy, fx) if swap else (fx, fy)
        pf, ps = db["collections"][first]["entity_it"], db["collections"][second]["entity_it"]
        nl = rng.choice([f"{verb} {pf} e {ps}", f"{verb} {pf} con {ps}", f"{verb} {pf} con {ps} corrispondenti",
                         f"{verb} i dati di {pf} e di {ps}", f"{verb} {pf} insieme a {ps}"])
        q = f"JOIN OF COLLECTIONS {first}@{db['name']} AS {fx}, {second}@{db['name']} AS {fy} CASE WHERE .{ax}.{name} = .{bx}._id;"
        n = sum(1 for d in A["docs"] if d[name] in ids_b)
        return dict(family="join_direct", coll=a, nl=nl, query=q, expected=n)
    refsub = extra[1]
    e = rng.choice(ALIASES2)
    tmp = f"chaintemp{rng.choice([1, 2, 3])}"
    q = (f"GET COLLECTION {a}; EXPAND UNPACK TRUE ARRAY .{name} TO .{e}; SAVE AS {tmp}@{db['name']}; "
         f"GET COLLECTION {tmp}; JOIN OF COLLECTIONS {tmp}@{db['name']} AS {x}, {b}@{db['name']} AS {y} "
         f"CASE WHERE .{x}.{e}.item.{refsub} = .{y}._id;")
    n = sum(1 for d in A["docs"] for it_ in d[name] if it_[refsub] in ids_b)
    nl = rng.choice([f"{verb} {pa} con {pb}", f"{verb} {pa} e {pb}", f"{verb} {pa} con {pb} corrispondenti",
                     f"{verb} i dati di {pa} e di {pb}"])
    return dict(family="join_array", coll=a, nl=nl, query=q, expected=n)


def gen_null_example(rng, db):
    """Filtri in cui compare almeno una condizione FIELD .x IS [NOT] NULL (da sola, in AND o in OR)."""
    cname = rng.choice(list(db["collections"]))
    coll = db["collections"][cname]
    fields = leaf_fields(coll)
    nulls = [f for f in fields if f[2] == "null"]
    if not nulls:
        return None
    n = len(coll["docs"])
    fam = rng.choices(["single", "and", "or"], weights=[4, 3, 3])[0]
    for _ in range(30):
        first = rng.choice(nulls)
        chosen = [first]
        if fam != "single":
            others = [f for f in fields if f[0] != first[0]]
            if not others:
                return None
            chosen.append(rng.choice(others))
            rng.shuffle(chosen)
        conds = [make_cond(rng, coll, f) for f in chosen]
        hit = [d for d in coll["docs"] if (any if fam == "or" else all)(c["f"](d) for c in conds)]
        if 0 < len(hit) < n:
            nlj = " oppure " if fam == "or" else " e "
            nl = f"{rng.choice(OPENERS)} {coll['entity_it']} " + nlj.join(f"{c['nl'][0]} {c['nl'][1]}" for c in conds)
            q = f"GET COLLECTION {cname}; FILTER CASE WHERE " + (" OR " if fam == "or" else " AND ").join(c["q"] for c in conds) + ";"
            return dict(family=fam, coll=cname, nl=nl, query=q, expected=len(hit))
    return None


def gen_focus_example(rng, db):
    g = rng.choices(["join", "null", "null_setop", "group_filter", "merge"], weights=[6, 4, 2, 3, 3])[0]
    if g == "join":
        return gen_join_example2(rng, db)
    if g == "null":
        return gen_null_example(rng, db)
    if g == "null_setop":
        return gen_setop_example(rng, db, null_first=True)
    if g == "group_filter":
        ex = gen_group_example(rng, db, force_cond=True)
        return ex
    return gen_setop_example(rng, db, force_op="MERGE")


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbs", type=int, default=20)
    ap.add_argument("--per-db", type=int, default=25)
    ap.add_argument("--heldout", type=float, default=0.15, help="quota di database tenuti fuori (schemi mai visti)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="out")
    ap.add_argument("--extra-per-db", type=int, default=8, help="esempi GROUP / MERGE-INTERSECT-SUBTRACT / proiezioni per database (aggiunti in coda)")
    ap.add_argument("--v2-dbs", type=int, default=0, help="v2: database NUOVI (solo training) con piu' campi nullable, aggiunti in coda")
    ap.add_argument("--v2-per-db", type=int, default=10, help="v2: esempi generali per ciascun database nuovo")
    ap.add_argument("--focus-per-db", type=int, default=0, help="v2: esempi mirati (join, NULL, group_filter, merge) per ogni database di training, vecchio o nuovo")
    ap.add_argument("--backend-dir", default=os.path.join(HERE, "..", "backend", "database"))
    a = ap.parse_args()
    rng = random.Random(a.seed)
    os.makedirs(a.out, exist_ok=True)
    dbs = [make_database(rng, i, "en" if i % 2 == 0 else "it") for i in range(a.dbs)]
    n_held = max(1, round(a.dbs * a.heldout))
    held = {d["name"] for d in dbs[-n_held:]}
    seen = set()
    f_tr = open(os.path.join(a.out, "dataset_train.jsonl"), "w", encoding="utf-8")
    f_me = open(os.path.join(a.out, "dataset_meta.jsonl"), "w", encoding="utf-8")
    for db in dbs:
        schema = {c: discover(v["docs"], a.backend_dir) for c, v in db["collections"].items()}
        db["schema"] = schema
        split = "heldout" if db["name"] in held else "train"
        got = 0
        while got < a.per_db:
            ex = gen_example(rng, db)
            if ex is None or (db["name"], ex["nl"], ex["query"]) in seen:
                continue
            seen.add((db["name"], ex["nl"], ex["query"]))
            prompt = build_tuned_prompt(db["name"], schema, ex["nl"])
            meta = dict(db=db["name"], split=split, **ex)
            f_me.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"], meta=meta), ensure_ascii=False) + "\n")
            if split == "train":
                f_tr.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"]), ensure_ascii=False) + "\n")
            got += 1
    # famiglie aggiuntive, in coda e con un generatore separato: gli esempi precedenti restano identici
    erng = random.Random(a.seed + 1000)
    for db in dbs:
        split = "heldout" if db["name"] in held else "train"
        got = tries = 0
        while got < a.extra_per_db and tries < 400:
            tries += 1
            ex = gen_extra_example(erng, db)
            if ex is None or (db["name"], ex["nl"], ex["query"]) in seen:
                continue
            seen.add((db["name"], ex["nl"], ex["query"]))
            prompt = build_tuned_prompt(db["name"], db["schema"], ex["nl"])
            meta = dict(db=db["name"], split=split, **ex)
            f_me.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"], meta=meta), ensure_ascii=False) + "\n")
            if split == "train":
                f_tr.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"]), ensure_ascii=False) + "\n")
            got += 1
    # --- v2: database nuovi e esempi mirati, SEMPRE in coda e con un altro generatore casuale:
    # i dati di v1 (e i database tenuti fuori) restano identici, quindi v1 e v2 si valutano sulle stesse richieste.
    new_dbs = []
    if a.v2_dbs or a.focus_per_db:
        r3 = random.Random(a.seed + 2000)
        new_dbs = [make_database(r3, 500 + i, "en" if i % 2 == 0 else "it", null_rate=0.4) for i in range(a.v2_dbs)]

        def emit(db, ex):
            if ex is None or (db["name"], ex["nl"], ex["query"]) in seen:
                return False
            seen.add((db["name"], ex["nl"], ex["query"]))
            prompt = build_tuned_prompt(db["name"], db["schema"], ex["nl"])
            meta = dict(db=db["name"], split="train", **ex)
            f_me.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"], meta=meta), ensure_ascii=False) + "\n")
            f_tr.write(json.dumps(dict(instruction=prompt, input="", output=ex["query"]), ensure_ascii=False) + "\n")
            return True

        for db in new_dbs:
            db["schema"] = {c: discover(v["docs"], a.backend_dir) for c, v in db["collections"].items()}
            got = tries = 0
            while got < a.v2_per_db and tries < 400:
                tries += 1
                got += emit(db, gen_example(r3, db))
            got = tries = 0
            while got < a.extra_per_db and tries < 400:
                tries += 1
                got += emit(db, gen_extra_example(r3, db))
        for db in [d for d in dbs if d["name"] not in held] + new_dbs:
            got = tries = 0
            while got < a.focus_per_db and tries < 400:
                tries += 1
                got += emit(db, gen_focus_example(r3, db))
    f_tr.close(); f_me.close()
    json.dump([{"name": d["name"], "style": d["style"], "split": "heldout" if d["name"] in held else "train",
                "collections": {c: v["docs"] for c, v in d["collections"].items()}} for d in dbs + new_dbs],
              open(os.path.join(a.out, "databases.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"{a.dbs} database ({n_held} tenuti fuori) + {len(new_dbs)} nuovi (solo training), scritti in {a.out}/")


if __name__ == "__main__":
    main()
