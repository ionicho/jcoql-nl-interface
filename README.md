# JCoQL+ Natural Language Interface

Sistema di traduzione Natural Language → JCoQL+ con RAG (Retrieval-Augmented Generation), validazione tramite parser ANTLR3 ufficiale ed esecuzione su database MongoDB reale tramite il motore J-CO Framework.

**Università degli Studi di Bergamo**
**Tesi Magistrale** - Nicholas Iotti
**Relatori:** Prof. Giuseppe Psaila, Prof. Paolo Fosci

---

## 🎯 Obiettivo

Permettere agli utenti di interrogare database MongoDB usando **linguaggio naturale** invece di scrivere query JCoQL+ manualmente, con:
- ✅ Generazione automatica di query JCoQL+ tramite LLM (multi-provider: cloud e locale)
- ✅ Validazione tramite il parser ANTLR3 ufficiale del progetto J-CO
- ✅ Esecuzione reale tramite il motore J-CO Framework, non una reimplementazione
- ✅ Supporto a 9 comandi del linguaggio, non solo GET COLLECTION+FILTER
- ✅ Multi-database, con scoperta automatica dello schema e riconoscimento approssimato dei campi

> Nota metodologica: le sezioni di questo README riportano solo dati verificati con test diretti sul sistema. Dove una misura non è stata riverificata di recente, è segnalato esplicitamente.

---

## 🏗️ Architettura

```
┌─────────────────────────────────────────────────────────┐
│  USER INPUT                                              │
│  • Natural Language: "Raggruppa gli ordini per stato"    │
│  • Direct JCoQL+: GET COLLECTION hotels; ...              │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  RAG RETRIEVAL (ChromaDB)                                │
│  • Esempi validati, caricati da examples/validated/*.txt │
│  • Embedding locali: all-MiniLM-L6-v2                    │
│  • Top-N esempi semanticamente più simili                │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  LLM GENERATION (multi-provider, selezione if/elif,      │
│  non una vera Factory)                                   │
│  • Google Gemini (cloud)                                 │
│  • Llama 3.1 / Gemma via Ollama (locale)                 │
│  • Schema MongoDB reale del database attivo nel prompt    │
│  • Regole sintattiche JCoQL+ per tutti i 9 comandi        │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  PARSER VALIDATION                                        │
│  • ANTLR3 Official (repository del progetto J-CO)         │
│  • Repair loop automatico sugli errori di validazione     │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  JCO FRAMEWORK EXECUTOR                                   │
│  • Motore Java ufficiale J-CO, lanciato come subprocess    │
│  • Per i comandi diversi da GET COLLECTION il motore       │
│    riporta solo il conteggio: i risultati sono             │
│    ricostruiti lato Python e verificati incrociando il      │
│    conteggio dichiarato dal motore stesso                  │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  MONGODB EXECUTION                                         │
│  • Multi-database, con switching da interfaccia            │
│  • Schema discovery ricorsiva per database connesso         │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  RESULTS VISUALIZATION                                     │
│  • Documenti JSON, sintassi JCoQL+ completa eseguita        │
│  • Conteggio reale (non limitato ai documenti visualizzati) │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.x**
- **Node.js**
- **MongoDB**
- **Ollama** (per LLM locali, opzionale)
- **Java 8+** (per il motore J-CO Framework e il parser ANTLR3)
- **Gradle** (per compilare il framework J-CO, se modificato)

### Installation
```bash
# 1. Clone repository
git clone https://github.com/ionicho/jcoql-nl-interface.git
cd jcoql-nl-interface

# 2. Backend setup
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt

# 3. Frontend setup
cd frontend
npm install

# 4. Environment variables
cp .env.example .env
# Modifica .env con la tua GEMINI_API_KEY

# 5. MongoDB
# Assicurati che MongoDB sia in esecuzione e che i database/collezioni
# che intendi usare siano popolati (vedi backend/database/ per gli script
# di seed, se presenti)

# 6. Carica gli esempi in ChromaDB
python backend/database/load_examples.py
```

`load_examples.py` scansiona **tutti** i file `.txt` presenti in `examples/validated/`
(percorso calcolato rispetto alla posizione dello script, non alla cartella da cui lo
lanci) e ricrea la collection ChromaDB da zero a ogni esecuzione — dopo averlo lanciato,
**riavvia il backend**, altrimenti resta collegato al riferimento della collection precedente.

### Run
```bash
# Terminal 1: Backend (dalla radice del progetto - gli import usano il pacchetto "backend")
venv\Scripts\activate
uvicorn main:app --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

Apri il browser su: **http://localhost:5173**

### Debug

Il sistema stampa log diagnostici dettagliati (output grezzo del motore Java per i
comandi diversi da GET COLLECTION, esempi RAG recuperati per ogni richiesta, riepilogo
dell'esecuzione) solo se richiesto esplicitamente:
```bash
set JCOQL_DEBUG=true   # Windows (PowerShell: $env:JCOQL_DEBUG="true")
# export JCOQL_DEBUG=true   # Linux/Mac
```
Di default è spento, per non intasare la console durante un uso normale.

---

## 📦 Stack Tecnologico

### Backend
- **Framework:** FastAPI
- **Database:** MongoDB
- **Vector DB:** ChromaDB (persistente, locale)
- **LLM Cloud:** Google Gemini
- **LLM Locale:** Ollama (Llama 3.1, Gemma)
- **Embeddings:** sentence-transformers (all-MiniLM-L6-v2, locali)
- **Parser:** ANTLR3 (repository ufficiale del progetto J-CO)
- **Executor:** motore J-CO Framework (Java), lanciato come subprocess

### Frontend
- **Framework:** React
- **Build:** Vite
- **Routing:** React Router
- **HTTP:** Axios

---

## 🗄️ Database Integration

### Multi-Database
- Selezione del database da interfaccia (singolo o multiplo)
- Scoperta automatica dello schema per il database attivo, inclusi campi annidati
- Riconoscimento approssimato dei nomi di campo (basato su `difflib`, non su liste di
  parole chiave scritte a mano) per gestire richieste cross-lingua

### Query Execution — esempi verificati

**Modalità 1: Linguaggio Naturale → JCoQL+**
```
Input: "Raggruppa gli ordini per stato"
  ↓
Query generata: GET COLLECTION orders;
                GROUP PARTITION TRUE BY .status INTO .orders_by_status;
  ↓
Esecuzione: 5 gruppi, conteggio verificato contro il motore J-CO
```

**Modalità 2: Query JCoQL+ diretta**
```
Input: JOIN OF COLLECTIONS users AS u, orders AS o
       CASE WHERE .o.user_id = .u._id;
  ↓
Esecuzione: 2 documenti, conteggio identico a quello riportato dal motore
```

---

## ⚙️ Comandi JCoQL+ Supportati

Il sistema supporta 9 comandi del linguaggio, tutti eseguiti dal motore J-CO Framework
reale (non da una reimplementazione Python del linguaggio):

| Comando | Stato | Note |
|---|---|---|
| `GET COLLECTION` + `FILTER` | ✅ Completo | Operatori di confronto, `AND`/`OR`, `IN_RANGE`, campi annidati |
| `JOIN OF COLLECTIONS` | ✅ Stesso database | Cross-database (`@db1`/`@db2`) non funzionante, causa non identificata |
| `GROUP PARTITION` | ✅ Completo | Condizioni di partizione a singolo confronto |
| `EXPAND UNPACK` | ✅ Completo | Condizioni a singolo confronto, una sola clausola UNPACK per istruzione |
| `MERGE COLLECTIONS` | ✅ Completo | Con `REMOVE DUPLICATES` opzionale |
| `INTERSECT COLLECTIONS` | ⚠️ Verificato solo su dati disgiunti | Mai testato un caso con overlap reale |
| `SUBTRACT COLLECTIONS` | ⚠️ Verificato solo su dati disgiunti | Come sopra |
| `SAVE AS coll@db` | ✅ Completo | `@database` sempre obbligatorio, altrimenti non scrive su MongoDB (by design) |
| `SAVE TO FILE` | ✅ Verificato | Percorsi relativi risolti rispetto alla working directory del processo Java |

**Non implementati, fuori dallo scope attuale:** `GET DICTIONARY`, `LOOKUP FROM WEB`,
`TRAJECTORY MATCHING`, le 7 varianti di `CREATE FUZZY` (due delle quali,
`CREATE JAVA/JAVASCRIPT FUNCTION`, permetterebbero l'esecuzione di codice arbitrario
lato server generato da un prompt in linguaggio naturale — evitate per ragioni di
sicurezza, non solo di complessità implementativa).

Per ciascun comando diverso da `GET COLLECTION`, il motore J-CO riporta sullo standard
output solo il **conteggio** dei documenti risultanti, mai il loro contenuto: i risultati
vengono ricostruiti lato Python re-interrogando MongoDB, e il conteggio ricostruito è
verificato automaticamente contro quello dichiarato dal motore a ogni esecuzione (un
disallineamento genera un avviso in log).

---

## 🏭 Architecture Patterns

Il sistema usa il **Factory Pattern** per due componenti — non per la selezione del
LLM, che è realizzata con un semplice `if`/`elif` sul provider richiesto, non una vera
classe Factory:

```python
# backend/parsers/parser_factory.py
class ParserFactory:
    @staticmethod
    def create_parser(parser_type: ParserType):
        return ANTLR3OfficialParser()

# backend/executors/executor_factory.py
class ExecutorFactory:
    @staticmethod
    def create_executor(executor_type: ExecutorType):
        return JcoFrameworkExecutor()
```

---

## 🚧 Limitazioni Note

- **JOIN cross-database**: la sintassi `collezione@database` per collegare collezioni
  in database MongoDB diversi fallisce con un errore generico riportato dal motore; la
  causa non è stata identificata nonostante l'indagine.
- **Selezione della chiave di JOIN via linguaggio naturale**: quando due collezioni
  condividono un nome di campo che però si riferisce a entità diverse (es. un campo
  `user_id` con significati diversi in due collezioni), il modello linguistico può
  scegliere una chiave di collegamento sintatticamente valida ma semanticamente errata,
  perché il recupero RAG non sempre individua l'esempio più pertinente quando la
  richiesta condivide vocabolario superficiale con esempi di natura diversa (limite noto
  dei modelli di *sentence embedding* di piccole dimensioni). Per questo motivo
  l'interfaccia mantiene anche un meccanismo di JOIN manuale, dove l'utente specifica
  direttamente i campi di collegamento.
- **`INTERSECT`/`SUBTRACT`**: l'uguaglianza fra documenti (basata sul contenuto,
  esclusa `_id`) è verificata solo su collezioni prive di sovrapposizione reale.
- **Modelli LLM locali**: nei test comparativi, Llama e Gemma mostrano un tasso di
  successo sensibilmente inferiore al provider cloud sugli stessi input, oltre a una
  latenza per chiamata più alta.
- **Percorsi relativi**: sia lato Java (classpath, file di configurazione del motore)
  sia lato script Python (`load_examples.py`), diversi bug incontrati durante lo
  sviluppo sono derivati da percorsi relativi risolti rispetto alla cartella di lancio
  invece che a un riferimento assoluto — un'indagine approfondita su uno di questi casi
  (il comando `SAVE AS`) è documentata in un report tecnico separato.

---

## 📁 Project Structure

```
jcoql-nl-interface/
├── main.py                        # FastAPI backend (va lanciato dalla radice)
├── .env
├── requirements.txt
│
├── backend/
│   ├── query_corrector.py
│   ├── rag_with_validation.py
│   ├── rag_examples_extended.txt  # Iniettato SEMPRE in ogni prompt - solo pattern
│   │                               # sintattici generici, nessun nome di campo legato
│   │                               # a un database specifico
│   │
│   ├── parsers/
│   │   ├── parser_factory.py
│   │   └── antlr3_official_parser.py
│   │
│   ├── executors/
│   │   ├── executor_factory.py
│   │   └── jco_framework_executor_v2.py
│   │
│   └── database/
│       └── load_examples.py       # Scansiona examples/validated/*.txt, percorsi
│                                    # assoluti rispetto alla posizione dello script
│
├── examples/validated/
│   └── *.txt                       # Esempi RAG, caricati automaticamente tutti
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── QueryExecutor.jsx
│   │   ├── DatabaseSelector.jsx    # Include anche il JOIN manuale (fallback)
│   │   └── Dashboard.jsx
│   └── package.json
│
└── chroma_data/                    # Storage persistente ChromaDB
```

---

## 🤝 Contributors

**Nicholas Iotti** - Università degli Studi di Bergamo
GitHub: [@ionicho](https://github.com/ionicho)

**Relatori:**
- Prof. Giuseppe Psaila
- Prof. Paolo Fosci

---

## 📄 License

Progetto tesi magistrale - Università degli Studi di Bergamo