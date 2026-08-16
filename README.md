# JCoQL+ Natural Language Interface

Sistema di traduzione Natural Language → JCoQL+ con RAG (Retrieval-Augmented Generation), validazione tramite parser ANTLR3 ufficiale ed esecuzione su database MongoDB reale tramite il motore J-CO Framework.

**Università degli Studi di Bergamo**
**Tesi Magistrale** - Nicholas Iotti
**Relatori:** Prof. Giuseppe Psaila, Prof. Paolo Fosci

---

## Obiettivo

Permettere agli utenti di interrogare database MongoDB usando **linguaggio naturale** invece di scrivere query JCoQL+ manualmente, con:
- Generazione automatica di query JCoQL+ tramite LLM (multi-provider: cloud e locale)
- Validazione tramite il parser ANTLR3 ufficiale del progetto J-CO
- Esecuzione reale tramite il motore J-CO Framework, non una reimplementazione
- Supporto a 10 comandi del linguaggio, inclusi JOIN cross-database e concatenati, MERGE su N database, GENERATE, GET DICTIONARY
- Multi-database, con scoperta automatica dello schema (inclusi tipi e valori di esempio per campo) e riconoscimento approssimato dei campi

> Nota metodologica: le sezioni di questo README riportano solo dati verificati con test diretti sul sistema. Dove una misura non è stata riverificata di recente, è segnalato esplicitamente.

---

## Architettura

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
│    (tipo e valori di esempio per campo, non solo il nome) │
│  • Grammatica JCoQL+ completa nel prompt, non un sottoinsieme │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  PARSER VALIDATION + RIPARAZIONI DETERMINISTICHE          │
│  • ANTLR3 Official (repository del progetto J-CO)         │
│  • Repair loop automatico sugli errori di validazione     │
│  • Riparazioni mirate per errori ricorrenti non risolti    │
│    in modo affidabile dal solo prompt (vedi sezione        │
│    "Riparazioni deterministiche" più sotto)                │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  JCO FRAMEWORK EXECUTOR                                   │
│  • Motore Java ufficiale J-CO, lanciato come subprocess    │
│  • Strategia "auto SAVE AS": ogni query riceve in coda     │
│    un SAVE AS verso una collection temporanea univoca;     │
│    il risultato è riletto da MongoDB e la collection       │
│    cancellata subito dopo — è il motore stesso a calcolare │
│    il risultato, non una ricostruzione lato Python          │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  MONGODB EXECUTION                                         │
│  • Multi-database, con switching da interfaccia            │
│  • Schema discovery ricorsiva per ogni database connesso    │
└──────────────────┬────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  RESULTS VISUALIZATION                                     │
│  • Documenti JSON, sintassi JCoQL+ completa eseguita        │
│  • Conteggio reale (non limitato ai documenti visualizzati) │
│  • Query preferite salvabili e ricercabili (localStorage)   │
└─────────────────────────────────────────────────────────┘
```

---

## Quick Start

> Guida rapida. Per la procedura completa passo-passo (inclusi i comandi
> esatti per Ollama, il seed di MongoDB, e l'ordine corretto in cui
> lanciare tutto la prima volta), vedi **[SETUP.md](SETUP.md)**.

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
# Assicurati che MongoDB sia in esecuzione. Per popolare il database di
# esempio "jcoql_test" da zero, vedi SETUP.md (sezione "Dati di esempio").

# 6. Carica gli esempi in ChromaDB
python backend/database/load_examples.py
```

`load_examples.py` scansiona **tutti** i file `.txt` presenti in `examples/validated/`
(percorso calcolato rispetto alla posizione dello script, non alla cartella da cui lo
lanci) e ricrea la collection ChromaDB da zero a ogni esecuzione — dopo averlo lanciato,
**riavvia il backend**, altrimenti resta collegato al riferimento della collection precedente.

> Questo era già tutto quello che serve per un avvio "al volo" se hai già un ambiente
> pronto. Per un ambiente nuovo (Ollama, modelli locali, seed MongoDB, verifica finale),
> segui **[SETUP.md](SETUP.md)** in ordine — evita gran parte degli errori più comuni
> incontrati durante lo sviluppo (percorsi relativi, ordine di avvio, modelli Ollama
> non scaricati).

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

Il sistema stampa log diagnostici dettagliati (query completa mandata al motore Java,
esempi RAG recuperati per ogni richiesta, riepilogo dell'esecuzione) — la query completa
è sempre visibile in console, il resto solo se richiesto esplicitamente:
```bash
set JCOQL_DEBUG=true   # Windows (PowerShell: $env:JCOQL_DEBUG="true")
# export JCOQL_DEBUG=true   # Linux/Mac
```
Di default è spento, per non intasare la console durante un uso normale.

---

## Stack Tecnologico

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
- **Persistenza locale:** localStorage (query preferite)

---

## Database Integration

### Multi-Database
- Selezione di uno o più database da interfaccia (un'unica modalità, la selezione
  "singolo database" precedente è stata rimossa perché ridondante)
- Scoperta automatica dello schema per ogni database connesso, inclusi campi annidati,
  tipo osservato e valori di esempio reali per campo
- Riconoscimento approssimato dei nomi di campo (basato su `difflib`, non su liste di
  parole chiave scritte a mano) per gestire richieste cross-lingua
- La generazione riceve l'elenco completo dei database selezionati (non solo il primo),
  necessario perché l'LLM possa usare i nomi reali in query che coinvolgono più database
  invece di indovinarli

### Query Execution — esempi verificati

**Modalità 1: Linguaggio Naturale → JCoQL+**
```
Input: "Raggruppa gli ordini per stato"
  ↓
Query generata: GET COLLECTION orders;
                GROUP PARTITION TRUE BY .status INTO .orders_by_status;
  ↓
Esecuzione: risultato reale letto dal motore, nessuna ricostruzione lato Python
```

**Modalità 2: Query JCoQL+ diretta, con JOIN cross-database**
```
Input: USE DB jcoql_test ON DEFAULT SERVER;
       USE DB test_db ON DEFAULT SERVER;
       JOIN OF COLLECTIONS users@jcoql_test AS t1, users@test_db AS t2
       CASE WHERE .t1.user_id = .t2.id;
  ↓
Esecuzione: 5 documenti reali, letti dal motore
```

**Modalità 3: Più JOIN nella stessa richiesta ("join concatenati")**
```
Input: "ordini con l'utente che li ha effettuati e i prodotti acquistati"
  ↓
Query generata: JOIN (ordini↔utenti) → SAVE AS intermedio → EXPAND
                dell'array articoli → JOIN (articoli↔prodotti)
  ↓
Esecuzione: 6 documenti reali; le collection intermedie sono cancellate
            automaticamente a fine esecuzione
```

---

## Comandi JCoQL+ Supportati

Il sistema supporta 10 comandi principali del linguaggio, tutti eseguiti dal motore
J-CO Framework reale (non da una reimplementazione Python del linguaggio):

| Comando | Stato | Note |
|---|---|---|
| `GET COLLECTION` (database) | Completo | Operatori di confronto, `AND`/`OR`, `IN_RANGE`, campi annidati |
| `GET COLLECTION FROM WEB` / `FROM FILE` | Completo | Il percorso di `FROM FILE` è risolto rispetto alla working directory del processo Java |
| `FILTER` + `GENERATE` (`BUILD`/`ADD FIELDS`/`REMOVE FIELDS`) | Completo | `KEEP`/`DROP OTHERS` validi solo dopo una `CASE WHERE`; nessuna aritmetica diretta come valore di campo (solo riferimenti, letterali, funzioni) |
| `JOIN OF COLLECTIONS` | Completo, solo `INNER` | Cross-database funzionante (nativo, `@db1`/`@db2`); `LEFT`/`RIGHT`/`FULL OUTER` non esistono nella grammatica JCoQL+, non implementati per scelta |
| Join concatenati (più `JOIN` nella stessa query) | Completo | Tramite `SAVE AS` intermedio, con pulizia automatica delle collezioni temporanee; se la chiave di join è dentro un array serve un `EXPAND` intermedio (il confronto `=` richiede stesso tipo sui due lati, un array non è mai "uguale" a un valore singolo anche se lo contiene) |
| `GROUP PARTITION` | Completo | Multi-partizione nello stesso comando, `ORDER BY` (richiede `TYPE NUMERIC`/`STRING`/`BOOLEAN` esplicito) |
| `EXPAND UNPACK` | Completo | Multi-clausola nello stesso comando |
| `MERGE COLLECTIONS` | Completo | Numero qualunque di collezioni/database, `REMOVE DUPLICATES` opzionale |
| `INTERSECT COLLECTIONS` | Verificato solo su dati disgiunti | Mai testato un caso con overlap reale |
| `SUBTRACT COLLECTIONS` | Verificato solo su dati disgiunti | Come sopra |
| `GET DICTIONARY` + `TRANSLATE` | Completo | Riparazione automatica se l'LLM genera `TRANSLATE` senza il `GET DICTIONARY` corrispondente (vedi sotto) |
| `SAVE AS coll@db` | Completo | `@database` sempre obbligatorio, altrimenti non scrive su MongoDB (by design) |
| `SAVE TO FILE` | Verificato | Percorsi relativi risolti rispetto alla working directory del processo Java |

**Non implementati, fuori dallo scope attuale:** `LOOKUP FROM WEB`, `TRAJECTORY MATCHING`,
le 7 varianti di `CREATE FUZZY` (due delle quali, `CREATE JAVA/JAVASCRIPT FUNCTION`,
permetterebbero l'esecuzione di codice arbitrario lato server generato da un prompt in
linguaggio naturale — evitate per ragioni di sicurezza, non solo di complessità
implementativa).

Per ogni comando, il risultato mostrato è quello vero calcolato dal motore J-CO: la
query ricevuta viene fatta seguire in modo trasparente da un `SAVE AS` verso una
collection temporanea a nome univoco, il cui contenuto viene poi riletto da MongoDB e la
collection cancellata — non c'è più nessuna ricostruzione della semantica dei comandi
lato Python (vedi architettura sopra).

---

## Riparazioni deterministiche

Durante lo sviluppo alcuni errori di generazione si sono ripresentati più volte in modo
sistematico, anche dopo aver rafforzato l'istruzione nel prompt e verificato che l'esempio
RAG pertinente venisse effettivamente recuperato. In quei casi, invece di continuare a
insistere sul prompt, l'errore viene riconosciuto e corretto direttamente nel codice dopo
la generazione:

- **`TRANSLATE` senza `GET DICTIONARY`**: se la query generata usa `TRANSLATE(...)` ma non
  registra mai il dizionario con `GET DICTIONARY`, il nome del dizionario viene cercato
  nella richiesta originale dell'utente (pattern tipo "dizionario X") e la riga mancante
  viene aggiunta automaticamente.
- **`@database` mancante o inventato** su un riferimento a collection dentro `JOIN`/`MERGE`:
  aggiunto se assente; se il modello ha inventato un nome che coincide con una collection
  invece di un database reale, la riga `USE DB` fittizia viene rimossa e sostituita con il
  database corretto (confrontato contro l'elenco dei database realmente registrati, non
  contro un elenco scritto a mano).
- **Disallineamento di tipo in un `JOIN`**: se la condizione confronta lo stesso nome di
  campo tra due collezioni con tipi diversi per quel campo secondo lo schema scoperto (es.
  un intero contro una stringa), è un segnale che il nome coincide ma il significato no —
  qui il sistema non sceglie un sostituto, segnala l'incongruenza e forza un altro
  tentativo di generazione con l'evidenza concreta.

---

## Architecture Patterns

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

> Esiste anche un secondo executor (`python_translator.py`, traduzione diretta
> JCoQL+→MongoDB senza passare dal motore Java, selezionabile con
> `ACTIVE_EXECUTOR=python_translator`), pensato come fallback leggero limitato a
> `GET COLLECTION`+`FILTER` semplice. Il progetto usa e testa sempre e solo
> `jco_framework` (il default): è quello a cui si riferisce l'intero README.

---

## Limitazioni Note

- **Scelta della chiave di JOIN via linguaggio naturale**: quando due collezioni
  condividono un nome di campo che però si riferisce a entità diverse (es. un campo
  `user_id` presente in entrambe, ma stringa identificativa in una e numero progressivo
  interno nell'altra), il modello può comunque scegliere il campo sbagliato al primo
  tentativo, nonostante lo schema mostri tipo e valori di esempio reali per ciascun campo.
  Il controllo di disallineamento di tipo (sezione sopra) intercetta il caso più comune e
  forza un altro tentativo, ma non garantisce che il tentativo successivo sia corretto —
  resta un limite del ragionamento del modello linguistico, non del meccanismo di verifica.
  Per questo l'interfaccia mantiene anche un JOIN manuale (form dedicato, non generato da
  LLM), dove l'utente specifica direttamente i campi di collegamento.
- **`INTERSECT`/`SUBTRACT`**: l'uguaglianza fra documenti (basata sul contenuto,
  esclusa `_id`) è verificata solo su collezioni prive di sovrapposizione reale.
- **Modelli LLM locali**: nei test comparativi, Llama e Gemma mostrano un tasso di
  successo sensibilmente inferiore al provider cloud sugli stessi input, oltre a una
  latenza per chiamata più alta.
- **Percorsi relativi**: sia lato Java (classpath, file di configurazione del motore)
  sia lato script Python (`load_examples.py`), diversi bug incontrati durante lo
  sviluppo sono derivati da percorsi relativi risolti rispetto alla cartella di lancio
  invece che a un riferimento assoluto — un'indagine approfondita su uno di questi casi
  (il comando `SAVE AS`, e la causa radice trovata poi nel fork del motore J-CO stesso)
  è documentata in un report tecnico separato.

---

## Project Structure

```
jcoql-nl-interface/
├── main.py                        # FastAPI backend (va lanciato dalla radice)
├── .env
├── requirements.txt
│
├── backend/
│   ├── query_corrector.py
│   ├── join_executor.py           # Costruisce query JOIN native (solo INNER)
│   ├── rag_examples_extended.txt  # Iniettato SEMPRE in ogni prompt - solo pattern
│   │                               # sintattici generici, nessun nome di campo legato
│   │                               # a un database specifico
│   ├── jcoql_syntax_official.txt  # Grammatica completa JCoQL.g, iniettata nel prompt
│   ├── jcoql_syntax_basic_official.txt  # Grammatica Basic, copia fedele (non iniettata)
│   │
│   ├── parsers/
│   │   ├── parser_factory.py
│   │   └── antlr3_official_parser.py
│   │
│   ├── executors/
│   │   ├── executor_factory.py
│   │   └── jco_framework_executor_v2.py  # Strategia "auto SAVE AS"
│   │
│   └── database/
│       ├── schema_discovery.py    # Scopre campi, tipi e valori di esempio
│       └── load_examples.py       # Scansiona examples/validated/*.txt, percorsi
│                                    # assoluti rispetto alla posizione dello script
│
├── examples/validated/
│   └── *.txt                       # Esempi RAG, caricati automaticamente tutti
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── QueryExecutor.jsx       # Pannello unico: input, query editabile, risultati
│   │   ├── Favorites.jsx           # Query preferite, ricerca, localStorage
│   │   ├── DatabaseSelector.jsx    # Include anche il JOIN manuale (fallback)
│   │   └── Dashboard.jsx
│   └── package.json
│
└── chroma_data/                    # Storage persistente ChromaDB
```

---

## Contributors

**Nicholas Iotti** - Università degli Studi di Bergamo
GitHub: [@ionicho](https://github.com/ionicho)

**Relatori:**
- Prof. Giuseppe Psaila
- Prof. Paolo Fosci

---

## License

Progetto tesi magistrale - Università degli Studi di Bergamo
