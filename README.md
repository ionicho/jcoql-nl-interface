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
│  JCOQL EXECUTOR                                        │
│  • Python Translator: JCoQL → MongoDB (90% query)      │
│  • JCO Framework: Support completo (opzionale)         │
│  • Traduzione automatica operatori                     │
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
- **Executor:** PyMongo + Custom JCoQL Translator

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

## 🎯 Complete Pipeline
```
User Input (NL/JCoQL) 
  → RAG Retrieval (ChromaDB top-3 examples)
    → LLM Generation (with MongoDB schema + JCoQL rules)
      → Parser Validation (ANTLR syntax check)
        → JCoQL→MongoDB Translation (Python executor)
          → Database Execution (PyMongo)
            → Results Display (React UI)
```

**Features:**
- ✅ Schema-aware generation (zero field hallucinations)
- ✅ Repair loop (max 3 tentativi su errori)
- ✅ Multi-LLM support (switch runtime)
- ✅ Multi-Parser support (ANTLR3/ANTLR4)
- ✅ Real-time database execution
- ✅ User data upload support

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
ACTIVE_PARSER=antlr4_custom  # Options: antlr4_custom, antlr3_official

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=jcoql_test

# JCO Framework (optional)
JCO_JAR_PATH=path/to/jcoql-engine.jar
ACTIVE_EXECUTOR=python_translator  # Options: python_translator, jco_framework
```

### Switch LLM at Runtime

**Via UI:** Interfaccia principale → Selettore LLM

**Via API:**
```bash
curl -X POST http://localhost:8000/api/set_llm?llm_type=llama
```

### Switch Parser at Runtime

**Via UI:** Interfaccia principale → Selettore Parser

**Via API:**
```bash
curl -X POST http://localhost:8000/api/set_parser?parser_type=antlr3_official
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

---

## 🚧 Limitazioni Note

### JCoQL Executor Python
**Supporta** (90% casi reali):
- `GET COLLECTION`
- `FILTER CASE WHERE ... KEEP/DROP OTHERS`
- Operatori: `=`, `>`, `<`, `>=`, `<=`, `!=`
- Logici: `AND`, `OR`
- Range: `IN_RANGE [min, max]`
- Campi nested: `.location.city`

**NON supporta** (estendibile):
- `JOIN`, `GROUP BY`, `AGGREGATE`
- `LOOKUP`, `MERGE`, `EXPAND`
- Query complesse multi-collection

**Soluzione:** Architettura supporta integrazione JCO Framework completo via Factory Pattern (2-3 ore implementazione).

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

- [ ] Integrazione JCO Framework completo
- [ ] Support query avanzate (JOIN, GROUP, AGGREGATE)
- [ ] Multi-database support (Elasticsearch, PostgreSQL)
- [ ] Query optimization suggestions
- [ ] Export risultati (CSV, Excel, JSON)
- [ ] Query history e favorites
- [ ] User authentication
- [ ] Cloud deployment

---

**Stato:** ✅ Completato (150%)  
**Last Update:** 27 Marzo 2026  
**Version:** 1.0.0