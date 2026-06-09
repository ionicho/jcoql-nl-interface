#!/usr/bin/env python3
"""
Test Suite Estesa - 20 Query di Complessità Crescente
Misura accuracy, precision, e analizza failure cases
"""
import os
from dotenv import load_dotenv
from google import genai
import chromadb
import time

load_dotenv()
API_KEY = os.getenv('GEMINI_API_KEY')

# Initialize
client_genai = genai.Client(api_key=API_KEY)
client_chroma = chromadb.PersistentClient(path="./chroma_data")
collection = client_chroma.get_collection(name="jcoql_examples")

def generate_query(user_input):
    """Generate JCoQL+ query using RAG"""
    # Retrieval
    results = collection.query(query_texts=[user_input], n_results=2)
    context = "\n\n".join(results['documents'][0])
    
    # Prompt
    prompt = f"""Sei un esperto traduttore di linguaggio naturale in query JCoQL+.
Usa strettamente la sintassi mostrata in questo esempio:

{context}

Richiesta dell'utente: {user_input}

Rispondi esclusivamente con il codice della query JCoQL+, senza spiegazioni o testo aggiuntivo.
"""
    
    # Generation
    response = client_genai.models.generate_content(
        model='models/gemini-2.5-flash',
        contents=prompt
    )
    
    return response.text.strip()

# Test Suite - 20 Query
test_cases = [
    # BASIC (1-5)
    ("Trova tutti i negozi a Bergamo", "GET COLLECTION", True),
    ("Prodotti con prezzo inferiore a 50", "<", True),
    ("Utenti che hanno email", "WITH", True),
    ("Clienti senza telefono", "WITHOUT", True),
    ("Ordini con status completato", "=", True),
    
    # INTERMEDIATE (6-10)
    ("Hotel a Milano con rating maggiore di 4", "AND", True),
    ("Prodotti tra 100 e 200 euro", "INRANGE", True),
    ("Ristoranti a Roma o Firenze", "OR", True),
    ("Aggiungi campo IVA al 22%", "ADD FIELDS", True),
    ("Rimuovi campi password e token", "REMOVE FIELDS", True),
    
    # ADVANCED (11-15)
    ("Hotel a Milano o Roma con rating > 4 e prezzo < 200", "AND.*OR|OR.*AND", True),
    ("Appartamenti tra 60 e 80 mq a Bergamo", "INRANGE.*AND|AND.*INRANGE", True),
    ("Mantieni solo id e nome utente", "BUILD", True),
    ("Ordina prodotti per prezzo decrescente", "SORT BY.*DESC", True),
    ("Primi 10 hotel più costosi", "TOP", True),
    
    # COMPLEX (16-20)
    ("Conta clienti per città", "GROUP BY.*COUNT", True),
    ("Calcola media prezzi per categoria", "GROUP BY.*AVG", True),
    ("Salva risultati in nuova collezione", "SAVE AS", True),
    ("Espandi array ordini in documenti singoli", "EXPAND UNPACK", True),
    ("Prodotti elettronica o tech tra 50 e 500 euro non dismessi", "AND.*OR.*NOT|OR.*AND.*NOT", True),
]

print("=" * 70)
print("TEST SUITE ESTESA - 20 QUERY")
print("=" * 70)
print()

results = []
success_count = 0

for i, (query_input, expected_pattern, should_pass) in enumerate(test_cases, 1):
    print(f"[{i}/20] Testing: {query_input[:60]}...")
    
    try:
        # Generate query
        generated = generate_query(query_input)
        
        # Validation
        has_get = "GET COLLECTION" in generated
        has_semicolon = ";" in generated
        
        # Pattern matching
        import re
        pattern_match = re.search(expected_pattern, generated, re.IGNORECASE) if expected_pattern != "GET COLLECTION" else has_get
        
        passed = has_get and has_semicolon and pattern_match
        
        if passed:
            print(f"  ✅ PASS")
            success_count += 1
        else:
            print(f"  ❌ FAIL")
            print(f"     Expected: {expected_pattern}")
            print(f"     Got: {generated[:100]}...")
        
        results.append({
            'input': query_input,
            'output': generated,
            'passed': passed
        })
        
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        results.append({
            'input': query_input,
            'output': f"ERROR: {e}",
            'passed': False
        })
    
    # Rate limiting (5 req/min = 1 ogni 12+ secondi)
    time.sleep(15)  # Attesa sicura per evitare 429
    print()

# Summary
print("=" * 70)
print("RESULTS SUMMARY")
print("=" * 70)
print(f"Total Tests: 20")
print(f"Passed: {success_count}")
print(f"Failed: {20 - success_count}")
print(f"Accuracy: {(success_count/20)*100:.1f}%")
print()

# Failed cases
failed = [r for r in results if not r['passed']]
if failed:
    print("FAILED CASES:")
    for case in failed:
        print(f"  - {case['input']}")
        print(f"    Output: {case['output'][:80]}...")
        print()

print("=" * 70)