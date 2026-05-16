#!/usr/bin/env python3
"""
RAG Pipeline con Validazione ANTLR + Schema MongoDB Discovery
NL Query → ChromaDB Retrieval → Schema Context → Gemini Generation → ANTLR Validation
"""
import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / '.env')

# Add parsers to path
sys.path.append(str(Path(__file__).parent / 'parsers'))

import google.generativeai as genai
from database.chroma_setup import get_chroma_collection
from parsers.validator import validate_jcoql_query


def load_mongodb_schema():
    """
    Carica schema MongoDB (discovered o fallback)
    Simula MongoDB Compass - schema reale dal database
    """
    try:
        # Prova schema discovered (dinamico - aggiornato da discovery)
        schema_path = Path(__file__).parent / "database" / "mongodb_schema_discovered.json"
        if schema_path.exists():
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
                print("✅ Using discovered MongoDB schema (real-time)")
                return schema
        
        # Fallback: schema statico
        schema_path = Path(__file__).parent / "database" / "mongodb_schema.json"
        if schema_path.exists():
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = json.load(f)
                print("⚠️ Using static MongoDB schema (fallback)")
                return schema
        
        print("⚠️ No MongoDB schema found")
        return {}
    
    except Exception as e:
        print(f"⚠️ Schema load error: {e}")
        return {}


def format_schema_for_prompt(schema):
    """
    Formatta schema MongoDB per prompt LLM
    Simile a come MongoDB Compass mostra le collections
    """
    if not schema:
        return ""
    
    lines = ["\n## 🗄️ REAL MONGODB SCHEMA (Available Collections & Fields):\n"]
    lines.append("**CRITICAL**: Use ONLY these collections and fields. Do NOT invent names!\n")
    
    for collection, info in schema.items():
        # Header collection
        total_docs = info.get('total_documents', 0)
        lines.append(f"\n📁 Collection: **{collection}** ({total_docs} documents)")
        
        # Fields
        if 'fields' in info and info['fields']:
            lines.append("   Available fields:")
            
            for field, field_info in sorted(info['fields'].items()):
                # Estrai info campo
                if isinstance(field_info, dict):
                    types = field_info.get('types', ['unknown'])
                    type_str = ", ".join(types)
                    examples = field_info.get('examples', [])
                    frequency = field_info.get('frequency', 1.0)
                    
                    # Formatta riga campo
                    line = f"      • .{field} ({type_str})"
                    
                    # Aggiungi frequenza se non 100%
                    if frequency < 1.0:
                        line += f" [{frequency*100:.0f}% present]"
                    
                    # Aggiungi esempi
                    if examples:
                        # Tronca esempi lunghi
                        ex_str = ", ".join([
                            f"'{e}'" if isinstance(e, str) else str(e)
                            for e in examples[:2]
                        ])
                        if len(ex_str) > 50:
                            ex_str = ex_str[:47] + "..."
                        line += f" (e.g., {ex_str})"
                    
                    lines.append(line)
                else:
                    # Formato semplice (backward compatibility)
                    lines.append(f"      • .{field} ({field_info})")
        else:
            lines.append("   (No fields discovered)")
    
    lines.append("\n⚠️ **IMPORTANT RULES**:")
    lines.append("   1. Use ONLY collections and fields listed above")
    lines.append("   2. Field names are case-sensitive: use exact spelling")
    lines.append("   3. For nested fields, use dot notation: .location.city")
    lines.append("   4. Arrays are marked as 'array' type")
    lines.append("")
    
    return "\n".join(lines)


def generate_jcoql_with_validation(nl_query, max_retries=2):
    """
    Generate JCoQL query with automatic validation and retry
    NOW WITH REAL MONGODB SCHEMA CONTEXT!
    
    Args:
        nl_query (str): Natural language query
        max_retries (int): Max validation retry attempts
    
    Returns:
        dict: {
            'nl_query': str,
            'jcoql_query': str,
            'is_valid': bool,
            'validation_errors': list,
            'attempts': int,
            'retrieved_examples': list,
            'schema_used': bool
        }
    """
    # Setup Gemini
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return {'error': 'GEMINI_API_KEY not found'}
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
    
    # Load MongoDB schema (REAL DATABASE SCHEMA!)
    schema = load_mongodb_schema()
    schema_context = format_schema_for_prompt(schema)
    
    # Retrieve examples from ChromaDB
    collection = get_chroma_collection()
    results = collection.query(
        query_texts=[nl_query],
        n_results=3
    )
    
    retrieved_examples = []
    if results['documents'] and results['documents'][0]:
        retrieved_examples = results['documents'][0]
    
    # Build examples text
    examples_text = "\n\n".join([
        f"Example {i+1}:\n{ex}" 
        for i, ex in enumerate(retrieved_examples)
    ])
    
    # Build complete prompt with schema context
    base_prompt = f"""You are a JCoQL 4.0 expert. Generate ONLY syntactically correct JCoQL queries using REAL database schema.

{schema_context}

## 📋 JCoQL 4.0 CRITICAL SYNTAX RULES:

1. **Always start with**: GET COLLECTION collection_name;
2. **Filter syntax**: FILTER CASE WHERE condition KEEP OTHERS;
3. **NO SQL**: Don't use SELECT, WHEN/THEN, FROM
4. **Field names**: Use dot notation: .city, .price, .rating
5. **IN_RANGE**: .field IN_RANGE [ min , max ] for inclusive bounds
6. **Operators**: AND, OR, NOT, =, >, <, >=, <=, !=
7. **Strings**: Single quotes: 'Milano' (NOT "Milano")
8. **Terminate**: End with semicolon: KEEP OTHERS;

## 📚 CORRECT EXAMPLES FROM DATABASE:

{examples_text}

## 🎯 USER REQUEST:
{nl_query}

**GENERATE ONLY THE JCOQL QUERY** (one statement, no explanations, no markdown):"""

    # Retry loop with validation
    for attempt in range(1, max_retries + 2):
        try:
            # Sleep between retries (after first attempt)
            if attempt > 1:
                print(f"  ⏰ Retry {attempt} - waiting 13s...")
                time.sleep(13)
            
            # Generate query
            response = model.generate_content(base_prompt)
            jcoql_query = response.text.strip()
            
            # Clean markdown artifacts
            jcoql_query = jcoql_query.replace('```jcoql', '').replace('```', '').strip()
            
            # Validate with ANTLR
            validation = validate_jcoql_query(jcoql_query)
            
            if validation['is_valid']:
                return {
                    'nl_query': nl_query,
                    'jcoql_query': jcoql_query,
                    'is_valid': True,
                    'validation_errors': [],
                    'attempts': attempt,
                    'retrieved_examples': retrieved_examples,
                    'schema_used': bool(schema)  # Flag: was schema available?
                }
            else:
                # Build error feedback for retry
                errors_text = "\n".join([
                    f"- {e['message']}" 
                    for e in validation['errors']
                ])
                
                base_prompt += f"\n\n❌ SYNTAX ERRORS (attempt {attempt}):\n{errors_text}\n\n**FIX AND REGENERATE**:"
                
                if attempt == max_retries + 1:
                    # Last attempt failed
                    return {
                        'nl_query': nl_query,
                        'jcoql_query': jcoql_query,
                        'is_valid': False,
                        'validation_errors': validation['errors'],
                        'attempts': attempt,
                        'retrieved_examples': retrieved_examples,
                        'schema_used': bool(schema)
                    }
        
        except Exception as e:
            return {
                'nl_query': nl_query,
                'error': str(e),
                'is_valid': False,
                'attempts': attempt,
                'schema_used': False
            }
    
    return {'error': 'Max retries exceeded'}


# Test
if __name__ == "__main__":
    print("="*70)
    print("🧪 RAG + SCHEMA DISCOVERY + ANTLR VALIDATION - TEST")
    print("="*70)
    
    test_queries = [
        "Hotel a Milano con rating superiore a 4",
        "Prodotti con prezzo tra 100 e 200 euro",
        "Ristoranti senza campo email"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n[{i}/{len(test_queries)}] Query: {query}")
        print("-"*70)
        
        result = generate_jcoql_with_validation(query)
        
        if 'error' in result:
            print(f"❌ ERROR: {result['error']}")
        else:
            print(f"✅ Valid: {result['is_valid']}")
            print(f"📊 Attempts: {result['attempts']}")
            print(f"🗄️ Schema used: {result.get('schema_used', False)}")
            print(f"📝 Generated Query:\n   {result['jcoql_query']}")
            
            if not result['is_valid']:
                print(f"\n⚠️ Validation errors:")
                for err in result['validation_errors']:
                    print(f"   - {err['message']}")
        
        # Sleep between queries (5 RPM quota = 12 seconds minimum)
        if i < len(test_queries):
            print(f"\n⏰ Waiting 13 seconds (quota: 5 RPM)...")
            time.sleep(13)
    
    print("\n" + "="*70)
    print("✅ Test complete!")