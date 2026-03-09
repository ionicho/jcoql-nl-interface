#!/usr/bin/env python3
"""
ChromaDB Setup - Vector Database per esempi JCoQL+
"""
import os
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings

# Load environment
load_dotenv()

# Setup ChromaDB
def setup_chromadb():
    """Initialize ChromaDB client and collection"""
    
    # Create persistent client
    client = chromadb.PersistentClient(
        path="./chroma_data",
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )
    
    print("✅ ChromaDB client initialized")
    print(f"📁 Data path: ./chroma_data")
    
    # Create or get collection
    try:
        collection = client.get_or_create_collection(
            name="jcoql_examples",
            metadata={"description": "JCoQL+ query examples for RAG"}
        )
        print(f"✅ Collection 'jcoql_examples' ready")
        print(f"📊 Current documents: {collection.count()}")
        
        return client, collection
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return None, None

if __name__ == "__main__":
    print("=" * 60)
    print("CHROMADB SETUP TEST")
    print("=" * 60)
    print()
    
    client, collection = setup_chromadb()
    
    if collection:
        print()
        print("🎉 ChromaDB setup successful!")
        print()
        print("Next steps:")
        print("1. Load examples from files")
        print("2. Generate embeddings")
        print("3. Test retrieval")
    else:
        print("❌ Setup failed!")