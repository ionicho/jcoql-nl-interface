#!/usr/bin/env python3
"""
Semantic Validator - Verifica che campi esistano nello schema
"""
import json
from pathlib import Path

def validate_fields_exist(jcoql_query, schema):
    """
    Verifica che tutti i campi nella query esistano nello schema
    
    Returns:
        dict: {
            'valid': bool,
            'errors': list[str],
            'warnings': list[str]
        }
    """
    errors = []
    warnings = []
    
    # Estrai collection name (GET COLLECTION nome;)
    if "GET COLLECTION" in jcoql_query:
        collection = jcoql_query.split("GET COLLECTION")[1].split(";")[0].strip()
        
        # Verifica collection esista
        if collection not in schema:
            errors.append(f"Collection '{collection}' not found in database")
            return {'valid': False, 'errors': errors, 'warnings': warnings}
        
        # Estrai campi (.fieldname)
        import re
        fields = re.findall(r'\.(\w+(?:\.\w+)*)', jcoql_query)
        
        # Verifica ogni campo
        available_fields = schema[collection].get('fields', {})
        
        for field in fields:
            if field not in available_fields:
                errors.append(
                    f"Field '.{field}' not found in collection '{collection}'. "
                    f"Available fields: {', '.join(list(available_fields.keys())[:5])}"
                )
    
    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    }