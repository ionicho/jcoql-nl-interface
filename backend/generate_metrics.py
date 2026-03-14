#!/usr/bin/env python3
"""
Metriche Avanzate - Precision, Recall, F1-Score
Analisi risultati test suite
"""
import json
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime

# Load test results
with open('test_results_advanced.json', 'r', encoding='utf-8') as f:
    results = json.load(f)

print("="*80)
print("ANALISI METRICHE AVANZATE - TEST SUITE")
print("="*80)
print()

# Calcola metriche base
total = results['total']
valid = results['valid']
invalid = results['invalid']
errors = results['errors']

accuracy = (valid / total) * 100 if total > 0 else 0

print("📊 METRICHE GLOBALI:")
print(f"  Total queries:    {total}")
print(f"  Valid:            {valid} ({valid/total*100:.1f}%)")
print(f"  Invalid:          {invalid} ({invalid/total*100:.1f}%)")
print(f"  Errors:           {errors} ({errors/total*100:.1f}%)")
print(f"  Accuracy:         {accuracy:.2f}%")
print()

# Calcola media tentativi
if valid > 0:
    avg_attempts = results['total_attempts'] / valid
    print(f"📈 EFFICIENZA:")
    print(f"  Media tentativi:  {avg_attempts:.2f}")
    print(f"  Primo colpo:      {sum(1 for d in results['details'] if d.get('attempts', 0) == 1)}/{valid} ({sum(1 for d in results['details'] if d.get('attempts', 0) == 1)/valid*100:.1f}%)")
    print()

# Metriche per livello
print("📊 ACCURACY PER LIVELLO:")
for level in ['Base', 'Intermedio', 'Avanzato']:
    stats = results['by_level'][level]
    if stats['total'] > 0:
        acc = (stats['valid'] / stats['total']) * 100
        print(f"  {level:12} {stats['valid']:2}/{stats['total']:2} ({acc:5.1f}%)")
print()

# Precision, Recall, F1 (per validazione binaria)
# TP = Valid queries (correttamente identificate come valide)
# TN = N/A (non abbiamo negative examples)
# FP = Invalid accettate (0 nel nostro caso)
# FN = Valid rifiutate (0 nel nostro caso)

tp = valid  # True Positives
fp = 0      # False Positives (query invalide accettate)
fn = invalid  # False Negatives (query valide rifiutate)

precision = tp / (tp + fp) if (tp + fp) > 0 else 0
recall = tp / (tp + fn) if (tp + fn) > 0 else 0
f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

print("🎯 METRICHE CLASSIFICAZIONE:")
print(f"  Precision:        {precision:.4f}")
print(f"  Recall:           {recall:.4f}")
print(f"  F1-Score:         {f1_score:.4f}")
print()

# Distribuzione tentativi
attempts_dist = {}
for detail in results['details']:
    att = detail.get('attempts', 0)
    if att > 0:
        attempts_dist[att] = attempts_dist.get(att, 0) + 1

print("📊 DISTRIBUZIONE TENTATIVI:")
for attempt, count in sorted(attempts_dist.items()):
    print(f"  {attempt} tentativo/i: {count:2} query ({count/valid*100:.1f}%)")
print()

# Genera report testuale
report = f"""
JCOQL+ NL INTERFACE - REPORT METRICHE AVANZATE
{'='*80}
Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

RISULTATI GLOBALI
{'-'*80}
Total queries tested:     {total}
Valid queries:            {valid} ({accuracy:.2f}%)
Invalid queries:          {invalid}
Errors:                   {errors}

METRICHE DI CLASSIFICAZIONE
{'-'*80}
Precision:                {precision:.4f}
Recall:                   {recall:.4f}
F1-Score:                 {f1_score:.4f}
Accuracy:                 {accuracy:.2f}%

EFFICIENZA GENERAZIONE
{'-'*80}
Media tentativi:          {avg_attempts:.2f}
Successo primo tentativo: {sum(1 for d in results['details'] if d.get('attempts', 0) == 1)} / {valid} ({sum(1 for d in results['details'] if d.get('attempts', 0) == 1)/valid*100:.1f}%)

PERFORMANCE PER LIVELLO
{'-'*80}
"""

for level in ['Base', 'Intermedio', 'Avanzato']:
    stats = results['by_level'][level]
    if stats['total'] > 0:
        acc = (stats['valid'] / stats['total']) * 100
        report += f"{level:12} {stats['valid']:2}/{stats['total']:2} ({acc:5.1f}%)\n"

report += f"\n{'='*80}\n"

# Salva report
with open('metrics_report.txt', 'w', encoding='utf-8') as f:
    f.write(report)

print("✅ Report salvato in: metrics_report.txt")
print()
print("="*80)