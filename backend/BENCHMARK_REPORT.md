# 📊 Benchmark LLM - Report Comparativo

**Data:** 15 Marzo 2026  
**Query Testate:** 30 (8 base, 12 intermedio, 10 avanzato)  
**LLM:** Gemini 3.1 Flash Lite vs Llama 3.1 8B

---

## Risultati

| Metrica | Gemini (Cloud) | Llama (Locale) | Vincitore |
|---------|----------------|----------------|-----------|
| **Accuracy** | 100.0% (30/30) | 100.0% (30/30) | 🤝 TIE |
| **Avg Latency** | 5.57s | 3.55s | 🏆 LLAMA |
| **Total Time** | 167.1s | 106.5s | 🏆 LLAMA |
| **Avg Attempts** | 1.03 | 1.03 | 🤝 TIE |
| **First Try %** | 96.7% | 96.7% | 🤝 TIE |
| **Quota** | 500 RPD | ∞ | 🏆 LLAMA |
| **Privacy** | Cloud | Locale 100% | 🏆 LLAMA |
| **Costo** | $0 (limitato) | $0 (illimitato) | 🏆 LLAMA |

---

## Conclusioni

### 🏆 **LLAMA 3.1 8B LOCALE SUPERIORE**

**Vantaggi Llama:**
- ✅ **36% più veloce** (3.55s vs 5.57s)
- ✅ **Quota illimitata** (vs 500/giorno)
- ✅ **100% privacy** (tutto locale)
- ✅ **Zero dipendenza** da API cloud
- ✅ **Stessa accuracy** di Gemini

**Quando usare Gemini:**
- GPU non disponibile
- Serve scaling oltre capacità locale

### 📈 **IMPATTO REGOLE SINTATTICHE**

L'integrazione delle regole ufficiali JCoQL 4.0 nel prompt ha portato:
- ✅ 100% accuracy (da ~85%)
- ✅ 96.7% successo primo tentativo
- ✅ Zero allucinazioni sintattiche

### 🎯 **QUERY CRITICA**

**Query #17:** "Prodotti in sconto maggiore del 20%"
- Unica query con 2 tentativi (entrambi LLM)
- Complessità: calcolo percentuale + confronto
- Risultato: Entrambi hanno corretto al 2° tentativo ✅

---

## Raccomandazione Deployment

**Configurazione Ottimale:**
```
Primary:   Llama 3.1 8B (locale)
Fallback:  Gemini 3.1 Flash Lite (cloud)
```

**Motivi:**
1. Performance superiore (36% più veloce)
2. Quota illimitata
3. Privacy garantita
4. Costo zero
5. Stessa qualità output

**Hardware Minimo:**
- GPU: NVIDIA RTX 4060 (8GB VRAM)
- RAM: 16GB
- Storage: 10GB (modello)
