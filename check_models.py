"""
Script di utilità per la verifica della configurazione API.
Carica le credenziali d'ambiente, si connette ai servizi Google e recupera
l'elenco dei modelli disponibili specificamente per la generazione di contenuti.
"""

import google.generativeai as genai
import os
from dotenv import load_dotenv

# Carica le variabili d'ambiente dal file .env situato nella radice del progetto.
# È fondamentale per mantenere segreta la GEMINI_API_KEY e non hardcodarla nel codice.
load_dotenv()

# Inizializza e configura il client SDK di Google Generative AI.
# Recupera la chiave API appena caricata in memoria da load_dotenv().
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

print("Lista modelli disponibili per la tua chiave:")

# Itera attraverso tutti i modelli LLM a cui l'account/chiave API ha accesso.
for m in genai.list_models():
    # Filtra la lista: seleziona esclusivamente i modelli che supportano il metodo 'generateContent'.
    # Questo esclude modelli dedicati solo ad altri scopi (es. text-embedding).
    if 'generateContent' in m.supported_generation_methods:
        print(f"✅ {m.name}")