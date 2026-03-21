#!/usr/bin/env python3
"""
Wrapper Python per Parser Java ANTLR3 Ufficiale
"""
import subprocess
import os
import re

def validate_with_java_parser(query: str) -> dict:
    """
    Valida query JCoQL usando parser Java ufficiale ANTLR3
    
    Args:
        query: Query JCoQL da validare
        
    Returns:
        dict con is_valid, errors, warnings
    """
    
    # Percorsi
    base_dir = os.path.dirname(__file__)
    project_root = os.path.abspath(os.path.join(base_dir, '..', '..'))
    resources_dir = os.path.join(project_root, 'resources')
    input_file = os.path.join(resources_dir, 'input.file')
    
    parser_jar = os.path.join(base_dir, "jcoql-parser-official.jar")
    antlr_jar = os.path.join(base_dir, "antlr-3.4-complete.jar")
    
    # Crea directory resources se non esiste
    os.makedirs(resources_dir, exist_ok=True)
    
    # Scrivi query in input.file (UTF-8 senza BOM)
    with open(input_file, 'w', encoding='utf-8') as f:
        f.write(query)
    
    try:
        # Chiama parser Java (da project root)
        result = subprocess.run(
            [
                'java',
                '-cp',
                f'{parser_jar};{antlr_jar}',
                'jco.ql.parser.test.ParserTester'
            ],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=project_root,  # Esegui da root per trovare resources/
            encoding='utf-8'
        )
        
        output = result.stdout
        errors_output = result.stderr
        
        # Parse output per estrarre info
        errors = []
        warnings = []
        
        # Cerca "Numero di errori: N"
        error_match = re.search(r'Numero di errori:\s*(\d+)', output)
        num_errors = int(error_match.group(1)) if error_match else 0
        
        # Cerca "Numero di warning: N"
        warning_match = re.search(r'Numero di warning:\s*(\d+)', output)
        num_warnings = int(warning_match.group(1)) if warning_match else 0
        
        # Estrai errori (linee che iniziano con numeri seguito da punto)
        for line in output.split('\n'):
            if re.match(r'^\d+\.\s+(Syntax Error|Lexical Error)', line):
                errors.append(line.strip())
            elif re.match(r'^\d+\.\s+Warning', line):
                warnings.append(line.strip())
        
        # Valido se 0 errori
        is_valid = num_errors == 0
        
        return {
            'is_valid': is_valid,
            'errors': errors,
            'warnings': warnings,
            'num_errors': num_errors,
            'num_warnings': num_warnings,
            'full_output': output
        }
        
    except subprocess.TimeoutExpired:
        return {
            'is_valid': False,
            'errors': ['Timeout: parser non ha risposto'],
            'warnings': [],
            'num_errors': 1,
            'num_warnings': 0,
            'full_output': ''
        }
    except Exception as e:
        return {
            'is_valid': False,
            'errors': [f'Exception: {str(e)}'],
            'warnings': [],
            'num_errors': 1,
            'num_warnings': 0,
            'full_output': ''
        }

# Test
if __name__ == "__main__":
    queries = [
        "GET COLLECTION hotels; FILTER CASE WHERE .city = 'Milano' KEEP OTHERS;",
        "GET COLLECTION products;",
        "INVALID SYNTAX HERE"
    ]
    
    for query in queries:
        print(f"\n{'='*70}")
        print(f"Query: {query[:50]}...")
        result = validate_with_java_parser(query)
        print(f"Valid: {result['is_valid']}")
        print(f"Errors: {result['num_errors']}")
        print(f"Warnings: {result['num_warnings']}")
        if result['errors']:
            print(f"Details: {result['errors']}")