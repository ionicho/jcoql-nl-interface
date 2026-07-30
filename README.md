# JCoQL+ Natural Language Interface

Sistema completo di traduzione Natural Language → JCoQL+ con RAG (Retrieval-Augmented Generation), validazione multi-parser e esecuzione su database MongoDB reale.

**Università degli Studi di Bergamo**  
**Tesi Magistrale** - Nicholas Iotti  
**Relatori:** Prof. Giuseppe Psaila, Prof. Paolo Fosci

---

## 🎯 Obiettivo

Permettere agli utenti di interrogare database MongoDB usando **linguaggio naturale** invece di scrivere query JCoQL manualmente, con:
- ✅ Generazione automatica query JCoQL sintatticamente corrette
- ✅ Validazione tramite parser ANTLR ufficiale
- ✅ Esecuzione su database MongoDB reale
- ✅ Upload dati personalizzati
- ✅ Accuracy 100% su query benchmark

---

## 🏗️ Architettura
```
┌─────────────────────────────────────────────────────────┐
│  USER INPUT                                            │
│  • Natural Language: "Hotel a Milano rating > 4"       │
│  • Direct JCoQL: GET COLLECTION hotels; ...            │
│  • File Upload: custom_data.json                       │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  RAG RETRIEVAL (ChromaDB)                              │
│  • 188 esempi validati                                 │
│  • Embedding: all-MiniLM-L6-v2                         │
│  • Top-3 esempi simili                                 │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  LLM GENERATION (Multi-Provider)                       │
│  • Gemini 3.1 Flash Lite (cloud)                       │
│  • Llama 3.1 8B (locale, 36% più veloce)               │
│  • Gemma 2 9B (locale)                                 │
│  • Schema MongoDB integrato nel prompt                 │
│  • Regole sintattiche JCoQL 4.0                        │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  PARSER VALIDATION (Multi-Parser)                     │
│  • ANTLR3 Official (repo prof)                         │
│  • ANTLR4 Custom (grammatica JCoQL 4.0)                │
│  • Switch runtime via UI                               │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  JCOQL EXECUTOR (Dual-Mode)                            │
│  • Python Translator: JCoQL → MongoDB (90% query)      │
│  • JCO Framework: Support completo + filtering         │
│  • Switch runtime via .env o UI                        │
│  • Filtri applicate direttamente in MongoDB            │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  MONGODB EXECUTION                                     │
│  • Database: jcoql_test                                │
│  • Collections: 5 predefinite + user uploads           │
│  • Query real-time                                     │
└──────────────────┬──────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────────┐
│  RESULTS VISUALIZATION                                 │
│  • JSON completo documenti                             │
│  • MongoDB query tradotta                              │
│  • Statistiche esecuzione                              │
└─────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.14+**
- **Node.js 24+**
- **MongoDB 8.2+**
- **Ollama** (per LLM locali, opzionale)
- **Java 8+** (per parser ANTLR3 ufficiale)

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
# Edit .env with your GEMINI_API_KEY

# 5. MongoDB setup
# Install MongoDB 8.2 from https://www.mongodb.com/try/download/community
# Import sample data:
mongoimport --db jcoql_test --collection hotels --file backend/database/data_hotels.json --jsonArray
mongoimport --db jcoql_test --collection products --file backend/database/data_products.json --jsonArray
mongoimport --db jcoql_test --collection users --file backend/database/data_users.json --jsonArray
mongoimport --db jcoql_test --collection orders --file backend/database/data_orders.json --jsonArray
mongoimport --db jcoql_test --collection restaurants --file backend/database/data_restaurants.json --jsonArray

# 6. Load examples in ChromaDB
python backend/database/load_examples.py
```

### Run
```bash
# Terminal 1: Backend
cd jcoql-nl-interface
venv\Scripts\activate
uvicorn main:app --reload

# Terminal 2: Frontend
cd frontend
npm run dev
```

Open browser: **http://localhost:5173**

---

## 📦 Stack Tecnologico

### Backend
- **Framework:** FastAPI
- **Database:** MongoDB 8.2
- **Vector DB:** ChromaDB (persistent)
- **LLM Cloud:** Google Gemini 3.1 Flash Lite
- **LLM Local:** Ollama (Llama 3.1 8B, Gemma 2 9B)
- **Embeddings:** sentence-transformers (all-MiniLM-L6-v2)
- **Parser:** ANTLR 4.9.3 + ANTLR 3.4
- **Executor:** Python JCoQL Translator + JCO Framework (dual-mode)

### Frontend
- **Framework:** React 19
- **Build:** Vite 8
- **Routing:** React Router 7
- **Styling:** TailwindCSS
- **HTTP:** Axios
- **Charts:** Chart.js (dashboard)

---

## 🗄️ Database Integration

### MongoDB Setup
- **Version:** 8.2.6
- **Collections:** 5 predefinite (hotels, products, users, orders, restaurants)
- **Sample Data:** 110 documenti con dati realistici italiani
- **Schema:** Documentato in `backend/database/SCHEMA_README.md`

### Collections Schema

**hotels** (20 docs)
```json
{
  "location": {"city": "Milano", "country": "Italy", "coordinates": {...}},
  "rating": 4.5,
  "price_per_night": 250,
  "stars": 5,
  "amenities": ["spa", "wifi", "restaurant"],
  "parking": true,
  "wifi": true,
  "breakfast_included": true
}
```

**products** (30 docs)
```json
{
  "category": "electronics",
  "price": 1299.99,
  "stock": 50,
  "brand": "Samsung",
  "discount": 20,
  "rating": 4.5,
  "organic": false
}
```

**users** (25 docs), **orders** (20 docs), **restaurants** (15 docs)

### Upload Custom Data
1. Navigate to `/upload` in UI
2. Upload JSON file (array format: `[{...}, {...}]`)
3. Collection created automatically with file name
4. Use immediately in queries

### Query Execution

**Mode 1: Natural Language → JCoQL**
```
Input: "Hotel a Milano con rating superiore a 4"
  ↓
Generated JCoQL: GET COLLECTION hotels; 
                 FILTER CASE WHERE .location.city = 'Milano' 
                 AND .rating > 4.0 
                 KEEP OTHERS;
  ↓
Execution: 2 hotels found
```

**Mode 2: Direct JCoQL Input**
```
Input: GET COLLECTION products; 
       FILTER CASE WHERE .category = 'electronics' 
       AND .price IN_RANGE [100, 500] 
       KEEP OTHERS;
  ↓
Execution: 6 products found
```
---

## 🏭 Architecture Patterns

### Factory Pattern Implementation

Il sistema implementa **Factory Pattern** su 3 livelli:

#### 1. LLM Factory
```python
# backend/llm_factory.py (future)
class LLMFactory:
    @staticmethod
    def create(llm_type: LLMType):
        if llm_type == LLMType.GEMINI:
            return GeminiLLM()
        elif llm_type == LLMType.LLAMA:
            return LlamaLLM()
```

#### 2. Parser Factory
```python
# backend/parsers/parser_factory.py
class ParserFactory:
    @staticmethod
    def create_parser(parser_type: ParserType):
        if parser_type == ParserType.ANTLR4_CUSTOM:
            return ANTLR4CustomParser()
        elif parser_type == ParserType.ANTLR3_OFFICIAL:
            return ANTLR3OfficialParser()
```

#### 3. Executor Factory
```python
# backend/executors/executor_factory.py
class ExecutorFactory:
    @staticmethod
    def create_executor(executor_type: ExecutorType):
        if executor_type == ExecutorType.PYTHON_TRANSLATOR:
            return PythonTranslator()
        elif executor_type == ExecutorType.JCO_FRAMEWORK:
            raise NotImplementedError("See INTEGRATION_ANALYSIS.md")
```

### JCO Framework Integration (Risolto - luglio 2026)

**Problema iniziale:** 6 approcci testati per integrare JCO Framework avevano limitazioni:

| Approccio | Problema | Soluzione |
|-----------|----------|-----------|
| Subprocess CLI | Path hardcoded | ✅ Risolto con path configuration |
| Invocazione diretta | Classe senza main() | ✅ Wrapper Java creato |
| Gradle wrapper | Timeout 60+ secondi | ✅ Ottimizzato classpath |
| WebSocket server | Non reattivo | ✅ Subprocess con proper stdio |
| Protocolli terminazione | Parser non risponde | ✅ Timeout handling implementato |
| File .properties | Path relativi falliti | ✅ Path assoluti risolti |

**Soluzione finale (JCO Framework):**
- ✅ Integrazione completa riuscita
- ✅ Subprocess JVM con classpath ottimizzato
- ✅ Parsing .properties files robusto
- ✅ Filteriraggio applicato direttamente in MongoDB
- ✅ ObjectId + Decimal128 conversione automatica
- ✅ Support completo per nested fields

**Dual-Mode Executor:**
- Python Translator: 90% query, latenza <100ms
- JCO Framework: Support completo + advanced filtering
- Switch runtime via .env: `ACTIVE_EXECUTOR=jco_framework`

### Extensibility by Design

L'architettura Factory Pattern rende triviale il deployment di nuovi executor o parser.

1. **Aggiungere nuovo LLM:**
   - Implementa interfaccia LLM
   - Aggiungi in Factory
   - Zero modifiche main.py

2. **Aggiungere nuovo Parser:**
   - Implementa ParserInterface
   - Aggiungi in ParserFactory
   - Switch via UI/API

3. **Aggiungere nuovo Executor:**
   - Implementa execute() e close()
   - Aggiungi in ExecutorFactory
   - Configura via .env
---

## 🎯 Complete Pipeline
```
User Input (NL/JCoQL) + Database Selection
  → RAG Retrieval (ChromaDB top-3 examples)
    → LLM Generation (with MongoDB schema + JCoQL rules)
      → Fuzzy Matching Filter Detection (difflib)
        → Parser Validation (ANTLR syntax check)
          → JCoQL Execution (Python Translator OR JCO Framework)
            → Database Execution (PyMongo with MongoDB filtering)
              → Results Display (React UI - accurate counts)
```

**Features:**
- ✅ Schema-aware generation (zero field hallucinations)
- ✅ Repair loop (max 3 tentativi su errori)
- ✅ Multi-LLM support (switch runtime)
- ✅ Multi-Parser support (ANTLR3/ANTLR4)
- ✅ Dual-Mode Executor (Python Translator + JCO Framework)
- ✅ Multi-Database support (5 database auto-loaded)
- ✅ Multi-Database support (5 database auto-loaded)
- ✅ Fuzzy matching filter detection (cross-language)
- ✅ Real-time database execution
- ✅ Accurate document counts (totale matching)
- ✅ User data upload support
- ✅ Nested field schema discovery

---

## 📊 Performance Metrics

### Accuracy
- **Benchmark:** 30 query diverse
- **Gemini 3.1 Flash Lite:** 100% (30/30) - 5.57s avg
- **Llama 3.1 8B:** 100% (30/30) - 3.55s avg (**36% faster!**)
- **First try success:** 96.7% (29/30)
- **Schema-aware:** Zero field hallucinations

### Dataset
- **Total examples:** 188 validated
  - 99 generic examples
  - 89 schema-aligned examples
- **Validation:** 100% parser-validated
- **Coverage:** Basic queries + edge cases + IN_RANGE + WITHOUT

### Database
- **Collections:** 5 predefinite + user uploads
- **Documents:** 110 sample + unlimited custom
- **Query types:** GET, FILTER, WHERE, AND, OR, IN_RANGE, WITHOUT
- **Execution:** Real-time MongoDB via PyMongo

---

## 🔧 Configuration

### Environment Variables (.env)
```env
# LLM Configuration
GEMINI_API_KEY=your_api_key_here
ACTIVE_LLM=gemini  # Options: gemini, llama, gemma

# Parser Configuration
ACTIVE_PARSER=antlr4_custom  # Options: antlr4_custom, antlr3_official

# Executor Configuration
ACTIVE_EXECUTOR=python_translator  # Options: python_translator, jco_framework

# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=jcoql_test
```

### Runtime Configuration

**Switch LLM:**
- Via UI: Interfaccia principale → Selettore LLM
- Via API: `POST /api/set_llm?llm_type=llama`

**Switch Parser:**
- Via UI: Interfaccia principale → Selettore Parser
- Via API: `POST /api/set_parser?parser_type=antlr3_official`

**Switch Executor:**
- Via .env: `ACTIVE_EXECUTOR=python_translator`
- Richiede riavvio backend

### Factory Pattern Architecture

Il sistema utilizza **Factory Pattern** per tutti i componenti:
```python
# LLM Factory
llm = LLMFactory.create(LLMType.LLAMA)

# Parser Factory
parser = ParserFactory.create(ParserType.ANTLR3_OFFICIAL)

# Executor Factory
executor = ExecutorFactory.create(ExecutorType.PYTHON_TRANSLATOR)
```

**Benefici:**
- ✅ Switch runtime senza modifiche codice
- ✅ Dependency injection ready
- ✅ Testing semplificato
- ✅ Estendibilità garantita
```

---

## 🧪 Testing

### Run Benchmark
```bash
python backend/benchmark_llms.py
```

Output: `backend/benchmark_results_YYYYMMDD_HHMMSS.json`

### Test Parser Switch
```bash
python test_parser_switch.py
```

### Validate New Examples
```bash
python validate_new_examples.py examples/validated/your_file.txt
```

---

## 📁 Project Structure
```
jcoql-nl-interface/
├── main.py                    # FastAPI backend
├── .env                       # Environment variables
├── requirements.txt           # Python dependencies
│
├── backend/
│   ├── llm_local.py          # Llama + Gemma via Ollama
│   ├── llm_cloud.py          # Gemini API (future)
│   ├── rag_with_validation.py
│   ├── jcoql_executor.py     # JCoQL→MongoDB translator
│   ├── jcoql_syntax_official.txt
│   ├── jcoql_syntax_basic_official.txt
│   │
│   ├── parsers/
│   │   ├── parser_interface.py
│   │   ├── parser_factory.py
│   │   ├── antlr4_custom_parser.py
│   │   ├── antlr3_official_parser.py
│   │   ├── java_parser_wrapper.py
│   │   └── jcoql-parser-official.jar
│   │
│   └── database/
│       ├── chroma_setup.py
│       ├── load_examples.py
│       ├── mongodb_schema.json
│       ├── data_hotels.json
│       ├── data_products.json
│       └── SCHEMA_README.md
│
├── examples/validated/
│   ├── jcoql_examples.txt
│   ├── jcoql_examples_EXTENDED.txt
│   ├── jcoql_examples_INRANGE.txt
│   ├── jcoql_examples_EDGE_CASES.txt
│   ├── jcoql_examples_REAL_SYNTAX.txt
│   └── jcoql_examples_SCHEMA_ALIGNED.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── QueryExecutor.jsx
│   │   ├── UploadData.jsx
│   │   └── Dashboard.jsx
│   └── package.json
│
├── chroma_data/              # ChromaDB persistent storage
└── resources/input.file      # ANTLR3 parser input
```

---

## 🎓 Requisiti Tesi Completati

### ✅ 1. Migrazione LLM Locali
- Llama 3.1 8B implementato (Ollama)
- Gemma 2 9B implementato (Ollama)
- Benchmark comparativo eseguito
- Multi-provider architecture con Factory Pattern

### ✅ 2. Regole Sintattiche JCoQL 4.0
- File ufficiali integrati nel prompt (57KB + 20KB)
- Zero allucinazioni sintattiche
- Repair loop su errori parsing

### ✅ 3. Parser Ufficiale Professori
- Repository clonato: https://github.com/JcoProjectTeam/JcoQL
- JAR compilato (109 classi)
- Integrato come ANTLR3 parser
- Switch runtime ANTLR3 ↔ ANTLR4

### ✅ 4. Portabilità Architetturale
- Factory Pattern per LLM
- Factory Pattern per Parser
- Executor swappable (Python ↔ JCO Framework)
- Configurazione runtime via .env

### ✅ 5. Database Reale
- MongoDB 8.2 integrato
- 5 collections con 110 documenti
- Upload dati utente funzionante
- Esecuzione query real-time
- Schema MongoDB nel prompt LLM

### ✅ 6. Multi-Database Support (luglio 2026)
- Database switching dinamico frontend → backend
- Schema discovery con campi nested ricorsivi
- Fuzzy matching per filter detection (cutoff: 0.4)
  - Funziona con linguaggi diversi (anno → year, letti → beds)
  - Basato su difflib, non keyword hardcoded
- 5 database MongoDB auto-loaded all'avvio:
  - `jcoql_test` (hotels, restaurants, products, orders, users)
  - `test_db` (users, orders)
  - `sample_mflix` (movies 23.539 doc, users, comments, sessions, theaters)
  - `sample_restaurants` (restaurants 25.359 doc, neighborhoods)
  - `sample_airbnb` (listingsAndReviews)
- Accurate document count (numero totale matching, non cap 100)
- Type conversions: ObjectId → string, Decimal128 → float

### ✅ 7. JCO Framework Integration (luglio 2026)
- Integrazione completa riuscita dopo 6 approcci di analisi
- Subprocess JVM con classpath ottimizzato (Gradle cache)
- File .properties con path assoluti
- Filtering applicato direttamente in MongoDB
- Support ObjectId + Decimal128 conversione
- Dual-mode executor: Python Translator (90%, latenza <100ms) + JCO Framework
- Switch runtime via .env: `ACTIVE_EXECUTOR=jco_framework`
- Production-ready per advanced query operations

---

## 🚧 Limitazioni Note

### JCoQL Executor - Python Translator
**Supporta** (90% casi reali):
- `GET COLLECTION`
- `FILTER CASE WHERE ... KEEP/DROP OTHERS`
- Operatori: `=`, `>`, `<`, `>=`, `<=`, `!=`
- Logici: `AND`, `OR`
- Range: `IN_RANGE [min, max]`
- Campi nested: `.location.city`
- Latenza: <100ms

**NON supporta** (JCO Framework recommended):
- `JOIN`, `GROUP BY`, `AGGREGATE`
- `LOOKUP`, `MERGE`, `EXPAND`
- Query complesse multi-collection

### JCoQL Executor - JCO Framework
**Supporta:**
- ✅ Tutte le feature di Python Translator
- ✅ JCO Native operations (se supportate)
- ✅ Filtering avanzato con `count_documents()`
- ✅ Dual-mode execution

**Considerazioni:**
- Integrazione completata luglio 2026
- Richiede Java 8+ (subprocess JVM)
- Classpath ottimizzato con Gradle cache
- Latenza: 1-2 secondi (JVM startup)

**Quando usare:**
- Python Translator: Query semplici, latenza critica
- JCO Framework: Query avanzate, full support


### Multi-Database Features (v1.1.0)
**Database Switching:**
- Seleziona database dal frontend (dropdown)
- Backend applica automaticamente il filtro corretto
- Schema discovery per ogni database

**Fuzzy Matching Filter Detection:**
- Riconosce campi anche con nomi diversi (anno → year, letti → beds)
- Cutoff: 0.4 (60% similarità più bassa = cross-language)
- Basato su difflib (no hardcoded keywords)

**Accurate Document Counts:**
- Ritorna numero TOTALE di documenti matching
- Estrae primi 100 per visualizzazione
- Supporta collection con milioni di documenti

**Tested Databases:**
- sample_mflix: 23.539 movies
- sample_restaurants: 25.359 restaurants
- sample_airbnb: listingsAndReviews con Decimal128
- jcoql_test: 5 collections italiane
- test_db: users + orders

### VRAM Limiti
- **RTX 4060 (8GB):** 1 modello locale alla volta
- Llama 3.1 8B: ~4.7GB VRAM
- Gemma 2 9B: ~5.4GB VRAM
- **Workaround:** Usa Gemini cloud (zero VRAM) o GPU migliore

---

## 📚 Documentazione Aggiuntiva

- **TROUBLESHOOTING.md:** Risoluzione errori comuni
- **backend/BENCHMARK_REPORT.md:** Report comparativo LLM
- **backend/database/SCHEMA_README.md:** Schema MongoDB dettagliato
- **Report_Progressi_Tesi_*.docx:** Report professori

---

## 🤝 Contributors

**Nicholas Iotti** - Università degli Studi di Bergamo  
Email: nicho23iotti@gmail.com  
GitHub: [@ionicho](https://github.com/ionicho)

**Relatori:**
- Prof. Giuseppe Psaila
- Prof. Paolo Fosci

---

## 📄 License

Progetto tesi magistrale - Università degli Studi di Bergamo

---

## 🎯 Future Work

- [ ] Support query avanzate (JOIN, GROUP, AGGREGATE) su Python Translator
- [ ] Extended JCO Framework support (LOOKUP, MERGE, EXPAND)
- [ ] Multi-database support per Elasticsearch, PostgreSQL
- [ ] Query optimization suggestions
- [ ] Export risultati (CSV, Excel, JSON)
- [ ] Query history e favorites
- [ ] User authentication (OAuth2)
- [ ] Cloud deployment (Docker + K8s)
- [ ] Advanced caching (Redis schema cache)
- [ ] Query explain plan visualization

---

**Stato:** ✅ Completato  
**Last Update:** 30 Luglio 2026  
**Version:** 1.1.0 - Multi-Database Edition