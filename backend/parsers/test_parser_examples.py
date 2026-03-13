#!/usr/bin/env python3
"""
Test parser ANTLR su tutti i 39 esempi JCoQL 4.0
"""
import sys
import os
import re
from validator import validate_jcoql_query

# Leggi tutti i file esempi
example_files = [
    '../../examples/validated/jcoql_examples.txt',
    '../../examples/validated/jcoql_examples_EXTENDED.txt',
    '../../examples/validated/jcoql_examples_INRANGE.txt'
]

def parse_examples_file(filepath):
    """Parse esempi da file"""
    if not os.path.exists(filepath):
        return []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    examples = []
    parts = re.split(r'ESEMPIO \d+:', content)
    
    for part in parts[1:]:
        lines = part.strip().split('\n')
        
        # Extract title
        title_line = [l for l in lines if l.strip() and not l.startswith('-') and 'Descrizione:' not in l and 'Query:' not in l]
        if not title_line:
            continue
        title = title_line[0].strip()
        
        # Extract query
        query_match = re.search(r'Query:\s*\n(.+?)(?=\n\n(?:ESEMPIO|=+)|\Z)', part, re.DOTALL)
        if query_match:
            query = query_match.group(1).strip()
            examples.append({
                'title': title,
                'query': query
            })
    
    return examples

print("="*70)
print("TEST PARSER ANTLR - 39 ESEMPI JCOQL 4.0")
print("="*70)
print()

all_examples = []
for filepath in example_files:
    if os.path.exists(filepath):
        examples = parse_examples_file(filepath)
        all_examples.extend(examples)
        print(f"✅ Loaded {len(examples)} from {os.path.basename(filepath)}")

print(f"\n📚 Total examples: {len(all_examples)}")
print()
print("="*70)
print("VALIDAZIONE")
print("="*70)
print()

valid_count = 0
invalid_count = 0
error_count = 0

for i, example in enumerate(all_examples, 1):
    title = example['title'][:50]
    query = example['query']
    
    print(f"[{i}/{len(all_examples)}] {title}...")
    
    result = validate_jcoql_query(query)
    
    if result['is_valid']:
        print(f"  ✅ VALID")
        valid_count += 1
    else:
        print(f"  ❌ INVALID")
        invalid_count += 1
        for error in result['errors'][:2]:  # Max 2 errori
            print(f"     - {error['message']}")
    
    print()

print("="*70)
print("RISULTATI FINALI")
print("="*70)
print(f"✅ Valid:   {valid_count}/{len(all_examples)} ({valid_count/len(all_examples)*100:.1f}%)")
print(f"❌ Invalid: {invalid_count}/{len(all_examples)} ({invalid_count/len(all_examples)*100:.1f}%)")
print("="*70)

if valid_count == len(all_examples):
    print("\n🎉 PERFETTO! Tutti gli esempi sono sintatticamente corretti!")
else:
    print(f"\n⚠️  {invalid_count} esempi da correggere")