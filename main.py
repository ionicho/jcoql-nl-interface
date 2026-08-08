#!/usr/bin/env python3
"""
JCoQL+ Natural Language Interface - Main Application
Modulo principale FastAPI per la traduzione da linguaggio naturale a query JCoQL+
e per l'esecuzione/gestione dei database MongoDB.
"""

# IMPORT LIBRERIE STANDARD E TERZE PARTI
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


# CONFIGURAZIONE PATH E MODULI INTERNI
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


# INIZIALIZZAZIONE CONFIGURAZIONE ED AMBIENTE
load_dotenv()

# Timestamp di avvio del processo, usato da /api/stats per calcolare
# l'uptime reale (vedi sotto) invece di un valore fisso.
APP_START_TIME = time.time()

# Caricamento regole sintattiche
def load_file_content(path: str) -> str:
    # In caso di errore (es. file mancante) ritorna una stringa vuota
    # invece di sollevare l'eccezione — l'app continua ad avviarsi anche
    # se uno di questi file manca, ma il prompt inviato all'LLM perde
    # silenziosamente quella parte di contesto.
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return ""

JCOQL_SYNTAX_FULL = load_file_content('backend/jcoql_syntax_official.txt')
JCOQL_SYNTAX_BASIC = load_file_content('backend/jcoql_syntax_basic_official.txt')
EXTENDED_EXAMPLES = load_file_content('backend/rag_examples_extended.txt')
# Nota: JCOQL_SYNTAX_FULL viene caricato qui ma non è mai inserito in
# nessun prompt più avanti nel file — solo JCOQL_SYNTAX_BASIC ed
# EXTENDED_EXAMPLES vengono effettivamente usati (vedi la costruzione del
# prompt più sotto, verso la riga 397-399). Il caricamento di
# jcoql_syntax_official.txt (1633 righe) avviene comunque ad ogni avvio,
# senza che il contenuto raggiunga mai l'LLM.

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



# FASTAPI APP & MIDDLEWARE
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
    max_retries: int = 3

class QueryRequest(BaseModel):
    jcoql_query: str = ""
    database_name: Optional[str] = None
    databases: List[str] = ["jcoql_test"]
    join_config: Optional[dict] = None


# LIFECYCLE EVENTS

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


# ENDPOINT: GENERAZIONE QUERY JCOQL (NL -> JCoQL)

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
                        # Estrai il tipo
                        if isinstance(field_info, dict):
                            field_type = field_info.get('type', 'unknown')
                            if isinstance(field_type, list):
                                field_type = ', '.join(field_type) if field_type else 'unknown'
                        else:
                            field_type = type(field_info).__name__
                        schema_prompt_str += f"  .{field_name} ({field_type})\n"
            
            schema_prompt_str += "\n"
    else:
        schema_prompt_str = f"""SCHEMA MONGODB - Database '{db_registry.get_current_database_name()}'
    Nessuna collezione disponibile in questo database."""

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

        • EXPAND — l'utente chiede ESPLICITAMENTE "un documento/risultato separato per ogni
          elemento" di un array (es. "elenca ogni attore di ogni film separatamente", "un
          risultato per ogni genere"):
          GET COLLECTION collezione;
          EXPAND UNPACK TRUE ARRAY .campoArray TO .campoDestinazione;
          Opzionali KEEP OTHERS / DROP OTHERS per i documenti privi di quell'array.

          🚨 NON usare EXPAND per un semplice controllo "l'array contiene questo valore"
          (es. "film con l'attore X", "prodotti con il tag Y") - in quel caso basta un FILTER
          diretto sul campo array, senza espanderlo:
          GET COLLECTION movies;
          FILTER CASE WHERE .cast = 'Claudio Bisio' KEEP OTHERS;
          Questo funziona perché confrontare un campo array con un valore singolo (es.
          .cast = 'valore') controlla automaticamente se l'array CONTIENE quel valore - non
          serve nessun operatore speciale, e NON esiste comunque un operatore CONTAINS in
          JCoQL+ (non scriverlo mai). Usa EXPAND SOLO quando l'utente vuole vedere ogni
          elemento come riga/documento separato nel risultato, non solo per filtrare.

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

{EXTENDED_EXAMPLES}

{JCOQL_SYNTAX_BASIC}

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

            # Fix: applicato a TUTTI i modelli locali (Llama e Gemma), non solo Llama.
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

            # Validazione sintattica ANTLR
            is_valid, errors = parser.validate(current_query)
            
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


# ENDPOINT: GESTIONE MODELLI LLM E PARSER

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


# ENDPOINT: ESECUZIONE QUERY JCOQL SU MONGODB

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
            actual_results = join_executor.execute_join(jcoql_query, join_config)
            actual_count = len(actual_results)
            # Stringa solo descrittiva per il campo "database" della
            # risposta (usata per il testo mostrato in UI) — "db1 ⊕ db2"
            # non è un nome di database Mongo valido, è per questo che
            # QueryExecutor.jsx (frontend) tratta il caso join_config
            # presente separatamente, mostrando le due USE DB reali
            # invece di usare questo valore come se fosse un database
            # singolo (vedi il commento in quel file).
            target_db = f"{join_config.get('db1', '')} ⊕ {join_config.get('db2', '')}"
            
            return {
                "success": True,
                "jcoql_query": jcoql_query,
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
            return {"success": False, "error": "Query non valida"}

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


# ENDPOINT: GESTIONE COLLEZIONI MONGODB

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


# ENDPOINT: GESTIONE MULTI-DATABASE

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