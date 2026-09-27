#!/usr/bin/env python3
"""
JCoQL+ Natural Language Interface - Main Application
Modulo principale FastAPI per la traduzione da linguaggio naturale a query JCoQL+
e per l'esecuzione/gestione dei database MongoDB.
"""

# ==============================================================================
# IMPORT LIBRERIE STANDARD E TERZE PARTI
# ==============================================================================
import os
import sys
import time
import json
import re
from pathlib import Path
from typing import List, Optional
from datetime import datetime

# FastAPI e utilità HTTP
from fastapi import FastAPI, HTTPException, Request, UploadFile, Query, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Pydantic per la validazione dei dati in ingresso
from pydantic import BaseModel

# Vector DB per RAG (Retrieval-Augmented Generation)
import chromadb

# SDK Generative AI di Google
import google.generativeai as genai

# Gestione variabili d'ambiente (.env)
from dotenv import load_dotenv

# Import moduli interni di backend
from backend.query_corrector import correct_query
from backend.database_persistence import load_databases_from_file, save_databases_to_file
from backend.join_executor import JoinExecutor

# ==============================================================================
# CONFIGURAZIONE PATH E MODULI INTERNI
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

sys.path.append(os.path.join(BASE_DIR, "backend", "parsers"))
executors_path = Path(BASE_DIR) / "backend" / "executors"
if str(executors_path) not in sys.path:
    sys.path.insert(0, str(executors_path))

from backend.logging_config import setup_logging, get_startup_logger, get_query_logger, get_db_logger
from backend.database.database_registry import db_registry
from backend.llm_local import generate_with_llama, generate_with_gemma
from backend.parsers.parser_factory import ParserFactory, ParserType
from executor_factory import ExecutorFactory, ExecutorType

# ==============================================================================
# INIZIALIZZAZIONE CONFIGURAZIONE ED AMBIENTE
# ==============================================================================
load_dotenv()

# Timestamp di avvio del processo, usato da /api/stats per calcolare
# l'uptime reale (vedi sotto) invece di un valore fisso.
APP_START_TIME = time.time()

# Caricamento regole sintattiche
def load_file_content(path: str) -> str:
    # In caso di errore (es. file mancante) ritorna una stringa vuota
    # invece di sollevare l'eccezione — l'app continua ad avviarsi anche
    # se uno di questi file manca, ma il prompt inviato all'LLM perde
    # silenziosamente quella parte di contesto, senza nessun log o
    # avviso visibile che lo segnali.
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return ""


def _fix_missing_collection_db(query: str, current_db: str) -> str:
    """
    Riparazione deterministica (15/08): aggiunge "@current_db" a ogni
    riferimento a collection dentro JOIN OF COLLECTIONS / MERGE COLLECTIONS
    che ne è sprovvisto. Senza @database esplicito, sia JoinExecutor.java
    sia MergeCollectionsExecutor.java (motore ufficiale) cercano il nome
    tra le collection temporanee della pipeline invece che su MongoDB —
    per una collection reale come "users" o "products", questo fallisce
    sempre a runtime. Non tocca riferimenti già completi di @database
    (es. "chaintemp1@jcoql_test", scritto correttamente dal modello nei
    test osservati) — idempotente, non modifica una query già corretta.
    """
    def fix_refs(match):
        keyword = match.group(1)
        refs_text = match.group(2)
        parts = [p.strip() for p in refs_text.split(',')]
        fixed = []
        for part in parts:
            if '@' not in part:
                m = re.match(r'^(\w+)(\s+AS\s+\w+)?$', part, re.IGNORECASE)
                if m:
                    name, alias = m.group(1), m.group(2) or ''
                    part = f"{name}@{current_db}{alias}"
            fixed.append(part)
        return f"{keyword} " + ", ".join(fixed)

    pattern = (
        r'(JOIN OF COLLECTIONS|MERGE COLLECTIONS)\s+(.+?)'
        r'(?=\s*(?:CASE\b|CASES\b|ON\s+GEOMETRY|SET\s+GEOMETRY|REMOVE\s+DUPLICATES|;))'
    )
    return re.sub(pattern, fix_refs, query, flags=re.IGNORECASE | re.DOTALL)


def _fix_hallucinated_databases(query: str, current_db: str, real_databases: set) -> str:
    """
    Riparazione deterministica (15/08, seconda parte): a differenza del
    caso sopra (@database mancante del tutto), qui il modello AGGIUNGE
    già un @database — ma a volte inventa un nome che in realtà è il nome
    di una collection, non un database reale (osservato: "USE DB users;"
    e "users@users AS u", quando "users" è solo una collection dentro
    jcoql_test — non esiste nessun database chiamato "users"). Rimuove la
    riga USE DB fittizia e sostituisce ogni "@nomeFittizio" con
    "@current_db". Un vero JOIN tra due database realmente registrati non
    viene toccato (controllato contro real_databases, non contro un
    elenco scritto a mano).
    """
    used_dbs = set(re.findall(r'USE\s+DB\s+(\w+)', query, re.IGNORECASE))
    fake_dbs = {db for db in used_dbs if db not in real_databases}
    if not fake_dbs:
        return query
    for fake in fake_dbs:
        query = re.sub(
            rf'USE\s+DB\s+{re.escape(fake)}\s+ON\s+DEFAULT\s+SERVER\s*;\s*\n?',
            '', query, flags=re.IGNORECASE
        )
        query = re.sub(rf'@{re.escape(fake)}\b', f'@{current_db}', query, flags=re.IGNORECASE)
    return query


def _build_multi_database_query(generated_query: str, databases: list, all_databases: dict) -> str:
    """
    Costruzione deterministica (16/08, sullo stesso modello di
    join_executor.py per il JOIN): se sono selezionati 2+ database, la
    generazione LLM scrive sempre e solo per il database corrente (non ha
    modo di sapere se l'utente intendesse coinvolgerli tutti) — prima si
    chiedeva all'LLM di dedurlo dalla formulazione della richiesta
    ("cerca su tutti i database selezionati"), ma è un'aspettativa poco
    intuitiva: selezionare più database in un controllo di selezione
    dovrebbe significare "usali", non "tienili disponibili nel caso li
    nomini esplicitamente". Ora, quando 2+ database sono selezionati e la
    query generata è un semplice "GET COLLECTION nome;" (eventualmente
    seguito da altro, es. FILTER — preservato e applicato dopo l'unione),
    viene ricostruita automaticamente per coprire TUTTI i database
    selezionati tramite MERGE COLLECTIONS.

    FIX (18/09): prima includeva CIECAMENTE ogni database selezionato,
    anche quando quel database non ha affatto la collection in
    questione — osservato dal vivo: "MERGE COLLECTIONS products@db1,
    products@db2;" generato anche se db2 non ha nessuna collection
    "products", con un test che ha richiesto solo "prodotti con prezzo
    > 500...", senza mai menzionare più database. Ora include SOLO i
    database che hanno davvero quella collection nel proprio schema
    scoperto. Se resta un solo database valido (o nessuno oltre al
    corrente), il MERGE non avrebbe senso — la query semplice originale
    non viene toccata.

    Non tocca la query se non è nella forma semplice attesa (es. contiene
    già JOIN/GROUP/EXPAND/MERGE espliciti) — la costruzione automatica
    riguarda solo il caso base "prendi questa collection", che è anche
    l'unico caso per cui un'unione multi-database ha un significato ovvio
    e univoco.
    """
    if not databases or len(databases) < 2:
        return generated_query

    match = re.match(r'^\s*GET\s+COLLECTION\s+(\w+)\s*;(.*)$', generated_query, re.IGNORECASE | re.DOTALL)
    if not match:
        return generated_query

    collection_name = match.group(1)
    rest = match.group(2).strip()

    valid_databases = [
        db for db in databases
        if collection_name in ((all_databases.get(db, {}) or {}).get('schema', {}) or {})
    ]

    if len(valid_databases) < 2:
        return generated_query

    use_db_lines = "\n".join(f"USE DB {db} ON DEFAULT SERVER;" for db in valid_databases)
    merge_refs = ", ".join(f"{collection_name}@{db}" for db in valid_databases)

    result = f"{use_db_lines}\nMERGE COLLECTIONS {merge_refs};"
    if rest:
        result += f"\n{rest}"
    return result


def _fix_array_field_filter(query: str, current_schema: dict) -> str:
    """
    Riparazione deterministica (16/08): un FILTER CASE WHERE che confronta
    con = o != un campo che lo schema conosce come array (es. .languages,
    .cast, .tags) non può funzionare così com'è — verificato tracciando
    l'intera catena nel codice sorgente del motore, da ValueUtils.java
    (ogni array MongoDB diventa un ArrayValue) fino a
    ComparisonPredicateEvaluator.java (che rifiuta un confronto = tra un
    ArrayValue e un valore singolo, sempre, a prescindere dal contenuto).

    Prima di questa settimana funzionava comunque, perché il FILTER veniva
    ricalcolato lato Python con una gestione esplicita degli array
    ("value in doc_value" invece di "doc_value == value", commit 339af27)
    — sostituita dalla strategia "auto SAVE AS" (che affida il calcolo
    reale al motore, più fedele per JOIN/GROUP/MERGE, ma senza quella
    gestione speciale degli array che il motore stesso non replica).
    Questa funzione richiude quel varco senza tornare alla ricostruzione
    Python: riscrive la query aggiungendo un EXPAND per ciascun campo
    array coinvolto nella condizione, e aggiorna il riferimento al campo
    di conseguenza (.campo diventa .expanded_campo.item — "item" è la
    chiave fissa del motore per il contenuto di un elemento espanso, vedi
    JCOConstants.java, ITEM_FIELD_NAME).

    Toglie anche un eventuale KEEP OTHERS/DROP OTHERS quando riscrive:
    la combinazione con un confronto su un campo array che prima falliva
    sempre silenziosamente è quasi sempre un errore (vedi caso osservato:
    restituiva praticamente tutta la collection invece delle sole
    corrispondenze).

    ATTENZIONE PRESTAZIONI (non risolto qui): se la condizione coinvolge
    PIÙ campi array su una collection grande, gli EXPAND in sequenza
    creano il prodotto di tutte le combinazioni — può essere lento o
    andare in timeout (osservato dal vivo su sample_mflix.movies,
    countries × cast). Qui si risolve solo la correttezza del risultato,
    non le prestazioni su collection grandi con più array coinvolti — un
    filtraggio a stadi (EXPAND+FILTER su un campo, poi SAVE AS, poi
    EXPAND+FILTER sul successivo) risolverebbe anche quello, ma non è
    implementato in automatico.

    FIX (26/09): la versione precedente usava filter_pattern.search(query)
    e coll_match = re.search(...) — un solo match ciascuno, sempre il
    PRIMO della query. Con più blocchi FILTER nella stessa query (tipico
    quando si costruiscono due sottoinsiemi separati prima di un
    INTERSECT/MERGE/SUBTRACT), se il primo FILTER non toccava un campo
    array (es. perché referenziava già un campo espanso, .expanded_x.item)
    la funzione usciva subito senza mai esaminare i FILTER successivi —
    osservato dal vivo: un INTERSECT tra due sottoinsiemi di products,
    il primo costruito via EXPAND, il secondo con `.reviews.user = valore`
    diretto mai corretto, quindi sempre vuoto (il motore rifiuta sempre
    quel confronto), e di conseguenza l'INTERSECT sempre a 0 documenti
    anche quando i documenti in comune esistevano davvero. Ora si scorrono
    TUTTI i blocchi FILTER della query, ciascuno controllato contro la
    collection realmente attiva in quel punto (l'ultimo GET COLLECTION
    incontrato prima della sua posizione, utile perché una query può
    cambiare collection a metà, es. due blocchi "GET COLLECTION products"
    separati per costruire i due lati di un INTERSECT), e le riscritture
    vengono applicate dalla fine della query verso l'inizio per non
    invalidare gli offset dei match precedenti.
    """
    get_coll_pattern = re.compile(r'GET\s+COLLECTION\s+(\w+)\s*;', re.IGNORECASE)
    get_matches = list(get_coll_pattern.finditer(query))
    if not get_matches:
        return query

    def collection_at(pos):
        active = None
        for gm in get_matches:
            if gm.start() <= pos:
                active = gm.group(1)
            else:
                break
        return active

    filter_pattern = re.compile(
        r'FILTER\s+(CASE|CASES)\s+WHERE\s+(.+?)\s*(KEEP\s+OTHERS|DROP\s+OTHERS)?\s*;',
        re.IGNORECASE | re.DOTALL
    )
    filter_matches = list(filter_pattern.finditer(query))
    if not filter_matches:
        return query

    replacements = []
    for fm in filter_matches:
        collection_name = collection_at(fm.start())
        if not collection_name:
            continue

        coll_schema = (current_schema or {}).get(collection_name, {})
        coll_fields = coll_schema.get('fields', {}) if isinstance(coll_schema, dict) else {}

        array_fields = set()
        for field_name, field_info in coll_fields.items():
            if '.' in field_name:
                # Ambito limitato ai campi di primo livello — un campo array
                # annidato dentro un oggetto richiederebbe un percorso EXPAND
                # più complesso, non gestito qui.
                continue
            types = field_info.get('types', []) if isinstance(field_info, dict) else []
            if 'array' in types:
                array_fields.add(field_name)

        if not array_fields:
            continue

        case_kw, condition_text, _others_kw = fm.groups()

        # FIX (19/09): il controllo originale riconosceva solo il confronto
        # DIRETTO sull'intero campo array (.campo = valore) — non copriva
        # l'accesso a un SOTTOCAMPO dentro ogni elemento (.campo.sottoCampo,
        # es. .reviews.rating) con un operatore DIVERSO da =/!= (es. <, >).
        # Osservato dal vivo: "NOT (.reviews.rating < 3)" senza EXPAND, mai
        # intercettato da questo controllo, perché non è un confronto diretto
        # sull'array e non usa =/!=. Il pattern ora cattura un sottopercorso
        # opzionale dopo il nome del campo, e qualunque operatore di
        # confronto (non solo =/!=) — !=/<=/>= prima di =/</> nell'alternanza,
        # così l'operatore più lungo vince quando entrambi potrebbero
        # combaciare parzialmente.
        used_array_fields = [
            field for field in array_fields
            if re.search(rf'\.{re.escape(field)}\b(?:\.\w+)*\s*(?:!=|<=|>=|=|<|>)', condition_text)
        ]
        if not used_array_fields:
            continue

        expand_lines = []
        new_condition = condition_text
        for field in used_array_fields:
            dest_name = f"expanded_{field}"
            expand_lines.append(f"EXPAND UNPACK TRUE ARRAY .{field} TO .{dest_name};")
            new_condition = re.sub(
                rf'\.{re.escape(field)}\b((?:\.\w+)*)(\s*(?:!=|<=|>=|=|<|>))',
                f'.{dest_name}.item\\1\\2',
                new_condition
            )

        new_filter_block = f"FILTER {case_kw} WHERE {new_condition};"
        replacement = "\n".join(expand_lines) + "\n" + new_filter_block
        replacements.append((fm.start(), fm.end(), replacement))

    if not replacements:
        return query

    result = query
    for start, end, replacement in sorted(replacements, key=lambda r: r[0], reverse=True):
        result = result[:start] + replacement + result[end:]
    return result


def _stage_multi_expand_filter(query: str, current_db: str) -> str:
    """
    Riparazione deterministica (16/08): N EXPAND consecutivi (su array
    diversi) seguiti da un unico FILTER con condizione AND che li
    referenzia tutti creano il prodotto di tutte le combinazioni prima di
    scartarne nessuna — su una collection grande, timeout garantito
    (osservato dal vivo due volte, 30s su sample_mflix.movies con
    countries × cast). La regola nel prompt suggeriva di "preferire" lo
    stadio per collezioni grandi, ma l'LLM non ha modo di sapere con
    certezza quanto sia grande una collection — meglio togliere il
    giudizio dall'equazione e farlo sempre, in automatico, a prescindere.

    Riscrive in versione a stadi: primo EXPAND, poi SOLO le condizioni del
    FILTER che riguardano quella destinazione, poi SAVE AS + GET
    COLLECTION sul risultato ridotto, poi il secondo EXPAND (che ora
    lavora su molti meno documenti), e così via. Le condizioni non
    legate a nessuna destinazione EXPAND (es. .year > 2000) vengono
    applicate al primo stadio.

    Limiti dichiarati: si applica solo a condizioni unite con AND (una
    OR renderebbe la separazione in stadi semanticamente diversa dalla
    query originale, quindi qui non si tocca nulla se c'è un OR) e solo
    se gli EXPAND sono consecutivi con un unico FILTER subito dopo
    l'ultimo (il caso osservato finora) — pattern più complessi non
    vengono riconosciuti e la query passa invariata.
    """
    expand_pattern = re.compile(
        r'EXPAND\s+UNPACK\s+TRUE\s+ARRAY\s+\.(\S+)\s+TO\s+\.(\w+)\s*;',
        re.IGNORECASE
    )
    expands = list(expand_pattern.finditer(query))
    if len(expands) < 2:
        return query

    for i in range(len(expands) - 1):
        if query[expands[i].end():expands[i + 1].start()].strip() != '':
            return query

    filter_pattern = re.compile(
        r'FILTER\s+(CASE|CASES)\s+WHERE\s+(.+?)\s*(KEEP\s+OTHERS|DROP\s+OTHERS)?\s*;',
        re.IGNORECASE | re.DOTALL
    )
    fm = filter_pattern.search(query, expands[-1].end())
    if not fm or query[expands[-1].end():fm.start()].strip() != '':
        return query

    case_kw, condition_text, _others = fm.groups()
    destinations = [m.group(2) for m in expands]

    if ' OR ' in condition_text.upper():
        return query

    parts = re.split(r'\s+AND\s+', condition_text, flags=re.IGNORECASE)
    assigned = {dest: [] for dest in destinations}
    leftover = []
    for part in parts:
        matched = False
        for dest in destinations:
            if re.search(rf'\.{re.escape(dest)}\b', part):
                assigned[dest].append(part.strip())
                matched = True
                break
        if not matched:
            leftover.append(part.strip())
    assigned[destinations[0]] = leftover + assigned[destinations[0]]

    # FIX (16/08): prima cercava un "USE DB" nel testo della query per
    # dedurre il database — ma in questo punto del flusso (dentro il
    # repair loop di /api/generate) quella riga non c'è ancora, la
    # aggiunge il frontend solo dopo aver ricevuto la risposta. Il
    # fallback letterale 'current_db' finiva quindi scritto per davvero
    # nella query ("SAVE AS chaintemp1@current_db;", un database che non
    # esiste) invece di essere sostituito. Ora riceve il nome vero come
    # parametro, stesso valore già usato dal resto della funzione
    # chiamante per ogni altra riparazione.
    db_name = current_db

    pieces = []
    for i, m in enumerate(expands):
        pieces.append(m.group(0))
        dest = destinations[i]
        conds = assigned.get(dest, [])
        if conds:
            pieces.append(f"FILTER {case_kw} WHERE {' AND '.join(conds)};")
        if i < len(expands) - 1:
            temp_name = f"chaintemp{i + 1}"
            pieces.append(f"SAVE AS {temp_name}@{db_name};")
            pieces.append(f"GET COLLECTION {temp_name};")

    replacement = "\n".join(pieces)
    return query[:expands[0].start()] + replacement + query[fm.end():]


def _lookup_field_type(all_databases: dict, db_name: str, coll_name: str, field_name: str):
    """Legge il tipo (o i tipi) osservato per un campo di una collection,
    dallo schema già scoperto — usato solo da _check_join_type_mismatch."""
    try:
        schema = all_databases.get(db_name, {}).get('schema', {})
        field_info = schema.get(coll_name, {}).get('fields', {}).get(field_name, {})
        types = field_info.get('types', [])
        if isinstance(types, list) and types:
            return ', '.join(types)
    except Exception:
        pass
    return None


def _fix_missing_expand_item_wrapper(query: str) -> str:
    """
    Riparazione deterministica (17/09) — a differenza degli altri
    controlli su EXPAND (che segnalano un problema e forzano un altro
    tentativo), qui la correzione è CERTA, non richiede indovinare: per
    ogni destinazione dichiarata da un EXPAND (TO .destName), se compare
    successivamente come .destName.X dove X NON è "item" né "position",
    manca il livello fisso "item" del wrapper (JCOConstants.java,
    ITEM_FIELD_NAME — vedi anche _check_undeclared_expand_reference sopra
    per il caso complementare, destinazione mai dichiarata). Il percorso
    corretto per accedere a un sottocampo dell'elemento espanso è SEMPRE
    .destName.item.X — non .destName.X.

    Osservato dal vivo: con "item" scelto sia come nome di destinazione
    sia essendo la parola fissa del motore, il modello ha scritto
    .c.item.product_id invece di .c.item.item.product_id — probabilmente
    perché il doppio "item" consecutivo sembra un errore di battitura da
    evitare, anche dopo aver letto la regola che lo richiede esplicitamente.

    Il regex usa un lookbehind negativo (non preceduto da .destName) per
    non ri-applicarsi al proprio stesso inserimento su match successivi
    nella stessa stringa — senza quello, ".destName.item.X" già corretto
    veniva riletto come "ancora mancante" e diventava
    ".destName.item.item.X", un baco trovato testando questa stessa
    funzione prima di integrarla.
    """
    declared = set(re.findall(r'UNPACK\s+.+?\s+ARRAY\s+\.\S+\s+TO\s+\.(\w+)', query, re.IGNORECASE))
    if not declared:
        return query
    for dest in declared:
        pattern = re.compile(rf'(?<!\.{re.escape(dest)})\.{re.escape(dest)}\.(?!item\b)(?!position\b)(\w+)')
        query = pattern.sub(rf'.{dest}.item.\1', query)
    return query


def _remove_pointless_keep_others(query: str) -> str:
    """
    Riparazione deterministica (18/09, generalizzata lo stesso giorno):
    un FILTER con condizione semplice (nessun GENERATE) e KEEP OTHERS
    presente non ha mai senso, A PRESCINDERE da cosa viene dopo — non
    solo prima di un SAVE (ambito della prima versione di questa
    funzione, poi rivelatosi troppo ristretto: osservato dal vivo lo
    stesso identico problema anche con un FILTER che mostra il
    risultato direttamente, senza nessun SAVE dopo). Il ragionamento è
    generale: se non c'è GENERATE, l'UNICO effetto del FILTER è
    decidere quali documenti passano — con KEEP OTHERS passano tutti
    comunque, rendendo la condizione scritta completamente priva di
    effetto. Non esiste un caso legittimo per questa combinazione.

    Non tocca un FILTER con GENERATE (lì KEEP OTHERS ha un senso reale:
    trasforma/aggiunge un campo a tutti i documenti, mantenendo anche
    quelli che non soddisfano la condizione — es. un flag "urgente" su
    ogni ordine, non solo un sottoinsieme).
    """
    pattern = re.compile(
        r'FILTER\s+(CASE|CASES)\s+WHERE\s+([^;]+?)\s+KEEP\s+OTHERS\s*;',
        re.IGNORECASE
    )

    def replacer(m):
        case_kw, condition = m.groups()
        if 'GENERATE' in condition.upper():
            return m.group(0)
        return f"FILTER {case_kw} WHERE {condition};"

    return pattern.sub(replacer, query)


def _fix_missing_semicolon_before_save(query: str) -> str:
    """
    Riparazione deterministica (18/09) — osservato dal vivo, ripetuto
    anche dopo l'introduzione di _remove_keep_others_before_save sopra:
    un FILTER CASE WHERE la cui condizione è seguita DIRETTAMENTE da
    SAVE AS/SAVE TO FILE, senza il punto e virgola che dovrebbe
    terminare il FILTER, non è sintassi valida. Sospetto sulla causa:
    un'abitudine residua del modello a scrivere il punto e virgola
    subito dopo KEEP OTHERS — togliendo KEEP OTHERS (per la riparazione
    sopra, o di sua iniziativa) sembra portarsi via anche quello.
    Inserisce il punto e virgola mancante subito prima di SAVE. Gestisce
    anche il caso in cui KEEP OTHERS sia presente ma il punto e virgola
    manchi comunque (non solo il caso senza KEEP OTHERS osservato per
    primo).
    """
    pattern = re.compile(
        r'(FILTER\s+(?:CASE|CASES)\s+WHERE\s+[^;]+?)\s+(SAVE\s+(?:AS|TO\s+FILE))',
        re.IGNORECASE
    )
    return pattern.sub(r'\1;\n\2', query)


def _fix_lowercase_boolean(query: str) -> str:
    """
    Riparazione deterministica (18/09) — su un errore trovato testando
    OR su campo array+diretto: JCoQL+ definisce il token booleano
    letteralmente come 'TRUE' | 'FALSE' (verificato contro il parser
    ufficiale) — un valore minuscolo true/false in un confronto non
    corrisponde a quel token, viene letto come un identificativo
    generico, e produce un errore di sintassi criptico ("expecting LP",
    perché il parser prova a interpretarlo come l'inizio di una chiamata
    a funzione). La correzione è certa e univoca — non richiede un altro
    tentativo di generazione.

    Non tocca un valore stringa vero (es. .campo = 'true') — il
    lookbehind/lookahead negativo sugli apici esclude quel caso, così
    come non tocca un'occorrenza dentro un identificativo più lungo
    (es. .true_value) grazie ai confini di parola (\\b).
    """
    pattern = re.compile(r"(?<!['\"])\b(true|false)\b(?!['\"])", re.IGNORECASE)
    return pattern.sub(lambda m: m.group(1).upper(), query)


def _fix_arithmetic_in_generate(query: str) -> str:
    """
    Riparazione deterministica (18/09) — su una regola già esistente nel
    prompt (vedi REGOLA CRITICA su GENERATE/BUILD) che non si è
    dimostrata affidabile da sola: il valore di un campo dentro
    GENERATE ADD FIELDS/BUILD può essere SOLO un riferimento a campo, un
    valore letterale, o una chiamata a funzione — MAI un'espressione
    aritmetica diretta (verificato contro il parser ufficiale: perfino
    una sottrazione o moltiplicazione singola, senza nulla attorno,
    produce un errore di sintassi). Né gli operatori diretti né funzioni
    candidate come MULTIPLY/DIVIDE risolvono aritmetica a runtime
    (verificato dal vivo: 0 documenti, fallimento silenzioso, stesso
    segnale già visto con SIZE per il conteggio di array) — è un limite
    del linguaggio, non solo di sintassi.

    Quando trova un valore contenente un operatore aritmetico (+, -, *,
    /) fuori da una stringa tra apici, lo sostituisce con il PRIMO
    riferimento a campo (.qualcosa) trovato in quell'espressione — non
    un calcolo, ma un dato reale e valido invece di un errore di
    sintassi, in linea con quanto la regola nel prompt già suggerisce
    come ripiego.

    Scansiona carattere per carattere (non un unico regex) per separare
    i campi sulle virgole di primo livello, gestendo correttamente le
    parentesi annidate (es. ".price - (.price * .discount / 100)") senza
    il rischio di blocco di un pattern regex complesso.

    Limite noto: assume che il blocco GENERATE non contenga a sua volta
    parentesi graffe annidate (un sotto-oggetto costruito con BUILD
    dentro un altro campo) — un caso raro, non gestito qui.
    """
    block_pattern = re.compile(
        r'(GENERATE\s+(?:ADD\s+FIELDS|BUILD)\s*)\{([^{}]*)\}',
        re.IGNORECASE | re.DOTALL
    )

    def fix_block(m):
        prefix, inner = m.group(1), m.group(2)
        parts = []
        depth = 0
        current = []
        for ch in inner:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            if ch == ',' and depth == 0:
                parts.append(''.join(current))
                current = []
            else:
                current.append(ch)
        parts.append(''.join(current))

        fixed_parts = []
        for part in parts:
            if ':' not in part:
                fixed_parts.append(part)
                continue
            key, _, value = part.partition(':')
            stripped_value = value.strip()
            is_fully_quoted = (
                (stripped_value.startswith("'") and stripped_value.endswith("'"))
                or (stripped_value.startswith('"') and stripped_value.endswith('"'))
            )
            if re.search(r'[+\-*/]', stripped_value) and not is_fully_quoted:
                field_match = re.search(r'\.\w+(?:\.\w+)*', stripped_value)
                fixed_parts.append(f"{key}: {field_match.group(0)}" if field_match else part)
            else:
                fixed_parts.append(part)

        return prefix + '{' + ','.join(fixed_parts) + '}'

    return block_pattern.sub(fix_block, query)


def _add_remove_duplicates_if_same_source(query: str) -> str:
    """
    Riparazione deterministica (19/09) — su un errore reale di esecuzione
    (MongoDB E11000 duplicate key), non solo di sintassi: un MERGE
    COLLECTIONS tra due collezioni che derivano ENTRAMBE (tramite GET
    COLLECTION prima del rispettivo SAVE AS) dalla STESSA collezione
    originale può avere documenti in comune (es. due FILTER diversi
    sulla stessa collection, dove un documento soddisfa entrambe le
    condizioni) — senza REMOVE DUPLICATES, il tentativo di scrivere due
    volte lo stesso _id fa fallire l'intera query in esecuzione, non solo
    in validazione. La regola nel prompt lo spiega, ma non si è
    dimostrata affidabile da sola (osservato dal vivo: MERGE generato
    correttamente ma senza REMOVE DUPLICATES, nonostante la regola).

    Aggiunge REMOVE DUPLICATES SOLO quando riesce a verificare che
    entrambe le collezioni derivano dalla stessa origine — REMOVE
    DUPLICATES è innocuo quando non serve (la nostra stessa regola lo
    dice: se non ci sono duplicati, non toglie nulla), ma non lo si
    aggiunge comunque a ogni MERGE per restare fedeli a cosa la query
    dichiara di fare, non solo per sicurezza.

    Non tocca un MERGE che ha già REMOVE DUPLICATES, né uno le cui
    collezioni derivano da origini diverse o non tracciabili (es. hotels
    e restaurants, o nomi non passati per un GET COLLECTION rintracciabile
    nella stessa query).
    """
    merge_pattern = re.compile(r'MERGE\s+COLLECTIONS\s+([^;]+?)(REMOVE\s+DUPLICATES\s*)?;', re.IGNORECASE)

    def replacer(m):
        colls_text, has_remove = m.group(1), m.group(2)
        if has_remove:
            return m.group(0)

        coll_names = [c.strip().split('@')[0] for c in colls_text.split(',')]
        origins = []
        for name in coll_names:
            save_pattern = re.compile(rf'SAVE\s+AS\s+{re.escape(name)}\s*@', re.IGNORECASE)
            sm = save_pattern.search(query)
            if not sm:
                origins.append(None)
                continue
            preceding = query[:sm.start()]
            get_matches = list(re.finditer(r'GET\s+COLLECTION\s+(\w+)\s*;', preceding, re.IGNORECASE))
            origins.append(get_matches[-1].group(1) if get_matches else None)

        if len(set(origins)) == 1 and origins[0] is not None:
            return f"MERGE COLLECTIONS {colls_text.strip()} REMOVE DUPLICATES;"
        return m.group(0)

    return merge_pattern.sub(replacer, query)


def _reorder_expand_before_join(query: str) -> str:
    """
    Riparazione deterministica (17/09) — su richiesta esplicita di NON
    indovinare/hardcodare un calcolo di quanti livelli di annidamento
    aggiungere: invece di correggere il percorso dopo un EXPAND fatto
    PRIMA di un JOIN che riusa la stessa collection (che richiederebbe
    calcolare un livello di annidamento in più per ogni JOIN successivo —
    fragile, e osservato dal vivo produrre lo stesso errore più volte
    nonostante un avviso esplicito nel prompt), RISCRIVE la query
    scambiando l'ordine in JOIN-poi-EXPAND — la struttura che sappiamo
    per certo essere sempre corretta con un solo livello di annidamento,
    verificata più volte in questa sessione (esempio 29 del corpus RAG,
    e la query salvata dall'utente).

    Riconosce il pattern:
        GET COLLECTION X[@db];
        EXPAND UNPACK TRUE ARRAY .campo TO .dest;
        SAVE AS chaintempN@db2;
        JOIN OF COLLECTIONS chaintempN@db2 AS alias1, altra@db3 AS alias2
        CASE WHERE condizione;
    e lo riscrive in:
        JOIN OF COLLECTIONS X@db AS alias1, altra@db3 AS alias2
        CASE WHERE condizione;
        SAVE AS chaintempN@db2;
        GET COLLECTION chaintempN;
        EXPAND UNPACK TRUE ARRAY .alias1.campo TO .dest;
    (gestisce chaintempN sia come primo sia come secondo lato del JOIN).
    Il resto della query — qualunque cosa venga dopo, incluso un
    eventuale JOIN successivo che referenzia .dest — non viene toccato:
    con dest di nuovo in cima al documento, quei riferimenti sono già
    corretti così come sono, non serve calcolare nulla su di loro.

    Non tocca nulla se il pattern non è presente per intero (es. l'ordine
    è già corretto, non c'è nessun JOIN successivo che riusa la
    collection espansa — come nell'esempio 27, EXPAND multiplo senza
    JOIN dopo, dove questo riordino non ha senso).
    """
    pattern = re.compile(
        r'GET\s+COLLECTION\s+(\w+)(?:@(\w+))?\s*;\s*'
        r'EXPAND\s+UNPACK\s+TRUE\s+ARRAY\s+\.(\w+)\s+TO\s+\.(\w+)\s*;\s*'
        r'SAVE\s+AS\s+(chaintemp\w+)@(\w+)\s*;\s*'
        r'JOIN\s+OF\s+COLLECTIONS\s+'
        r'(?:'
        r'\5@\6\s+AS\s+(\w+)\s*,\s*(\w+)@(\w+)\s+AS\s+(\w+)'
        r'|'
        r'(\w+)@(\w+)\s+AS\s+(\w+)\s*,\s*\5@\6\s+AS\s+(\w+)'
        r')\s*'
        r'(CASE|CASES)\s+WHERE\s+(.+?);',
        re.IGNORECASE | re.DOTALL
    )
    m = pattern.search(query)
    if not m:
        return query

    src_coll, src_db, array_field, dest_name, chaintemp_name, chaintemp_db = m.group(1, 2, 3, 4, 5, 6)
    if m.group(7):
        expand_alias, other_coll, other_db, other_alias = m.group(7, 8, 9, 10)
    else:
        other_coll, other_db, other_alias, expand_alias = m.group(11, 12, 13, 14)
    case_kw, condition = m.group(15, 16)

    if not src_db:
        use_db_before = list(re.finditer(
            r'USE\s+DB\s+(\w+)\s+ON\s+DEFAULT\s+SERVER', query[:m.start()], re.IGNORECASE
        ))
        src_db = use_db_before[-1].group(1) if use_db_before else chaintemp_db

    replacement = (
        f"JOIN OF COLLECTIONS {src_coll}@{src_db} AS {expand_alias}, {other_coll}@{other_db} AS {other_alias}\n"
        f"{case_kw} WHERE {condition};\n"
        f"SAVE AS {chaintemp_name}@{chaintemp_db};\n"
        f"GET COLLECTION {chaintemp_name};\n"
        f"EXPAND UNPACK TRUE ARRAY .{expand_alias}.{array_field} TO .{dest_name};"
    )
    return query[:m.start()] + replacement + query[m.end():]


def _collect_all_ids(obj, ids_found: set):
    """Raccoglie tutti i valori _id presenti ovunque in un documento —
    usato solo da _find_unresolved_id_references sotto, per sapere quali
    riferimenti risultano già risolti da qualche parte nello stesso
    documento (un JOIN riuscito AGGIUNGE il lato risolto accanto
    all'originale, non lo SOSTITUISCE — quindi il riferimento grezzo
    resta comunque presente anche quando è stato risolto correttamente)."""
    if isinstance(obj, dict):
        if '_id' in obj and isinstance(obj['_id'], (str, int)):
            ids_found.add(obj['_id'])
        for v in obj.values():
            _collect_all_ids(v, ids_found)
    elif isinstance(obj, list):
        for item in obj:
            _collect_all_ids(item, ids_found)


def _find_unresolved_id_references(documents: list, max_examples: int = 3):
    """
    Trasparenza sul risultato (17/09), non un controllo che blocca o
    corregge nulla — su richiesta esplicita di non indovinare/hardcodare
    quale JOIN mancherebbe: guarda i DOCUMENTI VERI del risultato (non il
    testo della query) e segnala se contengono un riferimento non
    risolto, usando solo una convenzione di denominazione universale
    (un campo che finisce per "_id", diverso da "_id" stesso) — non un
    elenco di nomi scritto per questo caso specifico.

    Ambito ristretto alla firma del wrapper creato da EXPAND (un dict con
    ESATTAMENTE "item" e "position" come chiavi, dove "item" è a sua
    volta un dict) — un campo _id grezzo lì dentro è quasi sempre un
    riferimento mai risolto con un JOIN successivo.

    FIX (17/09, stesso giorno): un JOIN riuscito AGGIUNGE il lato
    risolto accanto all'originale, non SOSTITUISCE il riferimento grezzo
    — quindi anche dopo un JOIN corretto con products, .item.product_id
    resta comunque presente nel documento accanto al prodotto vero
    (osservato dal vivo: falso positivo su una query in realtà completa
    e corretta, 6 documenti giusti). Ora, prima di segnalare un
    riferimento, si controlla se il SUO VALORE coincide con un _id
    presente DA QUALCHE PARTE nello stesso documento (_collect_all_ids)
    — se sì, è già stato risolto altrove, non viene segnalato.

    Non impedisce l'esecuzione, non modifica il risultato — aggiunge solo
    un'informazione in più nella risposta, perché un utente che non sa a
    priori quanti documenti aspettarsi possa comunque accorgersi che il
    risultato contiene riferimenti grezzi mai risolti, invece di
    scoprirlo per caso o non scoprirlo affatto.
    """
    found = []

    def scan(obj, path, candidates):
        if isinstance(obj, dict):
            if 'item' in obj and 'position' in obj and isinstance(obj['item'], dict):
                inner = obj['item']
                for k, v in inner.items():
                    if isinstance(v, (str, int)) and re.match(r'^[a-zA-Z]\w*_id$', k, re.IGNORECASE) and k.lower() != '_id':
                        candidates.append((f'{path}.item.{k}' if path else f'item.{k}', v))
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    scan(v, f'{path}.{k}' if path else k, candidates)
        elif isinstance(obj, list):
            for item in obj:
                scan(item, path, candidates)

    for doc in documents:
        if len(found) >= max_examples:
            break
        resolved_ids = set()
        _collect_all_ids(doc, resolved_ids)
        candidates = []
        scan(doc, '', candidates)
        for path, val in candidates:
            if val not in resolved_ids:
                found.append((path, val))
                if len(found) >= max_examples:
                    break
    return found


def _check_undeclared_expand_reference(query: str, current_schema: dict):
    """
    Controllo semantico (16/08): rileva un riferimento ".nome.item" (il
    pattern che indica un elemento prodotto da EXPAND — "item" è la
    chiave fissa del motore, vedi JCOConstants.java) per un "nome" che
    non è MAI stato dichiarato come destinazione di un EXPAND UNPACK ...
    TO .nome nella stessa query. Osservato dal vivo: l'LLM ha scritto
    ".actor.item = 'Claudio Bisio'" senza mai scrivere l'EXPAND
    corrispondente — probabilmente confuso dal fatto che negli esempi
    RAG "actor" compare come nome di DESTINAZIONE scelto (TO .actor), non
    come nome di campo reale (che è "cast") — e ha saltato il passaggio
    di EXPAND vero e proprio, usando il nome di destinazione come se
    fosse già disponibile da solo.

    A differenza delle altre riparazioni, qui NON si prova a indovinare
    quale campo array l'utente intendesse (un confronto testuale tra
    "actor" e "cast" non aiuterebbe, non si somigliano) — si segnala
    l'incongruenza con l'elenco dei campi array VERI disponibili, e si
    forza un altro tentativo di generazione con quell'informazione
    concreta, stessa filosofia del controllo sul disallineamento di tipo.
    """
    coll_match = re.search(r'GET\s+COLLECTION\s+(\w+)\s*;', query, re.IGNORECASE)
    if not coll_match:
        return None
    collection_name = coll_match.group(1)

    coll_schema = (current_schema or {}).get(collection_name, {})
    coll_fields = coll_schema.get('fields', {}) if isinstance(coll_schema, dict) else {}
    array_fields = sorted({
        f for f, info in coll_fields.items()
        if '.' not in f and isinstance(info, dict) and 'array' in info.get('types', [])
    })

    declared = set(re.findall(r'UNPACK\s+.+?\s+ARRAY\s+\.\S+\s+TO\s+\.(\w+)', query, re.IGNORECASE))
    # FIX (16/08, falso positivo trovato subito dopo aver scritto il
    # controllo): un JOIN concatenato tipo ".c.item.item.product_id" (c è
    # l'alias del JOIN, non una destinazione EXPAND) veniva letto male —
    # il regex sotto, non "overlapping", si fermava al primo ".c.item" e
    # scambiava l'alias "c" per un nome mai dichiarato. Gli alias di
    # JOIN/MERGE (dichiarati con "AS nome") vanno esclusi dal conteggio:
    # non sono mai destinazioni di EXPAND, quindi comparire dopo un punto
    # seguito da ".item" è normale per loro (fanno da preambolo al vero
    # percorso), non un errore.
    join_aliases = set(re.findall(r'\bAS\s+(\w+)\b', query, re.IGNORECASE))
    referenced = set(re.findall(r'\.(\w+)\.item\b', query))
    undeclared = referenced - declared - join_aliases

    if not undeclared:
        return None

    hint = ', '.join(array_fields) if array_fields else "nessun campo array trovato nello schema"
    names = ', '.join(sorted(undeclared))
    return (
        f"Nella query usi '.{names}.item' ma non hai mai scritto un EXPAND che dichiari "
        f"'{names}' come destinazione (TO .{names}) — quel nome non esiste da nessuna parte "
        f"finché non lo crei tu con EXPAND UNPACK TRUE ARRAY .campoReale TO .{names};. "
        f"I campi array realmente disponibili in {collection_name} sono: {hint}. "
        f"Trova tra questi quello giusto per la richiesta e aggiungi l'EXPAND mancante prima del FILTER."
    )


def _sample_field_values(all_databases: dict, db_name: str, coll_name: str, field_name: str, limit: int = 30):
    """Legge un campione di valori non-null di un campo, direttamente da
    MongoDB — usato solo da _check_join_key_data_overlap sotto."""
    info = all_databases.get(db_name)
    if not info:
        return []
    client = info["client"]
    mongo_db = client[info["database_name"]]
    coll = mongo_db[coll_name]
    cursor = coll.find({field_name: {"$ne": None}}, {field_name: 1}).limit(limit)
    return [doc[field_name] for doc in cursor if field_name in doc and doc[field_name] is not None]


def _fetch_matching_values(all_databases: dict, db_name: str, coll_name: str, field_name: str, candidate_values: list):
    """Controlla quanti dei candidate_values esistono davvero come valore
    di field_name in coll_name — una singola query $in su MongoDB."""
    if not candidate_values:
        return []
    info = all_databases.get(db_name)
    if not info:
        return []
    client = info["client"]
    mongo_db = client[info["database_name"]]
    coll = mongo_db[coll_name]
    cursor = coll.find({field_name: {"$in": candidate_values}}, {field_name: 1}).limit(5)
    return [doc[field_name] for doc in cursor if field_name in doc]


def _trace_chaintemp_origin(query: str, chaintemp_name: str, _depth: int = 0):
    """
    Prova a risalire a quale collection REALE (non un'altra chaintemp) ha
    originato una collection chaintempN — cerca l'ultima GET COLLECTION
    prima del SAVE AS che crea chaintemp_name. Usato sia da
    _check_join_key_data_overlap sia da _check_join_type_mismatch, per
    poter verificare/controllare anche campi di una chaintemp che non
    sono stati toccati da un EXPAND/GENERATE nel frattempo (un EXPAND
    aggiunge un campo nuovo, non modifica quelli preesistenti — quindi
    per un campo semplice come "user_id", i valori/il tipo di chaintempN
    sono sempre gli stessi della collection di origine).

    RICORSIVA (17/09, prima si fermava al primo livello): se la GET
    COLLECTION trovata è a sua volta un'altra chaintemp (es. chaintemp2
    che deriva da chaintemp1, non direttamente da una collection reale —
    osservato dal vivo: un passaggio "GET COLLECTION orders; SAVE AS
    chaintemp1;" senza fare nulla in mezzo, prima di espandere solo
    chaintemp1 in chaintemp2), risale ricorsivamente attraverso quel
    livello invece di arrendersi — altrimenti il controllo di tipo non
    scattava proprio in questo genere di catena più lunga del solito.
    _depth con un limite di 5 previene una ricorsione infinita su query
    malformate o circolari (mai un caso reale, solo una rete di sicurezza).

    Limite noto, non risolto qui: se un passaggio intermedio usa GENERATE
    per rimuovere o ridefinire il campo che si sta cercando, la risalita
    lo darebbe comunque per invariato — un caso raro (di solito non si
    rinomina un campo su cui si sta per fare JOIN), non gestito.
    """
    if _depth >= 5:
        return None, None
    save_as_pattern = re.compile(rf'SAVE\s+AS\s+{re.escape(chaintemp_name)}\s*@\s*(\w+)', re.IGNORECASE)
    m = save_as_pattern.search(query)
    if not m:
        return None, None
    preceding_text = query[:m.start()]
    get_coll_matches = list(re.finditer(r'GET\s+COLLECTION\s+(\w+)\s*;', preceding_text, re.IGNORECASE))
    if not get_coll_matches:
        return None, None
    last_get = get_coll_matches[-1]
    origin_coll = last_get.group(1)
    if origin_coll.lower().startswith('chaintemp'):
        return _trace_chaintemp_origin(query, origin_coll, _depth + 1)
    use_db_matches = list(re.finditer(
        r'USE\s+DB\s+(\w+)\s+ON\s+DEFAULT\s+SERVER', preceding_text[:last_get.start()], re.IGNORECASE
    ))
    origin_db = use_db_matches[-1].group(1) if use_db_matches else None
    return origin_coll, origin_db


def _check_join_key_data_overlap(query: str, all_databases: dict):
    """
    Controllo empirico (17/09) — deliberatamente SENZA nessun giudizio sul
    NOME dei campi coinvolti (su richiesta esplicita di evitare
    hardcoding, stessa richiesta già fatta per _check_join_type_mismatch):
    per un JOIN che confronta .X.campoA = .Y.campoB, verifica interrogando
    MongoDB — non lo schema, i dati veri — se esiste ALMENO una
    corrispondenza reale tra un campione di valori di campoA e i valori
    di campoB. Se NESSUNO dei valori campionati da un lato compare mai
    nell'altro, è un segnale forte che quella non sia la chiave di join
    giusta, a prescindere da come si chiamano i due campi.

    Si applica SOLO quando i due campi hanno NOMI DIVERSI — il caso
    "stesso nome, tipo diverso" è già coperto da _check_join_type_mismatch
    sopra; qui si copre il caso complementare, altrettanto reale: stesso
    tipo (es. entrambi stringa), nome diverso, ma valori che non si
    sovrappongono mai (osservato dal vivo: .a.user_id confrontato con
    .b.name — "user_005" non ha nessuna relazione con "User 5", ma sono
    comunque due stringhe, quindi il controllo di tipo non lo vedeva).

    Quando un lato è una collection chaintempN (join concatenati), prova
    prima a risalire alla collection reale che l'ha originata (vedi
    _trace_chaintemp_origin) e verifica su QUELLA — chaintempN non esiste
    ancora fisicamente su MongoDB in questa fase (viene creata solo
    quando la query viene poi eseguita davvero, non durante la
    generazione), quindi non è mai interrogabile direttamente qui. Se la
    risalita non è possibile (es. l'origine è un'altra chaintemp, o il
    campo stesso è quello creato dall'EXPAND — questi hanno sempre un
    punto nel nome, .item.item..., già esclusi sotto), quel lato del JOIN
    viene saltato invece di dare un falso allarme.

    Se la verifica empirica stessa fallisce per qualunque motivo
    (connessione, campo non esistente, ecc.) non blocca la generazione:
    non è pensata per essere l'unica rete di sicurezza, solo un controllo
    in più quando può essere eseguito con successo.
    """
    join_pattern = re.compile(
        r'JOIN OF COLLECTIONS\s+(\w+)@(\w+)\s+AS\s+(\w+)\s*,\s*(\w+)@(\w+)\s+AS\s+(\w+).*?'
        r'WHERE\s+\.(\w+)\.([\w.]+)\s*=\s*\.(\w+)\.([\w.]+)',
        re.IGNORECASE | re.DOTALL
    )
    for m in join_pattern.finditer(query):
        coll1, db1, alias1, coll2, db2, alias2, cond_alias1, field1, cond_alias2, field2 = m.groups()
        if field1 == field2 or '.' in field1 or '.' in field2:
            continue

        alias_to_coll_db = {alias1: (coll1, db1), alias2: (coll2, db2)}
        if cond_alias1 not in alias_to_coll_db or cond_alias2 not in alias_to_coll_db:
            continue
        coll_a, db_a = alias_to_coll_db[cond_alias1]
        coll_b, db_b = alias_to_coll_db[cond_alias2]

        # Per ciascun lato che è una chaintemp, risali alla collection
        # reale di origine per poterla interrogare — chaintempN stessa
        # non esiste ancora in questa fase (creata solo all'esecuzione).
        query_coll_a, query_db_a = coll_a, db_a
        if coll_a.lower().startswith('chaintemp'):
            query_coll_a, query_db_a = _trace_chaintemp_origin(query, coll_a)
        query_coll_b, query_db_b = coll_b, db_b
        if coll_b.lower().startswith('chaintemp'):
            query_coll_b, query_db_b = _trace_chaintemp_origin(query, coll_b)

        if not query_coll_a or not query_coll_b:
            continue

        try:
            sample_a = _sample_field_values(all_databases, query_db_a, query_coll_a, field1, limit=30)
            overlap = _fetch_matching_values(all_databases, query_db_b, query_coll_b, field2, sample_a)
        except Exception:
            continue

        if sample_a and not overlap:
            example_vals = ", ".join(str(v) for v in sample_a[:3])
            return (
                f"Nel JOIN tra {coll_a}@{db_a} e {coll_b}@{db_b}, la condizione confronta "
                f".{cond_alias1}.{field1} con .{cond_alias2}.{field2} — ho verificato "
                f"direttamente su MongoDB (non solo lo schema) e NESSUNO dei valori "
                f"campionati da {coll_a}.{field1} (es: {example_vals}) risulta presente in "
                f"{coll_b}.{field2}, su un campione di {len(sample_a)} documenti. "
                f"Probabilmente non è la chiave di join corretta, anche se il tipo coincide. "
                f"Guarda gli altri campi disponibili in {coll_b} (con i loro tipi ed esempi, "
                f"nello schema sopra) per trovarne uno i cui valori corrispondano davvero a "
                f".{cond_alias1}.{field1}."
            )
    return None


def _check_join_type_mismatch(query: str, all_databases: dict):
    """
    Controllo semantico (15/08, non un pattern fisso su un nome di campo —
    su richiesta esplicita di evitare hardcoding): rileva un JOIN OF
    COLLECTIONS che confronta lo STESSO nome di campo su entrambi i lati
    (es. .alias1.user_id = .alias2.user_id) quando le due collezioni REALI
    coinvolte (non una "chaintempN" intermedia, di cui non conosciamo lo
    schema) hanno TIPI DIVERSI per quel campo secondo lo schema scoperto —
    segnale che, a prescindere da quale sia il nome del campo, i due lati
    non rappresentano la stessa cosa (osservato due volte di fila su
    .user_id: intero in una collection, stringa identificativa nell'altra).
    Ritorna un messaggio di avviso con i tipi/collection reali coinvolti se
    trova un'incongruenza, altrimenti None — non sceglie lui stesso un
    campo alternativo, si limita a segnalare cosa non torna.
    """
    join_pattern = re.compile(
        r'JOIN OF COLLECTIONS\s+(\w+)@(\w+)\s+AS\s+(\w+)\s*,\s*(\w+)@(\w+)\s+AS\s+(\w+).*?'
        r'WHERE\s+\.(\w+)\.([\w.]+)\s*=\s*\.(\w+)\.([\w.]+)',
        re.IGNORECASE | re.DOTALL
    )
    for m in join_pattern.finditer(query):
        coll1, db1, alias1, coll2, db2, alias2, cond_alias1, field1, cond_alias2, field2 = m.groups()
        if field1 != field2:
            continue
        alias_to_coll_db = {alias1: (coll1, db1), alias2: (coll2, db2)}
        if cond_alias1 not in alias_to_coll_db or cond_alias2 not in alias_to_coll_db:
            continue
        coll_a, db_a = alias_to_coll_db[cond_alias1]
        coll_b, db_b = alias_to_coll_db[cond_alias2]

        # FIX (17/09): prima si saltava del tutto ogni JOIN con una
        # collection chaintempN da un lato (schema sconosciuto) — ma
        # questo lasciava passare senza controllo esattamente il caso dei
        # join concatenati, dove capita più spesso (osservato dal vivo:
        # .a.user_id = .b.user_id con "a" = chaintemp1, mai controllato).
        # Come per _check_join_key_data_overlap sopra, si prova a
        # risalire alla collection reale di origine (_trace_chaintemp_origin)
        # e si guarda lo schema di QUELLA — un EXPAND non cambia il tipo
        # dei campi preesistenti, solo ne aggiunge uno nuovo.
        lookup_coll_a, lookup_db_a = coll_a, db_a
        if coll_a.lower().startswith('chaintemp'):
            lookup_coll_a, lookup_db_a = _trace_chaintemp_origin(query, coll_a)
        lookup_coll_b, lookup_db_b = coll_b, db_b
        if coll_b.lower().startswith('chaintemp'):
            lookup_coll_b, lookup_db_b = _trace_chaintemp_origin(query, coll_b)
        if not lookup_coll_a or not lookup_coll_b:
            continue

        type_a = _lookup_field_type(all_databases, lookup_db_a, lookup_coll_a, field1)
        type_b = _lookup_field_type(all_databases, lookup_db_b, lookup_coll_b, field2)

        # FIX (16/08): il controllo originale confrontava i tipi solo
        # quando il campo esiste su ENTRAMBI i lati — se manca del tutto su
        # uno dei due (osservato: test_db.users non ha nessun campo
        # "user_id", solo "id" — la query generata comunque scriveva
        # .a.user_id = .b.user_id, producendo 0 risultati senza nessun
        # avviso) il controllo non aveva nulla da confrontare e lasciava
        # passare in silenzio. Un campo assente è un segnale ancora più
        # netto di un campo con tipo diverso — va segnalato per primo.
        if type_a is None or type_b is None:
            missing_side = f".{cond_alias1}.{field1} (in {coll_a})" if type_a is None else f".{cond_alias2}.{field2} (in {coll_b})"
            present_side = f".{cond_alias2}.{field2} (tipo: {type_b}, in {coll_b})" if type_a is None else f".{cond_alias1}.{field1} (tipo: {type_a}, in {coll_a})"
            return (
                f"Nel JOIN tra {coll_a}@{db_a} e {coll_b}@{db_b}, la condizione confronta "
                f"{missing_side} con {present_side} — ma {missing_side.split(' (')[0]} non risulta "
                f"esistere affatto nello schema scoperto di quella collection (nomi di campo simili "
                f"non bastano, verifica quello giusto guardando i campi realmente presenti, mostrati "
                f"nello schema sopra)."
            )

        if type_a and type_b and type_a != type_b:
            return (
                f"Nel JOIN tra {coll_a}@{db_a} e {coll_b}@{db_b}, la condizione confronta "
                f".{cond_alias1}.{field1} (tipo: {type_a}, in {coll_a}) con "
                f".{cond_alias2}.{field2} (tipo: {type_b}, in {coll_b}) — tipi diversi, "
                f"probabilmente NON è la chiave di join corretta anche se il nome del campo "
                f"coincide. Guarda gli altri campi disponibili in {coll_a} (con i loro tipi ed "
                f"esempi, nello schema sopra) per trovarne uno il cui tipo/valori siano "
                f"compatibili con .{cond_alias2}.{field2} — spesso, ma non sempre, è _id."
            )
    return None


JCOQL_SYNTAX_FULL = load_file_content('backend/jcoql_syntax_official.txt')
JCOQL_SYNTAX_BASIC = load_file_content('backend/jcoql_syntax_basic_official.txt')
EXTENDED_EXAMPLES = load_file_content('backend/rag_examples_extended.txt')
# Nota (13/08): JCOQL_SYNTAX_FULL è ora la grammatica effettivamente
# iniettata nel prompt (JCoQL.g ufficiale, copia identica — vedi il
# repository separato JcoProjectTeam/JcoQL, quello dedicato al parser,
# diverso da JcoFrameworkCode) — copre tutti i costrutti del linguaggio,
# non solo il sottoinsieme di JCOQL_SYNTAX_BASIC (JCoQLBasic.g ufficiale,
# che ad esempio esclude deliberatamente GET COLLECTION FROM FILE).
# JCOQL_SYNTAX_BASIC resta caricata qui ma non iniettata nel prompt — non
# serve più dato che FULL la contiene (nella sostanza) per intero, tenuta
# solo per compatibilità/eventuali usi futuri.

# Selezione LLM, Parser ed Executor attivi
# Nota sulla mutabilità di queste tre variabili a runtime: ACTIVE_LLM può
# cambiare dopo l'avvio (l'endpoint /api/set_llm sotto fa "global
# ACTIVE_LLM" e la riassegna). ACTIVE_PARSER e ACTIVE_EXECUTOR invece non
# hanno un endpoint equivalente — restano fissate al valore letto da
# variabile d'ambiente al momento dell'avvio per tutta la vita del
# processo; cambiarle richiede riavviare il server con una diversa
# variabile d'ambiente.
ACTIVE_LLM = os.getenv("ACTIVE_LLM", "gemini")
ACTIVE_PARSER = os.getenv("ACTIVE_PARSER", "antlr3_official")
ACTIVE_EXECUTOR = os.getenv("ACTIVE_EXECUTOR", "jco_framework")

# Interruttore di debug: imposta JCOQL_DEBUG=true per riattivare i log diagnostici
# dettagliati (esempi RAG recuperati, riepilogo execution_result). Spento di default.
JCOQL_DEBUG = os.getenv("JCOQL_DEBUG", "false").lower() == "true"

# Istanzia il parser sintattico (singleton di modulo — stessa istanza
# riusata per tutte le richieste, coerente con ACTIVE_PARSER fissato
# all'avvio descritto sopra)
parser = ParserFactory.create_parser(ParserType(ACTIVE_PARSER))

# Configurazione Google Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
# FIX (17/09): la temperatura non era mai impostata — Gemini usava il
# proprio default (non zero), spiegando gran parte della variabilità
# osservata tra una generazione e l'altra per la stessa richiesta (alias
# diversi, ordine dei lati del JOIN invertito, nomi di destinazione EXPAND
# diversi, e in alcuni casi anche una scelta di correttezza diversa — vedi
# caso reale: stessa richiesta, tre query strutturalmente diverse). Stessa
# scelta già fatta per i modelli locali in llm_local.py (temperature=0) —
# qui coerente con quella. model è usato una sola volta in tutto il file
# (riga con model.generate_content, nel loop di generazione), quindi
# impostarlo qui a livello di modello non tocca nessun altro utilizzo.
model = genai.GenerativeModel(
    "gemini-3.1-flash-lite-preview",
    generation_config=genai.GenerationConfig(temperature=0)
)

# Inizializzazione ChromaDB
# Nota: get_collection (non get_or_create_collection) solleva
# un'eccezione se la collection "jcoql_examples" non esiste ancora —
# catturata qui sotto e trasformata in collection=None, quindi l'app
# comunque si avvia. Perché la collection esista è necessario aver
# lanciato almeno una volta backend/database/load_examples.py.
chroma_client = chromadb.PersistentClient(path="./chroma_data")
try:
    collection = chroma_client.get_collection(name="jcoql_examples")
except Exception as e:
    collection = None

# Logging
logger, log_file = setup_logging()
startup_logger = get_startup_logger()
query_logger = get_query_logger()
db_logger = get_db_logger()

startup_logger.info("📦 Caricamento configurazione completato.")

executor = None
GLOBAL_SCHEMA = {}
# Entrambe sono variabili globali di modulo, valorizzate qui solo come
# placeholder — vengono assegnate per davvero dentro startup_event() più
# sotto (con "global executor, GLOBAL_SCHEMA"), non qui.

from bson import ObjectId
from json import JSONEncoder

class MongoDBJSONEncoder(JSONEncoder):
    """Encoder personalizzato per convertire ObjectId e altri tipi MongoDB"""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)  # Converti ObjectId a string
        return super().default(obj)


# ==============================================================================
# FASTAPI APP & MIDDLEWARE
# ==============================================================================
# Nota: json_encoder=MongoDBJSONEncoder qui sotto NON ha alcun effetto.
# FastAPI (0.141.1, verificato) non espone un parametro "json_encoder" nel
# costruttore — la classe FastAPI accetta comunque la chiamata perché
# **extra assorbe silenziosamente qualunque kwargs non riconosciuto,
# senza sollevare errori né fare nulla con esso. MongoDBJSONEncoder,
# definito subito sopra proprio per gestire la serializzazione di
# ObjectId, non viene quindi mai usato dalla serializzazione delle
# risposte FastAPI. Il progetto evita comunque il problema perché ogni
# executor converte _id in stringa manualmente prima di restituire i
# risultati (es. python_translator.py, riga "doc['_id'] = str(doc['_id'])"),
# quindi in pratica ObjectId grezzi non arrivano fin qui — ma se in
# futuro un endpoint restituisse un documento Mongo senza quella
# conversione manuale, questo encoder non lo salverebbe da un errore di
# serializzazione, contrariamente a quanto il codice lascia intendere.
app = FastAPI(title="JCoQL+ Multi-Parser API", json_encoder=MongoDBJSONEncoder)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
# Nota: allow_origins=["*"] insieme a allow_credentials=True è una
# combinazione che i browser rifiutano per le richieste che includono
# credenziali (cookie, header Authorization con withCredentials) — la
# specifica CORS non permette un wildcard quando le credenziali sono
# abilitate. Non causa problemi allo stato attuale perché nessuna
# chiamata del frontend (axios/fetch, verificato nei componenti React)
# imposta withCredentials, quindi non sono mai richieste credenziali
# realmente — ma se in futuro si aggiungesse autenticazione via cookie,
# questa configurazione andrebbe rivista (origine esplicita invece di "*").

class GenerateRequest(BaseModel):
    nl_query: str
    database: str = None
    # Lista completa dei database selezionati in sidebar (non solo il
    # primo/"corrente") — necessaria perché l'LLM possa generare
    # correttamente MERGE/query multi-database con i nomi VERI dei
    # database, invece di indovinarli da quello che ha sottomano (es.
    # scambiando nomi di collection per nomi di database, bug osservato
    # il 14/08 quando questo campo non esisteva ancora).
    databases: List[str] = []
    max_retries: int = 3

class QueryRequest(BaseModel):
    jcoql_query: str = ""
    database_name: Optional[str] = None
    databases: List[str] = ["jcoql_test"]
    join_config: Optional[dict] = None
    # Modalità "database di grandi dimensioni / risultato non necessario"
    # (vedi jco_framework_executor_v2.py: execute_count_only()). Quando True,
    # non viene accodato il SAVE AS automatico usato per rileggere i
    # documenti dal browser: si ottiene solo il conteggio stampato dal
    # motore su stdout, evitando il costo di persistenza su MongoDB isolato
    # come collo di bottiglia su collezioni grandi. Il risultato completo
    # resta comunque ispezionabile a mano su Compass se la query contiene un
    # SAVE AS scritto esplicitamente dall'utente (quello non viene toccato).
    count_only: bool = False

# ==============================================================================
# LIFECYCLE EVENTS
# ==============================================================================
@app.on_event("startup")
async def startup_event():
    global executor, GLOBAL_SCHEMA
    
    startup_logger.info("🔧 Inizializzazione Database Registry...")
    try:
        db_logger.info("📡 Connessione al database 'jcoql_test'...")
        # Connette sempre "jcoql_test" hardcoded, indipendentemente da
        # cosa contiene connected_databases.json — se "jcoql_test" era
        # già salvato lì (caso comune, essendo il database di default),
        # load_databases_from_file() poche righe sotto lo riconnette una
        # seconda volta (add_database sovrascrive senza controllare
        # duplicati). Nessun errore visibile, solo una doppia
        # connessione/schema-discovery ad ogni avvio per questo database.
        db_registry.add_database(
            db_name="jcoql_test",
            mongo_uri="mongodb://localhost:27017",
            database_name="jcoql_test"
        )
        
        GLOBAL_SCHEMA = db_registry.get_current_schema()
        startup_logger.info(f"✅ Database Registry inizializzato con {len(GLOBAL_SCHEMA)} collezioni")
        
        for coll_name, coll_data in GLOBAL_SCHEMA.items():
            if isinstance(coll_data, dict):
                field_count = len(coll_data)
                db_logger.info(f"  📋 Collection: {coll_name} ({field_count} campi)")
                
    except Exception as e:
        startup_logger.error(f"❌ Errore Database Registry: {e}", exc_info=True)
    
    load_databases_from_file(db_registry)

    startup_logger.info("🔧 Inizializzazione Executor...")
    try:
        # Recupera il database corrente impostato nel registry
        current_db = db_registry.get_current_database_name() or "jcoql_test"

        # Questo "executor" globale, creato qui la prima volta, è lo
        # stesso oggetto usato dagli endpoint /api/collections,
        # /api/upload-collection e affini più sotto. Viene poi ricreato
        # anche più avanti (in /api/execute e /api/databases/select)
        # quando il database target cambia — quindi NON resta fissato
        # per sempre al database di questo avvio. Il problema reale di
        # quegli endpoint (vedi commento dettagliato sopra la sezione
        # "GESTIONE COLLEZIONI MONGODB") è un altro: presuppongono un
        # attributo .db che jco_framework_executor_v2.py (l'executor di
        # default) non ha, indipendentemente da quale database sia
        # legato all'istanza corrente.
        executor = ExecutorFactory.create_executor(
            ExecutorType(ACTIVE_EXECUTOR),
            mongo_uri="mongodb://localhost:27017",
            database=current_db
        )
        startup_logger.info(f"✅ Executor '{ACTIVE_EXECUTOR}' inizializzato sul database '{current_db}'")
    except Exception as e:
        startup_logger.error(f"❌ Errore Inizializzazione Executor: {e}", exc_info=True)
        executor = None


@app.on_event("shutdown")
def shutdown():
    # Entrambi i blocchi ingoiano qualunque eccezione senza nemmeno
    # loggarla (a differenza del resto del file, che di solito logga
    # almeno un warning) — se la chiusura delle connessioni fallisce, non
    # se ne ha traccia da nessuna parte.
    try:
        if executor:
            executor.close()
    except Exception as e:
        pass
    
    try:
        db_registry.close_all()
    except Exception as e:
        pass

# ==============================================================================
# ENDPOINT: GENERAZIONE QUERY JCOQL (NL -> JCoQL)
# ==============================================================================
@app.post("/api/generate")
async def generate_query(request: GenerateRequest):
    """
    Riceve un prompt in Linguaggio Naturale e genera una query JCoQL valida
    """
    # "global collection" dichiarata qui, in cima alla funzione: serve per
    # poter riassegnare il riferimento globale alla collection ChromaDB più
    # sotto (auto-guarigione RAG) — deve stare prima di qualunque lettura
    # di "collection" in questa funzione, altrimenti Python solleva
    # SyntaxError ("name used prior to global declaration").
    global collection

    # Nota di concorrenza: db_registry.current_database è uno stato
    # GLOBALE condiviso da tutto il processo (vedi database_registry.py),
    # non uno stato per-richiesta. Impostarlo qui in base a
    # request.database significa che, con più richieste concorrenti su
    # database diversi, una potrebbe leggere/agire sul database impostato
    # da un'altra richiesta arrivata nel frattempo — non c'è isolamento
    # tra richieste su questo stato.
    if request.database:
        db_registry.set_current_database(request.database)   
    
    start_time = time.time()
    
    query_logger.info(f"📝 Query ricevuta: '{request.nl_query}'")
    query_logger.info(f"   Database Attivo: {db_registry.get_current_database_name()}")
    
    # Validazione input vuoto
    if not request.nl_query or not request.nl_query.strip():
        return {
            "jcoql_query": "",
            "is_valid": False,
            "attempts": 0,
            "validation_errors": [{"message": "❌ Query NL vuota!"}],
            "retrieved_examples": [],
            "llm_used": ACTIVE_LLM,
            "parser_used": parser.parser_name
        }
    
    context_str = ""
    retrieved_docs = []
    
    # Recupero contesto RAG
    # FIX (17/09): n_results era 6 — con il corpus cresciuto a 32+ esempi
    # che coprono pattern molto diversi tra loro (JOIN semplice, EXPAND,
    # GROUP, MERGE, filtro array, join concatenati a 3 passaggi...), un
    # pattern specifico e meno comune (es. join concatenati) rischia di
    # restare fuori dai primi 6 se altri esempi più generici sembrano
    # "assomigliare" di più a una richiesta formulata in modo ampio — anche
    # quando la sua descrizione userebbe quasi le stesse parole della
    # richiesta (osservato dal vivo: "ordini con utente e prodotti
    # acquistati" non ha portato l'esempio del join a 3 passaggi, la cui
    # descrizione contiene letteralmente "prodotti acquistati"). Alzato
    # prima a 9, poi RIDOTTO a 7 nello stesso giorno: con 9 il prompt è
    # cresciuto abbastanza da contribuire a esaurire più in fretta la
    # quota gratuita di Gemini (250k token/minuto) durante i test
    # ravvicinati — 7 è un compromesso tra il margine di recupero più
    # ampio e il consumo di quota, non ancora riportato al 6 originale.
    # Per i modelli locali (Llama/Gemma): meno esempi, per tenere il
    # prompt più leggero (vedi il lavoro sul prompt più snello per loro,
    # 19/09) — Gemini resta a 7, invariato.
    RAG_N_RESULTS = 4 if ACTIVE_LLM in ("llama", "gemma") else 7

    if collection:
        try:
            results = collection.query(
                query_texts=[request.nl_query],
                n_results=RAG_N_RESULTS
            )
            retrieved_docs = results['documents'][0] if (results and results.get('documents')) else []
            context_str = "\n\n".join(retrieved_docs)
        except Exception as e:
            # Auto-guarigione (16/08): se load_examples.py viene rilanciato
            # DOPO l'avvio del backend, ricrea la collection ChromaDB con un
            # UUID interno nuovo — il riferimento globale "collection" tenuto
            # qui resta agganciato al vecchio, e ogni query fallisce con
            # "Collection [uuid] does not exist" finché non si riavvia il
            # backend a mano. Osservato dal vivo: una generazione è arrivata
            # a ZERO esempi RAG per questo motivo (incluso proprio quello che
            # avrebbe dato la chiave di join giusta), causando una scelta di
            # campo sbagliata da parte dell'LLM senza nessun esempio a cui
            # appoggiarsi. Un solo tentativo di recupero: riprendere un
            # riferimento fresco alla collection e riprovare la stessa query,
            # prima di arrendersi e procedere senza esempi.
            query_logger.warning(f"⚠️ Errore RAG (primo tentativo): {e}")
            try:
                collection = chroma_client.get_collection(name="jcoql_examples")
                results = collection.query(
                    query_texts=[request.nl_query],
                    n_results=RAG_N_RESULTS
                )
                retrieved_docs = results['documents'][0] if (results and results.get('documents')) else []
                context_str = "\n\n".join(retrieved_docs)
                query_logger.info("✅ Riferimento ChromaDB rinfrescato — RAG recuperato al secondo tentativo")
            except Exception as e2:
                query_logger.warning(f"⚠️ Errore RAG (dopo tentativo di refresh, procedo senza esempi): {e2}")

    # Schema prompt
    def _format_schema_for_prompt(schema: dict, db_name: str) -> str:
        """
        Estratta il 16/08 dal blocco che prima costruiva solo lo schema del
        database corrente — riusata sotto per costruire lo schema COMPLETO
        (campi, tipi, esempi) anche degli altri database selezionati, non
        solo i loro nomi. Prima l'LLM vedeva lo schema vero solo del
        database corrente; per qualunque altro selezionato (es. in un JOIN
        cross-database) doveva indovinare i nomi dei campi, spesso
        assumendo — sbagliando — che fossero uguali a quelli del database
        corrente (osservato dal vivo: un JOIN che confrontava .user_id su
        entrambi i lati, quando il secondo database aveva invece un campo
        "id", mai visibile all'LLM).
        """
        out = f"SCHEMA MONGODB REALE (Database: {db_name}):\n\n"
        for coll_name, coll_data in schema.items():
            out += f"COLLECTION: {coll_name}\n"
            if isinstance(coll_data, dict):
                fields = coll_data.get('fields', {})
                if isinstance(fields, dict):
                    for field_name, field_info in fields.items():
                        if isinstance(field_info, dict):
                            field_type = field_info.get('types', field_info.get('type', 'unknown'))
                            if isinstance(field_type, list):
                                field_type = ', '.join(field_type) if field_type else 'unknown'
                            examples = field_info.get('examples', [])
                        else:
                            field_type = type(field_info).__name__
                            examples = []
                        examples_str = ''
                        if examples:
                            ex_display = [str(e)[:40] for e in examples[:2] if e is not None]
                            if ex_display:
                                examples_str = f" — es: {', '.join(ex_display)}"
                        out += f"  .{field_name} ({field_type}){examples_str}\n"
            out += "\n"
        return out

    current_schema = db_registry.get_current_schema()
    if current_schema:
        schema_prompt_str = _format_schema_for_prompt(current_schema, db_registry.get_current_database_name())
    else:
        schema_prompt_str = f"""SCHEMA MONGODB - Database '{db_registry.get_current_database_name()}'
    Nessuna collezione disponibile in questo database."""

    # Altri database selezionati (oltre a quello corrente/primario sopra) —
    # nomi VERI, presi dalla lista che il frontend manda ora per intero
    # (request.databases), non più solo il primo. Senza questo, l'LLM non
    # ha modo di sapere che esistono altri database oltre a quello
    # corrente, e nel tentativo di generare un MERGE/query multi-database
    # può confondere nomi di collection con nomi di database (bug
    # osservato il 14/08, corretto aggiungendo questa sezione).
    other_databases = [db for db in (request.databases or []) if db and db != db_registry.get_current_database_name()]
    if other_databases:
        other_databases_str = (
            "\nALTRI DATABASE SELEZIONATI DALL'UTENTE (disponibili, oltre a quello sopra) — "
            "schema completo di ciascuno, non solo il nome, per evitare di dover indovinare i "
            "nomi dei campi assumendo (spesso sbagliando) che siano uguali a quelli del database "
            "sopra:\n\n"
        )
        for db_name in other_databases:
            try:
                other_schema = db_registry.databases.get(db_name, {}).get('schema', {})
            except Exception:
                other_schema = {}
            if other_schema:
                other_databases_str += _format_schema_for_prompt(other_schema, db_name)
            else:
                other_databases_str += f"SCHEMA MONGODB REALE (Database: {db_name}): nessuna collezione scoperta.\n\n"
        other_databases_str += (
            "Se l'utente chiede di cercare/unire dati \"su tutti i database selezionati\" o simili, "
            "usa ESATTAMENTE questi nomi (più quello corrente sopra) — non inventare nomi di database, "
            "e non confonderli con nomi di collection. Per un JOIN cross-database, i nomi dei campi "
            "possono essere DIVERSI da un database all'altro anche per la stessa entità (es. \"id\" in "
            "uno, \"user_id\" nell'altro) — guarda gli schemi qui sopra invece di assumere simmetria.\n"
        )
    else:
        other_databases_str = ""

    attempts = 0
    is_valid = False
    current_query = ""
    all_errors = []
    validation_errors_for_frontend = []

    # Repair Loop
    while attempts < request.max_retries and not is_valid:
        attempts += 1
        missing_get_collection_hint = None
        current_db = db_registry.current_database or "nessuno"
        available_collections = []
        # FIX (stesso bug di /api/stats, vedi commento lì): prima si
        # chiamava db_registry.databases[current_db].list_collection_names(),
        # ma quel valore è un dizionario di metadati, non una connessione
        # MongoDB — l'AttributeError veniva ingoiato in silenzio e
        # available_collections restava sempre vuoto. Le collection sono
        # già note dallo schema scoperto alla connessione (le chiavi di
        # get_current_schema()), senza bisogno di richiamare Mongo qui.
        if current_db and current_db in db_registry.databases:
            try:
                available_collections = list(db_registry.get_current_schema().keys())
            except Exception:
                available_collections = []

        collections_str = ", ".join(available_collections) if available_collections else "nessuna"

        prompt = f"""Sei un esperto traduttore Natural Language → JCoQL+.

        📋 CONTESTO DATABASE:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Database Attuale: {current_db}
        Collezioni Disponibili: {collections_str}

        🚨 REGOLA CRITICA #1 - NON AGGIUNGERE FILTRI INDESIDERATI:
        ❌ SE L'UTENTE CHIEDE SOLO DI MOSTRARE I DATI (senza condizioni)
        ❌ NON aggiungere FILTER CASE WHERE automaticamente
        ✅ GENERA SOLO: GET COLLECTION <collection>;
        
        Aggiungi FILTER CASE WHERE SOLO se l'utente specifica una CONDIZIONE:
        • "Dove il campo X è..." → aggiungi FILTER
        • "Con valore > N" → aggiungi FILTER
        • "Che soddisfano..." → aggiungi FILTER
        • "Mostrami i dati" → NO FILTER!

        ESEMPI GENERICI:
        Input: "Mostrami i dati" → Query: GET COLLECTION <collezione>;
        Input: "Dati dove campo = valore" → Query: GET COLLECTION <collezione>; FILTER CASE WHERE .campo = valore KEEP OTHERS;
        Input: "Elementi con numero > 100" → Query: GET COLLECTION <collezione>; FILTER CASE WHERE .numero > 100 KEEP OTHERS;

        🚨 REGOLA CRITICA #2 - SINTASSI ISNOTNULL/ISNULL (corretta il 17/09 — la versione
        precedente di questa regola diceva l'esatto contrario di quello che richiede la
        grammatica, verificato ora contro il parser ufficiale):
        ❌ NON usare: .campo IS NOT NULL           (manca la parola chiave FIELD — errore di sintassi)
        ❌ NON usare: FILTER CASE WHERE .campo IS NOT NULL KEEP OTHERS;   (stesso problema)
        ✅ USA SEMPRE: FILTER CASE WHERE FIELD .campo IS NOT NULL KEEP OTHERS;
        ✅ Per il caso opposto (campo assente/nullo): FILTER CASE WHERE FIELD .campo IS NULL KEEP OTHERS;
        La parola chiave FIELD è obbligatoria subito prima del riferimento al campo, in
        questo caso specifico — non serve invece per un confronto con un valore:
        ✅ FILTER CASE WHERE .campo = 'valore' KEEP OTHERS;   (qui niente FIELD, campo diretto)

        🚨 REGOLA CRITICA #2bis - BOOLEANI IN MAIUSCOLO (scoperta il 18/09, verificato contro
        il parser ufficiale — il token è definito letteralmente come 'TRUE' | 'FALSE'):
        ❌ NON usare: .campo = true          (minuscolo — letto come identificativo generico,
                                               NON come valore booleano, causa un errore di
                                               sintassi criptico: "expecting LP", perché il
                                               parser prova a interpretarlo come l'inizio di
                                               una chiamata a funzione)
        ❌ NON usare: .campo = false
        ✅ USA SEMPRE: .campo = TRUE
        ✅ USA SEMPRE: .campo = FALSE
        A differenza di quasi tutti i linguaggi di programmazione (dove true/false sono
        minuscoli), in JCoQL+ i valori booleani letterali vanno SEMPRE scritti in MAIUSCOLO in
        un confronto — non confonderlo con le parole chiave TRUE di UNPACK TRUE/PARTITION TRUE,
        che sono già corrette così, è lo stesso identico token riusato in più punti.

        🔧 REGOLA CRITICA #3 - ATTRIBUTI NESTED (MOLTO IMPORTANTE):
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        MongoDB supporta strutture annidate. I campi nello schema possono avere più livelli.
        
        COME RICONOSCERE CAMPI ANNIDATI:
        • Se vedi ".document.field" nello schema → è un campo annidato
        • Se vedi ".outer.middle.inner" → è profondamente annidato
        • Se vedi ".field" (senza punti) → è un campo root
        
        REGOLA ASSOLUTA:
        Usa SEMPRE il percorso COMPLETO esattamente come mostrato nello schema.
        NON inventare percorsi accorciati.
        
        COME FARE:
        1. L'utente dice: "Filtra per [proprietà]"
        2. Cerchi [proprietà] nello SCHEMA MONGODB sotto
        3. Leggi il percorso ESATTO mostrato nello schema (con tutti i punti)
        4. Usa quel percorso nel filtro
        
        SCHEMA MONGODB REALE (Database: {db_registry.get_current_database_name()}):
{schema_prompt_str}
{other_databases_str}

        🔧 REGOLA CRITICA #4 - COMANDI AVANZATI (JOIN, GROUP, EXPAND, MERGE, INTERSECT, SUBTRACT, SAVE AS):
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Oltre a GET COLLECTION + FILTER, JCoQL+ supporta questi comandi. Usali SOLO quando la
        richiesta dell'utente lo richiede esplicitamente - altrimenti resta sempre sul pattern
        standard GET COLLECTION + FILTER.

        • JOIN — l'utente chiede di "unire"/"collegare"/"incrociare" due collezioni in base a un
          campo comune:
          JOIN OF COLLECTIONS collezione1 AS alias1, collezione2 AS alias2
          CASE WHERE .alias1.campo = .alias2.campo;
          La condizione di uguaglianza va SEMPRE in CASE WHERE, MAI in ON (ON è riservato a
          ON GEOMETRY per casi spaziali). Nel risultato i campi sono raggiungibili come
          .alias1.campo e .alias2.campo.
          🚨 IMPORTANTE: NON aggiungere MAI "KEEP OTHERS" alla fine di un JOIN, a meno che
          l'utente non lo chieda esplicitamente. Su un JOIN, "KEEP OTHERS" mantiene anche le
          coppie che NON soddisfano la condizione di uguaglianza, trasformando il join in un
          prodotto cartesiano completo (ogni documento della prima collezione abbinato a ogni
          documento della seconda) invece di un vero collegamento filtrato. Il JOIN termina
          con il solo punto e virgola dopo la condizione, senza KEEP OTHERS.

        • GROUP — l'utente chiede di "raggruppare"/"aggregare per":
          GET COLLECTION collezione;
          GROUP PARTITION TRUE BY .campo INTO .risultato;
          Usa PARTITION TRUE se non c'è una condizione specifica di selezione; opzionali
          DROP GROUPING FIELDS, KEEP OTHERS.
          Se l'utente chiede anche di "ordinare"/"in ordine crescente o decrescente" gli
          elementi dentro ogni gruppo:
          GROUP PARTITION TRUE BY .campo INTO .risultato ORDER BY .campoOrdinamento TYPE NUMERIC DESC;
          🚨 TYPE è OBBLIGATORIO dopo ogni campo di ordinamento, valore SOLO uno tra
          NUMERIC, STRING, BOOLEAN (a seconda del tipo del campo) — "ORDER BY .campo DESC"
          senza TYPE non è sintassi valida. La direzione (ASC/DESC) è opzionale, va DOPO TYPE.
          🚨 PIÙ PARTITION NELLO STESSO GROUP — verificato leggendo il codice del motore
          (GroupExecutor.java): per ogni documento, il motore prova le PARTITION IN ORDINE e
          si ferma alla PRIMA la cui condizione è vera (c'è un "break" esplicito) — le
          PARTITION successive non vengono MAI valutate per quel documento, anche se la loro
          condizione sarebbe risultata vera. Usa più PARTITION nello stesso comando SOLO se le
          condizioni sono RECIPROCAMENTE ESCLUSIVE (un documento può soddisfarne al massimo
          una), es. fasce di prezzo che non si sovrappongono:
          GROUP PARTITION .prezzo > 500 BY .campo1 INTO .risultato1
                PARTITION .prezzo <= 500 BY .campo2 INTO .risultato2;
          Se invece l'utente chiede raggruppamenti INDIPENDENTI tra loro sugli stessi documenti
          (es. "raggruppa sia per categoria sia per marca" — ogni prodotto ha sia una categoria
          sia una marca, non sono alternative) — le condizioni si sovrapporrebbero (spesso
          entrambe TRUE), quindi la seconda PARTITION risulterebbe sempre vuota. In questo caso
          servono comandi GROUP SEPARATI, ciascuno sulla collezione originale, non uniti in un
          solo comando:
          GET COLLECTION collezione;
          GROUP PARTITION TRUE BY .categoria INTO .per_categoria;
          GET COLLECTION collezione;
          GROUP PARTITION TRUE BY .marca INTO .per_marca;
          🚨 CONTARE GLI ELEMENTI DI UN GRUPPO NON È POSSIBILE — verificato dal vivo (18/09):
          JCoQL+ non ha NESSUNA funzione per contare quanti elementi ha un array/gruppo (niente
          SIZE, COUNT, LENGTH — nessuna di queste esiste nel motore, anche se sintatticamente
          "qualcosaCheNonEsiste(...)" non darebbe un errore di sintassi, fallisce silenziosamente
          a runtime restituendo 0 documenti). Se la richiesta chiede "categorie con più di N
          prodotti", "gruppi con almeno N elementi", o qualunque soglia sul NUMERO di elementi in
          un gruppo — NON È ESPRIMIBILE in una query JCoQL+, non inventare una funzione per
          provarci. In questo caso, genera SOLO il GROUP (senza nessuna condizione sul conteggio,
          che JCoQL+ non può esprimere) — il filtro sul numero di elementi non può far parte
          della query.

        • EXPAND — l'utente chiede di "espandere" un array, o "un documento/risultato per ogni
          elemento di" un campo che è una lista:
          GET COLLECTION collezione;
          EXPAND UNPACK TRUE ARRAY .campoArray TO .campoDestinazione;
          Opzionali KEEP OTHERS / DROP OTHERS per i documenti privi di quell'array.
          🚨 SE L'UTENTE CHIEDE DI ESPANDERE PIÙ ARRAY DIVERSI NELLA STESSA RICHIESTA (es. sia il
          cast sia le lingue di un film) — NON mettere più UNPACK nello stesso comando EXPAND.
          Verificato leggendo il codice del motore (ExpandExecutor.java): quando un EXPAND ha
          più UNPACK, per ogni documento il motore prova le condizioni IN ORDINE e si ferma alla
          PRIMA che risulta vera (c'è un "break" esplicito) — gli UNPACK successivi non vengono
          MAI eseguiti per quel documento. Con condizioni sempre vere (TRUE, il caso comune),
          solo il PRIMO UNPACK ha effetto, sempre — i campi degli altri non esistono mai. Più
          UNPACK nello stesso EXPAND serve solo per "prova questa struttura, se non c'è prova
          quest'altra" (documenti con forme diverse tra loro), MAI per espandere più array dello
          stesso documento insieme.
          Per espandere DAVVERO più array dello stesso documento, servono EXPAND SEPARATI in
          sequenza (ognuno il proprio comando completo):
          GET COLLECTION collezione;
          EXPAND UNPACK TRUE ARRAY .campoArray1 TO .dest1;
          EXPAND UNPACK TRUE ARRAY .campoArray2 TO .dest2;
          Se la collezione è grande (molti documenti, array non piccoli), preferisci filtrare
          dopo il primo EXPAND, salvare con SAVE AS, e fare il secondo EXPAND sul risultato già
          ridotto — due EXPAND su tutta la collezione senza filtrare in mezzo possono creare il
          prodotto di tutte le combinazioni e andare in timeout:
          GET COLLECTION collezione;
          EXPAND UNPACK TRUE ARRAY .campoArray1 TO .dest1;
          FILTER CASE WHERE .dest1.item = 'valore1';
          SAVE AS chaintemp1@{current_db};
          GET COLLECTION chaintemp1;
          EXPAND UNPACK TRUE ARRAY .campoArray2 TO .dest2;
          FILTER CASE WHERE .dest2.item = 'valore2';

        • MERGE — l'utente chiede di "unire"/"combinare"/"mettere insieme" documenti da due
          fonti, tenendo tutto ciò che viene da ENTRAMBI i lati (unione — l'opposto di
          INTERSECT sotto, che tiene solo le corrispondenze in comune): vale sia per collezioni
          intere sia per due sottoinsiemi filtrati dalla stessa collezione — la distinzione da
          INTERSECT/SUBTRACT sotto NON è "collezione intera vs sottoinsieme filtrato" (entrambi
          i comandi funzionano su entrambi i casi), è il SIGNIFICATO della richiesta: "unisci"/
          "metti insieme"/"combina" (tieni tutto) è sempre MERGE, "cosa hanno in comune"/
          "quali soddisfano entrambe le condizioni insieme" è INTERSECT, "togli"/"che però
          non" è SUBTRACT — anche quando entrambi i lati sono due FILTER diversi sulla stessa
          collezione (osservato dal vivo: "unisci i prodotti scontati con i biologici" generato
          per errore come INTERSECT invece di MERGE, probabilmente proprio per questa
          ambiguità):
          MERGE COLLECTIONS collezione1, collezione2;
          🚨 REMOVE DUPLICATES (opzionale) confronta i documenti per intero, _id incluso — ha
          senso SOLO se le collezioni derivano dalla stessa collezione originale (stessi _id
          possibili in comune, es. due sottoinsiemi filtrati diversamente dalla stessa
          collezione). Tra collezioni scorrelate per natura (es. hotels e restaurants, o la
          stessa collezione su database diversi) non troverà mai duplicati da togliere — non
          aggiungerlo in quel caso, sarebbe inutile.

        • INTERSECT / SUBTRACT — l'utente chiede "cosa hanno in comune"/"la differenza tra" due
          insiemi di documenti CHE DERIVANO DALLA STESSA COLLEZIONE, tipicamente due filtri
          diversi sulla stessa collezione (es. "prodotti scontati" e "prodotti elettronici", poi
          trova quelli in comune o la differenza). Verificato nel codice del motore: il
          confronto tra documenti è per intero, _id incluso — funziona correttamente SOLO
          quando entrambe le collezioni condividono gli stessi _id originali (perché derivano
          dagli stessi documenti sorgente, solo filtrati diversamente), MAI tra due collezioni
          scorrelate per natura (es. "hotels" e "restaurants", o la stessa collezione presa da
          due database diversi) — in quel caso _id non potrebbe mai coincidere e il risultato
          sarebbe sempre vuoto (INTERSECT) o l'insieme di partenza intatto (SUBTRACT), a
          prescindere da quanto i documenti si somiglino nel contenuto. 🚨 NON aggiungere KEEP
          OTHERS ai due FILTER qui sotto — questi due filtri devono SELEZIONARE solo le
          corrispondenze per creare due sottoinsiemi VERI, non trasformare l'intera collezione
          tenendo anche chi non soddisfa la condizione (altrimenti entrambi i "sottoinsiemi"
          finiscono per contenere l'intera collezione originale, vanificando l'operazione):
          GET COLLECTION collezione;
          FILTER CASE WHERE condizione1;
          SAVE AS sottoinsieme1@{current_db};
          GET COLLECTION collezione;
          FILTER CASE WHERE condizione2;
          SAVE AS sottoinsieme2@{current_db};
          INTERSECT COLLECTIONS sottoinsieme1@{current_db}, sottoinsieme2@{current_db};
          (SUBTRACT ha la stessa identica struttura, solo il nome del comando cambia)
          🚨 Se una delle due condizioni richiede un EXPAND o un JOIN (es. "con almeno una
          recensione a 5 stelle" — un campo dentro un array; oppure "e il nome dell'utente" —
          un dato che sta in un'altra collezione), NON usare EXPAND né JOIN prima di uno dei due
          FILTER qui sopra — verificato dal vivo, per entrambi separatamente: sia EXPAND sia
          JOIN, quando il risultato viene salvato con SAVE AS, generano SEMPRE un _id
          completamente nuovo (un ObjectId nuovo di MongoDB, senza nessuna relazione con l'_id
          originale del documento — per JOIN è anche intuitivo: unendo due documenti diversi non
          ci sarebbe comunque un _id "giusto" da ereditare da nessuno dei due lati) — anche
          ripulendo con GENERATE REMOVE FIELDS i campi aggiunti, l'_id resta comunque diverso,
          quindi INTERSECT/SUBTRACT non troverebbero MAI corrispondenze (risultato sempre vuoto).
          Non esiste un modo di aggirarlo componendo la query diversamente — è un limite del
          motore, non della query. Se la richiesta ha davvero bisogno di un EXPAND o un JOIN per
          una delle due condizioni, preferisci un singolo FILTER con AND (vedi combinazione di
          condizioni sopra) invece di INTERSECT/SUBTRACT — ottiene lo stesso risultato logico
          senza scontrarsi con questo limite.

        • SAVE AS — l'utente chiede di "salvare"/"creare una copia"/"fare un backup" del
          risultato come nuova collezione:
          GET COLLECTION collezione; [eventuali FILTER/GROUP/EXPAND]
          SAVE AS nuovoNome@{current_db};
          🚨 IMPORTANTE: il database dopo @ è SEMPRE OBBLIGATORIO. "SAVE AS nome;" senza
          @database NON scrive su MongoDB (salva solo temporaneamente nella pipeline interna).
          Se l'utente chiede di salvare, includi SEMPRE @{current_db} (o il database indicato
          esplicitamente dall'utente).

        • GET COLLECTION FROM WEB — l'utente chiede di "caricare"/"recuperare"/"scaricare i
          dati da" un URL (un'API/endpoint pubblico, non un file locale — quello è FROM FILE
          sotto):
          GET COLLECTION FROM WEB 'https://esempio.com/api/dati';
          🚨 STRUTTURA DEL RISULTATO (verificato dal vivo, 19/09) — i dati NON arrivano come
          documenti separati, arrivano SEMPRE incapsulati in UN SOLO documento, con i dati
          veri dentro un campo .data (un array), insieme a .timestamp e .url aggiunti dal
          motore. Per lavorare sui singoli elementi (filtrare, raggruppare) serve SEMPRE un
          EXPAND su .data prima, esattamente come per qualunque altro array:
          GET COLLECTION FROM WEB 'https://esempio.com/api/utenti';
          EXPAND UNPACK TRUE ARRAY .data TO .elemento;
          FILTER CASE WHERE .elemento.item.city = 'Roma';
          Il nome dell'URL va tra apici singoli o doppi, MAI senza apici. Nessun @database.

        • GET COLLECTION FROM FILE — l'utente chiede di "caricare"/"leggere"/"importare" un
          file (tipicamente uno esportato in precedenza con SAVE TO FILE, vedi sotto):
          GET COLLECTION FROM FILE 'nomefile.json';
          [eventuali FILTER/GROUP/EXPAND su questi dati, come su qualunque altra collezione]
          Il nome del file va tra apici singoli o doppi, MAI senza apici. Nessun @database —
          non è una collection MongoDB.
          🚨🚨 CAMPI ANNIDATI SE IL FILE VIENE DA UN JOIN — verificato dal vivo, capitato
          ripetutamente: se il file era stato esportato dopo un JOIN, OGNI campo resta
          annidato sotto l'alias usato in quel JOIN (es. .a.campo, .b.campo) — MAI un campo
          diretto in cima al documento, ANCHE SE il nome del campo sembra ovvio o unico (es.
          "priority", "status", "name"). Esempio concreto — SBAGLIATO:
          GET COLLECTION FROM FILE 'ordini_con_utenti.json';
          GROUP PARTITION TRUE BY .priority INTO .risultato;
          ...CORRETTO (stesso file, un JOIN orders AS a/users AS b lo aveva generato):
          GET COLLECTION FROM FILE 'ordini_con_utenti.json';
          GROUP PARTITION TRUE BY .a.priority INTO .risultato;
          Se non sai con certezza da dove viene il file, preferisci comunque il percorso con
          l'alias (.a.campo) quando la richiesta stessa nomina un JOIN precedente o un file
          con un nome che lo suggerisce (es. "..._con_utenti", "..._join", "..._unito") — un
          campo diretto in cima silenziosamente non trova nulla (0 risultati, nessun errore).

        • SAVE TO FILE — l'utente chiede di "esportare"/"scaricare"/"salvare su file"/"salvare
          come JSON" il risultato (non "su un'altra collezione" — quello è SAVE AS sopra):
          GET COLLECTION collezione; [eventuali FILTER/GROUP/EXPAND]
          SAVE TO FILE 'nomefile.json';
          Il nome del file va tra apici singoli o doppi (entrambi validi), MAI senza apici.
          Nessun @database qui — non è una collection, non serve nessuna destinazione oltre
          al nome del file. Il percorso, se relativo, è risolto rispetto alla working
          directory del processo Java che esegue la query, non rispetto a dove giri il
          browser o il backend Python.
          🚨 Se il FILTER prima di SAVE TO FILE ha una condizione di selezione (es. "gli utenti
          con nome X", "i prodotti scontati"), NON aggiungere KEEP OTHERS — l'utente vuole
          esportare SOLO le corrispondenze, KEEP OTHERS esporterebbe anche tutto il resto
          della collezione, vanificando la selezione (osservato dal vivo: un export "solo
          User 1" con KEEP OTHERS ha prodotto un file con tutti e 5 gli utenti).

        • GENERATE/BUILD — l'utente chiede di "mostrare solo alcuni campi", "rinominare un
          campo", "aggiungere un campo calcolato da un altro campo esistente", o "togliere un
          campo" dal risultato. Va dentro FILTER, dopo l'eventuale condizione WHERE (o anche
          senza nessuna condizione, per trasformare tutti i documenti):
          FILTER CASE WHERE .condizione GENERATE BUILD {{ .nuovoNome: .campoEsistente, ... }} KEEP OTHERS;
          FILTER CASE WHERE .condizione GENERATE ADD FIELDS {{ .nuovoCampo: .campoEsistente }} KEEP OTHERS;
          FILTER CASE WHERE .condizione GENERATE REMOVE FIELDS {{ .campoDaTogliere }} KEEP OTHERS;
          FILTER GENERATE BUILD {{ .campo1: .campo1, .campo2: .campo2 }};  ← senza condizione, su tutti i documenti
          🚨 REGOLE VERIFICATE CONTRO IL PARSER UFFICIALE (violarle produce un errore di sintassi):
          - BUILD sostituisce interamente i campi del documento con solo quelli elencati;
            ADD FIELDS li aggiunge a quelli esistenti; REMOVE FIELDS li toglie.
          - I nomi dei campi vanno SEMPRE scritti con il punto (.nome), sia a sinistra sia a
            destra dei due punti — MAI parole nude come "nome:" o ": prezzo".
          - Le tre parentesi ({{...}}) sono sempre GRAFFE, mai quadre, anche per REMOVE FIELDS.
          - Il valore di un campo può essere SOLO: un altro campo (.campo), un valore letterale,
            o una chiamata a funzione — MAI un'espressione aritmetica diretta come .prezzo * 2
            o .a + .b. Se l'utente chiede un calcolo aritmetico non disponibile con un semplice
            riferimento a campo, non inventare una sintassi: genera comunque BUILD/ADD FIELDS
            con i campi disponibili così come sono, senza il calcolo.

        • GENERATE dentro JOIN o GROUP (non solo dentro FILTER) — stesse regole di BUILD/ADD
          FIELDS/REMOVE FIELDS sopra, ma la posizione nella query cambia:
          — Dentro JOIN, GENERATE può stare insieme alla condizione (dentro la stessa CASE
            WHERE, non dopo) oppure al posto della condizione se non ce n'è una:
            JOIN OF COLLECTIONS coll1@db1 AS a, coll2@db2 AS b
            CASE WHERE .a.chiave1 = .b.chiave2 GENERATE ADD FIELDS {{ .nuovoCampo: .b.campo }};
            JOIN OF COLLECTIONS coll1@db1 AS a, coll2@db2 AS b
            GENERATE ADD FIELDS {{ .nuovoCampo: .b.campo }};  ← senza condizione, su ogni coppia
          — Dentro GROUP, GENERATE va sempre alla fine della PARTITION, dopo INTO (ed eventuali
            DROP GROUPING FIELDS / ORDER BY):
            GROUP PARTITION TRUE BY .campo INTO .risultato GENERATE ADD FIELDS {{ .nuovoCampo: .campo }};
          🚨 Non usare KEEP OTHERS/DROP OTHERS in nessuno dei due casi sopra quando non c'è una
          CASE WHERE — stessa regola generale già vista per FILTER.
          🚨 Se la richiesta nomina esplicitamente una chiave di corrispondenza ("usando
          l'id", "in base a", "che corrisponde a") NON scegliere mai la forma "senza
          condizione" — quella esiste solo per quando non c'è davvero nessuna chiave da
          abbinare (es. "unisci ogni prodotto con ogni categoria disponibile", un prodotto
          cartesiano voluto). Quando una chiave è nominata, la condizione va SEMPRE inclusa
          insieme a GENERATE, nella stessa CASE WHERE — verificato dal vivo che è possibile
          farlo insieme, non c'è nessun motivo tecnico per ometterla (osservato: un JOIN con
          GENERATE ma senza condizione, pur richiesta esplicitamente, ha prodotto un risultato
          con ogni combinazione possibile invece degli abbinamenti corretti).

        • GET DICTIONARY + TRANSLATE — l'utente chiede di "tradurre"/"mappare"/"convertire" un
          valore usando un'altra collezione come dizionario di corrispondenza:
          🚨 REGOLA VINCOLANTE, senza eccezioni: se generi anche solo una volta la funzione
          TRANSLATE(...) da qualunque parte nella query, lo script DEVE contenere anche un
          comando GET DICTIONARY che registra quello STESSO alias, PRIMA di tutto il resto.
          Una query con TRANSLATE(.campo, alias) ma senza "GET DICTIONARY ... AS alias;" da
          nessuna parte è SEMPRE SBAGLIATA, anche se sintatticamente valida — non generarla mai.
          Forma completa, sempre in quest'ordine:
          GET DICTIONARY nomeCollezioneDizionario@{current_db} AS aliasDizionario;
          GET COLLECTION collezionePrincipale;
          FILTER GENERATE ADD FIELDS {{ .nuovoCampo: TRANSLATE(.campoOriginale, aliasDizionario) }};
          🚨 Il simbolo @ prima del database è OBBLIGATORIO in GET DICTIONARY esattamente come
          in SAVE AS — "GET DICTIONARY nome AS alias;" senza @database non è sintassi valida.
          🚨 QUI NON va aggiunto KEEP OTHERS/DROP OTHERS alla fine — vedi la regola generale
          subito sotto sul perché.
          TRANSLATE si usa solo dentro GENERATE (BUILD/ADD FIELDS), mai da solo in un WHERE.


        • 🚨 REGOLA GENERALE su KEEP OTHERS / DROP OTHERS — un errore comune: KEEP OTHERS e
          DROP OTHERS sono validi SOLO dopo una condizione CASE WHERE (es. "FILTER CASE WHERE
          .campo > 0 GENERATE ... KEEP OTHERS;"). NON sono validi dopo un FILTER GENERATE
          "nudo", cioè senza nessuna condizione WHERE prima (es. "FILTER GENERATE BUILD {{...}};"
          — qui NON si scrive KEEP OTHERS/DROP OTHERS alla fine, altrimenti è un errore di
          sintassi). Regola pratica: se la query non ha un "CASE WHERE" da nessuna parte prima
          di GENERATE, non aggiungere KEEP OTHERS o DROP OTHERS.

        • MERGE su più di 2 database — l'utente chiede di "cercare su tutti i database
          selezionati", "unire i dati da più fonti", o simili, quando ha selezionato più di 2
          database. MERGE COLLECTIONS accetta un numero qualunque di collezioni, non solo 2:
          USE DB db1 ON DEFAULT SERVER;
          USE DB db2 ON DEFAULT SERVER;
          USE DB db3 ON DEFAULT SERVER;
          MERGE COLLECTIONS collezione@db1, collezione@db2, collezione@db3;
          Un USE DB per ciascun database PRIMA del MERGE, poi tutti i riferimenti
          collezione@database elencati nello stesso MERGE COLLECTIONS, separati da virgola.
          Nessuna condizione di corrispondenza tra i database — è un'unione, non un JOIN.
          Se serve anche filtrare il risultato unito, aggiungi un FILTER CASE WHERE dopo.
          🚨 db1/db2/db3 qui sopra sono solo segnaposto per la sintassi — i nomi VERI dei
          database da usare (quello corrente più eventuali altri) sono nella sezione
          "ALTRI DATABASE SELEZIONATI DALL'UTENTE" più sopra, se presente. Se quella sezione
          non compare, l'utente ha un solo database selezionato: non generare comunque un
          MERGE multi-database inventando nomi che non hai — genera una query normale su
          quell'unico database.

        • Più JOIN nella stessa richiesta ("join concatenati") — l'utente chiede qualcosa che
          richiede DUE (o più) operazioni di JOIN in sequenza, es. "utenti con i loro ordini, e
          gli ordini con i prodotti acquistati". JOIN OF COLLECTIONS accetta SEMPRE e SOLO 2
          collezioni alla volta — per concatenarne un terzo (o quarto...), il primo JOIN va
          materializzato con SAVE AS, poi referenziato come una collection normale nel JOIN
          successivo:
          USE DB db1 ON DEFAULT SERVER;
          USE DB db2 ON DEFAULT SERVER;
          JOIN OF COLLECTIONS coll1@db1 AS a, coll2@db2 AS b
          CASE WHERE .a.chiave1 = .b.chiave2;
          SAVE AS chaintemp1@db1;
          USE DB db1 ON DEFAULT SERVER;
          USE DB db3 ON DEFAULT SERVER;
          JOIN OF COLLECTIONS chaintemp1@db1 AS c, coll3@db3 AS d
          CASE WHERE .c.a.chiaveJoinPrecedente = .d.chiave3;
          🚨 Il nome della collection intermedia DEVE iniziare per "chaintemp" (es. chaintemp1,
          chaintemp2 per passaggi successivi) — il sistema la riconosce da questo prefisso e la
          cancella automaticamente a fine esecuzione, non lasciarla con un altro nome o resterà
          in giro su MongoDB inutilmente. Il database dopo @ per SAVE AS chaintempN può essere
          uno qualsiasi tra quelli coinvolti, non deve necessariamente coincidere con nessuno
          dei due — usane uno tra quelli già dichiarati con USE DB in precedenza.
          Nota sui riferimenti ai campi dopo il primo JOIN: il documento risultato di un JOIN ha
          i due lati annidati sotto i rispettivi alias (es. .a.campo, .b.campo) — quindi nel
          secondo JOIN, per riferirti a un campo che veniva dal primo JOIN, il percorso passa
          comunque per l'alias di quel primo JOIN (es. .c.a.chiaveJoinPrecedente nell'esempio
          sopra, non semplicemente .c.chiaveJoinPrecedente).
          🚨 SE LA CHIAVE DI JOIN È DENTRO UN ARRAY (es. un ordine con un array "items", e devi
          confrontare items[].product_id con un altro documento): NON puoi confrontare
          direttamente un campo dentro un array con un valore singolo — il motore richiede che
          i due lati di un confronto = siano dello stesso tipo, e un array non è mai considerato
          uguale a un valore singolo, anche se lo contiene. Devi prima "srotolare" l'array con
          EXPAND (un passaggio in più nella catena), POI fare il JOIN sul campo srotolato:
          [...primo JOIN come sopra, poi SAVE AS chaintemp1@db1...]
          GET COLLECTION chaintemp1;
          EXPAND UNPACK TRUE ARRAY .a.nomeArray TO .elemento;
          SAVE AS chaintemp2@db1;
          USE DB db1 ON DEFAULT SERVER;
          USE DB db3 ON DEFAULT SERVER;
          JOIN OF COLLECTIONS chaintemp2@db1 AS c, coll3@db3 AS d
          CASE WHERE .c.elemento.item.campoInterno = .d.chiave3;
          🚨🚨 ORDINE PREFERITO — JOIN PRIMA, EXPAND DOPO (come sopra, non il contrario):
          quando l'array da espandere appartiene a una delle due collezioni che comunque devi
          unire con JOIN, fai SEMPRE prima il JOIN e POI l'EXPAND sul risultato già unito —
          MAI il contrario (EXPAND su una collection da sola, prima di qualunque JOIN). Il
          motivo: ogni JOIN aggiunge un livello di annidamento con l'alias attorno a TUTTO il
          contenuto di quel lato — se fai prima EXPAND e POI JOIN quella collection già
          espansa, il campo creato dall'EXPAND finisce annidato sotto l'alias di quel JOIN
          (es. .c.a.elemento.item...), non più in cima al documento (.c.elemento.item...) —
          un livello in più facile da dimenticare, che porta a un percorso sbagliato e a 0
          risultati senza nessun errore visibile (osservato dal vivo). Facendo prima il JOIN
          e poi l'EXPAND, come nell'esempio sopra, il campo espanso resta sempre in cima al
          documento risultante — un solo livello da tenere a mente, non due.
          🚨🚨 ATTENZIONE al percorso dopo EXPAND — verificato leggendo il codice sorgente del
          motore (JCOConstants.java: ITEM_FIELD_NAME = "item"), non dedotto per tentativi: il
          nome scelto dopo TO (es. "elemento") NON diventa direttamente il contenuto
          dell'elemento — EXPAND lo avvolge in un oggetto con DUE campi FISSI, sempre chiamati
          "item" (il contenuto vero) e "position" (l'indice), a prescindere da quale nome hai
          scelto dopo TO. Il percorso è SEMPRE .alias.nomeScelto.item.campoInterno — "item" è
          una parola fissa del motore, non il nome che hai scelto ripetuto.
          Se l'elemento dell'array è un valore semplice (non un oggetto, es. un array di
          stringhe), il percorso si ferma a .alias.nomeScelto.item (senza altro campo dopo).

          🚨🚨 ERRORE COMUNE DA EVITARE — fermarsi troppo presto: dopo l'EXPAND sull'array,
          può sembrare che la richiesta sia già soddisfatta (i riferimenti sono lì,
          "srotolati") — ma se la richiesta NOMINA un'entità (es. "prodotti", "categorie",
          "autori") o CHIEDE "CHI" ha fatto qualcosa (chi ha scritto, chi ha acquistato, chi
          ha ordinato) e nei dati hai solo un riferimento grezzo a quell'entità (un valore
          semplice, non un nome/prezzo/altri dettagli), la richiesta NON è soddisfatta finché
          non fai anche il JOIN finale che porta dentro i dati veri di quell'entità. 🚨 QUESTO
          VALE ANCHE SE IL CAMPO NON SI CHIAMA "qualcosa_id" — un campo chiamato semplicemente
          "user", "autore", "owner" (senza suffisso _id) che contiene comunque un
          identificativo (non un nome leggibile) è lo stesso identico caso, non fare
          affidamento sul nome del campo per riconoscerlo. Un riferimento grezzo da solo non
          è "l'utente"/"l'autore" — è solo un riferimento A quell'entità. Prima di considerare
          finita una query con EXPAND su un array di riferimenti, controlla: la richiesta
          nomina esplicitamente l'entità referenziata, o chiede "chi" ha fatto qualcosa (es.
          "e i prodotti acquistati", "con i dettagli di X", "e chi le ha scritte")? Se sì,
          manca sempre un ultimo JOIN — non fermarti al solo riferimento srotolato, anche se
          sintatticamente la query già "funziona" così com'è (es. tramite GENERATE che si
          limita a copiare il riferimento grezzo nel risultato, senza mai risolverlo).

        • 🚨 STESSA REGOLA VALE PER FILTER (non solo per JOIN sopra) — verificato che
          SynchronizedFilterCycle.java (il motore per FILTER CASE WHERE) usa lo stesso
          evaluator di JOIN, quindi la stessa restrizione: un campo che è un array non è MAI
          uguale a un valore singolo con =, anche se lo contiene, anche se il campo ha un solo
          elemento. Questo riguarda in particolare richieste tipo "film con l'attore X",
          "prodotti con il tag Y", "ordini che contengono il prodotto Z" — qualunque richiesta
          che cerca un valore DENTRO un array. NON generare mai .campoArray = 'valore' — serve
          sempre un EXPAND prima:
          GET COLLECTION collezione;
          EXPAND UNPACK TRUE ARRAY .campoArray TO .elemento;
          FILTER CASE WHERE .elemento.item = 'valore';
          🚨 Qui NON va aggiunto KEEP OTHERS al FILTER finale — l'utente vuole SOLO le
          corrispondenze (una ricerca), KEEP OTHERS terrebbe anche tutto il resto, vanificando
          il filtro (esattamente l'errore osservato: un FILTER con KEEP OTHERS su un confronto
          sempre "non valutabile" per il disallineamento di tipo aveva restituito il 100% dei
          documenti invece delle sole corrispondenze).
          Se il campo dentro l'array è un OGGETTO (non un valore semplice), il percorso dopo
          EXPAND include anche il campo interno: .elemento.item.campoInterno = 'valore'
          (stessa regola del doppio nome vista sopra per JOIN).

        • 🚨 SCEGLIERE IL CAMPO GIUSTO PER UN JOIN — quando due collezioni hanno campi con lo
          stesso nome ma sono in realtà cose diverse (es. entrambe hanno un campo "user_id", ma
          in una è una stringa che identifica un altro documento, nell'altra è solo un numero
          progressivo interno), NON scegliere un campo solo perché il nome coincide con l'altro
          lato. Guarda il TIPO e i VALORI DI ESEMPIO REALI mostrati nello schema qui sotto per
          ciascun campo (es. ".campo (string) — es: user_005, user_012") — se il tipo o la forma
          dei valori di un campo non è compatibile con l'altro lato del confronto, quel campo
          quasi certamente non è la chiave di join giusta, anche se il nome sembra promettente.
          In particolare, l'identificativo naturale di un documento è quasi sempre il campo _id
          (mostrato anch'esso nello schema, con i suoi valori di esempio) — ma verificalo sempre
          confrontando i valori reali, non darlo per scontato a priori.

{EXTENDED_EXAMPLES}

{JCOQL_SYNTAX_FULL}

ESEMPI SIMILI (da RAG):
{context_str}

USER QUERY:
"{request.nl_query}"

{f"ATTENZIONE! ERRORI PRECEDENTI DA CORREGGERE: {all_errors[-1]}" if attempts > 1 else ""}

Genera SOLO la query JCoQL basata sullo SCHEMA REALE sopra.
Usa ESATTAMENTE i nomi campi dello schema. NESSUN testo aggiuntivo.
"""

        # MISURA DIAGNOSTICA (17/09): dimensione reale del prompt appena
        # costruito — per capire con certezza cosa sta saturando la quota
        # Gemini (250k token/minuto), invece di continuare a stimarlo da
        # fuori senza vedere lo schema vero del database dell'utente.
        # ~4 caratteri per token è una stima approssimativa ma ragionevole
        # per testo misto italiano/inglese — non è il conteggio esatto di
        # Gemini, ma dà l'ordine di grandezza. Stampato sempre, non solo
        # sotto JCOQL_DEBUG, perché è proprio il primo tentativo (quello
        # più difficile da riprodurre) quello che ci interessa vedere.
        query_logger.info(
            f"📏 Dimensione prompt: {len(prompt):,} caratteri "
            f"(~{len(prompt)//4:,} token stimati) — "
            f"grammatica: {len(JCOQL_SYNTAX_FULL):,} car., "
            f"esempi fissi: {len(EXTENDED_EXAMPLES):,} car., "
            f"schema+regole+RAG: {len(prompt) - len(JCOQL_SYNTAX_FULL) - len(EXTENDED_EXAMPLES):,} car."
        )

        try:
            # Prompt più snello per i modelli locali (19/09) — primo passo,
            # solo su questo punto per ora (le regole restano le stesse
            # invariate, un intervento più grosso da fare con calma a
            # parte): la grammatica FULL (~14.000 token stimati) è quella
            # ufficiale pensata per il parser stesso, non per spiegare
            # l'uso — osservato dal vivo un modello locale "perdersi" a
            # descriverla in prosa invece di usarla per generare una
            # query. JCOQL_SYNTAX_BASIC (~5.000 token, la grammatica
            # 'JCoQLBasic.g' ufficiale) copre tutto tranne GET COLLECTION
            # FROM FILE (verificato confrontando le due grammatiche) — un
            # limite accettato per ora, dato che la regola su FROM FILE
            # resta comunque nel testo delle regole condiviso sotto,
            # anche senza il supporto formale della grammatica.
            # Gemini NON è toccato da questo cambio — usa sempre `prompt`
            # tale e quale, mai `local_model_prompt`.
            #
            # Promemoria extra SOLO per i modelli locali (Llama/Gemma), che nei test si
            # sono dimostrati più propensi a usare solo l'ultimo segmento di un campo
            # annidato (es. .rating invece di .imdb.rating) invece di leggere il percorso
            # completo dallo schema. Regola generica su come leggere lo schema, non legata
            # a nessun database specifico - si applica a qualunque campo annidato di
            # qualunque database connesso.
            local_model_prompt = prompt
            if ACTIVE_LLM in ("llama", "gemma"):
                local_model_prompt = prompt.replace(JCOQL_SYNTAX_FULL, JCOQL_SYNTAX_BASIC) + (
                    "\n\nATTENZIONE - CAMPI ANNIDATI: nello SCHEMA MONGODB REALE sopra, se un "
                    "campo appare con un punto nel nome (es. 'imdb.rating', 'location.city'), "
                    "quello è un campo ANNIDATO: DEVI usare il percorso completo con il punto "
                    "nella query (es. .imdb.rating, .location.city), MAI solo l'ultimo segmento "
                    "(MAI .rating da solo se lo schema mostra imdb.rating). Controlla sempre lo "
                    "schema prima di scegliere un nome di campo."
                )
                query_logger.info(
                    f"📏 Dimensione prompt (modello locale, grammatica BASIC): "
                    f"{len(local_model_prompt):,} caratteri "
                    f"(~{len(local_model_prompt)//4:,} token stimati) — "
                    f"contro {len(prompt):,} caratteri che avrebbe avuto con la grammatica FULL"
                )

            if ACTIVE_LLM == "llama":
                current_query = generate_with_llama(local_model_prompt)
            elif ACTIVE_LLM == "gemma":
                current_query = generate_with_gemma(local_model_prompt)
            else:
                # FIX (17/09): nessun timeout esplicito qui — osservato dal
                # vivo un blocco di diversi minuti, senza errore né
                # risposta, subito dopo aver esaurito la quota gratuita
                # (429): la libreria di Google, sotto al cofano, sembra
                # ritentare automaticamente con attese crescenti, senza
                # far arrivare nulla ai nostri log nel frattempo. Un
                # timeout esplicito forza un errore chiaro dopo un tempo
                # ragionevole, invece di un blocco silenzioso indefinito.
                response = model.generate_content(prompt, request_options={"timeout": 20})
                current_query = response.text.strip()

            # 🔧 Fix: applicato a TUTTI i modelli locali (Llama e Gemma), non solo Llama.
            # I modelli locali quantizzati sono più soggetti a due tipi di errore:
            # (a) nome di collezione sbagliato ma presente, (b) clausola GET COLLECTION
            # omessa del tutto. Qui correggiamo (a) e rileviamo esplicitamente (b).
            if ACTIVE_LLM in ("llama", "gemma"):
                from difflib import get_close_matches

                match = re.search(r'GET COLLECTION\s+(\w+)', current_query, re.IGNORECASE)
                if match:
                    coll_name = match.group(1)

                    # (a) Nome di collezione presente ma non esistente: correggi con il più simile
                    if coll_name not in available_collections and available_collections:
                        close_matches = get_close_matches(coll_name, available_collections, n=1, cutoff=0.6)
                        if close_matches:
                            corrected = current_query.replace(
                                f"GET COLLECTION {coll_name}",
                                f"GET COLLECTION {close_matches[0]}"
                            )
                            query_logger.info(f"🔧 {ACTIVE_LLM.capitalize()} corretto: {coll_name} → {close_matches[0]}")
                            current_query = corrected
                else:
                    # (b) GET COLLECTION del tutto assente: non indoviniamo il nome collezione
                    # (rischia di essere semanticamente sbagliato, es. "film" vs "movies"),
                    # ma segnaliamo l'errore in modo esplicito così il repair loop successivo
                    # ha un'istruzione chiara da correggere, invece di un errore di parsing
                    # generico difficile da interpretare per il modello. Il messaggio viene
                    # unito a quello del parser più sotto (stesso tentativo), non aggiunto
                    # come voce separata, altrimenti verrebbe scartato: il prompt usa solo
                    # all_errors[-1].
                    query_logger.warning(
                        f"⚠️ {ACTIVE_LLM.capitalize()} ha omesso GET COLLECTION nella risposta"
                    )
                    missing_get_collection_hint = (
                        "La query DEVE iniziare con la clausola 'GET COLLECTION <nome_collezione>;' "
                        "seguita da un punto e virgola. Questa clausola era completamente assente "
                        f"nel tentativo precedente. Collezioni disponibili: {', '.join(available_collections)}."
                    )

            # Estrai TUTTI i nomi dei campi (inclusi quelli nested) dallo schema
            all_field_names = []
            if current_schema:
                for coll_name, coll_data in current_schema.items():
                    if isinstance(coll_data, dict):
                        fields = coll_data.get('fields', {})
                        if isinstance(fields, dict):
                            # Aggiungi sia i nomi top-level che quelli nested
                            for field_name in fields.keys():
                                all_field_names.append(field_name)
                                # Se è un percorso nested (contiene .), aggiungi anche la parte finale
                                if '.' in field_name:
                                    # Prendi anche la parte dopo il primo punto
                                    parts = field_name.split('.')
                                    for part in parts:
                                        if part and part not in all_field_names:
                                            all_field_names.append(part)

            # Controlla se l'utente ha menzionato uno dei campi dello schema (fuzzy match)
            from difflib import get_close_matches
            user_query_lower = request.nl_query.lower()
            user_words = user_query_lower.split()
            
            has_filter_request = False
            for word in user_words:
                # Cerca il campo più simile (cutoff = 0.6 per 60% di similarità)
                matches = get_close_matches(word, all_field_names, n=1, cutoff=0.4)
                if matches:
                    has_filter_request = True
                    break
            
            # Fallback: keyword generici universali
            if not has_filter_request:
                generic_keywords = ['dove', 'con', 'che', '>', '<', '>=', '<=', '=', '!=']
                has_filter_request = any(kw in user_query_lower for kw in generic_keywords)
            
            # Applicazione lato codice della REGOLA CRITICA #1 del prompt
            # (niente FILTER se l'utente non ha chiesto una condizione):
            # se il fuzzy match sopra non ha trovato nessun indizio di
            # filtro nella richiesta utente, ma il modello ha comunque
            # generato un FILTER CASE WHERE, lo tronca via tenendo solo
            # la GET COLLECTION — rete di sicurezza per quando il prompt
            # da solo non basta a farsi seguire dal modello.
            if not has_filter_request and 'FILTER CASE WHERE' in current_query.upper():
                collection_match = re.search(r'GET\s+COLLECTION\s+\w+', current_query, re.IGNORECASE)
                if collection_match:
                    current_query = collection_match.group(0) + ";"

            # Estrazione robusta della query JCoQL+ dal testo grezzo del LLM. Sostituisce
            # una logica precedente basata su filtro riga-per-riga, che falliva quando il
            # LLM avvolgeva la query in backtick SINGOLI (` query `): il carattere backtick
            # rompeva sia il controllo "la riga inizia con una parola chiave" sia "la riga
            # finisce con ;", lasciando la lista di righe valide vuota e la query grezza
            # (incluso testo conversazionale tipo "Ecco la query...") intatta, con
            # conseguente errore di parsing sul primo token estraneo.
            def _extract_jcoql_query(raw_text):
                text = raw_text.strip()

                # 1. Preferisci il contenuto di un blocco markdown, tripli o singoli backtick
                triple = re.search(r'```(?:jcoql|sql)?\s*\n?(.*?)\n?```', text, re.DOTALL)
                if triple:
                    text = triple.group(1).strip()
                else:
                    single = re.search(r'`([^`]*;[^`]*)`', text, re.DOTALL)
                    if single:
                        text = single.group(1).strip()

                # 2. Rimuovi eventuali backtick residui isolati (non in coppia, o rimasti
                #    da un markdown malformato)
                text = text.replace('`', '')

                # 3. Ancora sul punto in cui inizia davvero la sintassi JCoQL+, scartando
                #    qualunque preambolo conversazionale prima di quel punto
                start_kw = (r'(?:GET COLLECTION|JOIN OF COLLECTIONS|MERGE COLLECTIONS|'
                            r'INTERSECT COLLECTIONS|SUBTRACT COLLECTIONS|USE DB)')
                m = re.search(start_kw, text, re.IGNORECASE)
                if m:
                    text = text[m.start():]

                # 4. Scarta qualunque testo dopo l'ultimo ';' (spiegazioni post-query tipo
                #    "Nota che ho sostituito...")
                last_semicolon = text.rfind(';')
                if last_semicolon != -1:
                    text = text[:last_semicolon + 1]

                return text.strip()

            current_query = _extract_jcoql_query(current_query)

            # Filtro riga-per-riga mantenuto come rete di sicurezza aggiuntiva (ora
            # innocuo se non trova nulla da scartare, dato che l'estrazione sopra ha
            # già ripulito la maggior parte del rumore)
            jcoql_keywords = [
                'GET', 'FILTER', 'WHERE', 'KEEP', 'DROP', 'WITHOUT', 
                'IN_RANGE', 'INTERSECT', 'EXPAND', 'LOOKUP', 'MERGE', 
                'GROUP', 'SAVE', 'ALL', 'CREATE', 'TRAJECTORY', 'USE', 'SUBTRACT', 'JOIN'
            ]
            lines = current_query.split('\n')
            clean_lines = [
                l.strip() for l in lines 
                if l.strip() and (
                    any(l.strip().upper().startswith(kw) for kw in jcoql_keywords) 
                    or l.strip().startswith('.') 
                    or l.strip().endswith(';')
                )
            ]
            if clean_lines:
                current_query = '\n'.join(clean_lines).strip()

            # Rilevamento di "leakage" del template di prompt: capita che un modello più
            # debole (osservato con Gemma) non generi una query nuova per la richiesta,
            # ma copi letteralmente pezzi del prompt stesso (marcatori come "USER QUERY:",
            # "ESEMPI SIMILI", lo schema, o intere query degli esempi RAG concatenate senza
            # punti e virgola tra loro). In questo caso il parser produce una lunga lista di
            # errori "missing SC" poco utili per il repair loop - qui diamo invece un
            # messaggio esplicito e azionabile.
            prompt_leakage_hint = None
            leakage_markers = ["USER QUERY", "ESEMPI SIMILI", "SCHEMA MONGODB REALE", "REGOLA CRITICA"]
            found_marker = next((m for m in leakage_markers if m in current_query.upper()), None)
            if found_marker:
                query_logger.warning(
                    f"⚠️ {ACTIVE_LLM.capitalize()} ha copiato parte del prompt nell'output "
                    f"(marcatore rilevato: '{found_marker}') invece di generare una query nuova"
                )
                prompt_leakage_hint = (
                    "Il tentativo precedente conteneva testo copiato dal prompt stesso "
                    f"(es. '{found_marker}') o dagli esempi di riferimento concatenati insieme, "
                    "invece di una query JCoQL+ nuova per la richiesta dell'utente. Genera "
                    "UNA SOLA query JCoQL+ valida che risponda esattamente alla richiesta "
                    f"'{request.nl_query}', senza copiare gli esempi forniti come riferimento."
                )
                # Taglia comunque tutto da quel marcatore in poi, così quello che resta
                # (se qualcosa di valido c'è prima) può ancora essere tentato dal parser
                cut_idx = current_query.upper().find(found_marker)
                current_query = current_query[:cut_idx].strip()

            # Auto-correzione sintattica
            # Nota: qui si controlla solo il prefisso "QUERY:", non anche
            # "Operazione" come fa invece query_corrector.correct_query()
            # al suo interno (vedi query_corrector.py) — controllo un po'
            # più permissivo qui, la doppia rete di sicurezza dentro
            # correct_query() copre comunque anche quel caso.
            if current_query and not current_query.startswith("QUERY:"):
                current_query, _ = correct_query(current_query)

            # Costruzione multi-database deterministica (16/08): se 2+
            # database sono selezionati, ricostruisce una query semplice
            # "GET COLLECTION X;" in un MERGE su tutti i database
            # selezionati — vedi _build_multi_database_query per il
            # perché. Va DOPO l'auto-correzione sintattica sopra (lavora su
            # una query già ripulita) e PRIMA delle riparazioni sotto,
            # così quelle si applicano già alla versione multi-database
            # se necessario.
            current_query = _build_multi_database_query(current_query, request.databases, db_registry.databases)

            # Riparazione deterministica: FILTER che confronta con =/!= un
            # campo che lo schema conosce come array — vedi
            # _fix_array_field_filter per il perché (regressione introdotta
            # dalla strategia "auto SAVE AS", che ha tolto una gestione
            # esplicita degli array che prima esisteva lato Python).
            current_query = _fix_array_field_filter(current_query, current_schema)

            # Riparazione deterministica: N EXPAND consecutivi seguiti da
            # un unico FILTER combinato — riscritta a stadi per evitare il
            # prodotto di tutte le combinazioni su collection grandi (vedi
            # _stage_multi_expand_filter — timeout osservato due volte dal
            # vivo su sample_mflix.movies).
            current_query = _stage_multi_expand_filter(current_query, current_db)

            # Riparazione deterministica: EXPAND fatto prima di un JOIN
            # che riusa la stessa collection — riscritta scambiando
            # l'ordine (JOIN poi EXPAND), invece di calcolare un livello
            # di annidamento extra sul posto. Va PRIMA della riparazione
            # sul livello ".item" mancante sotto, così quella lavora già
            # sulla struttura riordinata. Vedi _reorder_expand_before_join.
            current_query = _reorder_expand_before_join(current_query)

            # Riparazione deterministica: percorso dopo EXPAND con un
            # livello ".item" mancante — vedi _fix_missing_expand_item_wrapper.
            # A differenza delle altre riparazioni su EXPAND, qui la
            # correzione è certa (non richiede un altro tentativo).
            current_query = _fix_missing_expand_item_wrapper(current_query)

            # Riparazione deterministica: KEEP OTHERS di troppo su un
            # FILTER senza GENERATE — vedi _remove_pointless_keep_others.
            # Generalizzata il 18/09: non più limitata al caso "prima di
            # un SAVE", riguarda ogni FILTER senza GENERATE (dove KEEP
            # OTHERS è sempre privo di effetto utile, a prescindere da
            # cosa viene dopo).
            current_query = _remove_pointless_keep_others(current_query)

            # Riparazione deterministica: punto e virgola mancante tra la
            # condizione del FILTER e un SAVE AS/SAVE TO FILE subito dopo
            # — vedi _fix_missing_semicolon_before_save. Va DOPO la
            # riparazione sopra (toglie KEEP OTHERS), così corregge anche
            # il punto e virgola che a volte sparisce insieme ad esso.
            current_query = _fix_missing_semicolon_before_save(current_query)

            # Riparazione deterministica: true/false minuscoli in un
            # confronto — vedi _fix_lowercase_boolean.
            current_query = _fix_lowercase_boolean(current_query)

            # Riparazione deterministica: aritmetica diretta dentro
            # GENERATE (non supportata dal motore) — vedi
            # _fix_arithmetic_in_generate.
            current_query = _fix_arithmetic_in_generate(current_query)

            # Riparazione deterministica: REMOVE DUPLICATES mancante su
            # un MERGE tra due sottoinsiemi con la stessa origine — vedi
            # _add_remove_duplicates_if_same_source.
            current_query = _add_remove_duplicates_if_same_source(current_query)

            # Riparazione deterministica: @database mancante su un
            # riferimento a collection dentro JOIN OF COLLECTIONS o MERGE
            # COLLECTIONS (osservato il 15/08 in un JOIN concatenato — il
            # modello aveva scritto correttamente "chaintemp1@jcoql_test"
            # ma dimenticato "@jcoql_test" su "users"/"orders"/"products").
            # Senza @database esplicito il motore cerca il nome tra le
            # collection temporanee della pipeline, non su MongoDB — quindi
            # non è un dettaglio stilistico, la query fallirebbe a runtime.
            # Stessa filosofia della riparazione per GET DICTIONARY sopra:
            # più affidabile ripararlo qui che sperare in un altro
            # tentativo di generazione.
            current_query = _fix_missing_collection_db(current_query, current_db)

            # Riparazione deterministica, seconda parte: @database presente
            # ma inventato (osservato il 15/08 SUBITO DOPO aver corretto il
            # caso sopra — il modello ha iniziato ad aggiungere "USE DB
            # users;"/"USE DB products;", usando nomi di collection come se
            # fossero database — nessuno dei due esiste come database
            # reale). Confrontato contro db_registry.databases, l'elenco
            # vero di quello che è davvero connesso.
            current_query = _fix_hallucinated_databases(
                current_query, current_db, set(db_registry.databases.keys())
            )

            # Validazione sintattica ANTLR
            is_valid, errors = parser.validate(current_query)

            # Controllo semantico aggiuntivo, non rilevabile dal parser (che
            # vede TRANSLATE(...) come sintatticamente valido a prescindere):
            # TRANSLATE senza il GET DICTIONARY corrispondente è sempre una
            # query rotta a runtime (l'alias del dizionario non esiste).
            # L'abbiamo trovato succedere nonostante l'istruzione nel prompt
            # — qui c'è la rete di sicurezza che forza un altro tentativo
            # invece di lasciar passare una query semanticamente invalida.
            translate_match = re.search(r'TRANSLATE\s*\(\s*[^,]+,\s*(\w+)', current_query, re.IGNORECASE)
            if is_valid and translate_match \
                    and not re.search(r'GET\s+DICTIONARY', current_query, re.IGNORECASE):
                used_alias = translate_match.group(1)
                # Di default consideriamo la query non valida finché non
                # riusciamo a ripararla sotto — evita che, se l'estrazione del
                # nome dizionario fallisce, is_valid resti erroneamente True.
                is_valid = False

                # AUTO-RIPARAZIONE (14/08): dopo aver verificato che l'LLM
                # (anche Gemini) non si corregge in modo affidabile su questo
                # caso specifico nemmeno con un esempio RAG pertinente
                # recuperato e un feedback "prima/dopo" esplicito (verificato
                # via log JCOQL_DEBUG — l'esempio giusto era tra i recuperati,
                # il problema non è il RAG), costruiamo noi la riga mancante
                # invece di richiederla ancora al modello. L'unica cosa che
                # non sappiamo con certezza è quale collection usare come
                # dizionario — ma chi chiede una traduzione di solito la nomina
                # esplicitamente ("usando il dizionario X", "tramite X"), quindi
                # proviamo a estrarla dalla richiesta originale dell'utente.
                dict_name_match = re.search(
                    r'dizionario\s+(\w+)|tramite\s+(?:il\s+)?(\w+)',
                    request.nl_query, re.IGNORECASE
                )
                dict_collection = None
                if dict_name_match:
                    dict_collection = dict_name_match.group(1) or dict_name_match.group(2)

                # FALLBACK (18/09): osservato dal vivo che una richiesta di
                # traduzione formulata in modo naturale ("tradotta in
                # italiano") non nomina affatto il dizionario — il tentativo
                # sopra non ha nulla da estrarre. Prima di arrendersi,
                # cerca nello schema del database corrente l'UNICA
                # collection con la forma tipica di un dizionario (solo
                # campi "key"/"value", a parte _id) — se ce n'è esattamente
                # una, non c'è ambiguità da indovinare, usala. Se ce n'è
                # più di una o nessuna, non si tenta nulla: resta il
                # messaggio di errore esplicito sotto, che chiede
                # all'utente di specificare quale.
                if not dict_collection:
                    dict_candidates = []
                    for coll_name, coll_data in (current_schema or {}).items():
                        coll_fields = set(((coll_data or {}).get('fields', {}) or {}).keys())
                        coll_fields.discard('_id')
                        if coll_fields == {'key', 'value'}:
                            dict_candidates.append(coll_name)
                    if len(dict_candidates) == 1:
                        dict_collection = dict_candidates[0]
                        query_logger.info(
                            f"🔧 Nessun nome dizionario nella richiesta — trovata un'unica "
                            f"collection a forma di dizionario nello schema: '{dict_collection}'"
                        )

                if dict_collection:
                    repaired_query = (
                        f"GET DICTIONARY {dict_collection}@{current_db} AS {used_alias};\n"
                        f"{current_query}"
                    )
                    repaired_valid, repaired_errors = parser.validate(repaired_query)
                    if repaired_valid:
                        query_logger.info(
                            f"🔧 Auto-riparata query TRANSLATE senza GET DICTIONARY: "
                            f"aggiunta 'GET DICTIONARY {dict_collection}@{current_db} AS {used_alias};' "
                            f"(nome dizionario estratto dalla richiesta utente, non generato dall'LLM)"
                        )
                        current_query = repaired_query
                        is_valid = True

                # Se l'auto-riparazione non è stata possibile (nessun nome
                # dizionario riconoscibile nella richiesta) o la query
                # risultante non valida per un altro motivo, resta il
                # messaggio di errore esplicito come fallback — l'utente in
                # quel caso vedrà comunque un errore chiaro, non un fallimento
                # silenzioso.
                if not is_valid:
                  errors = [type('Err', (), {
                    'message': (
                        f"NON RISCRIVERE la query da zero, NON rinominare '{used_alias}': "
                        f"ti manca solo UNA riga da aggiungere in cima, il resto della query "
                        f"che hai già scritto va bene così com'è. Esempio concreto — "
                        f"da questo (quello che hai appena generato, sbagliato):\n"
                        f"{current_query}\n"
                        f"...a questo (corretto — stessa identica query, con una sola riga "
                        f"aggiunta in cima):\n"
                        f"GET DICTIONARY <nome_collezione_dizionario>@{current_db} AS {used_alias};\n"
                        f"{current_query}"
                    )
                  })()]

            # Controllo semantico: JOIN che confronta lo stesso nome di
            # campo su due collezioni con tipi diversi per quel campo (vedi
            # _check_join_type_mismatch — non è un pattern fisso su un nome
            # specifico, guarda i tipi realmente scoperti). Non riparato in
            # automatico (a differenza dei due casi sopra): qui non sappiamo
            # con certezza quale sia il campo giusto, solo che quello scelto
            # è sospetto — meglio dirlo esplicitamente al modello e dargli
            # un altro tentativo con un indizio concreto, piuttosto che
            # indovinare noi un sostituto.
            if is_valid:
                type_mismatch_msg = _check_join_type_mismatch(current_query, db_registry.databases)
                if type_mismatch_msg:
                    is_valid = False
                    errors = [type('Err', (), {'message': type_mismatch_msg})()]

            # Controllo empirico (17/09): campi con NOMI DIVERSI, stesso
            # tipo, ma valori che non si sovrappongono mai nei dati veri —
            # vedi _check_join_key_data_overlap. Complementare al
            # controllo di tipo sopra, non sostitutivo: quello copre
            # "stesso nome, tipo diverso", questo copre "nome diverso,
            # tipo uguale, valori scorrelati".
            if is_valid:
                overlap_msg = _check_join_key_data_overlap(current_query, db_registry.databases)
                if overlap_msg:
                    is_valid = False
                    errors = [type('Err', (), {'message': overlap_msg})()]

            # Controllo semantico: riferimento a un elemento espanso
            # (.nome.item) il cui EXPAND non è mai stato dichiarato — vedi
            # _check_undeclared_expand_reference. Stessa filosofia di
            # quello sopra: non prova a indovinare il campo giusto, forza
            # un altro tentativo con l'elenco dei campi array veri.
            if is_valid:
                undeclared_msg = _check_undeclared_expand_reference(current_query, current_schema)
                if undeclared_msg:
                    is_valid = False
                    errors = [type('Err', (), {'message': undeclared_msg})()]

            if not is_valid:
                error_messages = [err.message for err in errors] if errors else ["Errore sintattico"]
                # Se avevamo rilevato leakage del prompt o l'assenza di GET COLLECTION,
                # questi suggerimenti espliciti vanno in testa: sono più utili al LLM del
                # solo errore ANTLR generico (che nel caso del leakage può arrivare a
                # dozzine di "missing SC" quasi identici e poco azionabili).
                if prompt_leakage_hint:
                    error_messages = [prompt_leakage_hint] + error_messages
                if missing_get_collection_hint:
                    error_messages = [missing_get_collection_hint] + error_messages
                all_errors.append(f"Tentativo {attempts}: {', '.join(error_messages)}")
                validation_errors_for_frontend = [{"message": msg} for msg in error_messages]

        except Exception as e:
            query_logger.error(f"⚠️ Errore durante la generazione: {e}")
            # FIX (17/09): un except Exception generico rimandava sempre lo
            # stesso 500 anche per un semplice limite di quota della API
            # Gemini (429, comune durante test ravvicinati) — l'utente
            # vedeva solo "Request failed with status code 500", niente
            # che spiegasse cosa fare (aspettare qualche secondo). Qui
            # riconosciamo il caso in base al testo dell'errore (non serve
            # sapere il nome esatto della classe di eccezione della
            # libreria Google, basta cercare i segnali che compaiono nel
            # loro stesso messaggio) e diamo un dettaglio utile — il resto
            # degli errori resta gestito come prima, invariato.
            error_str = str(e)
            if '429' in error_str or 'quota' in error_str.lower() or 'rate limit' in error_str.lower():
                raise HTTPException(
                    status_code=429,
                    detail="Limite di richieste della API Gemini raggiunto (quota gratuita esaurita per il momento) — riprova tra qualche decina di secondi."
                )
            if 'timeout' in error_str.lower() or 'deadline' in error_str.lower():
                raise HTTPException(
                    status_code=504,
                    detail="La chiamata alla API Gemini ha impiegato troppo tempo (oltre 20s) — probabilmente per un limite di quota raggiunto poco prima. Riprova tra qualche decina di secondi."
                )
            raise HTTPException(status_code=500, detail=str(e))

    result = {
        "jcoql_query": current_query,
        "is_valid": is_valid,
        "attempts": attempts,
        "validation_errors": validation_errors_for_frontend,
        "retrieved_examples": retrieved_docs,
        "llm_used": ACTIVE_LLM,
        "parser_used": parser.parser_name
    }

    # Log diagnostico degli esempi RAG recuperati per questa richiesta - utile per capire
    # se un errore del LLM dipende dal RAG (esempio giusto mai recuperato) o dal LLM stesso
    # (esempio recuperato ma non seguito correttamente). Attivo solo con JCOQL_DEBUG=true.
    if JCOQL_DEBUG:
        print(f"\n🔍 DEBUG RAG - esempi recuperati per '{request.nl_query[:60]}':")
        if retrieved_docs:
            for i, doc in enumerate(retrieved_docs, 1):
                print(f"   [{i}] {doc[:200]}")
        else:
            print("   (nessun esempio recuperato)")

    elapsed = time.time() - start_time
    query_logger.info(f"✅ Query processata in {elapsed:.3f}s | Valida: {result['is_valid']}")
    return result

# ==============================================================================
# ENDPOINT: GESTIONE MODELLI LLM E PARSER
# ==============================================================================
@app.get("/api/llms")
async def list_llms():
    return {
        "available": ["gemini", "llama", "gemma"],
        "current": ACTIVE_LLM
    }

@app.post("/api/set_llm")
async def set_llm(llm_type: str):
    global ACTIVE_LLM
    if llm_type not in ["gemini", "llama", "gemma"]:
        raise HTTPException(status_code=400, detail="LLM non valido")
    ACTIVE_LLM = llm_type
    return {"success": True, "llm": ACTIVE_LLM}

@app.get("/api/parsers")
async def list_parsers():
    return {
        "available": ParserFactory.get_available_parsers(),
        "current": ACTIVE_PARSER,
        "current_name": parser.parser_name,
        "current_version": parser.parser_version
    }

# ==============================================================================
# ENDPOINT: ESECUZIONE QUERY JCOQL SU MONGODB
# ==============================================================================
@app.post("/api/execute")
async def execute_query(request: QueryRequest):
    global executor

    exec_start_time = time.time()

    try:
        # 1. Estrazione di TUTTI i campi dalla request (evita NameError)
        jcoql_query = request.jcoql_query.strip() if request.jcoql_query else ""
        databases = request.databases or []
        database_name = request.database_name
        join_config = request.join_config
        count_only = bool(request.count_only)
        
        if not jcoql_query:
            return {"success": False, "error": "Query vuota"}

        # 2. Gestione JOIN mode (se presente)
        # FIX (15/08): join_executor.execute_join() presuppone sempre che
        # jcoql_query sia una query semplice ("GET COLLECTION nome; ...")
        # da cui costruire lui il JOIN nativo — ma dopo un'esecuzione il
        # pannello frontend si riallinea alla query REALMENTE eseguita
        # (comportamento voluto, per mostrare cosa gira davvero), che per
        # un JOIN è già un "JOIN OF COLLECTIONS ...;" completo. Se poi si
        # riesegue senza rigenerare da linguaggio naturale, join_config è
        # ancora attivo ma jcoql_query non è più una query semplice —
        # join_executor falliva con "Impossibile estrarre il nome della
        # collection" perché cercava un pattern "GET COLLECTION" che non
        # c'è più. Se il testo è già una query JOIN completa, la eseguiamo
        # così com'è (stesso percorso di qualunque altra query diretta),
        # invece di provare a ricostruirla da zero.
        query_is_already_join = bool(re.search(r'JOIN\s+OF\s+COLLECTIONS', jcoql_query, re.IGNORECASE))

        if join_config and len(databases) >= 2 and not query_is_already_join:
            query_logger.info("🔗 JOIN MODE ATTIVATO")
            join_executor = JoinExecutor(ExecutorFactory, parser, db_registry)
            actual_results, native_join_query, join_error = join_executor.execute_join(jcoql_query, join_config)

            # Se la query nativa non è stata nemmeno costruita (es. tipo di
            # JOIN diverso da INNER, non supportato — vedi docstring di
            # join_executor.py) o l'esecuzione sul motore è fallita,
            # restituiamo l'errore vero invece di un silenzioso "0 risultati"
            # che sembrerebbe un JOIN semplicemente senza corrispondenze.
            if join_error:
                query_logger.warning(f"⚠️ JOIN non riuscito: {join_error}")
                return {"success": False, "error": join_error}

            actual_count = len(actual_results)
            # Stringa solo descrittiva per il campo "database" della
            # risposta (usata per il testo mostrato in UI) — "db1 ⊕ db2"
            # non è un nome di database Mongo valido, è per questo che
            # QueryExecutor.jsx (frontend) tratta il caso join_config
            # presente separatamente, mostrando la query nativa reale
            # (native_join_query) invece di usare questo valore come se
            # fosse un database singolo.
            target_db = f"{join_config.get('db1', '')} ⊕ {join_config.get('db2', '')}"
            
            return {
                "success": True,
                "jcoql_query": native_join_query or jcoql_query,
                "count": actual_count,
                "results": actual_results,
                "database": target_db,
                "join_config": join_config,
                "mongo_query": None
            }

        # 3. Determinazione dinamica del Database Target dal registro o dalla request
        target_db = database_name or db_registry.get_current_database_name() or "jcoql_test"

        # Ricrea l'executor se il database è diverso
        # Nota: questo controllo funziona solo con l'executor
        # jco_framework_executor_v2.py, che imposta self.database_name
        # nel proprio __init__ (verificato). L'executor alternativo
        # python_translator.py (ExecutorType.PYTHON_TRANSLATOR) non
        # imposta questo attributo — se ACTIVE_EXECUTOR è impostato su
        # "python_translator", hasattr(executor, 'database_name') è
        # sempre False dopo la prima creazione, quindi l'executor non
        # viene mai ricreato al cambio di database target: le richieste
        # successive continuerebbero a interrogare il primo database con
        # cui l'executor è stato creato, indipendentemente da target_db.
        # Con l'executor di default (jco_framework) questo non succede.
        if not executor or (hasattr(executor, 'database_name') and executor.database_name != target_db):
            query_logger.info(f"🔄 Ricreazione executor per database: {target_db}")
            executor = ExecutorFactory.create_executor(
                ExecutorType(ACTIVE_EXECUTOR),
                mongo_uri="mongodb://localhost:27017",
                database=target_db
            )

        is_valid, errors = parser.validate(jcoql_query)
        if not is_valid:
            # FIX: prima veniva scartato il dettaglio vero di 'errors' (riga,
            # colonna, messaggio del parser) e restituito solo "Query non
            # valida" — impossibile da diagnosticare lato utente, e i log di
            # debug non venivano nemmeno raggiunti perché l'esecuzione si
            # fermava già qui, prima di arrivare all'executor.
            query_logger.warning(f"⚠️ Query non valida: {jcoql_query}")
            query_logger.warning(f"   Errori parser: {errors}")
            # FIX (16/08): str(e) su un oggetto ValidationError stampa il
            # repr Python di default ("<... object at 0x...>"), non il
            # messaggio — mai notato prima perché 'errors' era sempre vuota
            # in questo punto specifico (altro bug, corretto in
            # java_parser_wrapper.py), quindi il ramo "else" veniva sempre
            # preso. Va usato l'attributo .message dell'oggetto.
            return {
                "success": False,
                "error": "Query non valida: " + "; ".join(e.message for e in errors) if errors else "Query non valida"
            }

        query_logger.info(f"📤 Esecuzione: {jcoql_query}")
        query_logger.info(f"📦 Database Attivo: {target_db}") 

        # 4. Esecuzione passando il database target dinamico
        # Modalità "database di grandi dimensioni / risultato non necessario"
        # (count_only): salta il SAVE AS automatico usato per rileggere i
        # documenti dal browser, restituisce solo il conteggio stampato dal
        # motore - vedi execute_count_only() in jco_framework_executor_v2.py.
        # hasattr: l'executor alternativo python_translator.py non ha questo
        # metodo (non ne ha bisogno, legge già sempre da pymongo diretto) -
        # in quel caso il flag viene ignorato silenziosamente, comportamento
        # equivalente a count_only=False.
        if count_only and hasattr(executor, 'execute_count_only'):
            query_logger.info("📊 Modalità count-only attiva (nessun SAVE AS automatico)")
            execution_result = executor.execute_count_only(jcoql_query)
        else:
            execution_result = executor.execute(jcoql_query)
        exec_elapsed = time.time() - exec_start_time
        query_logger.info(f"⏱️ Esecuzione completata in {exec_elapsed:.3f}s")

        # Log diagnostico di riepilogo di cosa ritorna l'executor (riepilogo, non il
        # dump completo - con centinaia di documenti pesanti il dump intero rendeva
        # illeggibile la console). Attivo solo con JCOQL_DEBUG=true.
        if JCOQL_DEBUG:
            print(f"\n🔍 DEBUG execution_result keys: {execution_result.keys() if isinstance(execution_result, dict) else 'NOT A DICT'}")
            if isinstance(execution_result, dict):
                _dbg_count = execution_result.get('count', execution_result.get('doc_count', '?'))
                _dbg_results = execution_result.get('results', [])
                print(f"   success={execution_result.get('success')} count={_dbg_count} "
                      f"n_results_inviati={len(_dbg_results) if isinstance(_dbg_results, list) else '?'}")
                if isinstance(_dbg_results, list) and _dbg_results:
                    _first = str(_dbg_results[0])
                    print(f"   primo risultato (troncato a 300 char): {_first[:300]}")
                if execution_result.get('error'):
                    print(f"   error: {execution_result.get('error')}")

        actual_count = 0
        actual_results = []

        # Normalizzazione della forma di execution_result: i due executor
        # (jco_framework_executor_v2.py e python_translator.py) non
        # restituiscono esattamente la stessa struttura dati (uno passa
        # da un motore Java esterno con un formato di risposta più
        # articolato, l'altro è puro Python/pymongo con un dict più
        # semplice) — i rami sotto gestiscono le diverse combinazioni
        # osservate invece di assumerne una sola.
        if isinstance(execution_result, dict):
            if execution_result.get('success'):
                # Controlla se 'count' esiste direttamente in execution_result
                if 'count' in execution_result:
                    actual_count = execution_result['count']
                    actual_results = execution_result.get('results', [])
                else:
                    results = execution_result.get('results', {})
                    if isinstance(results, list):
                        actual_results = results
                        actual_count = execution_result.get('doc_count', len(actual_results))
                    elif isinstance(results, dict):
                        actual_results = results.get('data', results.get('text', []))
                        actual_count = results.get('doc_count', len(actual_results) if isinstance(actual_results, list) else 0)
                    else:
                        actual_results = results
                        actual_count = 1 if results else 0
            else:
                error_msg = execution_result.get('error', 'Errore sconosciuto')
                query_logger.error(f"❌ Errore Executor: {error_msg}")
                return {"success": False, "error": error_msg}

        # Trasparenza sul risultato (17/09): non blocca né modifica
        # nulla, vedi _find_unresolved_id_references — solo una nota se
        # il risultato contiene riferimenti .item.item.XXX_id mai
        # risolti con un JOIN successivo, così l'utente non deve
        # indovinare da solo se il risultato è completo.
        unresolved_refs = _find_unresolved_id_references(actual_results) if isinstance(actual_results, list) else []
        response = {
            "success": True,
            "jcoql_query": jcoql_query,
            "count": actual_count,
            "results": actual_results,
            "database": target_db,
            "mongo_query": None
        }
        if unresolved_refs:
            examples_str = ", ".join(f"{path} = {val!r}" for path, val in unresolved_refs)
            response["warning"] = (
                f"Il risultato contiene riferimenti non risolti dentro un elemento espanso "
                f"(es. {examples_str}) — se ti aspettavi anche i dati collegati a quel "
                f"riferimento, potrebbe mancare un JOIN successivo nella query."
            )
        return response

    except Exception as e:
        import traceback
        query_logger.error(f"❌ Errore non gestito in /api/execute: {e}")
        query_logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# ENDPOINT: GESTIONE COLLEZIONI MONGODB
# ==============================================================================
# 🔴 Attenzione — i 4 endpoint di questa sezione presuppongono che
# l'"executor" globale abbia un attributo .db (un oggetto pymongo
# Database). Questo è vero SOLO per python_translator.py
# (self.db = self.client[database], verificato), ma NON per
# jco_framework_executor_v2.py (verificato: nessun self.db, nessuna
# property "db" in tutto il file — la classe tiene solo mongo_uri e
# database_name come stringhe, senza una connessione pymongo persistente
# in un attributo con questo nome). Dato che ACTIVE_EXECUTOR di default è
# "jco_framework" (riga ~90), nella configurazione standard del progetto
# questi 4 endpoint sollevano AttributeError ad ogni chiamata — catturato
# dal blocco try/except di ciascuno e restituito come errore 500, quindi
# l'app non si blocca, ma questi endpoint non funzionano nella
# configurazione di default. È la stessa causa per cui il componente
# frontend UploadData.jsx, che li usa, è stato scollegato dal router
# (vedi il commento in cima a quel file).
@app.get("/api/collections")
async def list_collections():
    try:
        collections = executor.db.list_collection_names()
        return JSONResponse(content={
            'collections': collections,
            'database': executor.db.name
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})

@app.post("/api/upload-collection")
async def upload_collection(
    file: UploadFile = File(...),
    collection_name: str = None
):
    try:
        content = await file.read()
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return JSONResponse(
                status_code=400,
                content={'success': False, 'error': f'File JSON non valido: {str(e)}'}
            )
        
        if not isinstance(data, list) or len(data) == 0:
            return JSONResponse(
                status_code=400,
                content={'success': False, 'error': 'Il file deve contenere un array JSON non vuoto di documenti.'}
            )
        
        if not collection_name:
            collection_name = file.filename.replace('.json', '').lower()
            collection_name = ''.join(c for c in collection_name if c.isalnum() or c == '_')
        
        coll_ref = executor.db[collection_name]
        insert_result = coll_ref.insert_many(data)
        
        return JSONResponse(content={
            'success': True,
            'collection': collection_name,
            'documents_count': len(insert_result.inserted_ids),
            'message': f'Collection "{collection_name}" creata con {len(insert_result.inserted_ids)} documenti'
        })
        
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

@app.delete("/api/collections/{collection_name}")
async def delete_collection(collection_name: str):
    try:
        executor.db.drop_collection(collection_name)
        return JSONResponse(content={
            'success': True,
            'message': f'Collection "{collection_name}" eliminata con successo'
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

@app.get("/api/collections/{collection_name}/count")
async def get_collection_count(collection_name: str):
    try:
        count = executor.db[collection_name].count_documents({})
        return JSONResponse(content={'collection': collection_name, 'count': count})
    except Exception as e:
        return JSONResponse(status_code=500, content={'error': str(e)})

# ==============================================================================
# ENDPOINT: GESTIONE MULTI-DATABASE
# ==============================================================================
@app.get("/api/databases")
async def list_databases():
    """Restituisce la lista di tutti i database registrati"""
    try:
        databases_list = db_registry.list_databases()
        
        return {
            "databases": databases_list,
            "current": db_registry.get_current_database_name(),
            # Chiave presente nella risposta ma sempre vuota: nessun
            # codice la valorizza, e nessun componente del frontend la
            # legge (verificato) — campo vestigiale, non collegato a
            # nulla.
            "schemas": {}
        }
    except Exception as e:
        db_logger.error(f"❌ Errore /api/databases: {e}", exc_info=True)
        return {
            "databases": [],
            "current": "none",
            "schemas": {},
            "error": str(e)
        }

@app.post("/api/databases/select")
async def select_database(database_name: str = Query(None), request: Request = None):
    """
    Seleziona un database

    Accetta il nome sia come query parameter (?database_name=...) sia nel
    body JSON (chiave "database_name" o "database") — il fallback al
    body scatta solo se il query parameter non è stato fornito.
    """
    try:
        if not database_name and request:
            try:
                data = await request.json()
                database_name = data.get("database_name") or data.get("database")
            except:
                pass
        
        if not database_name:
            return {"success": False, "error": "database_name mancante"}
        
        success = db_registry.set_current_database(database_name)
        
        if success:
            global GLOBAL_SCHEMA, executor
            
            GLOBAL_SCHEMA = db_registry.get_current_schema()
            
            # Ricrea l'executor solo se ne esisteva già uno (executor
            # era rimasto None, es. per un errore all'avvio, questa
            # selezione non lo ripara).
            if executor:
                executor = ExecutorFactory.create_executor(
                    ExecutorType(ACTIVE_EXECUTOR), 
                    mongo_uri="mongodb://localhost:27017", 
                    database=database_name
                )
            
            return {
                "success": True,
                "current_database": database_name,
                "collections": len(GLOBAL_SCHEMA) if GLOBAL_SCHEMA else 0,
                "message": f"Database '{database_name}' selezionato"
            }
        
        return {"success": False, "error": f"Database '{database_name}' non trovato"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/databases/connect")
async def connect_database(db_name: str, mongo_uri: str, database_name: str):
    """
    Connetti a un database MongoDB

    I tre parametri arrivano come query string (non un body JSON) — il
    form "Connetti Nuovo Database" di DatabaseSelector.jsx (frontend) li
    concatena con fetch() senza encodeURIComponent, quindi un valore con
    caratteri speciali (spazio, '&', '@' in mongo_uri) altererebbe la
    query string prima ancora di arrivare qui (vedi il commento in
    DatabaseSelector.jsx, handleAddDatabase).
    """
    try:
        # add_database (vedi database_registry.py) esegue qui la schema
        # discovery in modo sincrono/bloccante — questa richiesta HTTP
        # non risponde finché la scoperta schema non è completata.
        db_registry.add_database(
            db_name=db_name,
            mongo_uri=mongo_uri,
            database_name=database_name
        )
        
        from backend.database_persistence import save_databases_to_file
        save_databases_to_file(db_registry)
        
        return {
            "success": True,
            "database": database_name,
            "message": f"✅ Connesso a {database_name}"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/databases/disconnect")
async def disconnect_database(db_name: str):
    try:
        if db_name not in db_registry.databases:
            return {
                "success": False,
                "message": f"Database '{db_name}' non trovato"
            }
        
        # FIX: chiude la connessione MongoDB prima di scartare la entry
        # (altrimenti il client resta aperto in memoria senza che nulla
        # lo referenzi più — piccola perdita di risorse ad ogni disconnect).
        try:
            db_registry.databases[db_name]["client"].close()
        except Exception:
            pass

        was_current = (db_name == db_registry.current_database)
        db_registry.databases.pop(db_name)
        db_logger.info(f"✅ Database '{db_name}' scollegato")

        # FIX: se il database appena scollegato era quello "corrente",
        # db_registry.current_database restava un nome non più presente
        # in db_registry.databases. La prossima chiamata a
        # get_current_schema() (es. dentro /api/generate) faceva
        # self.databases[self.current_database]["schema"] su una chiave
        # inesistente, sollevando KeyError non gestito — quindi la
        # generazione della query successiva falliva con un errore 500
        # generico, apparentemente scollegato dall'azione di disconnect
        # appena fatta. Ora si riassegna current_database a un database
        # ancora connesso rimasto (se ce n'è uno), altrimenti a None.
        if was_current:
            remaining = list(db_registry.databases.keys())
            db_registry.current_database = remaining[0] if remaining else None

        save_databases_to_file(db_registry)
        
        return {
            "success": True,
            "message": f"Database '{db_name}' scollegato con successo"
        }
    except Exception as err:
        db_logger.error(f"❌ Errore scollegamento database '{db_name}': {err}")
        return {"success": False, "message": str(err)}

@app.get("/api/databases/{db_name}")
async def get_database_info(db_name: str):
    info = db_registry.get_database_info(db_name)
    if info:
        return info
    return {"error": f"Database '{db_name}' non trovato"}

@app.get("/api/stats")
async def get_stats():
    try:
        db_list = []
        collections_count = 0
        
        try:
            for db_name, db_info in db_registry.databases.items():
                db_list.append(db_name)
                # FIX: db_info è il dizionario di metadati salvato da
                # DatabaseRegistry.add_database() (uri, database_name,
                # schema, client, collections) — non una connessione
                # MongoDB. Prima qui si chiamava db_conn.list_collection_names()
                # su questo stesso dizionario, che non ha quel metodo:
                # l'AttributeError veniva ingoiato dal except sotto e
                # collections_count restava sempre a 0. Il conteggio
                # corretto è già calcolato e salvato in add_database
                # come db_info["collections"] (len(schema) al momento
                # della connessione) — lo si usa direttamente, senza
                # bisogno di richiamare Mongo.
                try:
                    collections_count += db_info.get("collections", 0)
                except Exception:
                    pass
        except Exception as db_err:
            db_logger.warning(f"⚠️ Errore accesso databases: {db_err}")
            db_list = ['jcoql_test']
            collections_count = 0
        
        return {
            "executor": {
                "name": ACTIVE_EXECUTOR,
                "status": "active",
                "parser": parser.parser_name
            },
            "databases": {
                "count": len(db_list),
                "list": db_list,
                "collections_total": collections_count
            },
            "llms": {
                "available": ["gemini", "llama", "gemma"],
                "current": ACTIVE_LLM
            },
            "system": {
                # FIX: prima era un valore fisso (3600 = sempre "1h" in
                # Dashboard.jsx, indipendentemente da quanto il server
                # fosse realmente attivo). Calcolato ora dal timestamp di
                # avvio del processo (APP_START_TIME, impostato
                # all'inizio del file).
                "uptime_seconds": int(time.time() - APP_START_TIME),
                "version": "1.0.0-production"
            }
        }
    except Exception as err:
        return {
            "executor": {"name": ACTIVE_EXECUTOR, "status": "error"},
            "databases": {"count": 0, "list": [], "collections_total": 0},
            "llms": {"available": [], "current": None},
            "system": {"uptime_seconds": 0, "version": "1.0.0"}
        }