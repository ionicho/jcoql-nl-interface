# JCoQL+ Natural Language Interface

**Interfaccia Natural Language → JCoQL+ con Multi-LLM, RAG e Multi-Parser**

[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![ANTLR](https://img.shields.io/badge/ANTLR-4.9.3-orange.svg)](https://www.antlr.org/)
[![Accuracy](https://img.shields.io/badge/Accuracy-100%25-brightgreen.svg)]()
[![LLM](https://img.shields.io/badge/LLM-Multi--Provider-purple.svg)]()

Progetto di Tesi Magistrale - Università degli Studi di Bergamo  
Studente: Nicholas Iotti (nicho23iotti@gmail.com)

---

##  Indice

- [Panoramica](#-panoramica)
- [Architettura](#-architettura)
- [Features](#-features)
- [Risultati](#-risultati)
- [Installazione](#️-installazione)
- [Utilizzo](#-utilizzo)
- [Stack Tecnologico](#-stack-tecnologico)
- [Limitazioni Note](#️-limitazioni-note)
- [Troubleshooting](#-troubleshooting)
- [Roadmap](#-roadmap)

---

##  Panoramica

Sistema intelligente che traduce richieste in **linguaggio naturale** (italiano) in **query JCoQL+ sintatticamente corrette** attraverso:

1. **Multi-LLM**: Gemini (cloud) + Llama/Gemma (locale)
2. **RAG (Retrieval-Augmented Generation)** con ChromaDB
3. **Multi-Parser**: ANTLR4 Custom + ANTLR3 Official (switchable)
4. **Regole sintattiche** JCoQL 4.0 ufficiali integrate nel prompt
5. **Auto-correzione** con retry loop intelligente

###  Esempio
```
INPUT (Linguaggio Naturale):
"Hotel a Milano con rating superiore a 4"

↓ RAG Retrieval (Top 3 esempi simili)
↓ LLM Generation (Gemini/Llama/Gemma)
↓ ANTLR Validation

OUTPUT (JCoQL+ Validato):
GET COLLECTION hotels;
FILTER CASE WHERE .city = 'Milano' AND .rating > 4
KEEP OTHERS;
```

---

##  Architettura
```
┌────────────────────────────────────────────────────┐
│  Frontend React + Vite                             │
│  • LLM Selector (Gemini/Llama/Gemma)               │
│  • Parser Selector (ANTLR4/ANTLR3)                 │
│  • Dashboard metriche real-time                    │
└──────────────────┬─────────────────────────────────┘
                   ↓ HTTP
┌────────────────────────────────────────────────────┐
│  Backend FastAPI                                   │
│  • Multi-LLM routing                               │
│  • Multi-Parser factory                            │
│  • RAG pipeline                                    │
└──────────────────┬─────────────────────────────────┘
                   ↓
        ┌──────────┴──────────┐
        ↓                     ↓
┌──────────────┐      ┌──────────────┐
│  LLM Layer   │      │ Parser Layer │
├──────────────┤      ├──────────────┤
│ ☁️ Gemini    │      │ ANTLR4 Custom│
│ 🏠 Llama     │      │ ANTLR3 Official│
│ 🏠 Gemma     │      └──────────────┘
└──────────────┘
        ↓
┌────────────────────────────────────────────────────┐
│  ChromaDB Vector Store                             │
│  • 59 esempi validati JCoQL 4.0                    │
│  • Embedding: all-MiniLM-L6-v2 (locale)            │
│  • Top-3 retrieval per query                       │
└────────────────────────────────────────────────────┘
```

---

##  Features

###  Implementato

#### Multi-LLM Provider
-  **Gemini 3.1 Flash Lite** (Cloud, 500 RPD)
-  **Llama 3.1 8B** (Locale, ∞ quota, 4.7GB VRAM)
-  **Gemma 2 9B** (Locale, ∞ quota, 5.4GB VRAM)
-  **Runtime switching** (API + UI)
-  **Output cleanup** per ogni LLM

#### Multi-Parser Architecture
-  **Parser Factory** (Strategy Pattern)
-  **ANTLR4 Custom** (convertito, 100% testato)
-  **ANTLR3 Official** (prof, placeholder WIP)
-  **Runtime switching** (API + UI)

#### RAG & Validation
-  **ChromaDB** con 59 esempi validati
-  **Embeddings locali** (all-MiniLM-L6-v2)
-  **Regole sintattiche** JCoQL 4.0 nel prompt
-  **Retry loop** intelligente (max 3 tentativi)
-  **Metriche real-time**

#### Frontend & API
-  **React 19 + Vite 8**
-  **Tailwind CSS 4.x**
-  **FastAPI** con CORS
-  **Dashboard** Chart.js
-  **React Query** per state management

---

##  Risultati

### Validazione Parser (59 esempi)
```
✅ Accuracy:     100.0%
✅ Valid:        59/59
❌ Invalid:      0/59
⚠️  Errors:      0/59
```

### Test End-to-End (20 query)
```
Accuracy:     100.0%
Precision:    1.0000
Recall:       1.0000
F1-Score:     1.0000

Efficienza:
   95% successo primo tentativo
   Media tentativi: 1.05
```

### Performance per Livello
```
Base:        5/5  (100%)
Intermedio:  7/7  (100%)
Avanzato:    8/8  (100%)
Edge Cases: 20/20 (100%)
```

### Benchmark LLM (Query: "Hotel Milano rating > 4")
```
┌─────────┬──────────┬──────────┬────────────┐
│ LLM     │ Latency  │ Valid    │ Output     │
├─────────┼──────────┼──────────┼────────────┤
│ Gemini  │ 2.3s     │ ✅       │ Pulito     │
│ Llama   │ 1.8s     │ ✅       │ Pulito     │
│ Gemma   │ 2.1s     │ ✅       │ Pulito*    │
└─────────┴──────────┴──────────┴────────────┘
* Con cleanup aggressivo
```

---

##  Installazione

### Prerequisiti
- **Python** 3.14+
- **Node.js** 24.14+
- **Java** 8+ (per ANTLR)
- **Git**
- **Ollama** (per LLM locali)
- **GPU** NVIDIA (opzionale, per Llama/Gemma)

### Setup Completo

#### 1. Clone Repository
```bash
git clone https://github.com/ionicho/jcoql-nl-interface.git
cd jcoql-nl-interface
```

#### 2. Backend Setup
```bash
# Crea virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Installa dipendenze
pip install -r requirements.txt

# Setup environment variables
copy .env.example .env
# Modifica .env con la tua GEMINI_API_KEY
```

#### 3. Carica Esempi in ChromaDB
```bash
python backend\database\load_examples.py
```

#### 4. Frontend Setup
```bash
cd frontend
npm install
```

#### 5. Ollama Setup (LLM Locali)
```bash
# Installa Ollama: https://ollama.com/download

# Download modelli
ollama pull llama3.1:8b-instruct-q4_K_M
ollama pull gemma2:9b-instruct-q4_K_M
```

---

##  Utilizzo

### Avvio Sistema Completo

#### Terminale 1 - Backend
```powershell
cd C:\Users\nicho\jcoql-project\jcoql-nl-interface
venv\Scripts\activate
uvicorn main:app --reload
```
**Backend:** http://localhost:8000  
**API Docs:** http://localhost:8000/docs

#### Terminale 2 - Frontend
```powershell
cd C:\Users\nicho\jcoql-project\jcoql-nl-interface\frontend
npm run dev
```
**Frontend:** http://localhost:5173

---

### API Endpoints

#### Generate Query
```bash
POST /api/generate
Content-Type: application/json

{
  "nl_query": "Hotel a Milano con rating > 4",
  "max_retries": 3
}

Response:
{
  "jcoql_query": "GET COLLECTION hotels;...",
  "is_valid": true,
  "attempts": 1,
  "llm_used": "gemini",
  "parser_used": "ANTLR4 Custom Parser"
}
```

#### Switch LLM
```bash
POST /api/set_llm?llm_type=llama
GET /api/llms  # Lista LLM disponibili
```

#### Switch Parser
```bash
POST /api/set_parser?parser_type=antlr4_custom
GET /api/parsers  # Lista parser disponibili
```

---

### Test Suite
```bash
# Valida nuovi esempi
python validate_new_examples.py examples\validated\jcoql_examples_ADVANCED_V2.txt

# Test suite completo
python backend\test_advanced_queries.py

# Genera metriche
python backend\generate_metrics.py
```

---

## 🔧 Stack Tecnologico

### Backend
| Componente | Tecnologia | Versione |
|------------|-----------|----------|
| **Framework** | FastAPI | Latest |
| **LLM Cloud** | Google Gemini | 3.1 Flash Lite |
| **LLM Locale** | Llama (Meta) | 3.1 8B Q4 |
| **LLM Locale** | Gemma (Google) | 2 9B Q4 |
| **Vector DB** | ChromaDB | Latest |
| **Embeddings** | Sentence Transformers | all-MiniLM-L6-v2 |
| **Parser** | ANTLR | 4.9.3 |
| **Language** | Python | 3.14.3 |

### Frontend
| Componente | Tecnologia | Versione |
|------------|-----------|----------|
| **Framework** | React | 19 |
| **Build Tool** | Vite | 8 |
| **Styling** | Tailwind CSS | 4.x |
| **State** | React Query | Latest |
| **HTTP** | Axios | Latest |
| **Charts** | Chart.js | Latest |
| **Router** | React Router | DOM |

---

##  Limitazioni Note

### GPU VRAM (RTX 4060 - 8GB)

I modelli locali richiedono VRAM dedicata:

| Modello | VRAM | Compatibilità RTX 4060 |
|---------|------|------------------------|
| Llama 3.1 8B (Q4) | 4.7GB | ✅ Funziona |
| Gemma 2 9B (Q4) | 5.4GB | ✅ Funziona |
| **Llama + Gemma** | **10.1GB** | ❌ Overflow |

**Comportamento:**
- ✅ Un modello locale alla volta: **funziona**
- ❌ Switch Llama→Gemma senza riavvio Ollama: **CUDA error**

**Configurazione Raccomandata:**
```bash
# .env
ACTIVE_LLM=gemini  # o llama
```

**Configurazioni Testate:**
1. ☁️ **Gemini + 🏠 Llama** → ✅ Nessun conflitto (RACCOMANDATO)
2. 🏠 **Solo Llama** → ✅ Funziona perfettamente
3. 🏠 **Solo Gemma** → ✅ Funziona perfettamente
4. 🏠 **Llama + 🏠 Gemma** → ❌ Richiede riavvio Ollama tra switch

**Scalabilità:**
- **RTX 4070 (12GB)**: Llama + Gemma contemporaneamente 
- **RTX 4080 (16GB)**: 3+ modelli locali 
- **Cloud Only**: Nessun limite VRAM 

---

## 🔧 Troubleshooting

### CUDA Error: llama runner process terminated

**Sintomo:**
```
ollama._types.ResponseError: llama runner process has terminated: 
CUDA error (status code: 500)
```

**Causa:** VRAM GPU insufficiente (Ollama tiene modelli in memoria)

**Soluzione:**
```powershell
# Libera VRAM
ollama stop

# Oppure riavvia Ollama
taskkill /IM ollama.exe /F
ollama serve
```

**Prevenzione:**
- Usa Gemini + Llama (no conflitto)
- Evita switch rapidi tra Llama↔Gemma

---

### Frontend non si connette al Backend

**Verifica:**
```bash
# Backend deve essere su porta 8000
curl http://localhost:8000/api/llms

# Frontend deve essere su porta 5173
# Controlla CORS in main.py
```

---

### ChromaDB vuoto
```bash
# Ricarica esempi
python backend\database\load_examples.py

# Verifica
python -c "import chromadb; c=chromadb.PersistentClient('./chroma_data'); print(c.get_collection('jcoql_examples').count())"
# Output: 59
```

---

##  Struttura Progetto
```
jcoql-nl-interface/
├── main.py                         # Backend FastAPI
├── .env                            # Config (gitignored)
├── .env.example                    # Template config
├── requirements.txt                # Dipendenze Python
├── validate_new_examples.py        # Script validazione
│
├── backend/
│   ├── llm_local.py                # Ollama wrapper (Llama/Gemma)
│   ├── rag_with_validation.py     # Pipeline RAG
│   ├── test_advanced_queries.py   # Test suite
│   ├── generate_metrics.py        # Metriche
│   ├── jcoql_syntax_official.txt  # Regole JCoQL 4.0
│   ├── jcoql_syntax_basic_official.txt
│   │
│   ├── database/
│   │   ├── chroma_setup.py
│   │   └── load_examples.py
│   │
│   └── parsers/
│       ├── parser_interface.py     # ABC Parser
│       ├── parser_factory.py       # Factory Pattern
│       ├── antlr4_custom_parser.py # Parser ANTLR4
│       ├── antlr3_official_parser.py # Parser ANTLR3 (WIP)
│       ├── JCoQL.g4                # Grammatica
│       ├── JCoQL*.py               # Generated
│       └── validator.py
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Main UI
│   │   ├── Dashboard.jsx           # Metriche
│   │   └── index.css
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
│
├── examples/validated/
│   ├── jcoql_examples.txt          # 14 base
│   ├── jcoql_examples_EXTENDED.txt # 18 intermedi
│   ├── jcoql_examples_INRANGE.txt  # 7 range
│   └── jcoql_examples_EDGE_CASES.txt # 20 edge
│
└── chroma_data/                    # ChromaDB (59 docs)
```

---

##  Roadmap

###  Completato (Settimane 0-3)
- [x] POC NotebookLM (90% accuracy)
- [x] Setup ambiente sviluppo
- [x] ChromaDB con 59 esempi
- [x] Parser ANTLR4 JCoQL 4.0
- [x] Pipeline RAG + Validation
- [x] Test suite completo (20/20)
- [x] Metriche avanzate (P/R/F1)
- [x] Multi-LLM (Gemini/Llama/Gemma)
- [x] Multi-Parser (Factory Pattern)
- [x] Frontend React + Dashboard
- [x] API REST FastAPI
- [x] Regole sintattiche nel prompt

###  In Corso (Settimana 4)
- [ ] Parser ANTLR3 ufficiale (integrazione JAR)
- [ ] Espansione dataset (100+ esempi)
- [ ] Benchmark LLM comparativo completo

###  Prossimi Step (Settimane 5-6)
- [ ] Fine-tuning prompt per LLM locali
- [ ] Cache query frequenti
- [ ] Deploy demo (opzionale)
- [ ] Documentazione finale tesi

---

##  Metriche di Sviluppo

- **FTE consumato:** 5 giorni / 37 previsti
- **Efficienza:** +400% rispetto al piano
- **Accuracy:** 100% (59/59 esempi)
- **Code coverage:** 100% componenti core
- **Tech debt:** Minimo

---

##  Licenza

Progetto privato - Tesi Magistrale  
© 2026 Nicholas Iotti - Università degli Studi di Bergamo

---

##  Contatti

**Nicholas Iotti**  
Email: nicho23iotti@gmail.com  
Università: Università degli Studi di Bergamo  
Repository: https://github.com/ionicho/jcoql-nl-interface (Private)

---

##  Ringraziamenti

- Prof. Giuseppe Psaila e Paolo Fosci (relatori)
- Comunità ANTLR
- Google Gemini Team (Free Tier)
- Meta AI (Llama open-source)
- ChromaDB Team