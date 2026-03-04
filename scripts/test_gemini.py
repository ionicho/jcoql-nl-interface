#!/usr/bin/env python3
"""
Test Gemini 2.5 Flash API - Con gestione sicura API key
"""
import os
from dotenv import load_dotenv
from google import genai

# Carica variabili da .env
load_dotenv()

# Leggi API key da environment
API_KEY = os.getenv('GEMINI_API_KEY')

if not API_KEY:
    print("❌ ERRORE: GEMINI_API_KEY non trovata!")
    print("Crea file .env con: GEMINI_API_KEY=tua_key")
    exit(1)

# Crea client
client = genai.Client(api_key=API_KEY)

print("🧪 Testing Gemini 2.5 Flash API...\n")

try:
    response = client.models.generate_content(
        model='models/gemini-2.5-flash',
        contents="Ciao! Dimmi solo 'Funziono!' se mi ricevi."
    )
    
    print("✅ Risposta da Gemini 2.5 Flash:")
    print(response.text)
    print("\n🎉 SUCCESS! Gemini API funziona perfettamente!")
    
except Exception as e:
    print(f"❌ Errore: {e}")