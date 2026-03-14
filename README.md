# 🔍 JCoQL+ Natural Language Interface

**Interfaccia Natural Language → JCoQL+ con RAG e Validazione ANTLR**

[![Python](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![ANTLR](https://img.shields.io/badge/ANTLR-4.9.3-orange.svg)](https://www.antlr.org/)
[![Accuracy](https://img.shields.io/badge/Accuracy-100%25-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-Private-red.svg)]()

Progetto di Tesi Magistrale - Università degli Studi di Bergamo  
Studente: Nicholas Iotti (nicho23iotti@gmail.com)

---

## Indice

- [Panoramica](#-panoramica)
- [Architettura](#-architettura)
- [Features](#-features)
- [Risultati](#-risultati)
- [Installazione](#-installazione)
- [Utilizzo](#-utilizzo)
- [Stack Tecnologico](#-stack-tecnologico)
- [Struttura Progetto](#-struttura-progetto)
- [Roadmap](#-roadmap)

---

## Panoramica

Sistema intelligente che traduce richieste in **linguaggio naturale** (italiano) in **query JCoQL+ sintatticamente corrette** attraverso:

1. **RAG (Retrieval-Augmented Generation)** con ChromaDB
2. **LLM (Gemini 2.5 Flash)** per generazione query
3. **Parser ANTLR** per validazione sintattica
4. **Retry intelligente** con auto-correzione

### Esempio
```
INPUT (Linguaggio Naturale):
"Hotel a Milano con rating superiore a 4"

OUTPUT (JCoQL+ Validato):
GET COLLECTION Hotels;
FILTER CASE WHERE .city = 'Milano' AND .rating > 4
KEEP OTHERS;
```

---

## Architettura
```
┌─────────────────────────────────────────────────────┐
│  Natural Language Query                             │
│  "Hotel a Milano con rating > 4"                    │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│  ChromaDB - Retrieval (RAG)                         │
│  • Embedding locale (all-MiniLM-L6-v2)              │
│  • Top 3 esempi simili (cosine similarity)          │
│  • 39 esempi JCoQL validati                         │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│  Gemini 2.5 Flash - Generazione                     │
│  • Few-shot learning da esempi RAG                  │
│  • Prompt engineering ottimizzato                   │
│  • Output: query JCoQL pura                         │
└──────────────────┬──────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────────────────┐
│  ANTLR Parser - Validazione                         │
│  • Grammatica JCoQL 4.0 ufficiale                   │
│  • Lexer + Parser + AST                             │
│  • Errori dettagliati (linea, colonna)              │
└──────────────────┬──────────────────────────────────┘
                   ↓
            ╔═══════════╗
            ║  Valid?   ║
            ╚═════╤═════╝
          ✅ YES │ ❌ NO (retry max 2)
                 │
       ┌─────────┴─────────┐
       ↓                   ↓
  ┌─────────┐      ┌──────────────┐
  │ Success │      │ Add errors   │
  │ Return  │      │ to prompt    │
  └─────────┘      │ Regenerate   │
                   └──────┬───────┘
                          ↓
                   Back to Gemini
```

---

## Features

### Funzionalità Implementate

- **Retrieval semantico** con ChromaDB (embeddings locali)
- **Generazione query** con Gemini 2.5 Flash (free tier)
- **Validazione sintattica** con parser ANTLR 4.9.3
- **Auto-correzione** con retry loop intelligente (max 3 tentativi)
- **UI Streamlit** con visualizzazione stato validazione
- **Test suite automatizzato** (20 query di difficoltà crescente)
- **Metriche avanzate** (Precision, Recall, F1-Score)

### Sintassi JCoQL Supportate

- `GET COLLECTION`, `FILTER CASE`
- Operatori: `=`, `>`, `<`, `>=`, `<=`, `AND`, `OR`, `NOT`
- `IN_RANGE [ min , max ]` (estremi inclusi/esclusi)
- `IS NULL`, `IS NOT NULL`
- `WITH`, `WITHOUT`
- `GENERATE`, `BUILD`, `ADD FIELDS`, `REMOVE FIELDS`
- `EXPAND UNPACK`
- `MERGE`, `INTERSECT`, `SUBTRACT`
- `GROUP`, `SAVE AS`
- Condizioni complesse con parentesi

---

## Risultati

### Validazione Parser (39 esempi)
```
✅ Accuracy:     100.0%
✅ Valid:        39/39
❌ Invalid:      0/39
⚠️  Errors:      0/39
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
```

---

## Installazione

### Prerequisiti
- Python 3.14+
- Java 8+ (per ANTLR)
- Git

### Setup
```bash
# Clone repository
git clone https://github.com/ionicho/jcoql-nl-interface.git
cd jcoql-nl-interface

# Installa dipendenze
pip install -r requirements.txt

# Setup .env
echo "GEMINI_API_KEY=your_api_key_here" > .env

# Genera parser ANTLR
cd backend/parsers
java -jar antlr-4.9.3-complete.jar -Dlanguage=Python3 JCoQL.g4

# Carica esempi in ChromaDB
cd ../..
python backend/database/load_examples.py
```

---

## Utilizzo

### Streamlit UI
```bash
python -m streamlit run app.py
```

Apri browser: `http://localhost:8501`

### Test Suite
```bash
# Test parser su 39 esempi
python backend/parsers/test_parser_examples.py

# Test end-to-end 20 query
python backend/test_advanced_queries.py

# Genera metriche
python backend/generate_metrics.py
```

### Programmatic Usage
```python
from backend.rag_with_validation import generate_jcoql_with_validation

result = generate_jcoql_with_validation("Hotel a Milano con rating > 4")

print(f"Valid: {result['is_valid']}")
print(f"Query: {result['jcoql_query']}")
print(f"Attempts: {result['attempts']}")
```

---

## Stack Tecnologico

| Componente | Tecnologia | Versione |
|------------|-----------|----------|
| **LLM** | Google Gemini | 2.5 Flash |
| **Vector DB** | ChromaDB | Latest |
| **Embeddings** | Sentence Transformers | all-MiniLM-L6-v2 |
| **Parser** | ANTLR | 4.9.3 |
| **UI** | Streamlit | Latest |
| **Language** | Python | 3.14+ |
| **Runtime** | Java | 8+ |

---

## Struttura Progetto
```
jcoql-nl-interface/
├── app.py                          # Streamlit UI
├── .env                            # API keys
├── requirements.txt                # Dipendenze Python
│
├── backend/
│   ├── rag_with_validation.py     # Pipeline completa
│   ├── test_advanced_queries.py   # Test suite 20 query
│   ├── generate_metrics.py        # Analisi metriche
│   │
│   ├── database/
│   │   ├── chroma_setup.py        # Setup ChromaDB
│   │   └── load_examples.py       # Caricamento esempi
│   │
│   └── parsers/
│       ├── JCoQL.g4               # Grammatica ANTLR4
│       ├── JCoQL*.py              # Parser generato
│       ├── validator.py           # Wrapper validazione
│       └── antlr-4.9.3-complete.jar
│
├── examples/validated/
│   ├── jcoql_examples.txt         # 14 esempi base
│   ├── jcoql_examples_EXTENDED.txt # 18 esempi intermedi
│   └── jcoql_examples_INRANGE.txt  # 7 esempi range
│
├── chroma_data/                    # ChromaDB persistente
└── docs/                           # Documentazione
```

---

## Roadmap

### Completato (Settimane 0-2)
- [x] POC NotebookLM (90% accuracy)
- [x] Setup ambiente sviluppo
- [x] ChromaDB con 39 esempi
- [x] Parser ANTLR JCoQL 4.0
- [x] Pipeline RAG + Validation
- [x] Test suite completo
- [x] Metriche avanzate
- [x] Streamlit UI

### In Corso (Settimana 3)
- [ ] Espansione dataset (100+ esempi)
- [ ] Edge cases e query complesse
- [ ] Frontend React + Vite
- [ ] API REST con FastAPI

### Prossimi Step (Settimane 4-5)
- [ ] Fine-tuning embeddings (opzionale)
- [ ] Cache query frequenti
- [ ] Metriche real-time
- [ ] Documentazione API completa
- [ ] Deploy demo pubblico

---

## Metriche di Sviluppo

- **FTE consumato:** 3.5 giorni / 37 previsti
- **Efficienza:** +25% rispetto al piano
- **Code coverage:** Parser 100%, RAG 100%
- **Debt tecnico:** Minimo (aggiornamento SDK Gemini pending)

---

## Licenza

Progetto privato - Tesi Magistrale  
© 2026 Nicholas Iotti - Università degli Studi di Bergamo

---

## Contatti

**Nicholas Iotti**  
Email: nicho23iotti@gmail.com  
Università: Università degli Studi di Bergamo  
Repository: https://github.com/ionicho/jcoql-nl-interface (Private)

---

## Ringraziamenti

- Professori relatori e correlatori
- Comunità ANTLR
- Google Gemini Team (Free Tier)
- ChromaDB Team