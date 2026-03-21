#!/usr/bin/env python3
"""
Load JCoQL+ Examples into ChromaDB
USANDO EMBEDDINGS LOCALI (no API calls)
"""
import os
import re
import chromadb
from chromadb.config import Settings

def parse_examples_file(filepath):
    """Parse esempi da file .txt (supporta entrambi i formati)"""
    
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
    """Load all examples into ChromaDB with LOCAL embeddings"""
    
    print("=" * 60)
    print("CARICAMENTO ESEMPI JCOQL+ IN CHROMADB")
    print("=" * 60)
    print()
    
    # Initialize ChromaDB (usa embeddings LOCALI automaticamente!)
    client = chromadb.PersistentClient(
        path="./chroma_data",
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
    collection = client.create_collection(
        name="jcoql_examples",
        metadata={"description": "JCoQL+ query examples for RAG"}
    )
    
    print(f"✅ ChromaDB ready (embeddings LOCALI)")
    print()
    
    example_files = [
        'examples/validated/jcoql_examples.txt',
        'examples/validated/jcoql_examples_EXTENDED.txt',
        'examples/validated/jcoql_examples_INRANGE.txt',
        'examples/validated/jcoql_examples_EDGE_CASES.txt',
        'examples/validated/jcoql_examples_REAL_SYNTAX.txt'    
    ]
    
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