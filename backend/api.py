#!/usr/bin/env python3
"""
JCoQL+ API REST - FastAPI
Endpoints per generazione e validazione query
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent))

from rag_with_validation import generate_jcoql_with_validation
from parsers.validator import validate_jcoql_query

# Initialize FastAPI
app = FastAPI(
    title="JCoQL+ NL Interface API",
    description="API per traduzione Natural Language → JCoQL+ con validazione ANTLR",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Prod: specificare domini esatti
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response Models
class GenerateRequest(BaseModel):
    nl_query: str
    max_retries: Optional[int] = 2
    
    class Config:
        schema_extra = {
            "example": {
                "nl_query": "Hotel a Milano con rating superiore a 4",
                "max_retries": 2
            }
        }

class ValidateRequest(BaseModel):
    jcoql_query: str
    
    class Config:
        schema_extra = {
            "example": {
                "jcoql_query": "GET COLLECTION Hotels; FILTER CASE WHERE .city = 'Milano' KEEP OTHERS;"
            }
        }

class GenerateResponse(BaseModel):
    nl_query: str
    jcoql_query: str
    is_valid: bool
    attempts: int
    validation_errors: List[dict] = []
    retrieved_examples: List[str] = []

class ValidateResponse(BaseModel):
    jcoql_query: str
    is_valid: bool
    errors: List[dict] = []
    parse_tree: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    version: str
    components: dict

# Endpoints
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint - API info"""
    return {
        "message": "JCoQL+ NL Interface API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "generate": "/api/generate",
            "validate": "/api/validate",
            "health": "/health"
        }
    }

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "rag": "operational",
            "llm": "operational",
            "parser": "operational",
            "chromadb": "operational"
        }
    }

@app.post("/api/generate", response_model=GenerateResponse, tags=["Generation"])
async def generate_query(request: GenerateRequest):
    """
    Genera query JCoQL da linguaggio naturale
    
    - **nl_query**: Richiesta in linguaggio naturale (italiano)
    - **max_retries**: Numero massimo retry in caso di errori (default: 2)
    
    Returns:
    - Query JCoQL validata
    - Stato validazione
    - Numero tentativi
    - Eventuali errori
    - Esempi RAG utilizzati
    """
    try:
        result = generate_jcoql_with_validation(
            request.nl_query,
            max_retries=request.max_retries
        )
        
        if 'error' in result:
            raise HTTPException(status_code=500, detail=result['error'])
        
        return GenerateResponse(
            nl_query=result['nl_query'],
            jcoql_query=result['jcoql_query'],
            is_valid=result['is_valid'],
            attempts=result['attempts'],
            validation_errors=result.get('validation_errors', []),
            retrieved_examples=result.get('retrieved_examples', [])
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/validate", response_model=ValidateResponse, tags=["Validation"])
async def validate_query(request: ValidateRequest):
    """
    Valida sintassi query JCoQL con parser ANTLR
    
    - **jcoql_query**: Query JCoQL da validare
    
    Returns:
    - Stato validazione
    - Errori sintattici dettagliati (se presenti)
    - Parse tree (opzionale)
    """
    try:
        result = validate_jcoql_query(request.jcoql_query)
        
        return ValidateResponse(
            jcoql_query=result['query'],
            is_valid=result['is_valid'],
            errors=result.get('errors', []),
            parse_tree=result.get('parse_tree')
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stats", tags=["Statistics"])
async def get_stats():
    """Statistiche sistema (TODO: implementare tracking)"""
    return {
        "total_requests": 0,
        "valid_queries": 0,
        "average_attempts": 0.0,
        "cache_hits": 0
    }

# Run server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )