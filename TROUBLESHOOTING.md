# 🔧 Troubleshooting

Guida risoluzione problemi comuni

---

## CUDA Error: llama runner process terminated

**Sintomo:**
```
ollama._types.ResponseError: llama runner process has terminated: 
CUDA error (status code: 500)
```

**Causa:**
VRAM GPU insufficiente. Ollama tiene i modelli in memoria anche dopo il cambio LLM.

**Soluzioni:**

### Opzione A: Riavvia Ollama (RACCOMANDATO)
```powershell
# Windows
ollama stop

# Oppure force kill
taskkill /IM ollama.exe /F
ollama serve
```

### Opzione B: Usa configurazione senza conflitti
```bash
# .env
ACTIVE_LLM=gemini  # Cloud, nessun VRAM
# OPPURE
ACTIVE_LLM=llama   # Locale, 4.7GB VRAM
```

**Configurazione raccomandata:**
- ☁️ Gemini (cloud) + 🏠 Llama (locale) → ✅ Zero conflitti

### Opzione C: Upgrade GPU
- RTX 4070 (12GB): supporta Llama + Gemma simultaneamente
- RTX 4080 (16GB): supporta 3+ modelli locali

---

## Modelli Locali Lenti al Primo Avvio

**Sintomo:** Primo avvio Llama/Gemma richiede 30-60s

**Causa:** Download/caricamento iniziale modello (~5GB)

**Soluzione:** Normale! Avvii successivi: ~2s

**Preload modelli:**
```bash
ollama pull llama3.1:8b-instruct-q4_K_M
ollama pull gemma2:9b-instruct-q4_K_M
```

---

## ChromaDB Non Trova Esempi

**Sintomo:**
```
ATTENZIONE: Errore ChromaDB: Collection 'jcoql_examples' not found
```

**Soluzione:**
```bash
# Ricarica esempi
python backend\database\load_examples.py

# Verifica
python -c "import chromadb; c=chromadb.PersistentClient('./chroma_data'); print(c.get_collection('jcoql_examples').count())"
```

**Output atteso:** `59`

---

## Frontend Non Si Connette al Backend

**Sintomo:** Errori CORS o "Network Error"

**Verifica Backend:**
```bash
curl http://localhost:8000/api/llms
```

**Verifica CORS in `main.py`:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ← Deve essere "*" o "http://localhost:5173"
    ...
)
```

**Riavvia entrambi:**
```bash
# Backend: Ctrl+C poi uvicorn main:app --reload
# Frontend: Ctrl+C poi npm run dev
```

---

## Gemini API Quota Exceeded

**Sintomo:**
```
Error 429: Resource has been exhausted
```

**Causa:** Limite 500 richieste/giorno superato

**Soluzioni:**

### A) Switch a Llama (locale, illimitato)
```bash
# Frontend: cambia dropdown a "Llama"
# Oppure .env:
ACTIVE_LLM=llama
```

### B) Aspetta reset quota (24h)

### C) Usa API Key diversa (temporaneo)

---

## Parser Validation Fails (99% casi)

**Sintomo:** Query generata ma validation fallisce

**Causa:** Sintassi JCoQL non supportata dal parser

**Soluzione:** Regole sintattiche già integrate nel prompt!

**Se persiste:**
1. Verifica esempi in ChromaDB (devono essere 59)
2. Controlla prompt in `main.py` include `JCOQL_SYNTAX_BASIC`
3. Prova con LLM diverso (Llama vs Gemini)

---

## Import Error: No module named 'X'

**Sintomo:**
```
ModuleNotFoundError: No module named 'chromadb'
```

**Soluzione:**
```bash
# Attiva venv
venv\Scripts\activate  # Windows

# Reinstalla dipendenze
pip install -r requirements.txt
```

**Verifica venv attivo:**
```bash
which python  # Linux/Mac
where python  # Windows
# Output deve contenere "venv"
```

---

## Ollama Non Risponde

**Sintomo:** Timeout o "Connection refused"

**Verifica Ollama running:**
```bash
ollama list
```

**Se non funziona:**
```bash
# Riavvia Ollama
ollama serve
```

**Verifica modelli installati:**
```bash
ollama list
# Deve mostrare: llama3.1:8b-instruct-q4_K_M
```

---

## React Build Fails

**Sintomo:** `npm run dev` errori

**Soluzione:**
```bash
cd frontend

# Pulisci node_modules
rm -rf node_modules
rm package-lock.json

# Reinstalla
npm install

# Riprova
npm run dev
```

---

## Per Altri Problemi

**Apri issue su GitHub:** https://github.com/ionicho/jcoql-nl-interface/issues  
**O contatta:** nicho23iotti@gmail.com