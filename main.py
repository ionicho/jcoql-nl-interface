#!/usr/bin/env python3
import os
import sys
import chromadb
from fastapi import FastAPI, HTTPException
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

# --- CONFIGURAZIONE ---
ACTIVE_LLM = os.getenv("ACTIVE_LLM", "gemini")
ACTIVE_PARSER = os.getenv("ACTIVE_PARSER", "antlr4_custom")

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

@app.post("/api/generate")
async def generate_query(request: GenerateRequest):
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
        
        prompt = f"""
Sei un esperto di JCoQL+. Traduci la richiesta in linguaggio naturale in una query JCoQL+ valida.
Rispondi SOLO con il codice della query, terminato da punto e virgola (;). Niente markdown.

CONTESTO (Esempi):
{context_str}

{f"ATTENZIONE! ERRORI DA CORREGGERE: {all_errors[-1]}" if attempts > 1 else ""}

RICHIESTA: {request.nl_query}
"""
        
        try:
            # LLM Generation
            if ACTIVE_LLM == "llama":
                current_query = generate_with_llama(prompt)
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