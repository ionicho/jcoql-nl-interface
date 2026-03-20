#!/usr/bin/env python3
"""
Valida nuovi esempi JCoQL
"""
import sys
sys.path.append('backend/parsers')

from backend.parsers.validator import validate_jcoql_query

def validate_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Estrai query
    examples = []
    current = {}
    
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('Titolo:'):
            if current.get('query'):
                examples.append(current)
            current = {'title': line.replace('Titolo:', '').strip()}
        elif line.startswith('Query:'):
            current['query'] = line.replace('Query:', '').strip()
    
    if current.get('query'):
        examples.append(current)
    
    # Valida
    valid = 0
    invalid = 0
    
    for i, ex in enumerate(examples, 1):
        result = validate_jcoql_query(ex['query'])
        if result['is_valid']:
            print(f"✅ {i}/{len(examples)}: {ex['title']}")
            valid += 1
        else:
            print(f"❌ {i}/{len(examples)}: {ex['title']}")
            print(f"   Errori: {result.get('errors', [])}")
            invalid += 1
    
    print(f"\n{'='*70}")
    print(f"RISULTATO: {valid}/{len(examples)} validi ({valid/len(examples)*100:.1f}%)")
    print(f"{'='*70}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        validate_file(sys.argv[1])
    else:
        validate_file('examples/validated/jcoql_examples_ADVANCED_V2.txt')