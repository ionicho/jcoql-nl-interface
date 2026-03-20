#!/usr/bin/env python3
"""
Benchmark: Gemini vs Llama vs Gemma
"""
import os
import time
import json
from datetime import datetime

# Simula cambio LLM
def test_with_llm(llm_name: str, test_queries: list):
    """Testa un LLM specifico"""
    os.environ['ACTIVE_LLM'] = llm_name
    
    # Importa dopo aver settato env
    from rag_with_validation import generate_jcoql_with_validation
    
    results = []
    
    for query in test_queries:
        start = time.time()
        result = generate_jcoql_with_validation(query)
        elapsed = time.time() - start
        
        results.append({
            'nl_query': query,
            'jcoql': result['jcoql_query'],
            'valid': result['is_valid'],
            'attempts': result['attempts'],
            'time': elapsed
        })
        
        time.sleep(1)  # Pausa tra query
    
    return results

def run_benchmark():
    """Benchmark completo"""
    test_queries = [
        "Hotel a Milano con rating > 4",
        "Prodotti con prezzo tra 100 e 200",
        "Utenti senza email",
    ]
    
    llms = ['gemini', 'llama', 'gemma']
    
    benchmark = {
        'timestamp': datetime.now().isoformat(),
        'results': {}
    }
    
    for llm in llms:
        print(f"\n{'='*70}")
        print(f"TESTING: {llm.upper()}")
        print(f"{'='*70}")
        
        results = test_with_llm(llm, test_queries)
        
        # Calcola stats
        valid_count = sum(1 for r in results if r['valid'])
        avg_time = sum(r['time'] for r in results) / len(results)
        avg_attempts = sum(r['attempts'] for r in results) / len(results)
        
        benchmark['results'][llm] = {
            'queries': results,
            'accuracy': valid_count / len(results),
            'avg_time': avg_time,
            'avg_attempts': avg_attempts
        }
        
        print(f"Accuracy: {valid_count}/{len(results)}")
        print(f"Avg Time: {avg_time:.2f}s")
        print(f"Avg Attempts: {avg_attempts:.2f}")
    
    # Salva risultati
    with open('benchmark_results.json', 'w') as f:
        json.dump(benchmark, f, indent=2)
    
    print(f"\n{'='*70}")
    print("CONFRONTO FINALE:")
    print(f"{'='*70}")
    for llm, stats in benchmark['results'].items():
        print(f"{llm.upper():10} | Acc: {stats['accuracy']:.1%} | Time: {stats['avg_time']:.2f}s | Attempts: {stats['avg_attempts']:.2f}")

if __name__ == "__main__":
    run_benchmark()