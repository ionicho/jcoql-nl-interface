#!/usr/bin/env python3
"""
Test Query Complesse - TOP e GROUP BY
"""
import os
from dotenv import load_dotenv
from google import genai
import chromadb
import time

load_dotenv()
API_KEY = os.getenv('GEMINI_API_KEY')

client_genai = genai.Client(api_key=API_KEY)
client_chroma = chromadb.PersistentClient(path="./chroma_data")
collection = client_chroma.get_collection(name="jcoql_examples")

def generate_query(user_input):
    results = collection.query(query_texts=[user_input], n_results=3)
    context = "\n\n".join(results['documents'][0])
    
    prompt = f"""Sei un esperto traduttore di linguaggio naturale in query JCoQL+.

SINTASSI JCOQL+ CRITICA:
- Per "primi N" usa: SORT BY ... ; TOP N;
- NON usare: ORDER BY, LIMIT, SELECT
- Per aggregazioni usa: GROUP BY campo WITH funzione
- NON usare: GENERATE AGGREGATE

Esempi:
{context}

Richiesta: {user_input}

Rispondi SOLO con il codice JCoQL+, niente altro.
"""
    
    response = client_genai.models.generate_content(
        model='models/gemini-2.5-flash',
        contents=prompt
    )
    return response.text.strip()

test_cases = [
    ("Primi 10 hotel più costosi", ["SORT BY", "TOP 10"]),
    ("Top 5 prodotti più venduti", ["SORT BY", "TOP 5"]),
    ("Conta clienti per città", ["GROUP BY", "WITH COUNT"]),
    ("Media prezzi per categoria", ["GROUP BY", "WITH AVG"]),
    ("Le 3 città con più utenti", ["GROUP BY", "SORT BY", "TOP 3"]),
]

print("=" * 70)
print("TEST QUERY AVANZATE - TOP e GROUP BY")
print("=" * 70)
print()

success = 0
for i, (query_input, required_keywords) in enumerate(test_cases, 1):
    print(f"[{i}/{len(test_cases)}] {query_input}")
    
    try:
        generated = generate_query(query_input)
        print(f"Generated:")
        print(f"  {generated}")
        print()
        
        # Check keywords
        all_present = all(kw in generated for kw in required_keywords)
        has_wrong_syntax = any(wrong in generated for wrong in ["ORDER BY", "LIMIT", "SELECT COUNT"])
        
        if all_present and not has_wrong_syntax:
            print(f"  ✅ PASS - Sintassi JCoQL+ corretta")
            success += 1
        elif has_wrong_syntax:
            print(f"  ❌ FAIL - Usa sintassi SQL invece di JCoQL+")
        else:
            print(f"  ❌ FAIL - Mancano keyword: {[k for k in required_keywords if k not in generated]}")
        
        print()
        
        if i < len(test_cases):
            print(f"  ⏳ Attesa 12s...")
            time.sleep(12)
        
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        print()

print("=" * 70)
print(f"RISULTATO: {success}/{len(test_cases)}")
print(f"Accuracy: {(success/len(test_cases))*100:.0f}%")
print("=" * 70)