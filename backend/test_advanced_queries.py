#!/usr/bin/env python3
"""
Test Suite Avanzato - 20 Query NL → JCoQL
Difficoltà: Base → Intermedia → Avanzata
"""
import time
from rag_with_validation import generate_jcoql_with_validation

# Test queries - Difficoltà crescente
test_queries = [
    # LIVELLO 1: BASE (1-5)
    {
        'id': 1,
        'level': 'Base',
        'nl': 'Negozi a Bergamo',
        'expected_keywords': ['GET COLLECTION', 'Bergamo', 'FILTER']
    },
    {
        'id': 2,
        'level': 'Base',
        'nl': 'Prodotti con prezzo maggiore di 50',
        'expected_keywords': ['GET COLLECTION', '.price', '>', '50']
    },
    {
        'id': 3,
        'level': 'Base',
        'nl': 'Hotel con rating 5',
        'expected_keywords': ['GET COLLECTION', '.rating', '=', '5']
    },
    {
        'id': 4,
        'level': 'Base',
        'nl': 'Utenti con email',
        'expected_keywords': ['GET COLLECTION', 'WITH', '.email']
    },
    {
        'id': 5,
        'level': 'Base',
        'nl': 'Documenti senza note',
        'expected_keywords': ['GET COLLECTION', 'WITHOUT', '.note']
    },
    
    # LIVELLO 2: INTERMEDIO (6-12)
    {
        'id': 6,
        'level': 'Intermedio',
        'nl': 'Hotel a Milano con rating superiore a 4 e prezzo inferiore a 200',
        'expected_keywords': ['Milano', '.rating', '>', '4', 'AND', '.price', '<', '200']
    },
    {
        'id': 7,
        'level': 'Intermedio',
        'nl': 'Ristoranti a Roma o Firenze',
        'expected_keywords': ['Roma', 'OR', 'Firenze']
    },
    {
        'id': 8,
        'level': 'Intermedio',
        'nl': 'Prodotti con prezzo tra 100 e 500 euro',
        'expected_keywords': ['IN_RANGE', '100', '500']
    },
    {
        'id': 9,
        'level': 'Intermedio',
        'nl': 'Appartamenti con superficie tra 50 e 100 metri quadri',
        'expected_keywords': ['IN_RANGE', '50', '100', '.superficie']
    },
    {
        'id': 10,
        'level': 'Intermedio',
        'nl': 'Ordini dove il campo note è null',
        'expected_keywords': ['IS NULL', '.note']
    },
    {
        'id': 11,
        'level': 'Intermedio',
        'nl': 'Clienti dove descrizione non è null',
        'expected_keywords': ['IS NOT NULL', '.descrizione']
    },
    {
        'id': 12,
        'level': 'Intermedio',
        'nl': 'Prodotti senza email e senza telefono',
        'expected_keywords': ['WITHOUT', '.email', 'AND', 'WITHOUT', '.phone']
    },
    
    # LIVELLO 3: AVANZATO (13-20)
    {
        'id': 13,
        'level': 'Avanzato',
        'nl': 'Hotel a Milano o Roma con rating maggiore di 4 e prezzo minore di 300',
        'expected_keywords': ['Milano', 'OR', 'Roma', 'AND', '.rating', '>', '4', 'AND', '.price', '<', '300']
    },
    {
        'id': 14,
        'level': 'Avanzato',
        'nl': 'Prodotti elettronici con prezzo tra 200 e 1000 e non discontinued',
        'expected_keywords': ['elettronici', 'IN_RANGE', '200', '1000', 'NOT', '.discontinued']
    },
    {
        'id': 15,
        'level': 'Avanzato',
        'nl': 'Clienti premium o gold che sono attivi',
        'expected_keywords': ['premium', 'OR', 'gold', 'AND', '.active']
    },
    {
        'id': 16,
        'level': 'Avanzato',
        'nl': 'Temperature tra 18.5 e 22.5 gradi',
        'expected_keywords': ['IN_RANGE', '18.5', '22.5', '.temperature']
    },
    {
        'id': 17,
        'level': 'Avanzato',
        'nl': 'Vendite per categoria con totale maggiore di zero',
        'expected_keywords': ['GROUP', '.category', '.amount', '>', '0']
    },
    {
        'id': 18,
        'level': 'Avanzato',
        'nl': 'Salva risultati come nuova collezione chiamata best_hotels',
        'expected_keywords': ['SAVE AS', 'best_hotels']
    },
    {
        'id': 19,
        'level': 'Avanzato',
        'nl': 'Unisci le collezioni clienti_europa e clienti_usa',
        'expected_keywords': ['MERGE COLLECTIONS', 'clienti_europa', 'clienti_usa']
    },
    {
        'id': 20,
        'level': 'Avanzato',
        'nl': 'Clienti comuni tra online e negozio',
        'expected_keywords': ['INTERSECT COLLECTIONS', 'online', 'negozio']
    }
]

def run_test_suite():
    """Execute full test suite"""
    results = {
        'total': len(test_queries),
        'valid': 0,
        'invalid': 0,
        'errors': 0,
        'total_attempts': 0,
        'by_level': {
            'Base': {'total': 0, 'valid': 0},
            'Intermedio': {'total': 0, 'valid': 0},
            'Avanzato': {'total': 0, 'valid': 0}
        },
        'details': []
    }
    
    print("="*80)
    print("TEST SUITE AVANZATO - 20 QUERY NL → JCoQL")
    print("="*80)
    print()
    
    for i, test_case in enumerate(test_queries, 1):
        level = test_case['level']
        nl_query = test_case['nl']
        
        print(f"[{i}/20] LIVELLO {level.upper()}")
        print(f"Query NL: {nl_query}")
        print("-"*80)
        
        # Execute
        result = generate_jcoql_with_validation(nl_query)
        
        # Update stats
        results['by_level'][level]['total'] += 1
        
        if 'error' in result:
            print(f"❌ ERROR: {result['error']}")
            results['errors'] += 1
            status = 'error'
        else:
            results['total_attempts'] += result['attempts']
            
            if result['is_valid']:
                print(f"✅ VALID (attempt {result['attempts']})")
                print(f"JCoQL: {result['jcoql_query'][:80]}...")
                results['valid'] += 1
                results['by_level'][level]['valid'] += 1
                status = 'valid'
            else:
                print(f"❌ INVALID after {result['attempts']} attempts")
                print(f"JCoQL: {result['jcoql_query'][:80]}...")
                if result.get('validation_errors'):
                    print(f"Errors: {result['validation_errors'][0]['message'][:60]}...")
                results['invalid'] += 1
                status = 'invalid'
        
        # Store details
        results['details'].append({
            'id': test_case['id'],
            'level': level,
            'nl': nl_query,
            'status': status,
            'jcoql': result.get('jcoql_query', ''),
            'attempts': result.get('attempts', 0),
            'valid': result.get('is_valid', False)
        })
        
        print()
        
        # Sleep between queries (quota: 5 RPM)
        if i < len(test_queries):
            print(f"⏰ Waiting 13 seconds (quota management)...")
            time.sleep(13)
            print()
    
    # Final report
    print("="*80)
    print("RISULTATI FINALI")
    print("="*80)
    print(f"✅ Valid:   {results['valid']}/20 ({results['valid']/20*100:.1f}%)")
    print(f"❌ Invalid: {results['invalid']}/20 ({results['invalid']/20*100:.1f}%)")
    print(f"⚠️  Errors:  {results['errors']}/20 ({results['errors']/20*100:.1f}%)")
    print()
    
    if results['valid'] > 0:
        avg_attempts = results['total_attempts'] / results['valid']
        print(f"📊 Media tentativi (query valide): {avg_attempts:.1f}")
    print()
    
    print("PER LIVELLO:")
    for level in ['Base', 'Intermedio', 'Avanzato']:
        stats = results['by_level'][level]
        if stats['total'] > 0:
            accuracy = (stats['valid'] / stats['total']) * 100
            print(f"  {level:12} {stats['valid']}/{stats['total']} ({accuracy:.1f}%)")
    
    print("="*80)
    
    return results

if __name__ == "__main__":
    results = run_test_suite()
    
    # Save results
    import json
    with open('test_results_advanced.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print()
    print("📄 Risultati salvati in: test_results_advanced.json")