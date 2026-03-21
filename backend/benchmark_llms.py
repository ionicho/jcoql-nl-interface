#!/usr/bin/env python3
"""
Benchmark comparativo: Gemini vs Llama (vs Gemma)
Test 30 query (ridotto per rate limits)
"""
import os
import sys
import time
import json
from datetime import datetime
from typing import Dict, List

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
os.environ['ACTIVE_LLM'] = 'gemini'

from backend.rag_with_validation import generate_jcoql_with_validation

# 30 Query (ridotto da 50 per rate limits)
TEST_QUERIES = [
    # Base (8)
    "Hotel a Milano",
    "Prodotti con prezzo maggiore di 100",
    "Utenti con età superiore a 18",
    "Ristoranti a Roma",
    "Ordini con stato spedito",
    "Clienti premium",
    "Dispositivi Android",
    "Email non lette",
    
    # Intermedio (12)
    "Hotel a Milano con rating superiore a 4",
    "Prodotti con prezzo tra 100 e 200 euro",
    "Utenti senza email registrata",
    "Ordini effettuati negli ultimi 30 giorni",
    "Clienti con almeno 3 ordini",
    "Articoli della categoria tecnologia",
    "Ristoranti aperti adesso",
    "Prodotti in sconto maggiore del 20%",
    "Utenti registrati a gennaio 2024",
    "Hotel con parcheggio gratuito",
    "Film con rating maggiore di 7",
    "Libri pubblicati dopo il 2020",
    
    # Avanzato (10)
    "Hotel 5 stelle a Milano con rating maggiore di 4.5",
    "Prodotti in sconto tra 20% e 50% della categoria elettronica",
    "Utenti premium registrati dopo gennaio 2024",
    "Ordini con totale superiore a 500 euro",
    "Ristoranti italiani a Roma con rating maggiore di 4",
    "Film d'azione con rating maggiore di 8",
    "Auto elettriche con autonomia maggiore di 300 km",
    "Appartamenti a Milano con almeno 3 camere",
    "Corsi di programmazione online con certificato",
    "Eventi musicali a Milano nel weekend"
]

def test_llm(llm_name: str, queries: List[str]) -> Dict:
    """Testa un LLM"""
    
    os.environ['ACTIVE_LLM'] = llm_name
    
    print(f"\n{'='*70}")
    print(f"🧪 TESTING: {llm_name.upper()}")
    print(f"{'='*70}\n")
    
    results = []
    total_time = 0
    
    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query[:50]}...")
        
        start = time.time()
        try:
            result = generate_jcoql_with_validation(query)
            elapsed = time.time() - start
            
            if 'jcoql_query' not in result:
                raise ValueError("Missing jcoql_query in result")
            
            results.append({
                'query': query,
                'jcoql': result.get('jcoql_query', ''),
                'valid': result.get('is_valid', False),
                'attempts': result.get('attempts', 0),
                'time': elapsed,
                'errors': result.get('validation_errors', [])
            })
            
            total_time += elapsed
            
            status = "✅" if result.get('is_valid', False) else "❌"
            print(f"   {status} Time: {elapsed:.2f}s | Attempts: {result.get('attempts', 0)}")
            
        except Exception as e:
            print(f"   ❌ ERROR: {e}")
            results.append({
                'query': query,
                'jcoql': None,
                'valid': False,
                'attempts': 0,
                'time': 0,
                'errors': [str(e)]
            })
        
        # RATE LIMITING
        if i < len(queries):
            if llm_name == 'gemini':
                sleep_time = 13  # 5 RPM = 13s tra query
                print(f"   ⏳ Sleep {sleep_time}s...")
                time.sleep(sleep_time)
            else:
                time.sleep(2)
    
    # Stats
    valid_count = sum(1 for r in results if r['valid'])
    accuracy = valid_count / len(results) if results else 0
    avg_time = total_time / len(results) if results else 0
    avg_attempts = sum(r['attempts'] for r in results) / len(results) if results else 0
    first_try = sum(1 for r in results if r['valid'] and r['attempts'] == 1)
    
    stats = {
        'llm': llm_name,
        'total_queries': len(results),
        'valid': valid_count,
        'invalid': len(results) - valid_count,
        'accuracy': accuracy,
        'avg_time': avg_time,
        'total_time': total_time,
        'avg_attempts': avg_attempts,
        'first_try_success_rate': first_try / len(results) if results else 0,
        'results': results
    }
    
    print(f"\n📊 STATS {llm_name.upper()}:")
    print(f"   Accuracy: {accuracy:.1%} ({valid_count}/{len(results)})")
    print(f"   Avg Time: {avg_time:.2f}s")
    print(f"   Total Time: {total_time:.1f}s")
    print(f"   Avg Attempts: {avg_attempts:.2f}")
    print(f"   First Try: {first_try}/{len(results)} ({first_try/len(results):.1%})")
    
    return stats

def run_full_benchmark():
    """Benchmark completo"""
    
    print(f"\n{'#'*70}")
    print(f"# BENCHMARK LLM")
    print(f"# Queries: {len(TEST_QUERIES)}")
    print(f"# Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*70}\n")
    
    all_stats = {}
    
    for llm in ['gemini', 'llama']:
        stats = test_llm(llm, TEST_QUERIES)
        all_stats[llm] = stats
        time.sleep(5)
    
    # Salva
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'backend/benchmark_results_{timestamp}.json'
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_stats, f, indent=2, ensure_ascii=False)
    
    # Report
    print(f"\n{'='*70}")
    print(f"📊 CONFRONTO FINALE")
    print(f"{'='*70}\n")
    
    print(f"{'LLM':<10} | {'Accuracy':<10} | {'Avg Time':<10} | {'Attempts':<10}")
    print(f"{'-'*60}")
    
    for llm, stats in all_stats.items():
        print(f"{llm.upper():<10} | "
              f"{stats['accuracy']:>8.1%} | "
              f"{stats['avg_time']:>8.2f}s | "
              f"{stats['avg_attempts']:>8.2f}")
    
    print(f"\n💾 Risultati: {filename}")
    
    return all_stats

if __name__ == "__main__":
    results = run_full_benchmark()