#!/usr/bin/env python3
"""
Load JCoQL+ Examples into ChromaDB
USANDO EMBEDDINGS LOCALI (no API calls)
"""
import os
import re
import glob
from pathlib import Path
import chromadb
from chromadb.config import Settings

# FIX 3 agosto 2026: percorsi calcolati rispetto alla posizione di QUESTO file, non
# rispetto alla cartella da cui viene lanciato lo script - prima, lanciandolo da
# 'backend/' invece che dalla radice del progetto, i percorsi relativi puntavano a
# cartelle sbagliate/inesistenti (esempi non trovati, e rischio di scrivere ChromaDB
# in una posizione diversa da quella che l'app vera legge).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples" / "validated"
CHROMA_PATH = PROJECT_ROOT / "chroma_data"

def parse_examples_file(filepath):
    """
    Parse esempi da file .txt (supporta entrambi i formati).

    NOTA: due formati coesistono per compatibilità con file di esempio
    scritti in momenti diversi del progetto:
    - Formato 1 "ESEMPIO N:" — usato dai file di esempio più vecchi.
    - Formato 2 "Titolo: / Descrizione: / Query:" — quello usato da tutti
      i file attualmente attivi in examples/validated/ (full, operators,
      REAL_SYNTAX, SCHEMA_ALIGNED). Se scrivi un nuovo file di esempi,
      usa questo formato per coerenza con gli altri.
    Il parser sceglie il ramo in base alla presenza della stringa
    'ESEMPIO' nel contenuto del file (riga "if 'ESEMPIO' in content:"
    sotto) — non è un parametro esplicito, quindi se un file nel formato
    2 contenesse per caso la parola "ESEMPIO" in una descrizione, verrebbe
    interpretato (erroneamente) come formato 1. Caso limite improbabile,
    ma se un giorno un file smette di essere caricato correttamente, è il
    primo posto da controllare.
    """
    
    if not os.path.exists(filepath):
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    examples = []
    
    # FORMATO 1: "ESEMPIO N:"
    if 'ESEMPIO' in content:
        parts = re.split(r'ESEMPIO \d+:', content)
        
        for part in parts[1:]:  # Skip header
            lines = part.strip().split('\n')
            
            if not lines:
                continue
            
            # Extract title
            title_line = [l for l in lines if l.strip() and not l.startswith('-')]
            if not title_line:
                continue
            title = title_line[0].strip()
            
            # Extract description
            desc_match = re.search(r'Descrizione:\s*(.+)', part)
            description = desc_match.group(1).strip() if desc_match else ""
            
            # Extract query
            query_match = re.search(r'Query:\s*\n(.+?)(?=\n\n|$)', part, re.DOTALL)
            query = query_match.group(1).strip() if query_match else ""
            
            if description and query:
                examples.append({
                    'title': title,
                    'description': description,
                    'query': query,
                    'source': os.path.basename(filepath)
                })
    
    # FORMATO 2: "Titolo: / Descrizione: / Query:"
    else:
        current_example = {}
        
        for line in content.split('\n'):
            line = line.strip()
            
            # Skip commenti, separatori, righe vuote
            if line.startswith('#') or line.startswith('=') or not line:
                continue
            
            if line.startswith('Titolo:'):
                # Salva esempio precedente se esiste
                if current_example.get('query'):
                    examples.append(current_example)
                # Nuovo esempio
                current_example = {
                    'title': line.replace('Titolo:', '').strip(),
                    'source': os.path.basename(filepath)
                }
            
            elif line.startswith('Descrizione:'):
                current_example['description'] = line.replace('Descrizione:', '').strip()
            
            elif line.startswith('Query:'):
                current_example['query'] = line.replace('Query:', '').strip()
        
        # Aggiungi ultimo esempio
        if current_example.get('query'):
            examples.append(current_example)
    
    return examples

def load_examples_to_chromadb():
    """
    Load all examples into ChromaDB with LOCAL embeddings

    NOTA IMPORTANTE PER IL SETUP DEL PROGETTO: questo script va lanciato
    ALMENO UNA VOLTA prima del primo avvio di main.py (es. `python
    backend/database/load_examples.py` dalla root del progetto). main.py
    si aspetta che la collection "jcoql_examples" esista già — usa
    chroma_client.get_collection(...) (non get_or_create_collection),
    quindi se questo script non è mai stato eseguito, l'app crasha
    all'avvio non trovando la collection. Se cloni il progetto da zero,
    questo è il primo script da lanciare.

    NOTA: ogni esecuzione fa un RESET completo — cancella la collection
    esistente (client.delete_collection) e la ricrea da zero con tutti i
    file .txt trovati in examples/validated/. Non è un caricamento
    incrementale/append: rilanciarlo ricostruisce l'intero corpus RAG da
    capo, quindi è sicuro rilanciarlo dopo aver modificato/aggiunto un
    file di esempi.
    """
    
    print("=" * 60)
    print("CARICAMENTO ESEMPI JCOQL+ IN CHROMADB")
    print("=" * 60)
    print()
    
    # Initialize ChromaDB (usa embeddings LOCALI automaticamente)
    print(f"📂 ChromaDB path: {CHROMA_PATH}")
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )
    
    # RESET collection per ricaricare tutto
    try:
        client.delete_collection("jcoql_examples")
        print("🗑️  Collection esistente eliminata")
    except:
        pass
    
    # Create collection
    # NOTA: qui non viene specificato metadata={"hnsw:space": "cosine"}
    # questa collection usa quindi la metrica di distanza di default di ChromaDB (L2/squared-L2). 
    # Dato che questo è lo script che crea davvero la collection usata in produzione, 
    # se in futuro si vuole cambiare metrica è qui che va specificata.
    collection = client.create_collection(
        name="jcoql_examples",
        metadata={"description": "JCoQL+ query examples for RAG"}
    )
    
    print(f"✅ ChromaDB ready (embeddings LOCALI)")
    print()
    
    # FIX 3 agosto 2026: prima era una lista fissa di nomi file, scritta a mano - qualunque
    # nuovo file di esempi (come jcoql_examples_full.txt, con JOIN/GROUP/EXPAND/MERGE/
    # INTERSECT/SUBTRACT/SAVE AS) veniva ignorato in silenzio se non esplicitamente elencato
    # qui. Ora si scansiona l'intera cartella (percorso assoluto, non relativo alla cartella
    # di lancio), cosi' qualunque file .txt presente viene sempre caricato, oggi e in
    # futuro, senza bisogno di ricordarsi di aggiornare questa lista.
    print(f"📂 Cartella esempi: {EXAMPLES_DIR}")
    example_files = sorted(str(p) for p in EXAMPLES_DIR.glob("*.txt"))
    
    all_examples = []
    for filepath in example_files:
        if os.path.exists(filepath):
            print(f"📖 Reading {filepath}...")
            examples = parse_examples_file(filepath)
            all_examples.extend(examples)
            print(f"   ✅ {len(examples)} esempi estratti")
        else:
            print(f"⚠️  File not found: {filepath}")
    
    print()
    print(f"📚 Total examples loaded: {len(all_examples)}")
    print()
    
    # Add to ChromaDB
    print("💾 Adding examples to ChromaDB...")
    print("   (Genera embeddings localmente, nessuna API call)")
    print()
    
    for i, example in enumerate(all_examples, 1):
        # Create document text
        doc_text = f"Titolo: {example['title']}\nDescrizione: {example['description']}\nQuery: {example['query']}"
        
        try:
            collection.add(
                documents=[doc_text],
                metadatas=[{
                    'title': example['title'],
                    'description': example['description'],
                    'query': example['query'],
                    'source': example['source']
                }],
                ids=[f"example_{i}"]
            )
            
            if i % 10 == 0 or i == len(all_examples):
                print(f"   ✅ {i}/{len(all_examples)} caricati...")
            
        except Exception as e:
            print(f"   ❌ Error on example {i}: {e}")
    
    print()
    print("=" * 60)
    print(f"✅ COMPLETATO!")
    print(f"📊 Examples in database: {collection.count()}")
    print("=" * 60)

if __name__ == "__main__":
    load_examples_to_chromadb()