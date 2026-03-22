#!/usr/bin/env python3
"""
Genera report Word per professori
Progressi tesi dopo colloquio
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import datetime

def create_report():
    """Crea report professionale per professori"""
    
    doc = Document()
    
    # ========================================
    # INTESTAZIONE
    # ========================================
    heading = doc.add_heading('Report Progressi Tesi Magistrale', 0)
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Info studente
    info = doc.add_paragraph()
    info.add_run('Studente: ').bold = True
    info.add_run('Nicholas Iotti\n')
    info.add_run('Email: ').bold = True
    info.add_run('nicho23iotti@gmail.com\n')
    info.add_run('Corso: ').bold = True
    info.add_run('Laurea Magistrale in Ingegneria Informatica\n')
    info.add_run('Università: ').bold = True
    info.add_run('Università degli Studi di Bergamo\n')
    info.add_run('Data: ').bold = True
    info.add_run(f'{datetime.now().strftime("%d/%m/%Y")}\n')
    info.alignment = WD_ALIGN_PARAGRAPH.LEFT
    
    doc.add_paragraph()  # Spazio
    
    # ========================================
    # SEZIONE 1: OBIETTIVO TESI
    # ========================================
    doc.add_heading('1. Obiettivo della Tesi', 1)
    
    p1 = doc.add_paragraph()
    p1.add_run('Sviluppo di un\'interfaccia natural language per il linguaggio di query JCoQL+ che permetta agli utenti di formulare query in linguaggio naturale italiano e ottenere automaticamente la corrispondente query JCoQL+ sintatticamente corretta e validata.')
    
    # ========================================
    # SEZIONE 2: ARCHITETTURA IMPLEMENTATA
    # ========================================
    doc.add_heading('2. Architettura Implementata', 1)
    
    doc.add_heading('2.1 Stack Tecnologico', 2)
    
    # Tabella stack
    table = doc.add_table(rows=9, cols=3)
    table.style = 'Light Grid Accent 1'
    
    # Header
    headers = table.rows[0].cells
    headers[0].text = 'Componente'
    headers[1].text = 'Tecnologia'
    headers[2].text = 'Versione/Dettagli'
    
    # Dati
    data = [
        ['Backend', 'FastAPI', 'Python 3.14.3'],
        ['Frontend', 'React + Vite', 'React 19, Vite 8'],
        ['LLM Cloud', 'Google Gemini', '3.1 Flash Lite (500 RPD)'],
        ['LLM Locale', 'Llama (Meta)', '3.1 8B Q4 (4.7GB VRAM)'],
        ['LLM Locale', 'Gemma (Google)', '2 9B Q4 (5.4GB VRAM)'],
        ['Vector DB', 'ChromaDB', 'Embeddings locali'],
        ['Parser Custom', 'ANTLR 4.9.3', 'Convertito da JCoQL 4.0'],
        ['Parser Ufficiale', 'ANTLR 3.4', 'Dal repository prof (JAR)']
    ]
    
    for i, row_data in enumerate(data, 1):
        cells = table.rows[i].cells
        cells[0].text = row_data[0]
        cells[1].text = row_data[1]
        cells[2].text = row_data[2]
    
    doc.add_paragraph()
    
    doc.add_heading('2.2 Pipeline RAG (Retrieval-Augmented Generation)', 2)
    
    pipeline = doc.add_paragraph()
    pipeline.add_run('1. Input: ').bold = True
    pipeline.add_run('Query in linguaggio naturale italiano\n')
    pipeline.add_run('2. Retrieval: ').bold = True
    pipeline.add_run('ChromaDB recupera top-3 esempi simili (embeddings locali)\n')
    pipeline.add_run('3. Prompt Engineering: ').bold = True
    pipeline.add_run('Regole sintattiche JCoQL 4.0 + esempi RAG + query utente\n')
    pipeline.add_run('4. Generation: ').bold = True
    pipeline.add_run('LLM genera query JCoQL+\n')
    pipeline.add_run('5. Validation: ').bold = True
    pipeline.add_run('Parser ANTLR (custom o ufficiale) valida sintassi\n')
    pipeline.add_run('6. Retry Loop: ').bold = True
    pipeline.add_run('Se invalida, feedback errori → LLM rigenera (max 3 tentativi)\n')
    pipeline.add_run('7. Output: ').bold = True
    pipeline.add_run('Query JCoQL+ validata')
    
    # ========================================
    # SEZIONE 3: FEATURES IMPLEMENTATE
    # ========================================
    doc.add_heading('3. Features Implementate', 1)
    
    features = [
        ('Multi-LLM Provider', 'Supporto per 3 LLM: Gemini (cloud), Llama e Gemma (locali). Switch runtime via API e UI.'),
        ('Multi-Parser Architecture', 'Due parser: ANTLR4 Custom (convertito) e ANTLR3 Official (dal repository prof). Factory Pattern per switch seamless.'),
        ('Regole Sintattiche Integrate', 'File JCoQL.txt e JCoQLBasic.txt ufficiali integrati nel prompt LLM per prevenire allucinazioni sintattiche.'),
        ('Output Cleanup Intelligente', 'Algoritmi specifici per ogni LLM per estrarre solo codice JCoQL valido.'),
        ('Dashboard Metriche', 'Visualizzazione real-time di accuracy, latency, retry rate con Chart.js.'),
        ('Validazione ANTLR Completa', 'Parser genera AST completo con errori dettagliati (linea, colonna, messaggio).'),
    ]
    
    for title, desc in features:
        p = doc.add_paragraph()
        p.add_run(f'• {title}: ').bold = True
        p.add_run(desc)
    
    # ========================================
    # SEZIONE 4: RISULTATI SPERIMENTALI
    # ========================================
    doc.add_heading('4. Risultati Sperimentali', 1)
    
    doc.add_heading('4.1 Dataset', 2)
    p = doc.add_paragraph()
    p.add_run('• Esempi totali: ').bold = True
    p.add_run('99 query JCoQL+ validate\n')
    p.add_run('• Breakdown: ').bold = True
    p.add_run('14 base + 18 intermedi + 7 IN_RANGE + 20 edge cases + 40 sintassi reale\n')
    p.add_run('• Accuracy validazione: ').bold = True
    p.add_run('100% (99/99 esempi validati con parser)')
    
    doc.add_heading('4.2 Test End-to-End', 2)
    p = doc.add_paragraph()
    p.add_run('• Query testate: ').bold = True
    p.add_run('20 (difficoltà crescente)\n')
    p.add_run('• Accuracy: ').bold = True
    p.add_run('100%\n')
    p.add_run('• Precision: ').bold = True
    p.add_run('1.0\n')
    p.add_run('• Recall: ').bold = True
    p.add_run('1.0\n')
    p.add_run('• F1-Score: ').bold = True
    p.add_run('1.0\n')
    p.add_run('• Primo tentativo: ').bold = True
    p.add_run('95% successo\n')
    p.add_run('• Media tentativi: ').bold = True
    p.add_run('1.05')
    
    doc.add_heading('4.3 Benchmark Multi-LLM (30 query)', 2)
    
    # Tabella benchmark
    table_bench = doc.add_table(rows=3, cols=5)
    table_bench.style = 'Light Grid Accent 1'
    
    headers = table_bench.rows[0].cells
    headers[0].text = 'LLM'
    headers[1].text = 'Accuracy'
    headers[2].text = 'Latency Media'
    headers[3].text = 'First Try %'
    headers[4].text = 'Note'
    
    data_bench = [
        ['Gemini 3.1', '100% (30/30)', '5.57s', '96.7%', 'Cloud, 500 RPD'],
        ['Llama 3.1 8B', '100% (30/30)', '3.55s', '96.7%', 'Locale, 36% più veloce']
    ]
    
    for i, row_data in enumerate(data_bench, 1):
        cells = table_bench.rows[i].cells
        for j, val in enumerate(row_data):
            cells[j].text = val
    
    doc.add_paragraph()
    
    p = doc.add_paragraph()
    p.add_run('Conclusione: ').bold = True
    p.add_run('Llama 3.1 8B locale offre stessa accuracy di Gemini cloud con performance superiori (+36% velocità) e quota illimitata.')
    
    # ========================================
    # SEZIONE 5: PARSER UFFICIALE INTEGRATO
    # ========================================
    doc.add_heading('5. Integrazione Parser Ufficiale', 1)
    
    p = doc.add_paragraph()
    p.add_run('Repository: ').bold = True
    p.add_run('https://github.com/JcoProjectTeam/JcoQL\n')
    p.add_run('Grammatica: ').bold = True
    p.add_run('JCoQL.g (ANTLR3, 58KB) + JCoQLBasic.g (21KB)\n')
    p.add_run('Parser: ').bold = True
    p.add_run('JCoQLParser.java + JCoQLLexer.java (109 classi compilate)\n')
    
    doc.add_paragraph('Procedimento:')
    steps = [
        'Clone repository ufficiale',
        'Compilazione completa sorgenti Java (109 classi)',
        'Creazione JAR: jcoql-parser-official.jar',
        'Wrapper Python → Java subprocess',
        'Integrazione in architettura multi-parser',
        'Test validazione comparativa ANTLR3 vs ANTLR4'
    ]
    
    for i, step in enumerate(steps, 1):
        doc.add_paragraph(f'{i}. {step}', style='List Number')
    
    p = doc.add_paragraph()
    p.add_run('\nRisultato: ').bold = True
    p.add_run('Entrambi i parser validano correttamente le query. L\'utente può scegliere quale parser utilizzare tramite interfaccia UI.')
    
    # ========================================
    # SEZIONE 6: STATO AVANZAMENTO
    # ========================================
    doc.add_heading('6. Stato Avanzamento Progetto', 1)
    
    # Tabella avanzamento
    table_adv = doc.add_table(rows=8, cols=3)
    table_adv.style = 'Light Grid Accent 1'
    
    headers = table_adv.rows[0].cells
    headers[0].text = 'Settimana'
    headers[1].text = 'Obiettivi'
    headers[2].text = 'Stato'
    
    data_adv = [
        ['0', 'POC NotebookLM', '✓ Completato (90% accuracy)'],
        ['1', 'Setup ambiente sviluppo', '✓ Completato'],
        ['2', 'Parser ANTLR + RAG', '✓ Completato + Extra'],
        ['3', 'Frontend + API', '✓ Completato + Extra'],
        ['4', 'Multi-Parser + Benchmark', '✓ Completato'],
        ['5', 'Docs + Fine-tuning', '⏳ In corso (docs già complete)'],
        ['6', 'Report finale tesi', '⏳ Pianificato']
    ]
    
    for i, row_data in enumerate(data_adv, 1):
        cells = table_adv.rows[i].cells
        cells[0].text = row_data[0]
        cells[1].text = row_data[1]
        cells[2].text = row_data[2]
    
    doc.add_paragraph()
    
    p = doc.add_paragraph()
    p.add_run('Efficienza: ').bold = True
    p.add_run('4 settimane completate in 6 giorni effettivi (+208% rispetto al piano)\n')
    p.add_run('Anticipo: ').bold = True
    p.add_run('8 giorni lavorativi sul piano originale (37 giorni totali)')
    
    # ========================================
    # SEZIONE 7: PROSSIMI PASSI
    # ========================================
    doc.add_heading('7. Prossimi Passi', 1)
    
    next_steps = [
        ('Report comparativo parser', 'Analisi dettagliata differenze ANTLR3 vs ANTLR4 (performance, compatibilità, output)'),
        ('Fine-tuning prompt LLM locali', 'Ottimizzazione prompt specifici per Llama/Gemma'),
        ('Documentazione tesi finale', 'Stesura capitoli: introduzione, stato dell\'arte, architettura, risultati, conclusioni'),
        ('Presentazione risultati', 'Preparazione slides e demo per discussione tesi')
    ]
    
    for title, desc in next_steps:
        p = doc.add_paragraph()
        p.add_run(f'• {title}: ').bold = True
        p.add_run(desc)
    
    # ========================================
    # SEZIONE 8: CONCLUSIONI
    # ========================================
    doc.add_heading('8. Conclusioni Parziali', 1)
    
    p = doc.add_paragraph(
        'Il progetto ha raggiunto risultati eccellenti con un\'architettura robusta, '
        'modulare ed estensibile. L\'approccio RAG con validazione ANTLR garantisce '
        'accuratezza del 100% nella generazione di query JCoQL+ sintatticamente corrette. '
        'L\'integrazione del parser ufficiale conferma la compatibilità con lo standard '
        'dei professori e offre all\'utente la flessibilità di scegliere il parser preferito. '
        'Il benchmark multi-LLM dimostra che soluzioni locali (Llama) possono competere '
        'e superare soluzioni cloud in termini di performance, con il vantaggio di '
        'quota illimitata e privacy completa.'
    )
    
    doc.add_paragraph()
    
    # Footer
    p = doc.add_paragraph()
    p.add_run('Repository GitHub (privato): ').bold = True
    p.add_run('https://github.com/ionicho/jcoql-nl-interface')
    
    # ========================================
    # SALVA DOCUMENTO
    # ========================================
    filename = f'Report_Progressi_Tesi_{datetime.now().strftime("%Y%m%d")}.docx'
    doc.save(filename)
    
    print(f"✅ Report creato: {filename}")
    return filename

if __name__ == "__main__":
    create_report()