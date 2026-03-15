import os
import sys
import chromadb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import google.generativeai as genai
from dotenv import load_dotenv

# --- CONFIGURAZIONE PATH PER ANTLR ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(BASE_DIR, "backend", "parsers"))

# Importiamo il validatore reale
from backend.parsers.validator import validate_jcoql_query

load_dotenv()

# 1. Inizializzazione Gemini 2.5 Flash
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

# 2. Inizializzazione ChromaDB
chroma_client = chromadb.PersistentClient(path="./chroma_data")
try:
    collection = chroma_client.get_collection(name="jcoql_examples")
except Exception as e:
    print(f"ATTENZIONE: Errore nel caricamento di ChromaDB: {e}")
    collection = None

app = FastAPI()

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
    
    # --- STEP 1: RAG REALE ---
    if collection:
        try:
            results = collection.query(
                query_texts=[request.nl_query],
                n_results=3
            )
            retrieved_docs = results['documents'][0] if results['documents'] else []
            context_str = "\n\n".join(retrieved_docs)
        except Exception as e:
            print(f"Errore RAG: {e}")

    attempts = 0
    is_valid = False
    current_query = ""
    all_errors = []
    validation_errors_for_frontend = []

    # --- STEP 2: REPAIR LOOP CON VALIDATORE ANTLR ---
    while attempts < request.max_retries and not is_valid:
        attempts += 1
        
        prompt = f"""
        Sei un esperto di JCoQL+. Traduci la richiesta in linguaggio naturale in una query JCoQL+ valida.
        Rispondi SOLO con il codice della query, terminato da punto e virgola (;). Niente markdown.
        
        CONTESTO (Esempi):
        {context_str}
        
        {f"ATTENZIONE! LA QUERY PRECEDENTE AVEVA QUESTI ERRORI SINTATTICI DA CORREGGERE: {all_errors[-1]}" if attempts > 1 else ""}
        
        RICHIESTA: {request.nl_query}
        """
        
        try:
            response = model.generate_content(prompt)
            current_query = response.text.strip().replace("```jcoql", "").replace("```", "").strip()
            
            # --- VALIDAZIONE REALE (ANTLR) ---
            validation_result = validate_jcoql_query(current_query)
            is_valid = validation_result.get('is_valid', False)
            
            if not is_valid:
                errors_list = validation_result.get('errors', [{'message': 'Errore sconosciuto'}])
                error_messages = [err.get('message', str(err)) for err in errors_list]
                
                all_errors.append(f"Tentativo {attempts}: {', '.join(error_messages)}")
                validation_errors_for_frontend = [{"message": msg} for msg in error_messages]
            else:
                validation_errors_for_frontend = []
                
        except Exception as e:
            print(f"Errore API: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return {
        "jcoql_query": current_query,
        "is_valid": is_valid,
        "attempts": attempts,
        "validation_errors": validation_errors_for_frontend,
        "retrieved_examples": retrieved_docs
    }