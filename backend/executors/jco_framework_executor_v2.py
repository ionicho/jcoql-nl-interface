#!/usr/bin/env python3
"""
JCO Framework Executor - Multi-Database Support

Implementazione di ExecutorType.JCO_FRAMEWORK (vedi executor_factory.py),
l'executor di default (ACTIVE_EXECUTOR="jco_framework" in main.py).
Esegue le query JCoQL+ invocando il motore Java reale (J-CO Framework,
progetto separato jco-framework) in subprocess, scrivendo i file .jcoql/
.properties che il motore si aspetta di leggere e interpretando il suo
output testuale su stdout.

Per i comandi diversi da GET COLLECTION (JOIN, GROUP, EXPAND, MERGE,
INTERSECT, SUBTRACT, SAVE AS), il motore stampa su stdout solo il
conteggio dei documenti generati, non il loro contenuto — verificato
leggendo il codice Java ufficiale (es. JoinExecutor.java fa
"pipeline.addCollection(outCollection)" e stampa solo
"N documents generated", mai il contenuto).

STRATEGIA (rivista): invece di ricostruire ogni comando in Python
via pymongo (approccio fragile — richiede reimplementare a mano la
semantica di ciascun comando, con margine di errore, vedi cronologia
dei bug su JOIN senza WHERE), ad ogni query viene ora accodato in modo
trasparente un "SAVE AS <nome_univoco>@<db>;" — esattamente lo stesso
meccanismo che SAVE AS usa già (SaveCollectionExecutor.java:
"pipeline.getCurrentCollection()", generico per qualunque comando
precedente). Il motore fa il lavoro vero — qualunque esso sia, inclusi
comandi mai esplicitamente supportati qui (GET DICTIONARY, GENERATE/
BUILD, ecc.) — e noi rileggiamo il risultato reale da MongoDB, senza
dover approssimare nulla. Vedi _read_temp_result().
"""
import os, re, json, subprocess, uuid
from pathlib import Path
from urllib.parse import urlparse

# Interruttore di debug: imposta la variabile d'ambiente JCOQL_DEBUG=true per
# riattivare i log diagnostici dettagliati (output grezzo di Java per i comandi
# diversi da GET COLLECTION). Spento di default per non intasare la console durante
# un uso normale/dimostrativo del sistema.
JCOQL_DEBUG = os.getenv("JCOQL_DEBUG", "false").lower() == "true"

class JCoFrameworkExecutor:
    def __init__(self, mongo_uri="mongodb://localhost:27017", database="jcoql_test"):
        # Nota: questa classe non tiene una connessione MongoDB persistente
        # in un attributo (a differenza di python_translator.py, che ha
        # self.db) — ogni metodo che deve interrogare Mongo apre la sua
        # connessione con "with MongoClient(...) as client:" e la chiude
        # da sé. Di conseguenza questa classe non ha un metodo close():
        # main.py, nell'evento di shutdown, chiama comunque
        # "executor.close()" su qualunque tipo di executor sia attivo —
        # con questo (jco_framework, il default) quella chiamata solleva
        # AttributeError, ma è avvolta in un try/except che la ignora in
        # silenzio (vedi main.py), e non c'è comunque nulla da chiudere
        # qui, quindi nella pratica non causa perdite di risorse.
        user_home = Path.home()
        self.jco_base = user_home / "jcoql-project" / "jco-framework"
        self.data_path = user_home / ".data" / ".zunTestScripts"
        self.mongo_uri = mongo_uri
        self.database_name = database
        self.data_path.mkdir(parents=True, exist_ok=True)

    def set_database(self, db_name: str):
        """Aggiorna il database corrente per l'executor."""
        if db_name:
            self.database_name = db_name
    
    def _get_latest_jar(self, search_path, pattern):
        jars = [j for j in search_path.rglob(pattern) if "-sources" not in str(j)]
        return str(sorted(jars)[-1]) if jars else None

    def _extract_collection_name(self, jcoql_query):
            """Estrai il nome della collezione dalla query JCoQL"""
            # Pattern: GET COLLECTION nome_collezione
            match = re.search(r'GET\s+COLLECTION\s+(\w+)', jcoql_query, re.IGNORECASE)
            if match:
                return match.group(1)
            return None  # Nessun default

    def _sanitize_bson(self, value):
        """
        Converte ricorsivamente i tipi BSON non nativamente serializzabili in JSON
        (ObjectId -> str, Decimal128 -> float) ovunque compaiano nella struttura,
        non solo nel campo _id di primo livello. Necessario per JOIN e GROUP, i cui
        risultati contengono documenti Mongo interi (annidati) recuperati direttamente
        via pymongo, a differenza del percorso GET COLLECTION che converte solo _id.
        """
        try:
            from bson import ObjectId, Decimal128
        except ImportError:
            return value

        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, Decimal128):
            return float(value.to_decimal())
        if isinstance(value, dict):
            return {k: self._sanitize_bson(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize_bson(v) for v in value]
        return value

    def _get_nested(self, doc, dotted_field):
        """Naviga un campo annidato tipo 'user_id' o 'address.city' dentro un documento dict."""
        value = doc
        for part in dotted_field.split('.'):
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value

    def _parse_simple_condition(self, condition_str):
        """
        Analizza una condizione semplice a singolo confronto, es. '.amount > 100' o
        "(.type = 'movie')", usata in GROUP PARTITION ed EXPAND UNPACK. Restituisce
        (campo, operatore, valore) oppure None se la condizione e' TRUE o non riconosciuta
        (in quest'ultimo caso il chiamante deve trattarla come "nessun filtro", non come
        errore, per non rompere casi non ancora previsti).
        NON supporta condizioni composte con AND/OR - solo un singolo confronto.
        """
        cond = condition_str.strip()
        if cond.upper() == "TRUE":
            return None
        cond = cond.strip('()')
        m = re.match(
            r"\.([\w.]+)\s*(=|!=|>=|<=|>|<)\s*(?:'([^']*)'|\"([^\"]*)\"|([\w.\-]+))",
            cond
        )
        if not m:
            return None
        field, op, sval1, sval2, sval3 = m.groups()
        raw_value = sval1 if sval1 is not None else (sval2 if sval2 is not None else sval3)
        return (field, op, raw_value)

    def _condition_matches_doc(self, doc, condition_str):
        """Valuta una condizione semplice (vedi _parse_simple_condition) su un documento."""
        parsed = self._parse_simple_condition(condition_str)
        if parsed is None:
            return True  # TRUE o condizione non riconosciuta: nessun filtro (permissivo)
        field, op, raw_value = parsed
        try:
            value = float(raw_value) if any(c.isdigit() for c in raw_value) and \
                    raw_value.replace('.', '', 1).replace('-', '', 1).isdigit() else raw_value
        except (ValueError, AttributeError):
            value = raw_value
        doc_value = self._get_nested(doc, field)
        if doc_value is None:
            return False
        try:
            if op == '=':
                return doc_value == value or str(doc_value) == str(value)
            elif op == '!=':
                return doc_value != value
            elif op == '>':
                return doc_value > value
            elif op == '<':
                return doc_value < value
            elif op == '>=':
                return doc_value >= value
            elif op == '<=':
                return doc_value <= value
        except TypeError:
            return False
        return True

    def _condition_to_mongo_filter(self, condition_str):
        """Converte una condizione semplice (vedi _parse_simple_condition) in un filtro
        MongoDB nativo, per usarla in uno stage $match. Restituisce {} se TRUE o non
        riconosciuta (nessun filtro applicato)."""
        parsed = self._parse_simple_condition(condition_str)
        if parsed is None:
            return {}
        field, op, raw_value = parsed
        try:
            value = float(raw_value) if any(c.isdigit() for c in raw_value) and \
                    raw_value.replace('.', '', 1).replace('-', '', 1).isdigit() else raw_value
        except (ValueError, AttributeError):
            value = raw_value
        mongo_op_map = {'=': '$eq', '!=': '$ne', '>': '$gt', '<': '$lt', '>=': '$gte', '<=': '$lte'}
        mongo_op = mongo_op_map.get(op)
        if not mongo_op:
            return {}
        return {field: {mongo_op: value}}

    def _extract_join_documents(self, jcoql_query):
        """
        Estrae ed esegue lato Python un JOIN OF COLLECTIONS nativo JCoQL+, nel caso
        semplice di equi-join a due collezioni con una singola condizione di uguaglianza
        (.alias1.campo = .alias2.campo). Necessario perche' il motore J-CO Framework non
        stampa su stdout il contenuto dei documenti generati dal join (solo il conteggio),
        quindi il conteggio ufficiale del motore viene usato per validare il risultato,
        mentre il recupero dei documenti reali avviene qui.
        Non copre: JOIN geo-spaziali (ON GEOMETRY), condizioni composte con AND/OR,
        ne' database diversi per le due collezioni (@db).
        """
        join_match = re.search(
            r'JOIN\s+OF\s+COLLECTIONS\s+(\w+)(?:@(\w+))?\s+AS\s+(\w+)\s*,\s*(\w+)(?:@(\w+))?\s+AS\s+(\w+)',
            jcoql_query, re.IGNORECASE
        )
        if not join_match:
            return None

        coll1, db1, alias1, coll2, db2, alias2 = join_match.groups()

        if re.search(r'KEEP\s+OTHERS', jcoql_query, re.IGNORECASE):
            print("[JCoFrameworkExecutor] WARNING: JOIN con KEEP OTHERS rilevato - il motore "
                  "J-CO include anche le coppie che NON soddisfano la condizione di uguaglianza, "
                  "producendo il prodotto cartesiano completo. Questa estrazione ignora KEEP "
                  "OTHERS e applica solo la condizione di uguaglianza: il conteggio potrebbe "
                  "risultare diverso da quello del motore (atteso, non un errore).")

        cond_match = re.search(
            r'WHERE\s+\.(\w+)\.([\w.]+)\s*=\s*\.(\w+)\.([\w.]+)',
            jcoql_query, re.IGNORECASE
        )

        # Se manca la condizione WHERE, non è un errore: nella grammatica
        # JCoQL+ la clausola CASE (che porta il WHERE) è OPZIONALE in
        # joinOfCollectionsRule — un JOIN senza condizione è sintassi
        # valida ed esegue un prodotto cartesiano completo fra le due
        # collezioni (confermato empiricamente: query di test JOIN OF
        # COLLECTIONS senza WHERE, verificata via SAVE AS + MongoDB
        # Compass, produce documenti reali). Prima questo ramo restituiva
        # doc_count=0 senza nemmeno provare a replicare il prodotto
        # cartesiano — bug, non scelta voluta: il commento originale
        # diceva "non tentiamo un prodotto cartesiano completo" ma non
        # c'era una vera ragione tecnica per non farlo.
        if not cond_match:
            return self._join_cartesian_product(coll1, db1, alias1, coll2, db2, alias2, jcoql_query)

        left_alias, left_field, right_alias, right_field = cond_match.groups()

        alias_to_field = {left_alias: left_field, right_alias: right_field}
        if alias1 not in alias_to_field or alias2 not in alias_to_field:
            return {'doc_count': 0, 'results': []}

        field1 = alias_to_field[alias1]
        field2 = alias_to_field[alias2]

        try:
            from pymongo import MongoClient

            # FIX: prima "client = MongoClient(...)" senza mai chiudere
            # la connessione (verificato: nessun client.close() in tutto
            # il file, su 8 punti diversi che aprono una MongoClient) —
            # ogni JOIN/GROUP/EXPAND/ecc. apriva una connessione Mongo in
            # più che restava aperta per sempre, fino alla chiusura del
            # processo. Con "with" la connessione si chiude sempre
            # all'uscita dal blocco, anche in caso di eccezione.
            with MongoClient(self.mongo_uri) as client:
                db1_name = db1 or self.database_name
                db2_name = db2 or self.database_name

                docs1 = list(client[db1_name][coll1].find().limit(1000))
                docs2 = list(client[db2_name][coll2].find().limit(1000))

                # Indicizza la seconda collezione per valore del campo di join
                index2 = {}
                for d2 in docs2:
                    key = self._get_nested(d2, field2)
                    if key is not None:
                        index2.setdefault(str(key), []).append(d2)

                remove_duplicates = bool(re.search(r'REMOVE\s+DUPLICATES', jcoql_query, re.IGNORECASE))

                if remove_duplicates:
                    # Serve la lista completa (non troncata) per deduplicare correttamente
                    # prima di contare e troncare per la visualizzazione.
                    all_pairs = []
                    for d1 in docs1:
                        key = self._get_nested(d1, field1)
                        if key is None:
                            continue
                        for d2 in index2.get(str(key), []):
                            all_pairs.append({alias1: d1, alias2: d2, '_join_key': str(key)})

                    seen = set()
                    deduped = []
                    for pair in all_pairs:
                        canon_key = self._canonical_doc(pair)
                        if canon_key not in seen:
                            seen.add(canon_key)
                            deduped.append(pair)

                    total_count = len(deduped)
                    results = deduped[:100]
                else:
                    results = []
                    total_count = 0
                    for d1 in docs1:
                        key = self._get_nested(d1, field1)
                        if key is None:
                            continue
                        for d2 in index2.get(str(key), []):
                            total_count += 1
                            if len(results) < 100:
                                results.append({
                                    alias1: d1,
                                    alias2: d2,
                                    '_join_key': str(key)
                                })

                results = [self._sanitize_bson(r) for r in results]
                return {'doc_count': total_count, 'results': results}
        except Exception as e:
            print(f"[JCoFrameworkExecutor] WARNING estrazione JOIN fallita: {e}")
            return {'doc_count': 0, 'results': []}

    def _join_cartesian_product(self, coll1, db1, alias1, coll2, db2, alias2, jcoql_query):
        """
        Replica un JOIN OF COLLECTIONS senza clausola CASE/WHERE: prodotto
        cartesiano completo fra le due collezioni (ogni documento di coll1
        abbinato a ogni documento di coll2). Estratto in un metodo a parte
        perché condivide poco con l'equi-join di _extract_join_documents
        (nessun indice per chiave, nessun campo di confronto).

        ATTENZIONE dimensioni: un prodotto cartesiano cresce come
        N×M — con collezioni grandi il conteggio reale può diventare
        enorme molto in fretta. Qui non c'è un limite superiore diverso
        dal cap already esistente sulla singola lettura (.limit(1000) per
        lato, quindi al più 1.000.000 di coppie teoriche prima del taglio
        a 100 risultati mostrati) — se ti serve un tetto più stretto,
        è qui che andrebbe aggiunto.
        """
        try:
            from pymongo import MongoClient

            with MongoClient(self.mongo_uri) as client:
                db1_name = db1 or self.database_name
                db2_name = db2 or self.database_name

                docs1 = list(client[db1_name][coll1].find().limit(1000))
                docs2 = list(client[db2_name][coll2].find().limit(1000))

                remove_duplicates = bool(re.search(r'REMOVE\s+DUPLICATES', jcoql_query, re.IGNORECASE))

                if remove_duplicates:
                    all_pairs = [{alias1: d1, alias2: d2} for d1 in docs1 for d2 in docs2]
                    seen = set()
                    deduped = []
                    for pair in all_pairs:
                        canon_key = self._canonical_doc(pair)
                        if canon_key not in seen:
                            seen.add(canon_key)
                            deduped.append(pair)
                    total_count = len(deduped)
                    results = deduped[:100]
                else:
                    total_count = len(docs1) * len(docs2)
                    results = []
                    for d1 in docs1:
                        for d2 in docs2:
                            if len(results) >= 100:
                                break
                            results.append({alias1: d1, alias2: d2})
                        if len(results) >= 100:
                            break

                results = [self._sanitize_bson(r) for r in results]
                return {'doc_count': total_count, 'results': results}
        except Exception as e:
            print(f"[JCoFrameworkExecutor] WARNING estrazione JOIN (prodotto cartesiano) fallita: {e}")
            return {'doc_count': 0, 'results': []}

    def _extract_group_documents(self, jcoql_query):
        """
        Estrae ed esegue lato Python (via aggregazione MongoDB nativa) un GROUP
        JCoQL+ nel caso semplice: PARTITION TRUE BY campo1[, campo2...] INTO campoRisultato
        [DROP GROUPING FIELDS]. Necessario perche' il motore J-CO Framework non stampa su
        stdout il contenuto dei documenti raggruppati (solo il conteggio dei gruppi).
        Supporta condizioni di PARTITION con un singolo confronto (es. .campo > 100),
        tradotte in uno stage $match nativo. Non copre: condizioni composte con AND/OR,
        ORDER BY, KEEP UNCOMPARABLE,
        GENERATE SECTION, KEEP/DROP OTHERS.
        """
        source_collection = self._extract_collection_name(jcoql_query)
        if not source_collection:
            return None

        group_match = re.search(
            r'GROUP\s+PARTITION\s+(.+?)\s+BY\s+(.+?)\s+INTO\s+\.?([\w.]+)',
            jcoql_query, re.IGNORECASE | re.DOTALL
        )
        if not group_match:
            return None

        condition, by_fields_raw, into_field = group_match.groups()
        drop_grouping_fields = bool(re.search(r'DROP\s+GROUPING\s+FIELDS', jcoql_query, re.IGNORECASE))

        # Condizioni diverse da TRUE: convertite in filtro $match nativo (solo singolo
        # confronto - vedi _parse_simple_condition; condizioni composte con AND/OR non
        # sono ancora supportate e vengono trattate in modo permissivo, senza filtrare).
        match_filter = self._condition_to_mongo_filter(condition.strip())

        by_fields = [f.strip().lstrip('.') for f in by_fields_raw.split(',')]

        try:
            from pymongo import MongoClient

            with MongoClient(self.mongo_uri) as client:
                collection = client[self.database_name][source_collection]

                if len(by_fields) == 1:
                    group_id_expr = f"${by_fields[0]}"
                else:
                    group_id_expr = {f: f"${f}" for f in by_fields}

                pipeline = []
                if match_filter:
                    pipeline.append({"$match": match_filter})
                pipeline.append(
                    {"$group": {"_id": group_id_expr, into_field: {"$push": "$$ROOT"}}}
                )
                grouped = list(collection.aggregate(pipeline))

                results = []
                for g in grouped:
                    doc = {}
                    if not drop_grouping_fields:
                        if len(by_fields) == 1:
                            doc[by_fields[0]] = g["_id"]
                        else:
                            doc.update(g["_id"] or {})
                    # Limita la dimensione dell'array annidato per gruppo (evita payload enormi
                    # se un singolo gruppo contiene molti documenti, es. un anno con migliaia di
                    # film): il conteggio reale del gruppo resta comunque disponibile.
                    full_group = g[into_field]
                    doc[into_field] = full_group[:50]
                    doc['_group_size'] = len(full_group)
                    results.append(doc)

                results = [self._sanitize_bson(r) for r in results]
                return {'doc_count': len(results), 'results': results}
        except Exception as e:
            print(f"[JCoFrameworkExecutor] WARNING estrazione GROUP fallita: {e}")
            return {'doc_count': 0, 'results': []}

    def _extract_expand_documents(self, jcoql_query):
        """
        Estrae ed esegue lato Python un EXPAND UNPACK JCoQL+ nel caso semplice:
        una singola clausola UNPACK TRUE ARRAY campo TO campoDestinazione, con KEEP OTHERS
        opzionale (i documenti senza l'array o con condizione non soddisfatta vengono
        mantenuti invariati se KEEP OTHERS, scartati altrimenti). Come per JOIN/GROUP, il
        motore J-CO stampa solo il conteggio, non i documenti espansi.
        Supporta una condizione UNPACK con un singolo confronto (es. (.type = 'movie')),
        valutata per documento. Non copre: piu' clausole UNPACK nella stessa istruzione,
        condizioni composte con AND/OR,
        GENERATE SECTION.
        """
        source_collection = self._extract_collection_name(jcoql_query)
        if not source_collection:
            return None

        expand_match = re.search(
            r'EXPAND\s+UNPACK\s+(.+?)\s+ARRAY\s+\.?([\w.]+)\s+TO\s+\.?([\w.]+)',
            jcoql_query, re.IGNORECASE | re.DOTALL
        )
        if not expand_match:
            return None

        condition, array_field, dest_field = expand_match.groups()
        keep_others = bool(re.search(r'KEEP\s+OTHERS', jcoql_query, re.IGNORECASE))

        try:
            from pymongo import MongoClient

            with MongoClient(self.mongo_uri) as client:
                collection = client[self.database_name][source_collection]
                docs = list(collection.find())

                results = []
                total_count = 0
                for doc in docs:
                    # La condizione determina se QUESTO documento e' idoneo all'espansione
                    # (vedi expand.md: "if the condition is met..."). Se non lo e', il
                    # documento e' trattato come "array non applicabile", stessa sorte di un
                    # documento senza l'array (governata da KEEP/DROP OTHERS sotto).
                    condition_ok = self._condition_matches_doc(doc, condition.strip())
                    array_value = self._get_nested(doc, array_field) if condition_ok else None
                    if condition_ok and isinstance(array_value, list) and len(array_value) > 0:
                        for element in array_value:
                            total_count += 1
                            if len(results) < 100:
                                new_doc = dict(doc)
                                new_doc[dest_field] = element
                                results.append(new_doc)
                    elif keep_others:
                        total_count += 1
                        if len(results) < 100:
                            results.append(dict(doc))
                    # altrimenti (array assente/vuoto e non KEEP OTHERS): documento scartato

                results = [self._sanitize_bson(r) for r in results]
                return {'doc_count': total_count, 'results': results}
        except Exception as e:
            print(f"[JCoFrameworkExecutor] WARNING estrazione EXPAND fallita: {e}")
            return {'doc_count': 0, 'results': []}

    def _canonical_doc(self, doc):
        """
        Rappresentazione canonica di un documento per confronti di uguaglianza fra
        collezioni diverse (usata da MERGE/INTERSECT/SUBTRACT): esclude _id, che sara'
        quasi certamente diverso anche per documenti "logicamente uguali" provenienti da
        collezioni diverse, e serializza in modo deterministico (chiavi ordinate).
        Assunzione dichiarata, non confermata sull'handbook: da verificare col conteggio
        reale del motore.
        """
        sanitized = self._sanitize_bson(doc)
        if isinstance(sanitized, dict):
            sanitized = {k: v for k, v in sanitized.items() if k != '_id'}
        return json.dumps(sanitized, sort_keys=True, default=str)

    def _parse_collection_refs(self, refs_text):
        """Estrae una lista di (nome_collezione, db_opzionale) da un testo tipo
        'coll1@db1, coll2 AS alias, coll3'."""
        refs = []
        for part in refs_text.split(','):
            m = re.match(r'\s*(\w+)(?:@(\w+))?', part.strip())
            if m:
                refs.append((m.group(1), m.group(2)))
        return refs

    def _extract_merge_documents(self, jcoql_query):
        """MERGE COLLECTIONS c1[@db1], c2[@db2][, ...] [REMOVE DUPLICATES];
        Unione dei documenti di piu' collezioni. Con REMOVE DUPLICATES, elimina i
        duplicati per contenuto (vedi _canonical_doc)."""
        m = re.search(r'MERGE\s+COLLECTIONS\s+(.+?)\s*;', jcoql_query, re.IGNORECASE | re.DOTALL)
        if not m:
            return None
        refs_text = re.sub(r'REMOVE\s+DUPLICATES', '', m.group(1), flags=re.IGNORECASE)
        refs = self._parse_collection_refs(refs_text)
        remove_duplicates = bool(re.search(r'REMOVE\s+DUPLICATES', jcoql_query, re.IGNORECASE))

        try:
            from pymongo import MongoClient
            with MongoClient(self.mongo_uri) as client:
                all_docs = []
                for coll_name, db_name in refs:
                    db = db_name or self.database_name
                    all_docs.extend(client[db][coll_name].find())

                if remove_duplicates:
                    seen = set()
                    deduped = []
                    for d in all_docs:
                        key = self._canonical_doc(d)
                        if key not in seen:
                            seen.add(key)
                            deduped.append(d)
                    all_docs = deduped

                total_count = len(all_docs)
                results = [self._sanitize_bson(d) for d in all_docs[:100]]
                return {'doc_count': total_count, 'results': results}
        except Exception as e:
            print(f"[JCoFrameworkExecutor] WARNING estrazione MERGE fallita: {e}")
            return {'doc_count': 0, 'results': []}

    def _extract_intersect_documents(self, jcoql_query):
        """INTERSECT COLLECTIONS c1[@db1], c2[@db2];
        Documenti presenti in entrambe le collezioni (uguaglianza per contenuto,
        vedi _canonical_doc - assunzione da verificare)."""
        m = re.search(r'INTERSECT\s+COLLECTIONS\s+(\w+)(?:@(\w+))?\s*,\s*(\w+)(?:@(\w+))?',
                       jcoql_query, re.IGNORECASE)
        if not m:
            return None
        coll1, db1, coll2, db2 = m.groups()

        try:
            from pymongo import MongoClient
            with MongoClient(self.mongo_uri) as client:
                docs1 = list(client[db1 or self.database_name][coll1].find())
                docs2 = list(client[db2 or self.database_name][coll2].find())

                keys2 = {self._canonical_doc(d) for d in docs2}
                results_all = [d for d in docs1 if self._canonical_doc(d) in keys2]

                total_count = len(results_all)
                results = [self._sanitize_bson(d) for d in results_all[:100]]
                return {'doc_count': total_count, 'results': results}
        except Exception as e:
            print(f"[JCoFrameworkExecutor] WARNING estrazione INTERSECT fallita: {e}")
            return {'doc_count': 0, 'results': []}

    def _extract_subtract_documents(self, jcoql_query):
        """SUBTRACT COLLECTIONS c1[@db1], c2[@db2];
        Documenti in c1 assenti da c2 (uguaglianza per contenuto, vedi _canonical_doc -
        assunzione da verificare)."""
        m = re.search(r'SUBTRACT\s+COLLECTIONS\s+(\w+)(?:@(\w+))?\s*,\s*(\w+)(?:@(\w+))?',
                       jcoql_query, re.IGNORECASE)
        if not m:
            return None
        coll1, db1, coll2, db2 = m.groups()

        try:
            from pymongo import MongoClient
            with MongoClient(self.mongo_uri) as client:
                docs1 = list(client[db1 or self.database_name][coll1].find())
                docs2 = list(client[db2 or self.database_name][coll2].find())

                keys2 = {self._canonical_doc(d) for d in docs2}
                results_all = [d for d in docs1 if self._canonical_doc(d) not in keys2]

                total_count = len(results_all)
                results = [self._sanitize_bson(d) for d in results_all[:100]]
                return {'doc_count': total_count, 'results': results}
        except Exception as e:
            print(f"[JCoFrameworkExecutor] WARNING estrazione SUBTRACT fallita: {e}")
            return {'doc_count': 0, 'results': []}

    def _extract_saveas_documents(self, jcoql_query):
        """
        SAVE AS nuovaCollezione[@db]; e' una vera scrittura: il motore J-CO calcola il
        risultato della pipeline precedente (GET COLLECTION + eventuali FILTER/GROUP/...) e lo
        persiste in una nuova collezione MongoDB. A differenza di JOIN/GROUP/EXPAND/MERGE/
        INTERSECT/SUBTRACT, qui NON serve ricostruire alcuna logica lato Python: il motore ha
        gia' scritto il risultato vero, quindi ci limitiamo a rileggerlo da MongoDB come verifica
        e per restituirlo all'utente. Nota importante: a differenza di tutti gli altri comandi
        gestiti finora, questo MODIFICA realmente il database (crea una nuova collezione).
        SAVE TO FILE non e' gestito (scrive su file lato server, non verificabile via pymongo
        senza conoscere la convenzione di path usata da Java).
        """
        m = re.search(r'SAVE\s+AS\s+(\w+)(?:@(\w+))?', jcoql_query, re.IGNORECASE)
        if not m:
            return None  # probabilmente SAVE TO FILE, non supportato

        new_collection, target_db = m.groups()

        try:
            from pymongo import MongoClient
            with MongoClient(self.mongo_uri) as client:
                db = client[target_db or self.database_name]
                collection = db[new_collection]

                total_count = collection.count_documents({})
                if total_count == 0:
                    print(f"[JCoFrameworkExecutor] WARNING SAVE AS: la collezione '{new_collection}' "
                          f"in '{target_db or self.database_name}' risulta vuota o inesistente")
                results = [self._sanitize_bson(d) for d in collection.find().limit(100)]
                return {'doc_count': total_count, 'results': results, 'saved_collection': new_collection}
        except Exception as e:
            print(f"[JCoFrameworkExecutor] WARNING verifica SAVE AS fallita: {e}")
            return {'doc_count': 0, 'results': []}

    def _parse_output(self, output, jcoql_query):
        """
        [NON PIÙ CHIAMATO DAL PERCORSO PRINCIPALE — vedi execute(), che ora
        usa _read_temp_result() con la strategia "auto SAVE AS" descritta
        nel docstring del modulo] Lasciato come riferimento/fallback: se la
        nuova strategia mostrasse un problema imprevisto, questo metodo e i
        vari _extract_*_documents più sotto restano disponibili per tornare
        rapidamente al comportamento precedente, invece di doverli riscrivere.

        Ricostruisce i documenti del risultato leggendoli direttamente da
        MongoDB via pymongo, invece che dall'output testuale del motore
        Java (`output`). Necessario perché, per i comandi diversi da
        GET COLLECTION, il motore J-CO stampa su stdout solo il conteggio
        dei documenti generati, non il loro contenuto (vedi i commenti
        nei singoli metodi _extract_*_documents più sopra, uno per ogni
        comando avanzato). Il conteggio letto da `output` (quando
        presente) viene comunque usato come riferimento/validazione
        incrociata rispetto a quanto trovato interrogando Mongo
        direttamente — se i due numeri divergono, viene loggato un
        warning ma il risultato calcolato qui prevale comunque.
        """
        doc_count = 0
        docs = []

        # JOIN OF COLLECTIONS: il motore J-CO non stampa i documenti generati su
        # stdout (solo il conteggio), quindi l'estrazione segue un percorso dedicato.
        if re.search(r'JOIN\s+OF\s+COLLECTIONS', jcoql_query, re.IGNORECASE):
            join_result = self._extract_join_documents(jcoql_query)
            if join_result is not None:
                # Conteggio ufficiale del motore, usato solo per log/validazione incrociata
                engine_match = re.search(
                    r'\[Join Of Collections\]\s+executed:\s+(\d+)\s+documents generated',
                    output, re.IGNORECASE
                )
                if engine_match:
                    engine_count = int(engine_match.group(1))
                    if engine_count != join_result['doc_count']:
                        print(f"[JCoFrameworkExecutor] WARNING conteggio motore ({engine_count}) "
                              f"diverso da conteggio estratto ({join_result['doc_count']})")
                return {
                    'doc_count': join_result['doc_count'],
                    'results': join_result['results'],
                    'text': ''
                }

        # GROUP: estrazione dedicata via aggregazione MongoDB (il motore J-CO non
        # stampa i documenti raggruppati su stdout, solo il conteggio dei gruppi).
        if re.search(r'GROUP\s+PARTITION', jcoql_query, re.IGNORECASE):
            group_result = self._extract_group_documents(jcoql_query)
            if group_result is not None:
                engine_match = re.search(
                    r'\[Group\]\s+executed:\s+(\d+)\s+documents grouped',
                    output, re.IGNORECASE
                )
                if engine_match:
                    engine_count = int(engine_match.group(1))
                    if engine_count != group_result['doc_count']:
                        print(f"[JCoFrameworkExecutor] WARNING conteggio motore ({engine_count}) "
                              f"diverso da conteggio estratto ({group_result['doc_count']})")
                return {
                    'doc_count': group_result['doc_count'],
                    'results': group_result['results'],
                    'text': ''
                }
            return {'doc_count': 0, 'results': [], 'text': ''}

        # SAVE AS: vera scrittura, il motore ha gia' persistito il risultato in MongoDB -
        # ci limitiamo a rileggerlo come verifica, nessuna logica da replicare in Python.
        if re.search(r'SAVE\s+AS\s+\w+', jcoql_query, re.IGNORECASE):
            saveas_result = self._extract_saveas_documents(jcoql_query)
            if saveas_result is not None:
                return {
                    'doc_count': saveas_result['doc_count'],
                    'results': saveas_result['results'],
                    'text': f"Salvato in collezione: {saveas_result.get('saved_collection', '?')}"
                }
            return {'doc_count': 0, 'results': [], 'text': ''}

        # SAVE TO FILE: scrive su un file lato server (Java), non su MongoDB - non c'e' nulla
        # da rileggere via pymongo. Ci basiamo sul messaggio che Java stampa direttamente
        # ("[Save] executed: N documents saved to file <path>"), che include sia il conteggio
        # sia il percorso. NOTA (lezione dall'indagine SAVE AS): un messaggio di successo di
        # Java non garantisce che il file sia davvero verificabile da qui - il percorso puo'
        # essere relativo alla working directory del processo Java (non necessariamente la
        # stessa del wrapper Python), quindi tentiamo una lettura ma non falliamo se non
        # riusciamo a trovarlo: mostriamo comunque il percorso dichiarato per la verifica
        # manuale, come gia' fatto per SAVE AS al primo giro.
        if re.search(r'SAVE\s+TO\s+FILE', jcoql_query, re.IGNORECASE):
            file_msg_match = re.search(
                r'\[Save\]\s+executed:\s+(\d+)\s+documents saved to file\s+(.+)',
                output
            )
            if file_msg_match:
                declared_count = int(file_msg_match.group(1))
                declared_path = file_msg_match.group(2).strip()

                file_contents = None
                for candidate in (
                    Path(declared_path),
                    self.jco_base / declared_path,
                    Path.home() / declared_path,
                ):
                    try:
                        if candidate.is_file():
                            file_contents = json.loads(candidate.read_text(encoding='utf-8'))
                            break
                    except Exception:
                        continue

                if isinstance(file_contents, list):
                    results = [self._sanitize_bson(d) for d in file_contents[:100]]
                    return {
                        'doc_count': len(file_contents),
                        'results': results,
                        'text': f"Salvato su file: {declared_path} ({declared_count} documenti, verificato)"
                    }
                return {
                    'doc_count': declared_count,
                    'results': [],
                    'text': f"Il motore dichiara {declared_count} documenti salvati su file: "
                            f"{declared_path} - percorso non verificabile automaticamente da "
                            f"qui, controllalo manualmente."
                }
            return {'doc_count': 0, 'results': [], 'text': ''}

        # MERGE / INTERSECT / SUBTRACT COLLECTIONS: stesso schema di JOIN/GROUP/EXPAND.
        # Pattern del conteggio motore non ancora confermati empiricamente (nomi plausibili
        # per analogia con gli altri comandi: "[Merge Collections]", "[Intersect Collections]",
        # "[Subtract Collections]" seguiti da "executed:").
        _set_ops = [
            ('MERGE\\s+COLLECTIONS', self._extract_merge_documents, r'\[Merge Collections\]\s+executed:\s+(\d+)'),
            ('INTERSECT\\s+COLLECTIONS', self._extract_intersect_documents, r'\[Intersect Collections\]\s+executed:\s+(\d+)'),
            ('SUBTRACT\\s+COLLECTIONS', self._extract_subtract_documents, r'\[Subtract Collections\]\s+executed:\s+(\d+)'),
        ]
        for keyword_pattern, extract_fn, engine_pattern in _set_ops:
            if re.search(keyword_pattern, jcoql_query, re.IGNORECASE):
                set_result = extract_fn(jcoql_query)
                if set_result is not None:
                    engine_match = re.search(engine_pattern, output, re.IGNORECASE)
                    if engine_match:
                        engine_count = int(engine_match.group(1))
                        if engine_count != set_result['doc_count']:
                            print(f"[JCoFrameworkExecutor] WARNING conteggio motore ({engine_count}) "
                                  f"diverso da conteggio estratto ({set_result['doc_count']}) - "
                                  f"l'assunzione sull'uguaglianza documenti potrebbe essere errata")
                    return {
                        'doc_count': set_result['doc_count'],
                        'results': set_result['results'],
                        'text': ''
                    }
                return {'doc_count': 0, 'results': [], 'text': ''}

        # EXPAND: estrazione dedicata (il motore J-CO non stampa i documenti espansi
        # su stdout, solo il conteggio - pattern esatto da confermare empiricamente).
        if re.search(r'EXPAND\s+UNPACK', jcoql_query, re.IGNORECASE):
            expand_result = self._extract_expand_documents(jcoql_query)
            if expand_result is not None:
                engine_match = re.search(
                    r'\[Expand\]\s+executed:\s+(\d+)',
                    output, re.IGNORECASE
                )
                if engine_match:
                    engine_count = int(engine_match.group(1))
                    if engine_count != expand_result['doc_count']:
                        print(f"[JCoFrameworkExecutor] WARNING conteggio motore ({engine_count}) "
                              f"diverso da conteggio estratto ({expand_result['doc_count']}) - "
                              f"il pattern di riconoscimento del conteggio EXPAND potrebbe "
                              f"essere impreciso, verificare l'output raw")
                return {
                    'doc_count': expand_result['doc_count'],
                    'results': expand_result['results'],
                    'text': ''
                }
            return {'doc_count': 0, 'results': [], 'text': ''}

        # Ricerca del numero di documenti
        try:
            match = re.search(r'Get Collection.*?executed:\s+(\d+)\s+documents', output, re.DOTALL | re.IGNORECASE)
            if match:
                doc_count = int(match.group(1))
        except Exception as e:
            print(f"[JCoFrameworkExecutor] ⚠️ Errore lettura count: {e}")
        
        collection_name = self._extract_collection_name(jcoql_query)
        if collection_name:
            try:
                from pymongo import MongoClient
                from bson import ObjectId, Decimal128
                
                with MongoClient(self.mongo_uri) as client:
                    db = client[self.database_name]
                    collection = db[collection_name]
                    
                    # Estrai il filtro dalla query JCoQL
                    mongo_filter = self._extract_mongo_filter(jcoql_query)
                    
                    # ✅ Conta TUTTI i documenti che matchano
                    if mongo_filter:
                        total_matching = collection.count_documents(mongo_filter)
                    else:
                        total_matching = collection.count_documents({})
                    
                    # ✅ Estrai i primi 100
                    if mongo_filter:
                        docs = list(collection.find(mongo_filter).limit(100))
                    else:
                        docs = list(collection.find().limit(100))
                    
                    # Converti ObjectId e Decimal128
                    for doc in docs:
                        if '_id' in doc and isinstance(doc['_id'], ObjectId):
                            doc['_id'] = str(doc['_id'])
                        
                        def convert_decimal(obj):
                            if isinstance(obj, dict):
                                for key, val in obj.items():
                                    if isinstance(val, Decimal128):
                                        obj[key] = float(val.to_decimal())
                                    elif isinstance(val, (dict, list)):
                                        convert_decimal(val)
                            elif isinstance(obj, list):
                                for i, val in enumerate(obj):
                                    if isinstance(val, Decimal128):
                                        obj[i] = float(val.to_decimal())
                                    elif isinstance(val, (dict, list)):
                                        convert_decimal(val)
                        
                        convert_decimal(doc)
                    
                    # ✅ Ritorna il numero VERO
                    doc_count = total_matching
                
            except Exception as e:
                print(f"[JCoFrameworkExecutor] ❌ MongoDB fallito: {e}")
        
        return {
            'results': docs,
            'doc_count': doc_count, 
            'text': ''
        }

    def _extract_mongo_filter(self, jcoql_query):
        """Estrai il filtro JCOQL con supporto AND/OR"""
        match = re.search(r'WHERE\s+(.+?)\s+KEEP\s+OTHERS', jcoql_query, re.IGNORECASE)
        if not match:
            return None
        
        condition = match.group(1).strip()
        
        # Split per AND/OR
        if ' AND ' in condition.upper():
            parts = re.split(r'\s+AND\s+', condition, flags=re.IGNORECASE)
            filters = []
            for part in parts:
                f = self._parse_single_filter(part.strip())
                if f:
                    filters.append(f)
            if filters:
                return {'$and': filters}
        
        elif ' OR ' in condition.upper():
            parts = re.split(r'\s+OR\s+', condition, flags=re.IGNORECASE)
            filters = []
            for part in parts:
                f = self._parse_single_filter(part.strip())
                if f:
                    filters.append(f)
            if filters:
                return {'$or': filters}
        
        else:
            return self._parse_single_filter(condition)

    def _parse_single_filter(self, condition):
        """Parsa un singolo filtro: .field operator value"""
        field_match = re.match(r'\.([a-zA-Z0-9_.]+)\s*(>=|<=|>|<|=|!=)\s*(.+)', condition)
        if not field_match:
            return None
        
        field_path, operator, value_str = field_match.groups()
        value_str = value_str.strip().strip("'\"")
        
        # Conversione valore (codice existing)
        try:
            if value_str.lower() in ('true', 'false'):
                value = value_str.lower() == 'true'
            elif value_str.lstrip('-').isdigit():
                value = int(value_str)
            elif '.' in value_str:
                try:
                    value = float(value_str)
                except:
                    value = value_str
            else:
                value = value_str
        except:
            value = value_str
        
        mongo_op_map = {'>': '$gt', '<': '$lt', '>=': '$gte', '<=': '$lte', '=': '$eq', '!=': '$ne'}
        mongo_op = mongo_op_map.get(operator)
        if not mongo_op:
            return None
        
        return {field_path: {mongo_op: value}}


    def _get_documents_from_mongodb(self, collection_name, limit=100):
        """
        Fallback: estrai documenti direttamente da MongoDB se il parsing fallisce

        Nota: questo metodo non risulta chiamato da nessun punto del
        file (verificato con una ricerca su tutta la classe) — è un
        fallback scritto ma mai agganciato al flusso principale.
        """
        try:
            from pymongo import MongoClient
            from datetime import datetime
            
            # FIX: usava un URI hardcoded ("mongodb://localhost:27017")
            # invece di self.mongo_uri (l'URI passato all'executor alla
            # creazione) — se un giorno questo metodo venisse richiamato
            # con un database non locale, si sarebbe connesso comunque a
            # localhost invece che all'host giusto. Corretto anche il
            # mancato client.close() (stesso problema visto negli altri
            # 8 punti del file che aprono una MongoClient).
            with MongoClient(self.mongo_uri) as client:
                db = client[self.database_name]
                collection = db[collection_name]
                
                # Estrai i primi 'limit' documenti
                docs = list(collection.find().limit(limit))
                
                # CONVERTI TUTTI I CAMPI NON SERIALIZZABILI
                for doc in docs:
                    # Converti ObjectId a stringa
                    if '_id' in doc:
                        doc['_id'] = str(doc['_id'])
                    
                    # Converti tutti i datetime a ISO format
                    for key, value in doc.items():
                        if isinstance(value, datetime):
                            doc[key] = value.isoformat()
                        elif isinstance(value, dict):
                            # Se è un dict annidato, converti anche i datetime dentro
                            for k, v in value.items():
                                if isinstance(v, datetime):
                                    value[k] = v.isoformat()
                
                return docs
        except Exception as e:
            return []


    def _apply_filter_to_results(self, results: list, filter_condition: str) -> list:
        """
        [NON PIÙ CHIAMATO — vedi nota su _parse_output(). Era il fallback
        Python quando si sospettava che il FilterExecutor del motore non
        avesse applicato il filtro; con la strategia "auto SAVE AS" i
        risultati sono sempre quelli reali del motore, quindi non serve
        più riapplicare nulla qui.]
        Applica un filtro ai risultati quando il JCo non lo ha fatto
        Supporta: 
        - Singoli: .field > value
        - AND: .field = value AND .other > 5
        - OR: .field = value OR .other != 10
        """
        if not filter_condition or not results:
            return results
        
        # Supporto AND/OR
        if ' AND ' in filter_condition.upper():
            # Splitto per AND e applico tutti i filtri
            conditions = re.split(r'\s+AND\s+', filter_condition, flags=re.IGNORECASE)
            filtered = results
            for condition in conditions:
                filtered = self._apply_single_filter(filtered, condition.strip())
            return filtered
        
        elif ' OR ' in filter_condition.upper():
            # Splitto per OR - ritorna documenti che matchano ALMENO una condizione
            conditions = re.split(r'\s+OR\s+', filter_condition, flags=re.IGNORECASE)
            filtered = []
            for doc in results:
                for condition in conditions:
                    if self._matches_condition(doc, condition.strip()):
                        filtered.append(doc)
                        break  # Documento già matchato, non aggiungerlo di nuovo
            return filtered
        
        else:
            # Singolo filtro
            return self._apply_single_filter(results, filter_condition)
    
    def _apply_single_filter(self, results: list, filter_condition: str) -> list:
        """Applica un singolo filtro a una lista di risultati"""
        if not filter_condition or not results:
            return results
        
        # Parse della condizione: .field OPERATOR value
        match = re.match(r'\.([a-zA-Z0-9_.]+)\s*(>=|<=|>|<|=|!=)\s*(.+)', filter_condition.strip())
        
        if not match:
            return results  # Non riesco a parsare, ritorna tutto
        
        field_path, operator, value_str = match.groups()
        value_str = value_str.strip().strip("'\"")
        
        # Converti il valore
        try:
            if value_str.lower() in ('true', 'false'):
                value = value_str.lower() == 'true'
            elif value_str.lstrip('-').isdigit():
                value = int(value_str)
            elif '.' in value_str:
                try:
                    value = float(value_str)
                except:
                    value = value_str
            else:
                value = value_str
        except:
            value = value_str
        
        # Filtraggio reale
        filtered = []
        
        for doc in results:
            # Navigazione nested: .imdb.rating → doc["imdb"]["rating"]
            doc_value = doc
            for part in field_path.split('.'):
                if isinstance(doc_value, dict) and part in doc_value:
                    doc_value = doc_value[part]
                else:
                    doc_value = None
                    break
            
            if doc_value is None:
                continue  # Campo non trovato, skip
            
            # Applica l'operatore
            try:
                if operator == '>':
                    matches = doc_value > value
                elif operator == '<':
                    matches = doc_value < value
                elif operator == '>=':
                    matches = doc_value >= value
                elif operator == '<=':
                    matches = doc_value <= value
                elif operator == '=':
                    # Supporto array
                    if isinstance(doc_value, list):
                        matches = value in doc_value
                    else:
                        matches = doc_value == value
                elif operator == '!=':
                    # Supporto array
                    if isinstance(doc_value, list):
                        matches = value not in doc_value
                    else:
                        matches = doc_value != value
                else:
                    matches = False
                
                if matches:
                    filtered.append(doc)
            except TypeError:
                # Confronto non possibile (es: stringa > numero)
                pass
        
        return filtered
    
    def _matches_condition(self, doc: dict, filter_condition: str) -> bool:
        """Ritorna True se il documento matcha la condizione"""
        match = re.match(r'\.([a-zA-Z0-9_.]+)\s*(>=|<=|>|<|=|!=)\s*(.+)', filter_condition.strip())
        
        if not match:
            return True  # Se non riesco a parsare, considera come match
        
        field_path, operator, value_str = match.groups()
        value_str = value_str.strip().strip("'\"")
        
        # Converti il valore
        try:
            if value_str.lower() in ('true', 'false'):
                value = value_str.lower() == 'true'
            elif value_str.lstrip('-').isdigit():
                value = int(value_str)
            elif '.' in value_str:
                try:
                    value = float(value_str)
                except:
                    value = value_str
            else:
                value = value_str
        except:
            value = value_str
        
        # Estrai il valore dal documento
        doc_value = doc
        for part in field_path.split('.'):
            if isinstance(doc_value, dict) and part in doc_value:
                doc_value = doc_value[part]
            else:
                return False
        
        # Applica l'operatore
        try:
            if operator == '>':
                return doc_value > value
            elif operator == '<':
                return doc_value < value
            elif operator == '>=':
                return doc_value >= value
            elif operator == '<=':
                return doc_value <= value
            elif operator == '=':
                if isinstance(doc_value, list):
                    return value in doc_value
                else:
                    return doc_value == value
            elif operator == '!=':
                if isinstance(doc_value, list):
                    return value not in doc_value
                else:
                    return doc_value != value
            else:
                return False
        except TypeError:
            return False



    def _cleanup_chaintemp_collections(self, jcoql_query):
        """
        Pulizia "best-effort" delle collection intermedie chaintempN
        (create da un JOIN concatenato — vedi prompt in main.py) quando
        l'esecuzione fallisce a metà catena. Prima questa pulizia viveva
        solo dentro _read_temp_result(), chiamato solo sul percorso di
        successo — se il primo JOIN di una catena riusciva e creava
        chaintemp1, ma un passaggio successivo falliva, chaintemp1 restava
        in giro su MongoDB, mai ripulito. Richiamata sia dal ramo di
        successo sia da quelli di errore, così la pulizia avviene comunque.
        Ogni errore qui viene deliberatamente ignorato: è una pulizia
        opportunistica, non deve mai essere la causa di un errore mostrato
        all'utente al posto di quello vero dell'esecuzione.
        """
        try:
            from pymongo import MongoClient
            matches = re.findall(r'SAVE\s+AS\s+(chaintemp\w*)\s*@\s*(\w+)', jcoql_query, re.IGNORECASE)
            if not matches:
                return
            with MongoClient(self.mongo_uri) as client:
                for name, db in matches:
                    try:
                        client[db][name].drop()
                    except Exception:
                        pass
        except Exception:
            pass

    def _read_temp_result(self, temp_collection_name, output, jcoql_query):
        """
        Rilegge da MongoDB il vero risultato prodotto dal motore, salvato dal
        SAVE AS accodato automaticamente in execute() (vedi commento lì e nel
        docstring del modulo). Cancella la collection temporanea dopo averla
        letta. Funziona per qualunque comando, senza bisogno di sapere quale
        comando fosse — è l'intero motivo per cui questa strategia sostituisce
        i precedenti _extract_*_documents dedicati caso per caso.

        Pulisce anche le eventuali collection intermedie di un JOIN
        concatenato (vedi prompt in main.py — pattern insegnato all'LLM per
        "più join nella stessa query": un JOIN, un SAVE AS che materializza
        il risultato con nome "chaintempN", poi un secondo JOIN che lo
        referenzia come collection). Quei nomi sono riconoscibili dal
        prefisso "chaintemp" — a differenza di un SAVE AS scritto
        esplicitamente dall'utente con un nome a sua scelta (quello resta,
        è una richiesta reale di persistenza, non un'impalcatura interna).
        """
        try:
            from pymongo import MongoClient

            with MongoClient(self.mongo_uri) as client:
                coll = client[self.database_name][temp_collection_name]
                total_count = coll.count_documents({})
                docs = list(coll.find().limit(100))
                # Pulizia: la collection temporanea non deve restare in giro.
                try:
                    coll.drop()
                except Exception:
                    pass

                # Pulizia delle collection intermedie di un eventuale JOIN
                # concatenato — stesso principio, ma il nome/database di
                # ciascuna vanno estratti dalla query originale (possono
                # essere in database diversi tra loro).
                for name, db in re.findall(
                    r'SAVE\s+AS\s+(chaintemp\w*)\s*@\s*(\w+)', jcoql_query, re.IGNORECASE
                ):
                    try:
                        client[db][name].drop()
                    except Exception:
                        pass

            results = [self._sanitize_bson(d) for d in docs]

            # Messaggio informativo per SAVE AS / SAVE TO FILE espliciti
            # nella query DELL'UTENTE (non il nostro SAVE AS automatico,
            # accodato dopo, né le collection "chaintemp" intermedie di un
            # JOIN concatenato, già ripulite sopra): il motore ha comunque
            # scritto anche la collection/il file reali richiesti, non solo
            # la nostra copia temporanea di lettura — lo segnaliamo.
            text = ''
            save_matches = re.findall(r'SAVE\s+AS\s+(\w+)\s*@\s*(\w+)', jcoql_query, re.IGNORECASE)
            real_save = next((m for m in save_matches if not m[0].lower().startswith('chaintemp')), None)
            if real_save:
                text = f"Salvato anche in collezione: {real_save[0]}@{real_save[1]}"
            elif re.search(r'SAVE\s+TO\s+FILE', jcoql_query, re.IGNORECASE):
                file_match = re.search(r'\[Save\]\s+executed:\s+\d+\s+documents saved to file\s+(.+)', output)
                if file_match:
                    text = f"Salvato anche su file: {file_match.group(1).strip()}"

            # Se non troviamo nessun documento, controlliamo se è un risultato
            # genuinamente vuoto o se la query non è mai arrivata al nostro
            # SAVE AS automatico (es. comando sconosciuto al parser, errore
            # non intercettato dal controllo "ECCEZIONE:" fatto più in alto in
            # execute()) — in quel caso la collection temporanea non viene mai
            # creata, e vale la pena dirlo invece di mostrare silenziosamente
            # "0 risultati" come se fosse un esito normale.
            if total_count == 0 and not re.search(r'\[.*?\]\s*executed', output, re.IGNORECASE):
                text = text or ("Nessun risultato — il motore non sembra aver eseguito nessun "
                                 "comando riconosciuto in questa query (controlla l'output grezzo "
                                 "Java se il problema persiste).")

            return {'doc_count': total_count, 'results': results, 'text': text}
        except Exception as e:
            print(f"[JCoFrameworkExecutor] WARNING lettura risultato (auto SAVE AS) fallita: {e}")
            return {'doc_count': 0, 'results': [], 'text': ''}

    def execute(self, jcoql_query):
        try:
            query_file = self.data_path / "query.jcoql"
            prolog_file = self.data_path / "prolog.jcoql"
            conn_props = self.data_path / "mongodb_connection.properties"
            main_props = self.data_path / "mongodb_test.properties"
            
            # NOTA: questo primo blocco (File 1) scrive due file che, un
            # po' più sotto (File 2, "conn_props"/"main_props"), vengono
            # RISCRITTI DA CAPO con contenuto equivalente ma dinamico e
            # portabile. "properties_file" e "connection_file" qui sotto
            # risolvono esattamente agli stessi percorsi di "main_props" e
            # "conn_props" (stessa self.data_path, stesso nome file) — la
            # scrittura qui è quindi sempre sovrascritta prima che il
            # subprocess Java venga lanciato, e resta innocua nella
            # pratica. Ma "properties_content" sotto contiene un percorso
            # Windows ASSOLUTO hardcoded (C:/Users/nicho/...) — se in
            # futuro questo primo blocco diventasse l'unico a scrivere il
            # file (es. rimuovendo per errore la riscrittura successiva),
            # il subprocess fallirebbe silenziosamente su qualunque
            # macchina diversa da quella con quell'esatto nome utente
            # Windows. Il blocco try/except sotto ingoia comunque
            # qualunque errore di scrittura senza loggarlo.
            # File 1: mongodb_test.properties
            properties_file = os.path.join(os.path.expanduser("~"), ".data", ".zunTestScripts", "mongodb_test.properties")
            properties_content = f"""fileInProlog=C:/Users/nicho/.data/.zunTestScripts/prolog.jcoql
            fileInTest=C:/Users/nicho/.data/.zunTestScripts/query.jcoql
            testName=PythonAutomatedTest
            keyPropertyFile=C:/Users/nicho/.data/.zunTestScripts/mongodb_connection.properties
            default.server=localhost
            server.localhost.uri=mongodb://localhost:27017/{self.database_name}
            server.localhost.database={self.database_name}
            mongodb.uri=mongodb://localhost:27017/{self.database_name}
            mongodb.database={self.database_name}
            mongo.db={self.database_name}
            database={self.database_name}
            toScreen=true
            """

            # File 2: mongodb_connection.properties
            connection_file = os.path.join(os.path.expanduser("~"), ".data", ".zunTestScripts", "mongodb_connection.properties")
            connection_content = f"""mongodb.database={self.database_name}
            mongodb.uri=mongodb://localhost:27017/{self.database_name}
            """

            try:
                with open(properties_file, 'w') as f:
                    f.write(properties_content)
                with open(connection_file, 'w') as f:
                    f.write(connection_content)
            except Exception as e:
                pass

            # FIX: se jcoql_query inizia già con un proprio USE DB (sempre
            # più comune ora che il pannello frontend mostra/manda la query
            # completa, USE DB incluso — vedi QueryExecutor.jsx), scrivere
            # comunque qui un secondo USE DB di default è ridondante: non
            # è un errore (una USE DB ripetuta viene solo "sostituita"),
            # ma inutile — soprattutto visibile nei log dove la stessa riga
            # compare due volte di fila. Il prolog resta come fallback per
            # le query che NON specificano già un database di partenza.
            query_already_has_use_db = bool(re.match(r'^\s*USE\s+DB\b', jcoql_query, re.IGNORECASE))
            prolog_content = "" if query_already_has_use_db else f"USE DB {self.database_name} ON DEFAULT SERVER;\n"
            prolog_file.write_text(prolog_content, encoding='utf-8')

            # STRATEGIA "auto SAVE AS" (vedi docstring del modulo): accodiamo in modo
            # trasparente un SAVE AS verso una collection temporanea con nome univoco
            # per richiesta (uuid4, per evitare che due richieste concorrenti si
            # sovrascrivano a vicenda — stesso tipo di rischio già visto con
            # resources/input.file in java_parser_wrapper.py, qui evitato dalla
            # radice dando un nome diverso ad ogni chiamata). Funziona per qualunque
            # comando precedente perché SaveCollectionExecutor.java prende sempre
            # "pipeline.getCurrentCollection()" — il risultato corrente, quale che sia.
            #
            # FIX (trovato con un test reale): il nome deve essere un ID valido per
            # la grammatica JCoQL+ — "ID : LETTER (LETTER | DIGIT | '_')*" — cioè
            # deve iniziare con una lettera. Il primo tentativo ("__nlquery_...",
            # doppio underscore iniziale) non è un ID valido: il motore falliva con
            # "Lexical Error: Unrecognized token '_'" perché il lexer non riconosce
            # un identificatore che comincia con underscore. Qui sotto si parte
            # sempre con una lettera ("nlquery"), niente underscore da nessuna parte.
            temp_collection_name = f"nlquery{uuid.uuid4().hex[:16]}"
            wrapped_query = jcoql_query.rstrip()
            if not wrapped_query.endswith(';'):
                wrapped_query += ';'
            wrapped_query += f"\nSAVE AS {temp_collection_name}@{self.database_name};"

            # Stampa SEMPRE (non solo con JCOQL_DEBUG) la query completa e
            # reale che viene mandata al motore, prolog incluso — così in
            # PowerShell vedi esattamente cosa è stato eseguito, comprese
            # tutte le USE DB necessarie, senza dover attivare il debug.
            print("=" * 60)
            print("QUERY INVIATA AL MOTORE J-CO (prolog + query):")
            print(prolog_content.rstrip())
            print(wrapped_query)
            print("=" * 60)

            query_file.write_text(wrapped_query, encoding='utf-8')
            
            # URI con database
            parsed = urlparse(self.mongo_uri)
            mongo_uri_with_db = f"{parsed.scheme or 'mongodb'}://{parsed.netloc}/{self.database_name}"
            
            # Scrittura properties di connessione
            conn_props.write_text(
                "default.server=localhost\n"
                f"server.localhost.uri={mongo_uri_with_db}\n"
                f"server.localhost.database={self.database_name}\n"
                f"mongo.uri={self.mongo_uri}\n"
                f"mongodb.uri={mongo_uri_with_db}\n"
                f"mongo.db={self.database_name}\n"
                f"mongodb.database={self.database_name}\n"
                f"dbName={self.database_name}\n"
                f"database={self.database_name}\n"
                "mongo.useSSL=false\n",
                encoding='utf-8'
            )
            
            prolog_abs = str(prolog_file.resolve()).replace('\\', '/')
            query_abs = str(query_file.resolve()).replace('\\', '/')
            conn_abs = str(conn_props.resolve()).replace('\\', '/')

            # Scrittura del file principale delle properties
            main_props.write_text(
                f"fileInProlog={prolog_abs}\n"
                f"fileInTest={query_abs}\n"
                "testName=PythonAutomatedTest\n"
                f"keyPropertyFile={conn_abs}\n"
                "default.server=localhost\n"
                f"server.localhost.uri={mongo_uri_with_db}\n"
                f"server.localhost.database={self.database_name}\n"
                f"mongodb.uri={mongo_uri_with_db}\n"
                f"mongodb.database={self.database_name}\n"
                f"mongo.db={self.database_name}\n"
                f"database={self.database_name}\n"
                f"server.localhost.database={self.database_name}\n"
                "toScreen=true\n",
                encoding='utf-8'
            )
            
            # Classpath
            gradle_cache = Path.home() / ".gradle/caches/modules-2/files-2.1"
            jar_patterns = [
                (gradle_cache / "com.fasterxml.jackson.core/jackson-databind", "jackson-databind-*.jar"),
                (gradle_cache / "com.fasterxml.jackson.core/jackson-core", "jackson-core-*.jar"),
                (gradle_cache / "com.fasterxml.jackson.core/jackson-annotations", "jackson-annotations-*.jar"),
                
                # --- ANTLR & LOGGING ---
                (gradle_cache / "org.antlr/antlr-runtime", "antlr-runtime-*.jar"),
                (gradle_cache / "org.slf4j/slf4j-api", "slf4j-api-*.jar"),
                (gradle_cache / "org.slf4j/slf4j-log4j12", "slf4j-log4j12-*.jar"),
                (gradle_cache / "log4j/log4j", "log4j-*.jar"),
                (gradle_cache / "commons-logging/commons-logging", "commons-logging-*.jar"),
                
                # --- MONGODB ---
                (gradle_cache / "org.mongodb/bson", "bson-*.jar"),
                (gradle_cache / "org.mongodb/mongodb-driver-core", "mongodb-driver-core-*.jar"),
                (gradle_cache / "org.mongodb/mongodb-driver-sync", "mongodb-driver-sync-*.jar"),
                (gradle_cache / "org.mongodb/mongodb-driver", "mongodb-driver-*.jar"),
                (gradle_cache / "org.mongodb/mongo-java-driver", "mongo-java-driver-*.jar"),
                
                # --- SPRING FRAMEWORK ---
                (gradle_cache / "org.springframework/spring-core", "spring-core-*.jar"),
                (gradle_cache / "org.springframework/spring-context", "spring-context-*.jar"),
                (gradle_cache / "org.springframework/spring-aop", "spring-aop-*.jar"),
                (gradle_cache / "org.springframework/spring-beans", "spring-beans-*.jar"),
                (gradle_cache / "org.springframework/spring-expression", "spring-expression-*.jar"),
                (gradle_cache / "org.springframework/spring-jcl", "spring-jcl-*.jar"),
            ]
            
            classpath_parts = [
                str(self.jco_base),
                str(self.jco_base / "config"),
                # FIX 2 agosto 2026: mancavano le cartelle "resources" (contengono conf/servers.properties
                # e altri file di risorse) - solo "classes" era presente. Senza queste, getResourceAsStream
                # in ParserLauncher.java trovava (nella migliore delle ipotesi) risorse vecchie impacchettate
                # in un JAR non aggiornato sotto build/libs/*, invece dei file sorgente freschi.
                # Messe PRIMA dei JAR cosi' le risorse fresche hanno sempre la precedenza.
                str(self.jco_base / "jcoql-engine/build/resources/main"),
                str(self.jco_base / "jcoql-engine-mongodb/build/resources/main"),
                str(self.jco_base / "jcoql-model/build/resources/main"),
                str(self.jco_base / "jcoql-engine/build/classes/java/main"),
                str(self.jco_base / "jcoql-model/build/classes/java/main"),
                str(self.jco_base / "jcoql-engine-mongodb/build/classes/java/main"),
                
                str(self.jco_base / "jcoql-engine/build/libs/*"),
                str(self.jco_base / "jcoql-engine-mongodb/build/libs/*"),
                str(self.jco_base / "jcoql-model/lib/*"),
                str(self.jco_base / "jcoql-ds-core/lib/*"),
                str(self.jco_base / "jcoql-engine/lib/*"),
            ]
            
            for base_path, pattern in jar_patterns:
                if Path(base_path).exists():
                    latest = self._get_latest_jar(Path(base_path), pattern)
                    if latest:
                        classpath_parts.append(latest)
            
            classpath = os.pathsep.join(classpath_parts)

            cmd = [
                'java',
                '-Xmx512m',
                f'-Dmongodb.database={self.database_name}',
                f'-Dmongo.db={self.database_name}',
                f'-Ddatabase={self.database_name}',
                '-cp', classpath,
                'jco.ql.engine.JcoScriptLauncher',
                str(main_props.resolve())
            ]
            
            result = subprocess.run(cmd, cwd=str(self.jco_base), capture_output=True,
                                  text=True, timeout=30, encoding='utf-8', errors='replace')

            # Log diagnostico dell'output grezzo di Java per comandi diversi da GET COLLECTION
            # (JOIN/GROUP/EXPAND/MERGE/INTERSECT/SUBTRACT/SAVE), attivo solo con
            # JCOQL_DEBUG=true (vedi interruttore in cima al file).
            _q_upper = jcoql_query.upper()
            _needs_raw_debug = (
                "GROUP PARTITION" in _q_upper or "EXPAND UNPACK" in _q_upper
                or "SAVE AS" in _q_upper or "SAVE TO FILE" in _q_upper
                or "MERGE COLLECTIONS" in _q_upper or "INTERSECT COLLECTIONS" in _q_upper
                or "SUBTRACT COLLECTIONS" in _q_upper
            )
            if JCOQL_DEBUG and ("GET COLLECTION" not in _q_upper or _needs_raw_debug):
                print("=" * 60)
                print("DEBUG RAW JAVA STDOUT (comando non-GET COLLECTION):")
                print(f"   returncode: {result.returncode}")
                print(f"   stdout:\n{result.stdout}")
                print(f"   stderr:\n{result.stderr}")
                print("=" * 60)

            if result.returncode == 0 and "ECCEZIONE:" not in result.stdout:
                # Legge il vero risultato dal motore invece di ricostruirlo in
                # Python — vedi strategia "auto SAVE AS" nel docstring del modulo.
                # Sostituisce sia _parse_output() sia il vecchio fallback che
                # riapplicava il filtro in Python quando "il FilterExecutor del
                # JCo non aveva filtrato": quel fallback esisteva solo perché
                # prima si tentava di ricostruire il filtro con un pymongo_filter
                # scritto a mano, che poteva divergere dalla semantica reale del
                # motore. Ora il filtro è sempre quello vero, applicato dal motore
                # stesso — non serve più.
                parsed = self._read_temp_result(temp_collection_name, result.stdout, jcoql_query)

                return {
                    'success': True,
                    'jcoql_query': jcoql_query,
                    'count': parsed.get('doc_count', 0),
                    'results': parsed.get('results', []),
                    'text': parsed.get('text', ''),
                    'executor': 'jco_framework'
                }
            else:
                # Pulizia best-effort delle eventuali chaintempN già create
                # prima del fallimento (vedi _cleanup_chaintemp_collections).
                self._cleanup_chaintemp_collections(jcoql_query)

                # Estrae un messaggio d'errore leggibile dallo stdout Java, invece del
                # generico "Failed" che non dice nulla di utile all'utente (vedi indagine
                # SAVE AS: senza questo, ogni fallimento appariva identico e indistinguibile).
                readable_error = None
                exc_match = re.search(
                    r'ECCEZIONE:\s*\n(.+?)(?:\n\*ZUN|\n---|\Z)',
                    result.stdout, re.DOTALL
                )
                if exc_match:
                    readable_error = exc_match.group(1).strip().split('\n')[0]
                if not readable_error:
                    err_line_match = re.search(r'\[.+?\]\s*Error:\s*(.+)', result.stdout)
                    if err_line_match:
                        readable_error = err_line_match.group(1).strip()
                error_message = readable_error or result.stderr or "Errore sconosciuto durante l'esecuzione"
                return {
                    'success': False,
                    'error': error_message,
                    'executor': 'jco_framework'
                }
        except Exception as e:
            self._cleanup_chaintemp_collections(jcoql_query)
            return {'success': False, 'error': str(e), 'executor': 'jco_framework'}