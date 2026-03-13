#!/usr/bin/env python3
#!/usr/bin/env python3
"""
RAG Pipeline con Validazione ANTLR
NL Query → ChromaDB Retrieval → Gemini Generation → ANTLR Validation
"""
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / '.env')

# Add parsers to path
sys.path.append(str(Path(__file__).parent / 'parsers'))

import google.generativeai as genai
from database.chroma_setup import get_chroma_collection
from parsers.validator import validate_jcoql_query


def generate_jcoql_with_validation(nl_query, max_retries=2):
    """
    Generate JCoQL query with automatic validation and retry
    
    Args:
        nl_query (str): Natural language query
        max_retries (int): Max validation retry attempts
    
    Returns:
        dict: {
            'nl_query': str,
            'jcoql_query': str,
            'is_valid': bool,
            'validation_errors': list,
            'attempts': int,
            'retrieved_examples': list
        }
    """
    # Setup
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return {'error': 'GEMINI_API_KEY not found'}
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Retrieve examples
    collection = get_chroma_collection()
    results = collection.query(
        query_texts=[nl_query],
        n_results=3
    )
    
    retrieved_examples = []
    if results['documents'] and results['documents'][0]:
        retrieved_examples = results['documents'][0]
    
    # Build prompt
    examples_text = "\n\n".join([f"Esempio {i+1}:\n{ex}" 
                                  for i, ex in enumerate(retrieved_examples)])
    
    base_prompt = f"""Sei un esperto di JCoQL 4.0. Genera SOLO query JCoQL sintatticamente corrette.

REGOLE CRITICHE JCoQL 4.0:
1. Inizia SEMPRE con: GET COLLECTION nome_collezione;
2. FILTER usa: FILTER CASE WHERE condizione KEEP OTHERS;
3. NON usare SQL (NO SELECT, NO WHEN/THEN, NO FROM)
4. Usa FIELD_NAME con punto: .city, .price, .rating
5. IN_RANGE: .field IN_RANGE [ min , max ] per estremi inclusi
6. Operatori: AND, OR, NOT, =, >, <, >=, <=
7. Stringhe con apici singoli: 'Milano' (NON "Milano")
8. Termina con punto e virgola: KEEP OTHERS;

ESEMPI CORRETTI:
{examples_text}

QUERY RICHIESTA: {nl_query}

GENERA SOLO LA QUERY JCOQL (una sola istruzione, no spiegazioni, no markdown):"""

    for attempt in range(1, max_retries + 2):
        try:
            # Sleep tra retry (dopo primo tentativo)
            if attempt > 1:
                print(f"  ⏰ Retry {attempt} - waiting 13s...")
                time.sleep(13)
            
            # Generate
            response = model.generate_content(base_prompt)
            jcoql_query = response.text.strip()
            
            # Clean
            jcoql_query = jcoql_query.replace('```jcoql', '').replace('```', '').strip()
            
            # Validate
            validation = validate_jcoql_query(jcoql_query)
            
            if validation['is_valid']:
                return {
                    'nl_query': nl_query,
                    'jcoql_query': jcoql_query,
                    'is_valid': True,
                    'validation_errors': [],
                    'attempts': attempt,
                    'retrieved_examples': retrieved_examples
                }
            else:
                # Build error feedback for retry
                errors_text = "\n".join([f"- {e['message']}" for e in validation['errors']])
                base_prompt += f"\n\nERRORI SINTATTICI (tentativo {attempt}):\n{errors_text}\n\nCORREGGI E RIGENERA:"
                
                if attempt == max_retries + 1:
                    # Last attempt failed
                    return {
                        'nl_query': nl_query,
                        'jcoql_query': jcoql_query,
                        'is_valid': False,
                        'validation_errors': validation['errors'],
                        'attempts': attempt,
                        'retrieved_examples': retrieved_examples
                    }
        
        except Exception as e:
            return {
                'nl_query': nl_query,
                'error': str(e),
                'is_valid': False,
                'attempts': attempt
            }
    
    return {'error': 'Max retries exceeded'}


# Test
if __name__ == "__main__":
    test_queries = [
        "Hotel a Milano con rating superiore a 4",
        "Prodotti con prezzo tra 100 e 200 euro",
        "Utenti senza email registrata"
    ]
    
    print("="*70)
    print("RAG + VALIDAZIONE ANTLR - TEST")
    print("="*70)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n[{i}/{len(test_queries)}] Query: {query}")
        print("-"*70)
        
        result = generate_jcoql_with_validation(query)
        
        if 'error' in result:
            print(f"❌ ERROR: {result['error']}")
        else:
            print(f"✅ Valid: {result['is_valid']}")
            print(f"📊 Attempts: {result['attempts']}")
            print(f"📝 Query:\n{result['jcoql_query']}")
            
            if not result['is_valid']:
                print(f"\n⚠️  Validation errors:")
                for err in result['validation_errors']:
                    print(f"   - {err['message']}")
        
        # AGGIUNGI QUESTO:
        # Sleep tra query per rispettare quota (5 RPM = 12 secondi tra richieste)
        if i < len(test_queries):
            print(f"\n⏰ Waiting 13 seconds (quota: 5 RPM)...")
            time.sleep(13)