import re
import os

filepath = '../../examples/validated/jcoql_examples.txt'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Parse esempi
parts = re.split(r'ESEMPIO \d+:', content)

for i, part in enumerate(parts[1:], 1):
    if i == 14:  # Solo ESEMPIO 14
        lines = part.strip().split('\n')
        
        # Extract query
        query_match = re.search(r'Query:\s*\n(.+?)(?=\n\nESEMPIO|\Z)', part, re.DOTALL)
        if query_match:
            query = query_match.group(1).strip()
            
            print("="*60)
            print(f"ESEMPIO 14 - ESTRATTO DAL FILE:")
            print("="*60)
            print(f"Query letta:\n{repr(query)}\n")
            print("Query visualizzata:")
            print(query)
            print("="*60)