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
        if coll1.lower().startswith('chaintemp') or coll2.lower().startswith('chaintemp'):
            continue
        if field1 != field2:
            continue
        alias_to_coll_db = {alias1: (coll1, db1), alias2: (coll2, db2)}
        if cond_alias1 not in alias_to_coll_db or cond_alias2 not in alias_to_coll_db:
            continue
        coll_a, db_a = alias_to_coll_db[cond_alias1]
        coll_b, db_b = alias_to_coll_db[cond_alias2]
        type_a = _lookup_field_type(all_databases, db_a, coll_a, field1)
        type_b = _lookup_field_type(all_databases, db_b, coll_b, field2)
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
model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

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
    if collection:
        try:
            results = collection.query(
                query_texts=[request.nl_query],
                n_results=6
            )
            retrieved_docs = results['documents'][0] if (results and results.get('documents')) else []
            context_str = "\n\n".join(retrieved_docs)
        except Exception as e:
            query_logger.warning(f"⚠️ Errore RAG: {e}")

    # Schema prompt
    current_schema = db_registry.get_current_schema()
    if current_schema:
        schema_prompt_str = f"SCHEMA MONGODB REALE (Database: {db_registry.get_current_database_name()}):\n\n"
        for coll_name, coll_data in current_schema.items():
            schema_prompt_str += f"COLLECTION: {coll_name}\n"
            
            # Estrai i campi da coll_data['fields']
            if isinstance(coll_data, dict):
                fields = coll_data.get('fields', {})
                if isinstance(fields, dict):
                    for field_name, field_info in fields.items():
                        # FIX (15/08): schema_discovery.py scrive la chiave
                        # "types" (plurale, una lista — vedi quel file), ma
                        # qui si cercava "type" (singolare) che non esiste
                        # mai in quella struttura — field_type risultava
                        # SEMPRE "unknown" per ogni campo di ogni collection,
                        # per tutta la sessione. L'LLM non ha mai visto un
                        # tipo vero finora.
                        if isinstance(field_info, dict):
                            field_type = field_info.get('types', field_info.get('type', 'unknown'))
                            if isinstance(field_type, list):
                                field_type = ', '.join(field_type) if field_type else 'unknown'
                            examples = field_info.get('examples', [])
                        else:
                            field_type = type(field_info).__name__
                            examples = []
                        # Aggiunti valori di esempio reali (già raccolti da
                        # schema_discovery.py ma mai mostrati finora) — utili
                        # perché l'LLM possa distinguere due campi con lo
                        # stesso nome ma contenuto/tipo diverso tra due
                        # collezioni (es. un "user_id" stringa vs uno numerico),
                        # invece di scegliere quello sbagliato solo perché il
                        # nome coincide.
                        examples_str = ''
                        if examples:
                            ex_display = [str(e)[:40] for e in examples[:2] if e is not None]
                            if ex_display:
                                examples_str = f" — es: {', '.join(ex_display)}"
                        schema_prompt_str += f"  .{field_name} ({field_type}){examples_str}\n"
            
            schema_prompt_str += "\n"
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
            "\nALTRI DATABASE SELEZIONATI DALL'UTENTE (disponibili, oltre a quello sopra):\n"
            + ", ".join(other_databases)
            + "\nSe l'utente chiede di cercare/unire dati \"su tutti i database selezionati\" o simili, "
              "usa ESATTAMENTE questi nomi (più quello corrente sopra) — non inventare nomi di database, "
              "e non confonderli con nomi di collection.\n"
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

        🚨 REGOLA CRITICA #2 - SINTASSI ISNOTNULL:
        ❌ NON usare: FIELD .campo ISNOTNULL
        ❌ NON usare: .campo IS NOT NULL
        ✅ USA SOLO: FILTER CASE WHERE .campo IS NOT NULL KEEP OTHERS;
        
        Oppure per campi con valore:
        ✅ FILTER CASE WHERE .campo = 'valore' KEEP OTHERS;

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
          Se l'utente chiede raggruppamenti diversi/paralleli nella stessa richiesta (es. "sia
          per categoria sia per fascia di prezzo"), puoi mettere più PARTITION in un solo
          comando GROUP, una di seguito all'altra prima del punto e virgola finale:
          GROUP PARTITION cond1 BY .campo1 INTO .risultato1
                PARTITION cond2 BY .campo2 INTO .risultato2;

        • EXPAND — l'utente chiede di "espandere" un array, o "un documento/risultato per ogni
          elemento di" un campo che è una lista:
          GET COLLECTION collezione;
          EXPAND UNPACK TRUE ARRAY .campoArray TO .campoDestinazione;
          Opzionali KEEP OTHERS / DROP OTHERS per i documenti privi di quell'array.
          Se l'utente chiede di espandere PIÙ array nella stessa richiesta, puoi mettere più
          UNPACK in un solo comando EXPAND, uno di seguito all'altro prima del KEEP/DROP OTHERS
          finale (che si applica a tutto il comando, non va ripetuto per ogni UNPACK):
          EXPAND UNPACK TRUE ARRAY .campoArray1 TO .dest1
                 UNPACK TRUE ARRAY .campoArray2 TO .dest2
          KEEP OTHERS;

        • MERGE — l'utente chiede di "unire tutti i documenti"/"combinare" due collezioni intere:
          MERGE COLLECTIONS collezione1, collezione2;
          Opzionale REMOVE DUPLICATES.

        • INTERSECT — l'utente chiede "cosa hanno in comune" due collezioni, o i documenti
          presenti in entrambe:
          INTERSECT COLLECTIONS collezione1, collezione2;

        • SUBTRACT — l'utente chiede i documenti "presenti in X ma non in Y":
          SUBTRACT COLLECTIONS collezione1, collezione2;

        • SAVE AS — l'utente chiede di "salvare"/"creare una copia"/"fare un backup" del
          risultato come nuova collezione:
          GET COLLECTION collezione; [eventuali FILTER/GROUP/EXPAND]
          SAVE AS nuovoNome@{current_db};
          🚨 IMPORTANTE: il database dopo @ è SEMPRE OBBLIGATORIO. "SAVE AS nome;" senza
          @database NON scrive su MongoDB (salva solo temporaneamente nella pipeline interna).
          Se l'utente chiede di salvare, includi SEMPRE @{current_db} (o il database indicato
          esplicitamente dall'utente).

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
          CASE WHERE .c.elemento.elemento.campoInterno = .d.chiave3;
          🚨🚨 ATTENZIONE al percorso dopo EXPAND: il nome scelto dopo TO (es. "elemento") NON
          diventa direttamente il contenuto dell'elemento — EXPAND lo avvolge in un oggetto con
          DUE campi, uno chiamato come il nome scelto stesso (contenente l'elemento vero) e uno
          chiamato "position" (l'indice). Quindi il percorso per arrivare a un campo interno
          all'elemento è SEMPRE .alias.nomeScelto.nomeScelto.campoInterno (il nome ripetuto due
          volte), non .alias.nomeScelto.campoInterno — verificato empiricamente sul motore reale,
          è un dettaglio facile da sbagliare.
          🚨 SCEGLIERE IL CAMPO GIUSTO PER UN JOIN — quando due collezioni hanno campi con lo
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

        try:
            # Promemoria extra SOLO per i modelli locali (Llama/Gemma), che nei test si
            # sono dimostrati più propensi a usare solo l'ultimo segmento di un campo
            # annidato (es. .rating invece di .imdb.rating) invece di leggere il percorso
            # completo dallo schema. Regola generica su come leggere lo schema, non legata
            # a nessun database specifico - si applica a qualunque campo annidato di
            # qualunque database connesso.
            local_model_prompt = prompt
            if ACTIVE_LLM in ("llama", "gemma"):
                local_model_prompt = prompt + (
                    "\n\nATTENZIONE - CAMPI ANNIDATI: nello SCHEMA MONGODB REALE sopra, se un "
                    "campo appare con un punto nel nome (es. 'imdb.rating', 'location.city'), "
                    "quello è un campo ANNIDATO: DEVI usare il percorso completo con il punto "
                    "nella query (es. .imdb.rating, .location.city), MAI solo l'ultimo segmento "
                    "(MAI .rating da solo se lo schema mostra imdb.rating). Controlla sempre lo "
                    "schema prima di scegliere un nome di campo."
                )

            if ACTIVE_LLM == "llama":
                current_query = generate_with_llama(local_model_prompt)
            elif ACTIVE_LLM == "gemma":
                current_query = generate_with_gemma(local_model_prompt)
            else:
                response = model.generate_content(prompt)
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
        
        if not jcoql_query:
            return {"success": False, "error": "Query vuota"}

        # 2. Gestione JOIN mode (se presente)
        if join_config and len(databases) >= 2:
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
            return {
                "success": False,
                "error": "Query non valida: " + "; ".join(str(e) for e in errors) if errors else "Query non valida"
            }

        query_logger.info(f"📤 Esecuzione: {jcoql_query}")
        query_logger.info(f"📦 Database Attivo: {target_db}") 

        # 4. Esecuzione passando il database target dinamico
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

        return {
            "success": True,
            "jcoql_query": jcoql_query,
            "count": actual_count,
            "results": actual_results,
            "database": target_db,
            "mongo_query": None
        }

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