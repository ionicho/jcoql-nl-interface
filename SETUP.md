# Setup — jcoql-nl-interface

Guida passo-passo per far girare il progetto da zero su una macchina nuova, in
ordine. Ogni passo qui esiste perché durante lo sviluppo saltarlo o farlo
nell'ordine sbagliato ha causato un errore concreto — sono raccolti qui apposta
per non doverli riscoprire uno per uno.

---

## 1. Prerequisiti

| Software | Versione | Note |
|---|---|---|
| Python | 3.x | |
| Node.js | — | per il frontend |
| MongoDB | — | in esecuzione in locale su `localhost:27017` |
| Java | 8+ | necessario per il motore J-CO Framework e il parser ANTLR3 ufficiale |
| Ollama | — | solo se vuoi usare Llama/Gemma in locale; opzionale se usi solo Gemini |
| Gradle | — | solo se modifichi il fork `jco-framework`, non necessario per usare l'interfaccia così com'è |

---

## 2. Clona e installa le dipendenze

```bash
git clone https://github.com/ionicho/jcoql-nl-interface.git
cd jcoql-nl-interface

python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac

pip install -r requirements.txt

cd frontend
npm install
cd ..
```

---

## 3. Variabili d'ambiente

```bash
cp .env.example .env
```

Apri `.env` e imposta almeno `GEMINI_API_KEY` (necessaria anche se pensi di usare
solo i modelli locali: alcuni percorsi del codice la richiedono comunque
all'avvio). Le altre variabili (`ACTIVE_LLM`, `ACTIVE_PARSER`, `ACTIVE_EXECUTOR`,
`JCOQL_DEBUG`) hanno un default sensato e non serve toccarle per un primo avvio:

- `ACTIVE_LLM` — default `gemini`. Cambiabile anche a runtime dalla UI, non solo da qui.
- `ACTIVE_PARSER` — default `antlr3_official`. **Non ha un modo per cambiarlo a runtime**, solo da qui + riavvio.
- `ACTIVE_EXECUTOR` — default `jco_framework`. **È l'unico usato e testato in questo progetto** — esiste anche `python_translator` (traduzione diretta senza motore Java, copertura limitata a `GET COLLECTION`+`FILTER` semplice), ma non è quello su cui si basano gli esempi/i test di questo repository. Non cambiarlo se non stai facendo un esperimento apposito.

---

## 4. Ollama (solo se vuoi Llama/Gemma in locale)

Se non ti interessano i modelli locali, salta questo passo — Gemini funziona senza Ollama.

1. Installa Ollama: https://ollama.com
2. Scarica i due modelli usati dal progetto (i nomi esatti contano, sono hardcoded in `backend/llm_local.py`):
   ```bash
   ollama pull llama3.1:8b-instruct-q4_K_M
   ollama pull gemma:7b-instruct-q4_K_M
   ```
3. Verifica che Ollama sia in esecuzione prima di selezionare Llama/Gemma dalla UI — se non lo è, o se il modello non è stato scaricato con questo esatto tag, la generazione fallisce con un errore che risale fino all'endpoint `/api/generate` (l'eccezione non è gestita dentro `llm_local.py`, la vedi propagata).
4. Nota VRAM: passare da Gemma a Llama nella stessa sessione può richiedere un riavvio di Ollama per liberare memoria — te lo ricorda anche un avviso nella UI quando selezioni Llama.

---

## 5. Dati di esempio in MongoDB

Il database di riferimento usato da tutti gli esempi RAG e dai test è `jcoql_test`,
con 5 collection: `hotels`, `restaurants`, `products`, `orders`, `users`.

**Opzione A — rigenera i dati da zero:**
```bash
python backend/database/sample_data.py
```
Va lanciato dalla **radice del progetto** (usa percorsi relativi tipo
`backend/database/data_....json`) e crea 5 file `data_*.json` in
`backend/database/`. Nota: non usa un seed casuale fisso, quindi ogni esecuzione
genera dati leggermente diversi dalla precedente (nomi, prezzi, rating cambiano) —
se ti basta "dati di prova plausibili" va benissimo, se ti serve riprodurre
esattamente un run precedente non funziona così com'è.

Poi importa ciascun file in MongoDB, ad esempio con `mongoimport`:
```bash
mongoimport --db jcoql_test --collection hotels --file backend/database/data_hotels.json --jsonArray
mongoimport --db jcoql_test --collection restaurants --file backend/database/data_restaurants.json --jsonArray
mongoimport --db jcoql_test --collection products --file backend/database/data_products.json --jsonArray
mongoimport --db jcoql_test --collection orders --file backend/database/data_orders.json --jsonArray
mongoimport --db jcoql_test --collection users --file backend/database/data_users.json --jsonArray
```
(adatta i nomi dei campi array/formato JSON al comando/tool che preferisci usare — va bene anche MongoDB Compass.)

**Opzione B — hai già un database MongoDB popolato:** salta questo passo, e
collega il tuo database dalla UI (sidebar → "Connetti nuovo database") o
modificando la connessione di default in `main.py`/`.env`.

---

## 6. Carica gli esempi RAG in ChromaDB

**Passo obbligatorio, non saltabile:** il backend si aspetta che la collection
ChromaDB `jcoql_examples` esista già all'avvio (usa `get_collection`, non
`get_or_create_collection` — se la collection non c'è, l'inizializzazione fallisce
silenziosamente e la generazione delle query non ha esempi da cui partire).

```bash
python backend/database/load_examples.py
```

Scansiona **tutti** i file `.txt` presenti in `examples/validated/` (percorso
calcolato rispetto alla posizione dello script, non alla cartella da cui lo
lanci) e ricrea la collection da zero ogni volta che lo rilanci — sicuro da
rilanciare dopo aver modificato o aggiunto un file di esempi.

Se lo rilanci **a backend già avviato**, riavvia anche il backend: altrimenti
resta collegato al riferimento della collection precedente (chiusa/sostituita nel
frattempo) invece di quella appena ricreata.

---

## 7. Avvio

```bash
# Terminale 1 — Backend (dalla radice del progetto: main.py importa
# moduli con path tipo "backend.xxx", va lanciato da lì)
venv\Scripts\activate
uvicorn main:app --reload

# Terminale 2 — Frontend
cd frontend
npm run dev
```

Apri il browser su **http://localhost:5173**.

---

## 8. Verifica che sia tutto a posto

Checklist rapida dopo il primo avvio:

- [ ] Il backend si avvia senza errori in console (in particolare: nessun errore su ChromaDB/`jcoql_examples` — se lo vedi, torna al passo 6)
- [ ] Dalla UI, digitando una richiesta in linguaggio naturale semplice (es. "hotel a Milano") ottieni una query JCoQL+ generata e risultati
- [ ] La Dashboard (`/dashboard`) mostra database e collezioni connesse coerenti con quello che ti aspetti
- [ ] Se usi anche i modelli locali: selezionando Llama/Gemma dalla UI, la generazione funziona (altrimenti torna al passo 4)

---

## 9. Debug

Il sistema stampa log diagnostici dettagliati (output grezzo del motore Java per i
comandi diversi da `GET COLLECTION`, esempi RAG recuperati per ogni richiesta,
riepilogo dell'esecuzione) solo se richiesto esplicitamente:

```bash
set JCOQL_DEBUG=true          # Windows (PowerShell: $env:JCOQL_DEBUG="true")
# export JCOQL_DEBUG=true     # Linux/Mac
```

Di default è spento. I file di log applicativi (non il debug sopra) si trovano
comunque sempre in `logs/` (creata automaticamente al primo avvio, un file per
sessione con timestamp nel nome).

---

## 10. Problemi comuni e dove guardare

| Sintomo | Causa più probabile |
|---|---|
| Errore all'avvio su ChromaDB/`jcoql_examples` | Passo 6 (`load_examples.py`) non eseguito prima del primo avvio |
| "Modello non trovato" o "connection refused" selezionando Llama/Gemma | Ollama non in esecuzione, o modello non scaricato con il tag esatto (passo 4) |
| La generazione funziona ma i risultati sono su un database inatteso | Verifica quale database è "corrente" in sidebar — è uno stato del processo, non per singola richiesta |
| Upload di file/gestione collection da UI non disponibile | Funzionalità intenzionalmente disattivata in questa versione (richiede lavoro architetturale non ancora fatto sul lato multi-database) |
| Uno script standalone (es. `test_retrieval.py`, `sample_data.py`) dà `FileNotFoundError` | Quasi sempre un problema di working directory: questi script usano percorsi relativi e vanno lanciati dalla radice del progetto, non dalla cartella in cui si trovano |
