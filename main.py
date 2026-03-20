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

# Importa LLM locali
from backend.llm_local import generate_with_llama, generate_with_gemma

# Importa validatore
from backend.parsers.validator import validate_jcoql_query

# Carica env
load_dotenv()

# --- LLM CONFIGURATION ---
ACTIVE_LLM = os.getenv("ACTIVE_LLM", "gemini")  # gemini | llama | gemma

# --- GEMINI ---
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")

# --- CHROMADB ---
chroma_client = chromadb.PersistentClient(path="./chroma_data")
try:
    collection = chroma_client.get_collection(name="jcoql_examples")
except Exception as e:
    print(f"ATTENZIONE: ChromaDB error: {e}")
    collection = None

# --- FASTAPI ---
app = FastAPI(title="JCoQL+ API")

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
            # GENERAZIONE LLM
            if ACTIVE_LLM == "llama":
                current_query = generate_with_llama(prompt)
                
            elif ACTIVE_LLM == "gemma":
                current_query = generate_with_gemma(prompt)
                
                # Pulisce output Gemma
                if "```" in current_query:
                    lines = current_query.split('\n')
                    current_query = '\n'.join([l for l in lines if not l.startswith('```')])
                
                current_query = current_query.replace("Sure, here is the JCoQL query", "")
                current_query = current_query.replace(":", "").strip()
                
            else:  # gemini
                response = model.generate_content(prompt)
                current_query = response.text.strip()
            
            # Pulisce markdown (tutti i modelli)
            if current_query.startswith("```"):
                current_query = current_query.replace("```jcoql", "").replace("```", "").strip()
            
            # VALIDAZIONE
            validation_result = validate_jcoql_query(current_query)
            is_valid = validation_result.get('is_valid', False)
            
            if not is_valid:
                errors_list = validation_result.get('errors', [{'message': 'Errore sconosciuto'}])
                error_messages = [err.get('message', str(err)) for err in errors_list]
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
        "llm_used": ACTIVE_LLM
    }

@app.get("/api/llms")
async def list_llms():
    """Lista LLM disponibili"""
    return {
        "available": ["gemini", "llama", "gemma"],
        "current": ACTIVE_LLM
    }

@app.post("/api/set_llm")
async def set_llm(llm_type: str):
    """Cambia LLM runtime"""
    global ACTIVE_LLM
    
    if llm_type not in ["gemini", "llama", "gemma"]:
        raise HTTPException(status_code=400, detail="LLM non valido")
    
    ACTIVE_LLM = llm_type
    return {"success": True, "llm": ACTIVE_LLM}