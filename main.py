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

# Caricamento regole sintattiche
def load_file_content(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return ""

JCOQL_SYNTAX_FULL = load_file_content('backend/jcoql_syntax_official.txt')
JCOQL_SYNTAX_BASIC = load_file_content('backend/jcoql_syntax_basic_official.txt')
EXTENDED_EXAMPLES = load_file_content('backend/rag_examples_extended.txt')

# Selezione LLM, Parser ed Executor attivi
ACTIVE_LLM = os.getenv("ACTIVE_LLM", "gemini")
ACTIVE_PARSER = os.getenv("ACTIVE_PARSER", "antlr3_official")
ACTIVE_EXECUTOR = os.getenv("ACTIVE_EXECUTOR", "jco_framework")

# Istanzia il parser sintattico
parser = ParserFactory.create_parser(ParserType(ACTIVE_PARSER))

# Configurazione Google Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

# Inizializzazione ChromaDB
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
app = FastAPI(title="JCoQL+ Multi-Parser API", json_encoder=MongoDBJSONEncoder)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    nl_query: str
    database: str = None
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
                n_results=3
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
        current_db = db_registry.current_database or "nessuno"
        available_collections = []
        if current_db and current_db in db_registry.databases:
            try:
                available_collections = db_registry.databases[current_db].list_collection_names()
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
            if ACTIVE_LLM == "llama":
                current_query = generate_with_llama(prompt)
            elif ACTIVE_LLM == "gemma":
                current_query = generate_with_gemma(prompt)
            else:
                response = model.generate_content(prompt)
                current_query = response.text.strip()

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
            
            if not has_filter_request and 'FILTER CASE WHERE' in current_query.upper():
                collection_match = re.search(r'GET\s+COLLECTION\s+\w+', current_query, re.IGNORECASE)
                if collection_match:
                    current_query = collection_match.group(0) + ";"

            # Estrarre blocchi di codice markdown
            if "```" in current_query:
                match = re.search(r'```(?:jcoql|sql)?\s*\n?(.*?)\n?```', current_query, re.DOTALL)
                if match:
                    current_query = match.group(1).strip()

            # Pulizia linee non relative a JCoQL
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

            # Auto-correzione sintattica
            if current_query and not current_query.startswith("QUERY:"):
                current_query, _ = correct_query(current_query)

            # Validazione sintattica ANTLR
            is_valid, errors = parser.validate(current_query)
            
            if not is_valid:
                error_messages = [err.message for err in errors] if errors else ["Errore sintattico"]
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

        # DEBUG: Stampa cosa ritorna l'executor
        print(f"\n🔍 DEBUG execution_result keys: {execution_result.keys() if isinstance(execution_result, dict) else 'NOT A DICT'}")
        if isinstance(execution_result, dict):
            print(f"   execution_result: {execution_result}")

        actual_count = 0
        actual_results = []

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
    """Seleziona un database"""
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
    """Connetti a un database MongoDB"""
    try:
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
        
        db_registry.databases.pop(db_name)
        db_logger.info(f"✅ Database '{db_name}' scollegato")
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
            for db_name, db_conn in db_registry.databases.items():
                db_list.append(db_name)
                try:
                    collections_count += len(db_conn.list_collection_names())
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
                "uptime_seconds": 3600,
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