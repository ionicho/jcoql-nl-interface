#!/usr/bin/env python3
"""
Test RAG Base - Primo tentativo generazione JCoQL+
Usa Gemini con esempi in context
"""
import os
from dotenv import load_dotenv
from google import genai

# Load environment
load_dotenv()
API_KEY = os.getenv('GEMINI_API_KEY')

if not API_KEY:
    print("❌ ERRORE: GEMINI_API_KEY non trovata!")
    print("Crea file .env con: GEMINI_API_KEY=tua_key")
    exit(1)

# Create client
client = genai.Client(api_key=API_KEY)

# ===== KNOWLEDGE BASE (semplificata) =====
EXAMPLES = """
Esempi JCoQL+:

1. Input: "Trova tutti i ristoranti a Milano"
   Output: GET COLLECTION restaurants; FILTER CASE WHERE .city = 'Milano';

2. Input: "Prodotti con prezzo maggiore di 100"
   Output: GET COLLECTION products; FILTER CASE WHERE .price > 100;

3. Input: "Hotel a Roma con rating superiore a 4"
   Output: GET COLLECTION hotels; FILTER CASE WHERE .city = 'Roma' AND .rating > 4;

4. Input: "Appartamenti tra 50 e 100 metri quadri"
   Output: GET COLLECTION apartments; FILTER CASE WHERE .superficie INRANGE [ 50 , 100 ];

5. Input: "Clienti senza email"
   Output: GET COLLECTION customers; FILTER CASE WHERE WITHOUT .email;
"""

SYSTEM_PROMPT = f"""Sei un esperto traduttore da linguaggio naturale a JCoQL+.

JCoQL+ è un linguaggio per interrogare database NoSQL con sintassi:
- GET COLLECTION nome; per recuperare collezione
- FILTER CASE WHERE condizione; per filtrare
- Operatori: =, !=, >, <, >=, <=
- Logica: AND, OR, NOT, ()
- Range: INRANGE [ min , max ]
- Predicati: WITH .field, WITHOUT .field

Regole IMPORTANTI:
1. Punto e virgola obbligatorio alla fine di ogni statement
2. Campi con punto: .city, .price, .rating
3. FILTER separato da GET COLLECTION
4. Usa INRANGE per intervalli numerici

{EXAMPLES}

Genera SOLO la query JCoQL+, niente spiegazioni."""

def generate_jcoql(natural_language_query):
    """Generate JCoQL+ query from natural language"""
    
    # Prompt completo
    full_prompt = f"""{SYSTEM_PROMPT}

Query in linguaggio naturale: "{natural_language_query}"

Genera la query JCoQL+ corrispondente:"""
    
    try:
        # Usa ESATTAMENTE la stessa struttura di test_gemini.py
        response = client.models.generate_content(
            model='models/gemini-2.5-flash',
            contents=full_prompt
        )
        
        # Accesso al testo (stesso metodo di test_gemini.py)
        result = response.text # ← Type hint esplicito
        
        # Pulisci output
        result = result.strip()
        
        # Rimuovi markdown code blocks se presenti
        if '```' in result:
            lines = result.split('\n')
            cleaned_lines = []
            for line in lines:
                if not line.strip().startswith('```'):
                    cleaned_lines.append(line)
            result = '\n'.join(cleaned_lines).strip()
        
        return result
    
    except Exception as e:
        return f"❌ Errore: {str(e)}"

# ===== TEST CASES =====
test_cases = [
    "Trova tutti i negozi a Bergamo",
    "Prodotti con prezzo inferiore a 50 euro",
    "Hotel a Firenze con rating maggiore di 3",
    "Appartamenti tra 60 e 80 metri quadri",
    "Utenti che hanno una foto profilo",
    "Clienti che NON hanno un numero di telefono"
]

print("=" * 60)
print("TEST RAG BASE - GENERAZIONE JCOQL+")
print("=" * 60)
print()

success_count = 0
total_count = len(test_cases)

for i, test_query in enumerate(test_cases, 1):
    print(f"TEST {i}/{total_count}")
    print(f"Input:  {test_query}")
    
    jcoql_query = generate_jcoql(test_query)
    
    print(f"Output: {jcoql_query}")
    
    # Basic validation
    has_get = "GET COLLECTION" in jcoql_query
    has_semicolon = ";" in jcoql_query
    has_error = "❌" in jcoql_query
    
    if has_get and has_semicolon and not has_error:
        print("✅ Validazione base: OK")
        success_count += 1
    else:
        print("⚠️ Validazione base: FAIL")
        if not has_get:
            print("   - Manca GET COLLECTION")
        if not has_semicolon:
            print("   - Manca punto e virgola")
        if has_error:
            print("   - Errore nella generazione")
    
    print("-" * 60)
    print()

# Summary
print("=" * 60)
print(f"RISULTATI: {success_count}/{total_count} query generate correttamente")
accuracy = (success_count/total_count)*100 if total_count > 0 else 0
print(f"Accuracy: {accuracy:.1f}%")
print()

if accuracy >= 80:
    print("🎉 OTTIMO! RAG base funzionante!")
    print("✅ Pronto per Settimana 2: ChromaDB + RAG avanzato")
elif accuracy >= 60:
    print("✅ BUONO! Necessario miglioramento prompt")
    print("→ Prossimo step: espandere esempi e migliorare system prompt")
else:
    print("⚠️ ATTENZIONE! Rivedere approccio")
    print("→ Possibili cause: prompt poco chiaro, esempi insufficienti")

print("=" * 60)
print()
print("📊 SETTIMANA 1 QUASI COMPLETATA!")
print("Prossimi passi:")
print("- Commit script RAG base")
print("- Generare report finale Settimana 1")
print("- Preparazione Settimana 2 (ChromaDB)")