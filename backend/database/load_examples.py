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
    """Parse examples file and extract structured data"""
    examples = []
    
    if not os.path.exists(filepath):
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by ESEMPIO
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
    
    # Get or create collection (usa il modello locale per default)
    collection = client.get_or_create_collection(
        name="jcoql_examples",
        metadata={"description": "JCoQL+ query examples for RAG"}
    )
    
    print(f"✅ ChromaDB ready (embeddings LOCALI)")
    print(f"📊 Current documents: {collection.count()}")
    print()
    
    example_files = [
    'examples/validated/jcoql_examples.txt',
    'examples/validated/jcoql_examples_EXTENDED.txt',
    'examples/validated/jcoql_examples_INRANGE.txt',
    'examples/validated/jcoql_examples_ADVANCED.txt' 
    ]
    
    all_examples = []
    for filepath in example_files:
        if os.path.exists(filepath):
            print(f"📖 Reading {filepath}...")
            examples = parse_examples_file(filepath)
            all_examples.extend(examples)
            print(f"   Found {len(examples)} examples")
        else:
            print(f"⚠️  File not found: {filepath}")
    
    print()
    print(f"📚 Total examples loaded: {len(all_examples)}")
    print()
    
    # Add to ChromaDB (genera embeddings LOCALI automaticamente!)
    print("💾 Adding examples to ChromaDB...")
    print("   (Genera embeddings localmente, nessuna API call)")
    print()
    
    for i, example in enumerate(all_examples, 1):
        # Create document text
        doc_text = f"Titolo: {example['title']}\nDescrizione: {example['description']}\nQuery: {example['query']}"
        
        try:
            # Add to collection - ChromaDB genera embeddings automaticamente!
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
            
            print(f"   ✅ {i}/{len(all_examples)}: {example['title'][:50]}...")
            
        except Exception as e:
            print(f"   ❌ Error on example {i}: {e}")
    
    print()
    print("=" * 60)
    print(f"✅ COMPLETATO!")
    print(f"📊 Examples in database: {collection.count()}")
    print("=" * 60)

if __name__ == "__main__":
    load_examples_to_chromadb()