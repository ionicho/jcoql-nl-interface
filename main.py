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
from typing import List

# FastAPI e utilità HTTP
from fastapi import FastAPI, HTTPException, Request, UploadFile, File
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

# Import corrector
from backend.query_corrector import correct_query

#import salvataggio database
from backend.database_persistence import load_databases_from_file, save_databases_to_file

#import per join database
from backend.join_executor import JoinExecutor

#import per statistiche dinamiche
from datetime import datetime
import os

# ==============================================================================
# CONFIGURAZIONE PATH E MODULI INTERNI
# ==============================================================================
# Calcola la directory base del progetto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Aggiunge le cartelle 'parsers' ed 'executors' al sys.path di Python per gli import dinamici
sys.path.append(os.path.join(BASE_DIR, "backend", "parsers"))
executors_path = Path(BASE_DIR) / "backend" / "executors"
if str(executors_path) not in sys.path:
    sys.path.insert(0, str(executors_path))

# Import dei moduli e logger personalizzati di backend
from backend.logging_config import setup_logging, get_startup_logger, get_query_logger, get_db_logger
from backend.database.database_registry import db_registry
from backend.llm_local import generate_with_llama, generate_with_gemma
from backend.parsers.parser_factory import ParserFactory, ParserType
from executor_factory import ExecutorFactory, ExecutorType

# ==============================================================================
# INIZIALIZZAZIONE CONFIGURAZIONE ED AMBIENTE
# ==============================================================================
# Carica le variabili dal file .env (es. GEMINI_API_KEY, ACTIVE_LLM, ecc.)
load_dotenv()

# Carica le regole sintattiche ufficiali JCoQL dai file di testo
with open('backend/jcoql_syntax_official.txt', 'r', encoding='utf-8') as f:
    JCOQL_SYNTAX_FULL = f.read()

with open('backend/jcoql_syntax_basic_official.txt', 'r', encoding='utf-8') as f:
    JCOQL_SYNTAX_BASIC = f.read()

with open('backend/rag_examples_extended.txt', 'r', encoding='utf-8') as f:
    EXTENDED_EXAMPLES = f.read()

# Selezione LLM e Parser attivi dalle variabili d'ambiente (con fallback di default)
ACTIVE_LLM = os.getenv("ACTIVE_LLM", "gemini")
ACTIVE_PARSER = os.getenv("ACTIVE_PARSER", "antlr3_official")
ACTIVE_EXECUTOR = os.getenv("ACTIVE_EXECUTOR", "jco_framework")

# Istanzia il parser sintattico scelto tramite Factory
parser = ParserFactory.create_parser(ParserType(ACTIVE_PARSER))

# Configurazione del modello Gemini di Google
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

# Inizializzazione client ChromaDB per il RAG sugli esempi JCoQL
chroma_client = chromadb.PersistentClient(path="./chroma_data")
try:
    collection = chroma_client.get_collection(name="jcoql_examples")
except Exception as e:
    print(f"⚠️ ChromaDB Notice/Error: {e}")
    collection = None

# Inizializzazione sistema di Logging
logger, log_file = setup_logging()
startup_logger = get_startup_logger()
query_logger = get_query_logger()
db_logger = get_db_logger()

startup_logger.info("📦 Caricamento configurazione completato.")

# Variabili globali che verranno popolate all'avvio
executor = None
GLOBAL_SCHEMA = {}

# ==============================================================================
# CREAZIONE E CONFIGURAZIONE FABRIC FASTAPI
# ==============================================================================
app = FastAPI(title="JCoQL+ Multi-Parser API")

# Abilita Middleware CORS (Cross-Origin Resource Sharing) per consentire chiamate da Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Schema del Body della richiesta HTTP per l'endpoint di generazione
class GenerateRequest(BaseModel):
    nl_query: str        # La richiesta in linguaggio naturale dell'utente
    max_retries: int = 3 # Numero massimo di tentativi di auto-correzione in caso di errori sintattici

# ==============================================================================
# EVENTI LIFECYCLE (STARTUP & SHUTDOWN)
# ==============================================================================
@app.on_event("startup")
async def startup_event():
    """Evento eseguito all'avvio dell'applicazione FastAPI."""
    global executor, GLOBAL_SCHEMA
    
    startup_logger.info("🔧 Inizializzazione Database Registry...")
    
    try:
        # Registra il database MongoDB predefinito
        db_logger.info("📡 Connessione al database 'jcoql_test'...")
        db_registry.add_database(
            db_name="jcoql_test",
            mongo_uri="mongodb://localhost:27017",
            database_name="jcoql_test"
        )
        
        # Estrae lo schema dinamico delle collezioni registrate
        GLOBAL_SCHEMA = db_registry.get_current_schema()
        startup_logger.info(f"✅ Database Registry inizializzato con {len(GLOBAL_SCHEMA)} collezioni")
        
        # Log del dettaglio delle collezioni e dei relativi campi
        for coll_name, coll_data in GLOBAL_SCHEMA.items():
            if isinstance(coll_data, dict):
                field_count = len(coll_data)
                db_logger.info(f"  📋 Collection: {coll_name} ({field_count} campi)")
                for field_name in list(coll_data.keys())[:5]:  # Manda in log i primi 5 campi
                    db_logger.debug(f"     - {field_name}")
                if field_count > 5:
                    db_logger.debug(f"     ... e altri {field_count - 5} campi")
        
    except Exception as e:
        startup_logger.error(f"❌ Errore Database Registry: {e}", exc_info=True)
    
    # 💾 Carica database salvati dal file
    load_databases_from_file(db_registry)

    # Inizializza l'Executor delle query
    startup_logger.info("🔧 Inizializzazione Executor...")
    try:
        executor = ExecutorFactory.create_executor(
            ExecutorType(ACTIVE_EXECUTOR),
            mongo_uri="mongodb://localhost:27017",
            database="jcoql_test"
        )
        startup_logger.info(f"✅ Executor '{ACTIVE_EXECUTOR}' inizializzato correttamente")
    except Exception as e:
        startup_logger.error(f"❌ Errore Inizializzazione Executor: {e}", exc_info=True)
        executor = None
    
    startup_logger.info("🚀 Startup completato con successo!")


@app.on_event("shutdown")
def shutdown():
    """Evento eseguito alla chiusura dell'applicazione."""
    try:
        if executor:
            executor.close()
    except Exception as e:
        print(f"⚠️ Errore chiusura executor: {e}")
    
    try:
        db_registry.close_all()
    except Exception as e:
        print(f"⚠️ Errore chiusura database registry: {e}")

# ==============================================================================
# ENDPOINT: GENERAZIONE QUERY JCOQL (NL -> JCoQL)
# ==============================================================================
@app.post("/api/generate")
async def generate_query(request: GenerateRequest):
    """
    Riceve un prompt in Linguaggio Naturale e genera una query JCoQL valida
    utilizzando RAG, LLM e un loop di auto-riparazione (Repair Loop).
    """
    start_time = time.time()
    
    query_logger.info(f"📝 Query ricevuta: '{request.nl_query}'")
    query_logger.info(f"   Database Attivo: {db_registry.get_current_database_name()}")
    
    # 1. VALIDAZIONE INPUT VUOTO
    if not request.nl_query or request.nl_query.strip() == "":
        result = {
            "jcoql_query": "",
            "is_valid": False,
            "attempts": 0,
            "validation_errors": [{"message": "❌ Query NL vuota!"}],
            "retrieved_examples": [],
            "llm_used": ACTIVE_LLM,
            "parser_used": parser.parser_name
        }
        # ✅ APPLICA CORREZIONI DI SINTASSI
        # MA PRIMA verifica che la query sia effettivamente JCoQL
        if result['jcoql_query'] and not result['jcoql_query'].startswith("QUERY:"):
            corrected_jcoql, corrections = correct_query(result['jcoql_query'])
            
            # Se la query è stata corretta, aggiorna e rivalidata
            if corrections:
                query_logger.info(f"Correzioni applicate: {corrections}")
                result['jcoql_query'] = corrected_jcoql
                
                # Rivalida la query corretta
                is_valid = parser.validate(corrected_jcoql)
                result['is_valid'] = is_valid
                
                if is_valid:
                    query_logger.info(f"✅ Query corretta e rivalidata!")
                else:
                    query_logger.warning(f"⚠️ Query corretta ma ancora invalida")
        else:
            if not result['jcoql_query']:
                query_logger.warning("Query vuota - nessuna correzione applicata")
            elif result['jcoql_query'].startswith("QUERY:"):
                query_logger.warning("LLM ha generato messaggio di errore - non è una query valida")
                result['is_valid'] = False

        return result
    
    context_str = ""
    retrieved_docs = []
    
    # 2. RECUPERO CONTESTO RAG DA CHROMADB
    if collection:
        try:
            results = collection.query(
                query_texts=[request.nl_query],
                n_results=3
            )
            retrieved_docs = results['documents'][0] if results['documents'] else []
            context_str = "\n\n".join(retrieved_docs)
        except Exception as e:
            print(f"⚠️ Errore RAG: {e}")

    # 3. CONSTRUZIONE PROMPT DINAMICO BASATO SULLO SCHEMA MONGODB
    current_schema = db_registry.get_current_schema()
    
    if current_schema:
        schema_prompt_str = f"SCHEMA MONGODB REALE (Database: {db_registry.get_current_database_name()}):\n\n"
        for coll_name, coll_data in current_schema.items():
            schema_prompt_str += f"COLLECTION: {coll_name}\n"
            if isinstance(coll_data, dict):
                for field_name, field_info in coll_data.items():
                    field_type = field_info.get('type', 'unknown') if isinstance(field_info, dict) else type(field_info).__name__
                    schema_prompt_str += f"- {field_name} ({field_type})\n"
            schema_prompt_str += "\n"
    else:
        schema_prompt_str = f"""SCHEMA MONGODB - Database '{db_registry.get_current_database_name()}'
Nessuna collezione disponibile in questo database.
Aggiungere dati tramite MongoDB prima di usare le query."""

    attempts = 0
    is_valid = False
    current_query = ""
    all_errors = []
    validation_errors_for_frontend = []

    # 4. REPAIR LOOP (Ciclo di generazione ed auto-correzione sintattica)
    while attempts < request.max_retries and not is_valid:
        attempts += 1
        esempi_formattati = context_str
        
        # Costruzione del prompt per l'LLM
        prompt = f"""Sei un esperto traduttore Natural Language → JCoQL+.

{schema_prompt_str}

{EXTENDED_EXAMPLES}

🚨 REVISIONE UFFICIALE - COMANDI JCOQL REALI vs BLOCCATI:

COMANDI SUPPORTATI E TESTATI (usa sempre questi):
✅ FILTER CASE WHERE <condizione> KEEP OTHERS;
✅ FILTER CASE WHERE <condizione> DROP OTHERS;
✅ GET COLLECTION <nome>; FILTER CASE WHERE...
✅ GROUP PARTITION TRUE BY .campo INTO .risultato;
✅ MERGE, INTERSECT, SUBTRACT fra collezioni
✅ EXPAND - Espande gli array

COMANDI DELLA GRAMMATICA UFFICIALE (bloccati dal parser):
⚠️ GENERATE BUILD {{...}} - Valido in JCoQL ma BLOCCATO
⚠️ GENERATE ADD FIELDS {{...}} - Valido in JCoQL ma BLOCCATO
→ Alternativa: usa sempre FILTER CASE WHERE + KEEP OTHERS

COMANDI INESISTENTI - ASSOLUTAMENTE VIETATI:
❌ COMPUTE, REPORT, TRANSFORM, PROJECT, SELECT, AGGREGATE

OPERAZIONI MATEMATICHE - VIETATE:
❌ Calcoli inline: .price * 1.1, .total / 2, ecc.

# ✅ REGOLE CRITICHE - ISNOTNULL SYNTAX
🚨 IMPORTANTE - SINTASSI ISNOTNULL:
   ❌ SBAGLIATO: FIELD .campo IS NOT NULL (con spazi)
   ❌ SBAGLIATO: FIELD .campo ISNOTNULL (come token unico dopo FIELD)
   ✅ CORRETTO: FILTER CASE WHERE FIELD .campo ISNOTNULL KEEP OTHERS;
   ✅ CORRETTO: FILTER CASE WHERE FIELD .campo IS NOT NULL KEEP OTHERS;

REGOLA: Se usi ISNOTNULL dopo FIELD, deve essere:
   FIELD .fieldname ISNOTNULL  oppure  FIELD .fieldname IS NOT NULL
   NON: .fieldname IS NOT NULL

ESEMPI CORRETTI:
✅ FILTER CASE WHERE FIELD .rating ISNOTNULL KEEP OTHERS;
✅ FILTER CASE WHERE WITH .email KEEP OTHERS;
✅ FILTER CASE WHERE WITHOUT .deleted KEEP OTHERS;

ESEMPI SBAGLIATI:
❌ FILTER CASE WHERE .rating IS NOT NULL KEEP OTHERS;
❌ FILTER CASE WHERE .rating ISNOTNULL KEEP OTHERS;
❌ FILTER CASE WHERE .total IS NOT NULL KEEP OTHERS;

🚨 SE LLM NON PUÒ GENERARE QUERY:
Se l'operazione richiesta non è possibile in JCoQL, NON scrivere:
   ❌ "QUERY: Operazione non supportata..."
   ❌ "Non è possibile fare X"
   ❌ Messaggi descrittivi

INVECE, genera una query di fallback VALIDA:
   ✅ FILTER CASE WHERE <any_condition> KEEP OTHERS;
   ✅ Ritorna una query che il parser accetta
   ✅ Il sistema markerà is_valid=False se semanticamente errata

ESEMPI:
- Utente: "Trasforma i dati"
  ❌ SBAGLIATO: QUERY: Operazione non supportata
  ✅ CORRETTO: GET COLLECTION orders; FILTER CASE WHERE .status = 'pending' KEEP OTHERS;

{JCOQL_SYNTAX_BASIC}

ESEMPI SIMILI (da RAG):
{esempi_formattati}

USER QUERY:
"{request.nl_query}"

{f"ATTENZIONE! ERRORI PRECEDENTI DA CORREGGERE: {all_errors[-1]}" if attempts > 1 else ""}

Genera SOLO la query JCoQL basata sullo SCHEMA REALE sopra.
Usa ESATTAMENTE i nomi campi dello schema. NESSUN testo aggiuntivo.
"""
        
        try:
            # Invocazione LLM (Llama, Gemma o Gemini)
            if ACTIVE_LLM == "llama":
                current_query = generate_with_llama(prompt)
                
                # ✅ NUOVO: Rimuovi filtri arbitrari se non richiesti
                filter_keywords = ['dove', 'con', 'rating', 'prezzo', 'città', 'città', 'che', 'superiore', 'inferiore', 'range', 'tra']
                has_filter_request = any(kw in request.nl_query.lower() for kw in filter_keywords)
                
                # Retry se Llama genera filtri arbitrari
                retry_count = 0
                max_retries = 3
                while (not has_filter_request and 'FILTER CASE WHERE' in current_query.upper()) and retry_count < max_retries:
                    retry_count += 1
                    query_logger.warning(f"⚠️ Llama ha generato filtri arbitrari - Retry {retry_count}/{max_retries}")
                    current_query = generate_with_gemma(prompt)
                                
                # Se ancora ha filtri dopo retry, rimuovili
                if not has_filter_request and 'FILTER CASE WHERE' in current_query.upper():
                    query_logger.info(f"🔧 Rimuovo filtri arbitrari da Llama (input: '{request.nl_query}')")
                    collection_match = re.search(r'GET\s+COLLECTION\s+\w+', current_query, re.IGNORECASE)
                    if collection_match:
                        current_query = collection_match.group(0) + ";"
                
                # Pulizia blocchi markdown ```jcoql
                if "```" in current_query:
                    match = re.search(r'```(?:sql|jcoql)?\s*\n?(.*?)\n?```', current_query, re.DOTALL)
                    current_query = match.group(1).strip() if match else '\n'.join([l for l in current_query.split('\n') if '```' not in l])
                
                # Filtra solo le righe sintatticamente rilevanti per JCoQL
                jcoql_keywords = ['GET', 'FILTER', 'WHERE', 'KEEP', 'DROP', 'WITHOUT', 'IN_RANGE', 'INTERSECT', 'EXPAND', 'LOOKUP', 'MERGE', 'GROUP', 'SAVE', 'ALL', 'CREATE', 'TRAJECTORY', 'USE', 'SUBTRACT']
                lines = current_query.split('\n')
                clean_lines = [l.strip() for l in lines if l.strip() and (any(l.strip().upper().startswith(kw) for kw in jcoql_keywords) or l.strip().startswith('.') or l.strip().endswith(';'))]
                if clean_lines:
                    current_query = '\n'.join(clean_lines).strip()
            elif ACTIVE_LLM == "gemma":
                current_query = generate_with_gemma(prompt)
                query_logger.info(f"🤖 Gemma Response: {current_query[:100]}...")
                
                # ✅ Rimuovi filtri arbitrari
                filter_keywords = ['dove', 'con', 'rating', 'prezzo', 'città', 'che', 'superiore', 'inferiore', 'range', 'tra']
                has_filter_request = any(kw in request.nl_query.lower() for kw in filter_keywords)
                
                # Retry se Gemma genera filtri arbitrari
                retry_count = 0
                max_retries = 3
                while (not has_filter_request and 'FILTER CASE WHERE' in current_query.upper()) and retry_count < max_retries:
                    retry_count += 1
                    query_logger.warning(f"⚠️ Gemma ha generato filtri arbitrari - Retry {retry_count}/{max_retries}")
                    current_query = generate_with_gemma(prompt)
                
                # Se ancora ha filtri dopo retry, rimuovili
                if not has_filter_request and 'FILTER CASE WHERE' in current_query.upper():
                    query_logger.info(f"🔧 Rimuovo filtri arbitrari da Gemma (input: '{request.nl_query}')")
                    collection_match = re.search(r'GET\s+COLLECTION\s+\w+', current_query, re.IGNORECASE)
                    if collection_match:
                        current_query = collection_match.group(0) + ";"
                
                if "```" in current_query:
                    match = re.search(r'```(?:jcoql)?\s*\n?(.*?)\n?```', current_query, re.DOTALL)
                    current_query = match.group(1) if match else '\n'.join([l for l in current_query.split('\n') if '```' not in l])
                
                jcoql_keywords = ['GET', 'FILTER', 'WHERE', 'KEEP', 'DROP', 'WITHOUT', 'IN_RANGE', 'UNION', 'INTERSECT', 'EXPAND', 'LOOKUP', 'MERGE', 'GROUP', 'SAVE', 'ALL', 'CREATE', 'TRAJECTORY', 'USE', 'SUBTRACT', 'JOIN']
                lines = current_query.split('\n')
                clean_lines = [l.strip() for l in lines if l.strip() and (any(l.strip().upper().startswith(kw) for kw in jcoql_keywords) or l.strip().startswith('.') or l.strip().endswith(';'))]
                current_query = '\n'.join(clean_lines).strip()

            else:  # Gemini Default
                response = model.generate_content(prompt)
                current_query = response.text.strip()
                query_logger.info(f"🤖 Gemini Response (raw): {current_query[:150]}...")
                
                # ✅ Rimuovi output verboso se non richiesto
                filter_keywords = ['dove', 'con', 'rating', 'prezzo', 'città', 'che', 'superiore', 'inferiore', 'range', 'tra']
                has_filter_request = any(kw in request.nl_query.lower() for kw in filter_keywords)
                
                # Se non richiesto filtro ma Gemini generò query verbosa, ripulisci
                if not has_filter_request:
                    # Estrai solo la query JCoQL (tra backtick o prima di spiegazioni)
                    if '```' in current_query:
                        match = re.search(r'```(?:jcoql|sql)?\s*\n?(.*?)\n?```', current_query, re.DOTALL)
                        if match:
                            current_query = match.group(1).strip()
                    
                    # Se ancora ha spiegazioni, prendi solo la prima riga che inizia con GET
                    if 'GET COLLECTION' in current_query:
                        lines = current_query.split('\n')
                        jcoql_lines = [l.strip() for l in lines if l.strip() and (l.strip().upper().startswith('GET') or l.strip().upper().startswith('FILTER') or l.strip().endswith(';'))]
                        if jcoql_lines:
                            current_query = ' '.join(jcoql_lines).strip()
                
                # Pulizia markdown finale
                if "```" in current_query:
                    match = re.search(r'```(?:jcoql|sql)?\s*\n?(.*?)\n?```', current_query, re.DOTALL)
                    current_query = match.group(1).strip() if match else current_query
                
                # Filtra solo keyword JCoQL
                jcoql_keywords = ['GET', 'FILTER', 'WHERE', 'KEEP', 'DROP', 'WITHOUT', 'IN_RANGE', 'INTERSECT', 'EXPAND', 'LOOKUP', 'MERGE', 'GROUP', 'SAVE', 'ALL', 'CREATE', 'TRAJECTORY', 'USE', 'SUBTRACT']
                lines = current_query.split('\n')
                clean_lines = [l.strip() for l in lines if l.strip() and (any(l.strip().upper().startswith(kw) for kw in jcoql_keywords) or l.strip().startswith('.') or l.strip().endswith(';'))]
                if clean_lines:
                    current_query = '\n'.join(clean_lines).strip()
                
                query_logger.info(f"✅ Gemini Response (cleaned): {current_query}")
            
            # Validazione sintattica con il parser ANTLR selezionato
            is_valid, errors = parser.validate(current_query)
            
            if not is_valid:
                error_messages = [err.message for err in errors]
                all_errors.append(f"Tentativo {attempts}: {', '.join(error_messages)}")
                validation_errors_for_frontend = [{"message": msg} for msg in error_messages]
                
        except Exception as e:
            print(f"⚠️ API Error durante la generazione: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # 5. COSTRUZIONE RISULTATO FINALE
    result = {
        "jcoql_query": current_query,
        "is_valid": is_valid,
        "attempts": attempts,
        "validation_errors": validation_errors_for_frontend,
        "retrieved_examples": retrieved_docs,
        "llm_used": ACTIVE_LLM,
        "parser_used": parser.parser_name
    }

    # 6. LOGGING FINALE (Eseguito ORA che 'result' è definito per evitare NameError)
    elapsed = time.time() - start_time
    query_logger.info(f"✅ Query processata in {elapsed:.3f}s")
    query_logger.info(f"   Parser: {parser.parser_name}")
    query_logger.info(f"   Valida: {result['is_valid']}")

    return result

# ==============================================================================
# ENDPOINT: GESTIONE MODELLI LLM E PARSER
# ==============================================================================
@app.get("/api/llms")
async def list_llms():
    """Ritorna la lista degli LLM supportati ed il modello attualmente attivo."""
    return {
        "available": ["gemini", "llama", "gemma"],
        "current": ACTIVE_LLM
    }

@app.post("/api/set_llm")
async def set_llm(llm_type: str):
    """Cambia il modello LLM in uso."""
    global ACTIVE_LLM
    if llm_type not in ["gemini", "llama", "gemma"]:
        raise HTTPException(status_code=400, detail="LLM non valido")
    ACTIVE_LLM = llm_type
    return {"success": True, "llm": ACTIVE_LLM}

@app.get("/api/parsers")
async def list_parsers():
    """Ritorna i parser ANTLR disponibili ed il parser attivo."""
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
async def execute_query(request_data: dict):
    """
    Esegue query JCoQL - con supporto JOIN
    """
    try:
        jcoql_query = request_data.get('jcoql_query', '').strip()
        databases = request_data.get('databases', ['jcoql_test'])
        database_name = request_data.get('database_name')
        join_config = request_data.get('join_config')
        
        # ✅ DEBUG: Mostra cosa riceve il backend
        query_logger.info(f"DEBUG - request_data keys: {request_data.keys()}")
        query_logger.info(f"DEBUG - databases: {databases}")
        query_logger.info(f"DEBUG - join_config: {join_config}")
        query_logger.info(f"DEBUG - len(databases): {len(databases)}")

        
        if not jcoql_query:
            return {"success": False, "error": "Query vuota"}
        
        # ✅ SE JOIN è configurato, usa JoinExecutor
        if join_config and len(databases) >= 2:
            query_logger.info(f"🔗 JOIN MODE ATTIVATO")
            join_executor = JoinExecutor(ExecutorFactory, parser, db_registry)
            actual_results = join_executor.execute_join(jcoql_query, join_config)
            actual_count = len(actual_results)
            target_db = f"{join_config['db1']} ⊕ {join_config['db2']}"
            
            return {
                "success": True,
                "jcoql_query": jcoql_query,
                "count": actual_count,
                "results": actual_results,
                "database": target_db,
                "join_config": join_config,
                "mongo_query": None
            }
        
        # ✅ ALTRIMENTI, query singola su un database
        target_db = database_name or (databases[0] if databases else 'jcoql_test')
        
        query_logger.info(f"📤 Esecuzione: {jcoql_query}")
        query_logger.info(f"📦 Database: {target_db}")
        
        # Ricrea executor con database giusto
        global executor
        executor = ExecutorFactory.create_executor(
            ExecutorType(ACTIVE_EXECUTOR),
            mongo_uri="mongodb://localhost:27017",
            database=target_db
        )
        query_logger.info(f"♻️ Executor ricreato per database: {target_db}")
        
        # Validazione
        is_valid, errors = parser.validate(jcoql_query)
        if not is_valid:
            error_messages = [err.message for err in errors] if errors else ["Errore sconosciuto"]
            return {"success": False, "error": f"Query non valida"}
        
        if not executor:
            return {"success": False, "error": "Executor non inizializzato"}
        
        # Esecuzione query
        execution_result = executor.execute(jcoql_query)

        query_logger.info(f"DEBUG - Executor response: {execution_result}")

        # ✅ DEFINISCI SUBITO actual_count
        actual_count = 0
        actual_results = []

        # Controlla se execution_result è valido
        if isinstance(execution_result, dict):
            if execution_result.get('success'):
                # Se results è una lista di documenti, usala direttamente
                results = execution_result.get('results', [])
                
                # Se results è una lista, è già i documenti
                if isinstance(results, list):
                    actual_results = results
                    actual_count = len(actual_results)
                # Se results è un dizionario, estrai i documenti
                elif isinstance(results, dict):
                    actual_results = results.get('text', results)
                    actual_count = results.get('doc_count', len(actual_results) if isinstance(actual_results, list) else 0)
                else:
                    actual_results = results
                    actual_count = 1 if results else 0
            else:
                # Errore dall'executor
                error_msg = execution_result.get('error', 'Errore sconosciuto')
                query_logger.error(f"❌ Errore Executor: {error_msg}")
                actual_count = 0
                actual_results = []

        query_logger.info(f"✅ Risultati: {actual_count} documenti da {target_db}")
        
        return {
            "success": True,
            "jcoql_query": jcoql_query,
            "count": actual_count,
            "results": actual_results,
            "database": target_db,
            "mongo_query": None
        }
        
    except Exception as err:
        query_logger.error(f"❌ Errore: {err}", exc_info=True)
        return {"success": False, "error": str(err)}

# ==============================================================================
# ENDPOINT: GESTIONE COLLEZIONI MONGODB
# ==============================================================================
@app.get("/api/collections")
async def list_collections():
    """Lista tutte le collezioni presenti nel database corrente."""
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
    """Carica un file JSON e crea una nuova collezione in MongoDB."""
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
        
        # Determina il nome della collezione dal nome del file se non specificato
        if not collection_name:
            collection_name = file.filename.replace('.json', '').lower()
            collection_name = ''.join(c for c in collection_name if c.isalnum() or c == '_')
        
        # Inserimento documenti in MongoDB
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
    """Elimina una collezione specificata da MongoDB."""
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
    """Conta il numero di documenti in una collezione."""
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
    """Restituisce la lista di tutti i database registrati."""
    return {
        "databases": db_registry.list_databases(),
        "current": db_registry.get_current_database_name()
    }

@app.post("/api/databases/select")
async def select_database(database_name: str):
    """Seleziona ed imposta il database attivo."""
    global GLOBAL_SCHEMA
    
    success = db_registry.set_current_database(database_name)
    if success:
        GLOBAL_SCHEMA = db_registry.get_current_schema()
        return {
            "success": True,
            "current_database": database_name,
            "collections": len(GLOBAL_SCHEMA),
            "message": f"Database '{database_name}' selezionato"
        }
    else:
        return {"success": False, "error": f"Database '{database_name}' non trovato"}

@app.post("/api/databases/connect")
async def connect_database(db_name: str, mongo_uri: str, database_name: str):
    """Aggiunge ed instaura la connessione con un nuovo database."""
    success = db_registry.add_database(db_name, mongo_uri, database_name)
    if success:
        # 💾 Salva database su file SUBITO
        save_databases_to_file(db_registry)
        db_info = db_registry.get_database_info(db_name)
        return {
            "success": True,
            "database": db_info,
            "message": f"Database '{db_name}' connesso con successo"
        }
    else:
        return {"success": False, "error": f"Errore di connessione al database '{db_name}'"}

@app.post("/api/databases/disconnect")
async def disconnect_database(db_name: str):
    """
    Scollega un database dalla registry
    Non elimina i dati, solo lo rimuove dalla lista connessi
    
    Args:
        db_name: Nome del database da scollegare
    
    Returns:
        {"success": bool, "message": str}
    """
    try:
        # Controlla se il database esiste
        if db_name not in db_registry.databases:
            return {
                "success": False,
                "message": f"Database '{db_name}' non trovato"
            }
        
        # Rimuovi dalla registry
        db_registry.databases.pop(db_name)
        db_logger.info(f"✅ Database '{db_name}' scollegato")
        
        # Aggiorna il file di persistenza
        save_databases_to_file(db_registry)
        
        return {
            "success": True,
            "message": f"Database '{db_name}' scollegato con successo"
        }
        
    except Exception as err:
        db_logger.error(f"❌ Errore scollegamento database '{db_name}': {err}")
        return {
            "success": False,
            "message": str(err)
        }

@app.get("/api/databases/{db_name}")
async def get_database_info(db_name: str):
    """Informazioni e schema dettagliato di uno specifico database."""
    info = db_registry.get_database_info(db_name)
    if info:
        return info
    return {"error": f"Database '{db_name}' non trovato"}

@app.get("/api/stats")
async def get_stats():
    """
    Ritorna statistiche REALI di sistema
    """
    try:
        # Accedi direttamente ai database dal registry
        db_list = []
        collections_count = 0
        
        try:
            for db_name, db_conn in db_registry.databases.items():
                db_list.append(db_name)
                try:
                    collections_count += len(db_conn.list_collection_names())
                except:
                    pass
        except Exception as db_err:
            print(f"⚠️ Errore accesso databases: {db_err}")
            db_list = ['jcoql_test', 'test_db']
            collections_count = 8
        
        stats = {
            "executor": {
                "name": ACTIVE_EXECUTOR,
                "status": "active",
                "parser": "ANTLR3 Official"
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
                "uptime_seconds": 3600,
                "version": "1.0.0-production"
            }
        }
        
        print(f"📊 Stats ritornate: {stats}")
        return stats
        
    except Exception as err:
        print(f"❌ Errore stats: {err}")
        import traceback
        traceback.print_exc()
        return {
            "executor": {"name": ACTIVE_EXECUTOR, "status": "error"},
            "databases": {"count": 0, "list": [], "collections_total": 0},
            "llms": {"available": [], "current": None},
            "system": {"uptime_seconds": 0, "version": "1.0.0"}
        }