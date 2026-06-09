#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import chromadb
from fastapi import FastAPI, HTTPException
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import google.generativeai as genai
from dotenv import load_dotenv


# --- PATH ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "backend", "parsers"))

# Importa LLM
from backend.llm_local import generate_with_llama, generate_with_gemma

# Importa Parser Factory
from backend.parsers.parser_factory import ParserFactory, ParserType

# Carica env
load_dotenv()

# Carica regole sintattiche ufficiali JCoQL 4.0
with open('backend/jcoql_syntax_official.txt', 'r', encoding='utf-8') as f:
    JCOQL_SYNTAX_FULL = f.read()

with open('backend/jcoql_syntax_basic_official.txt', 'r', encoding='utf-8') as f:
    JCOQL_SYNTAX_BASIC = f.read()

with open('backend/rag_examples_extended.txt', 'r', encoding='utf-8') as f:
    EXTENDED_EXAMPLES = f.read()

# --- CONFIGURAZIONE LLM ---
# NOTA VRAM: Modelli locali occupano memoria GPU
# - Llama 3.1 8B: ~4.7GB VRAM
# - Gemma 2 9B: ~5.4GB VRAM
# RTX 4060 (8GB): può caricare 1 modello locale alla volta
# Ollama NON scarica automaticamente - serve riavvio manuale
ACTIVE_LLM = os.getenv("ACTIVE_LLM", "gemini")
ACTIVE_PARSER = os.getenv("ACTIVE_PARSER", "antlr4_custom")

# Carica schema MongoDB
MONGODB_SCHEMA = """
SCHEMA MONGODB REALE (usa ESATTAMENTE questi campi):

COLLECTION: hotels
- name (STRING): 'Hotel Duomo'
- location.city (STRING): 'Milano', 'Roma'
- location.country (STRING): 'Italy'
- rating (FLOAT): 3.0 - 5.0
- stars (INT): 3 - 5
- amenities (ARRAY): ['wifi', 'parking', 'pool', 'restaurant']  ⚠️ ARRAY - NON usare .swimming_pool!
- parking (BOOLEAN): true/false
- wifi (BOOLEAN): true/false
- breakfast_included (BOOLEAN): true/false

COLLECTION: products
- name (STRING): 'Laptop Dell'
- category (STRING): 'electronics', 'clothing', 'food', 'books'
- price (FLOAT): 5 - 5000
- discount (INT): 0 - 30
- stock (INT): 0 - 1000
- brand (STRING): 'Sony', 'Apple'
- rating (FLOAT): 0 - 5
- tags (ARRAY): ['new', 'bestseller', 'discount', 'organic']  ⚠️ ARRAY - NON usare .tag singolo!

COLLECTION: users
- email_verified (BOOLEAN): true/false
- age (INT): 18 - 80
- city (STRING): 'Milano', 'Roma'
- country (STRING): 'Italy'
- premium (BOOLEAN): true/false
- active (BOOLEAN): true/false

COLLECTION: orders
- status (STRING): 'pending', 'confirmed', 'shipped', 'delivered', 'cancelled'
- total (FLOAT): 0 - 10000
- priority (STRING): 'low', 'normal', 'high', 'urgent'

COLLECTION: restaurants
- city (STRING): 'Milano', 'Roma'
- cuisine (STRING): 'Italian', 'Japanese', 'Chinese'
- rating (FLOAT): 0 - 5
- status (STRING): 'open', 'closed'
- price_range (STRING): '$', '$$', '$$$', '$$$$'
- outdoor_seating (BOOLEAN): true/false

⚠️ ARRAY HANDLING:
- Hotels.amenities = ARRAY di stringhe. NON inventare campi tipo .swimming_pool!
- Products.tags = ARRAY di stringhe. NON usare .tag singolo!
- Filtra su campi reali (rating, stars, discount) NOT su elementi array.

IMPORTANTE: Usa ESATTAMENTE i nomi campi come scritto sopra (es: location.city NON city!)
"""

# Crea parser
parser = ParserFactory.create_parser(ParserType(ACTIVE_PARSER))

# Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

# ChromaDB
chroma_client = chromadb.PersistentClient(path="./chroma_data")
try:
    collection = chroma_client.get_collection(name="jcoql_examples")
except Exception as e:
    print(f"ChromaDB error: {e}")
    collection = None

# FastAPI
app = FastAPI(title="JCoQL+ Multi-Parser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    nl_query: str
    max_retries: int = 3

@app.on_event("startup")
async def startup_event():
    """Eseguito all'avvio del backend"""
    print("🚀 Starting JCoQL NL Interface...")
    
    # Refresh schema da MongoDB
    try:
        from backend.database.schema_discovery import MongoSchemaDiscoverer
        discoverer = MongoSchemaDiscoverer()
        schema = discoverer.discover_schema(sample_size=50)
        discoverer.save_schema(schema)
        discoverer.close()
        print("✅ MongoDB schema refreshed!")
    except Exception as e:
        print(f"⚠️ Schema refresh failed: {e}")
        print("   Using cached schema...")

@app.post("/api/generate")
async def generate_query(request: GenerateRequest):
    # ✅ NUOVO: Validazione input
    if not request.nl_query or request.nl_query.strip() == "":
        return {
            "jcoql_query": "",
            "is_valid": False,
            "attempts": 0,
            "validation_errors": [{"message": "❌ Query NL vuota! Inserisci una query valida."}],
            "retrieved_examples": [],
            "llm_used": ACTIVE_LLM,
            "parser_used": parser.parser_name
        }
    
    context_str = ""
    retrieved_docs = []
    
    # RAG
    if collection:
        try:
            results = collection.query(
                query_texts=[request.nl_query],
                n_results=3
            )
            retrieved_docs = results['documents'][0] if results['documents'] else []
            context_str = "\n\n".join(retrieved_docs)
        except Exception as e:
            print(f"RAG error: {e}")

    attempts = 0
    is_valid = False
    current_query = ""
    all_errors = []
    validation_errors_for_frontend = []

    # REPAIR LOOP
    while attempts < request.max_retries and not is_valid:
        attempts += 1

        
        
        esempi_formattati = context_str
        
        prompt = f"""Sei un esperto traduttore Natural Language → JCoQL+.

        
{MONGODB_SCHEMA}


{EXTENDED_EXAMPLES}


🚨 VIETATO ASSOLUTO - NON GENERARE MAI:
- ❌ Moltiplicazioni: .price * 1.1, .total * (1 - .discount/100)
- ❌ Divisioni: .price / 2
- ❌ Addizioni: .price + 10
- ❌ Sottrazioni: .total - 50
- ❌ GENERATE, BUILD, COMPUTE, ADD FIELDS, REPORT
- ❌ Campi calcolati: .discounted_price, .total_aumentato

✅ OBBLIGATORIO - GENERA SEMPRE:
- Filtra su campi REALI del database
- NON fare calcoli
- Se utente chiede "prezzo * 1.1" → filtra su campo reale (.total, .price, .discount)
- Se utente chiede "totale + 10%" → filtra su campo reale (.total)

ESEMPI DI ERRORI CHE NON DEVI FARE:
❌ FILTER CASE WHERE .price * (1 - .discount/100) < 50
❌ FILTER CASE WHERE .total * 1.1 > 100
❌ GENERATE BUILD {{ .calc: .price * 2 }}

ESEMPI CORRETTI CHE DEVI FARE:
✅ FILTER CASE WHERE .discount > 20 KEEP OTHERS;
✅ FILTER CASE WHERE .total > 100 KEEP OTHERS;
✅ FILTER CASE WHERE .price < 50 KEEP OTHERS;

{JCOQL_SYNTAX_BASIC}

ESEMPI SIMILI (da RAG):
{esempi_formattati}

USER QUERY:
"{request.nl_query}"

{f"ATTENZIONE! ERRORI PRECEDENTI: {all_errors[-1]}" if attempts > 1 else ""}

Genera SOLO la query JCoQL basata sullo SCHEMA REALE sopra.
Usa ESATTAMENTE i nomi campi dello schema (es: .location.city per città hotel).
NESSUN testo aggiuntivo, solo query JCoQL.

=== SINTASSI UFFICIALE JCOQL 4.0 ===
{JCOQL_SYNTAX_BASIC}

=== REGOLE CRITICHE ===
- Ogni statement termina con punto e virgola (;)
- Campi iniziano con punto: .field_name
- Stringhe tra apici singoli: 'text'
- FILTER CASE WHERE deve avere KEEP OTHERS o DROP OTHERS
- IN_RANGE usa [ ] per range inclusi
- WITHOUT per campi mancanti
- SIZE(campo) per lunghezza array
- Non usare: JOIN ON, GROUP BY, ORDER BY, LIMIT, PROJECT, DISTINCT, COUNT (non supportati)



=== ESEMPI DAL DATABASE ===
{context_str}

{f"ATTENZIONE! ERRORI PRECEDENTI DA CORREGGERE: {all_errors[-1]}" if attempts > 1 else ""}

=== RICHIESTA UTENTE ===
{request.nl_query}

GENERA SOLO LA QUERY JCOQL 4.0, NIENTE ALTRO.
"""
        
        try:
            # LLM Generation
            if ACTIVE_LLM == "llama":
                current_query = generate_with_llama(prompt)
                
                # PULIZIA LLAMA (rimuove spiegazioni)
                # Se contiene markdown code block, estrae solo quello
                if "```" in current_query:
                    import re
                    match = re.search(r'```(?:sql|jcoql)?\s*\n?(.*?)\n?```', current_query, re.DOTALL)
                    if match:
                        current_query = match.group(1).strip()
                    else:
                        # Fallback: rimuovi linee con ```
                        lines = current_query.split('\n')
                        current_query = '\n'.join([l for l in lines if '```' not in l])
                
                # Mantieni solo righe JCoQL valide (stesso filtro Gemma)
                jcoql_keywords = [
                    'GET', 'FILTER', 'WHERE', 'KEEP', 'DROP', 'WITHOUT', 
                    'IN_RANGE', 'INTERSECT', 'EXPAND', 'LOOKUP', 'MERGE',
                    'GROUP', 'SAVE', 'ALL', 'CREATE', 'TRAJECTORY', 'USE',
                    'SUBTRACT'
                ]
                
                lines = current_query.split('\n')
                clean_lines = []
                
                for line in lines:
                    line = line.strip()
                    if line and (
                        any(line.upper().startswith(kw) for kw in jcoql_keywords) or
                        line.startswith('.') or
                        line.endswith(';')
                    ):
                        clean_lines.append(line)
                
                if clean_lines:
                    current_query = '\n'.join(clean_lines).strip()
            elif ACTIVE_LLM == "gemma":
                current_query = generate_with_gemma(prompt)
                
                # PULIZIA ULTRA-AGGRESSIVA GEMMA
                # Step 1: Rimuovi markdown
                if "```" in current_query:
                    import re
                    # Estrae solo contenuto tra ```
                    match = re.search(r'```(?:jcoql)?\s*\n?(.*?)\n?```', current_query, re.DOTALL)
                    if match:
                        current_query = match.group(1)
                    else:
                        # Rimuovi solo le linee con ```
                        lines = current_query.split('\n')
                        current_query = '\n'.join([l for l in lines if '```' not in l])
                
                # Step 2: Mantieni solo righe che iniziano con keyword JCoQL
                jcoql_keywords = [
                    'GET', 'FILTER', 'WHERE', 'KEEP', 'DROP', 'WITHOUT', 
                    'IN_RANGE', 'UNION', 'INTERSECT', 'EXPAND', 'LOOKUP',
                    'MERGE', 'GROUP', 'SAVE', 'ALL', 'CREATE', 'TRAJECTORY',
                    'USE', 'SUBTRACT', 'JOIN'
                ]
                
                lines = current_query.split('\n')
                clean_lines = []
                
                for line in lines:
                    line = line.strip()
                    # Mantieni se inizia con keyword JCoQL o è continuazione (es: "  WHERE")
                    if line and (
                        any(line.upper().startswith(kw) for kw in jcoql_keywords) or
                        line.startswith('.') or  # Campo (es: .email)
                        line.endswith(';')       # Fine statement
                    ):
                        clean_lines.append(line)
                
                current_query = '\n'.join(clean_lines).strip()
                
                # Step 3: Se ancora vuoto, fallback al testo originale
                if not current_query:
                    current_query = generate_with_gemma(prompt)
            else:  # gemini
                response = model.generate_content(prompt)
                current_query = response.text.strip()
            
            # Pulisce markdown
            if current_query.startswith("```"):
                current_query = current_query.replace("```jcoql", "").replace("```", "").strip()
            
            # VALIDAZIONE con Parser Factory
            is_valid, errors = parser.validate(current_query)
            
            if not is_valid:
                error_messages = [err.message for err in errors]
                all_errors.append(f"Tentativo {attempts}: {', '.join(error_messages)}")
                validation_errors_for_frontend = [{"message": msg} for msg in error_messages]
                
        except Exception as e:
            print(f"API error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return {
        "jcoql_query": current_query,
        "is_valid": is_valid,
        "attempts": attempts,
        "validation_errors": validation_errors_for_frontend,
        "retrieved_examples": retrieved_docs,
        "llm_used": ACTIVE_LLM,
        "parser_used": parser.parser_name
    }

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

@app.post("/api/set_parser")
async def set_parser(parser_type: str):
    global parser, ACTIVE_PARSER
    try:
        ACTIVE_PARSER = parser_type
        parser = ParserFactory.create_parser(ParserType(parser_type))
        return {
            "success": True,
            "parser": parser.parser_name,
            "version": parser.parser_version
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
# ========================================
# ESECUZIONE QUERY JCOQL SU MONGODB
# ========================================
# DOPO (con Factory):
import sys
from pathlib import Path
executors_path = Path(__file__).parent / "backend" / "executors"
if str(executors_path) not in sys.path:
    sys.path.insert(0, str(executors_path))

from executor_factory import ExecutorFactory, ExecutorType

# Crea executor tramite Factory Pattern
ACTIVE_EXECUTOR = os.getenv("ACTIVE_EXECUTOR", "python_translator")
executor = ExecutorFactory.create_executor(
    ExecutorType(ACTIVE_EXECUTOR),
    mongo_uri="mongodb://localhost:27017",
    database="jcoql_test"
)

@app.post("/api/execute")
async def execute_query(request: Request):
    """
    Esegue query JCoQL su MongoDB
    
    Body:
    {
        "jcoql_query": "GET COLLECTION hotels; FILTER CASE WHERE ..."
    }
    
    Returns:
    {
        "success": true,
        "results": [...],
        "count": 5,
        "mongo_query": {...}
    }
    """
    try:
        data = await request.json()
        jcoql_query = data.get('jcoql_query', '')
        
        if not jcoql_query:
            return JSONResponse(
                status_code=400,
                content={'error': 'jcoql_query required'}
            )
        
        # Esegui query
        result = executor.execute(jcoql_query)
        
        return JSONResponse(content=result)
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e)
            }
        )

@app.get("/api/collections")
async def list_collections():
    """
    Lista collection disponibili in MongoDB
    
    Returns:
    {
        "collections": ["hotels", "products", "users", "orders", "restaurants"],
        "database": "jcoql_test"
    }
    """
    try:
        collections = executor.db.list_collection_names()
        return JSONResponse(content={
            'collections': collections,
            'database': executor.db.name
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'error': str(e)}
        )

from fastapi import UploadFile, File
import json

@app.post("/api/upload-collection")
async def upload_collection(
    file: UploadFile = File(...),
    collection_name: str = None
):
    """
    Carica file JSON e crea collection MongoDB
    
    Args:
        file: File JSON con array di documenti
        collection_name: Nome collection (opzionale, usa nome file)
    
    Returns:
        {
            "success": true,
            "collection": "my_data",
            "documents_count": 50,
            "message": "Collection creata con successo"
        }
    """
    try:
        # Leggi file
        content = await file.read()
        
        # Parse JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            return JSONResponse(
                status_code=400,
                content={
                    'success': False,
                    'error': f'File JSON non valido: {str(e)}'
                }
            )
        
        # Assicurati che sia array
        if not isinstance(data, list):
            return JSONResponse(
                status_code=400,
                content={
                    'success': False,
                    'error': 'Il file deve contenere un array JSON di documenti'
                }
            )
        
        if len(data) == 0:
            return JSONResponse(
                status_code=400,
                content={
                    'success': False,
                    'error': 'Array vuoto, nessun documento da caricare'
                }
            )
        
        # Usa nome file se collection_name non specificato
        if not collection_name:
            collection_name = file.filename.replace('.json', '').lower()
            # Rimuovi caratteri non validi
            collection_name = ''.join(c for c in collection_name if c.isalnum() or c == '_')
        
        # Inserisci in MongoDB
        collection = executor.db[collection_name]
        result = collection.insert_many(data)
        
        return JSONResponse(content={
            'success': True,
            'collection': collection_name,
            'documents_count': len(result.inserted_ids),
            'message': f'Collection "{collection_name}" creata con {len(result.inserted_ids)} documenti'
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e)
            }
        )

@app.delete("/api/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """
    Elimina una collection MongoDB
    
    Args:
        collection_name: Nome collection da eliminare
        
    Returns:
        {"success": true, "message": "..."}
    """
    try:
        executor.db.drop_collection(collection_name)
        return JSONResponse(content={
            'success': True,
            'message': f'Collection "{collection_name}" eliminata'
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                'success': False,
                'error': str(e)
            }
        )

@app.get("/api/collections/{collection_name}/count")
async def get_collection_count(collection_name: str):
    """
    Conta documenti in una collection
    
    Returns:
        {"collection": "hotels", "count": 20}
    """
    try:
        count = executor.db[collection_name].count_documents({})
        return JSONResponse(content={
            'collection': collection_name,
            'count': count
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={'error': str(e)}
        )

# Cleanup connessione MongoDB alla chiusura
@app.on_event("shutdown")
def shutdown_event():
    """Chiudi connessione MongoDB"""
    executor.close()