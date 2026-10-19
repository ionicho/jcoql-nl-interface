# Diagnostica quota Gemini: prova alcuni modelli con 1 chiamata e stampa l'errore COMPLETO.
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(HERE), ".env")); load_dotenv()
except Exception as e:
    print("dotenv:", e)
import google.generativeai as genai
key = os.environ.get("GEMINI_API_KEY", "")
print("chiave trovata:", bool(key), "| lunghezza:", len(key), "| ultime 4:", key[-4:])
genai.configure(api_key=key)
models = ["gemini-3.1-flash-lite-preview", "gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-flash-lite-latest"]
for name in models:
    print("\n=== ", name)
    try:
        r = genai.GenerativeModel(name).generate_content("Reply with the word ok")
        print("FUNZIONA:", r.text.strip()[:40])
    except Exception as ex:
        print("ERRORE:", type(ex).__name__)
        print(str(ex)[:2500])
