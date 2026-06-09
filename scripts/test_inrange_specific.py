#!/usr/bin/env python3
"""
Test Specifico INRANGE - Verifica che il sistema usi INRANGE invece di AND
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
    """Generate JCoQL+ query using RAG"""
    # Retrieval - più esempi per migliorare match
    results = collection.query(query_texts=[user_input], n_results=3)
    context = "\n\n".join(results['documents'][0])
    
    prompt = f"""Sei un esperto traduttore di linguaggio naturale in query JCoQL+.

IMPORTANTE: Quando l'utente chiede un range numerico (es. "tra X e Y", "da X a Y", "compreso tra X e Y"),
usa SEMPRE l'operatore INRANGE invece di AND con >= e <=.

Esempi di riferimento:
{context}

Richiesta dell'utente: {user_input}

Rispondi esclusivamente con il codice della query JCoQL+, senza spiegazioni.
"""
    
    response = client_genai.models.generate_content(
        model='models/gemini-2.5-flash',
        contents=prompt
    )
    return response.text.strip()

# Test INRANGE
test_cases = [
    "Prodotti con prezzo tra 100 e 200 euro",
    "Appartamenti tra 60 e 80 metri quadri",
    "Hotel con prezzo tra 80 e 150 euro a Milano",
    "Utenti con età compresa tra 18 e 65 anni",
    "Recensioni con rating tra 3.5 e 4.5 stelle",
]

print("=" * 70)
print("TEST INRANGE - Verifica Uso Operatore INRANGE")
print("=" * 70)
print()

success = 0
total = len(test_cases)

for i, query_input in enumerate(test_cases, 1):
    print(f"[{i}/{total}] Query: {query_input}")
    
    try:
        generated = generate_query(query_input)
        
        # Check INRANGE usage
        uses_inrange = "INRANGE" in generated.upper()
        uses_and_range = (">=" in generated or "<=" in generated) and "AND" in generated
        
        print(f"Generated:")
        print(f"  {generated}")
        print()
        
        if uses_inrange:
            print(f"  ✅ PASS - Usa INRANGE correttamente")
            success += 1
        elif uses_and_range:
            print(f"  ⚠️  SOFT FAIL - Usa AND invece di INRANGE (semanticamente corretto)")
        else:
            print(f"  ❌ FAIL - Non gestisce range")
        
        print()
        
        # Rate limiting - aspetta 10 secondi tra le query
        if i < total:
            print(f"  ⏳ Attesa 10 secondi...")
            time.sleep(10)
        
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        print()

print("=" * 70)
print(f"RISULTATO: {success}/{total} query usano INRANGE")
if success == total:
    print("🎉 PERFETTO! Tutte le query usano INRANGE!")
elif success >= total * 0.8:
    print("✅ OTTIMO! Maggioranza delle query usa INRANGE")
else:
    print("⚠️  ATTENZIONE: Poche query usano INRANGE - serve più training")
print(f"Accuracy INRANGE: {(success/total)*100:.1f}%")
print("=" * 70)