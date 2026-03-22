#!/usr/bin/env python3
"""
Aggiorna report con sezione MongoDB Schema
"""
from docx import Document
from datetime import datetime

def add_mongodb_section():
    """Aggiunge sezione MongoDB al report esistente"""
    
    # Apri report esistente
    filename = f'Report_Progressi_Tesi_{datetime.now().strftime("%Y%m%d")}.docx'
    doc = Document(filename)
    
    # Aggiungi nuova sezione DOPO "Integrazione Parser Ufficiale"
    doc.add_heading('6. Schema Database MongoDB', 1)
    
    p = doc.add_paragraph()
    p.add_run('DATABASE REALIZZATO:\n').bold = True
    p.add_run('Per garantire coerenza tra esempi JCoQL e dati reali, è stato creato uno schema MongoDB completo con 5 collection e 110 documenti sample.\n\n')
    
    doc.add_heading('6.1 Collections', 2)
    
    # Tabella collections
    table = doc.add_table(rows=6, cols=4)
    table.style = 'Light Grid Accent 1'
    
    headers = table.rows[0].cells
    headers[0].text = 'Collection'
    headers[1].text = 'Documenti'
    headers[2].text = 'Campi Principali'
    headers[3].text = 'Descrizione'
    
    data = [
        ['hotels', '20', 'location.city, rating, price_per_night, stars', 'Strutture ricettive italiane'],
        ['products', '30', 'category, price, stock, discount, rating', 'Prodotti e-commerce'],
        ['users', '25', 'age, city, premium, active, orders', 'Utenti registrati'],
        ['orders', '20', 'total, status, items, priority', 'Ordini e-commerce'],
        ['restaurants', '15', 'city, cuisine, rating, price_range', 'Ristoranti']
    ]
    
    for i, row_data in enumerate(data, 1):
        cells = table.rows[i].cells
        for j, val in enumerate(row_data):
            cells[j].text = val
    
    doc.add_paragraph()
    
    doc.add_heading('6.2 Dataset Allineato', 2)
    
    p = doc.add_paragraph()
    p.add_run('PRIMA: ').bold = True
    p.add_run('99 esempi JCoQL generici (collection ipotetiche)\n')
    p.add_run('DOPO: ').bold = True
    p.add_run('89 esempi JCoQL allineati a schema reale (campi effettivi)\n')
    p.add_run('TOTALE: ').bold = True
    p.add_run('188 esempi validati al 100%\n\n')
    
    p.add_run('ESEMPI ALLINEAMENTO:\n').bold = True
    
    ex_table = doc.add_table(rows=3, cols=2)
    ex_table.style = 'Light Grid Accent 1'
    
    ex_headers = ex_table.rows[0].cells
    ex_headers[0].text = 'Prima (generico)'
    ex_headers[1].text = 'Dopo (schema-aligned)'
    
    ex_data = [
        ['WHERE .city = \'Milano\'', 'WHERE .location.city = \'Milano\''],
        ['WHERE .price < 100', 'WHERE .price_per_night < 150']
    ]
    
    for i, row_data in enumerate(ex_data, 1):
        cells = ex_table.rows[i].cells
        cells[0].text = row_data[0]
        cells[1].text = row_data[1]
    
    doc.add_paragraph()
    
    doc.add_heading('6.3 File Generati', 2)
    
    files = [
        'mongodb_schema.json - Schema formale delle collection',
        'data_hotels.json - 20 hotel campione',
        'data_products.json - 30 prodotti campione',
        'data_users.json - 25 utenti campione',
        'data_orders.json - 20 ordini campione',
        'data_restaurants.json - 15 ristoranti campione',
        'jcoql_examples_SCHEMA_ALIGNED.txt - 89 esempi allineati'
    ]
    
    for f in files:
        doc.add_paragraph(f'• {f}', style='List Bullet')
    
    doc.add_paragraph()
    
    doc.add_heading('6.4 Prossimi Step: Integrazione JCO Framework', 2)
    
    p = doc.add_paragraph()
    p.add_run('SITUAZIONE ATTUALE:\n').bold = True
    p.add_run('Il sistema genera query JCoQL+ sintatticamente corrette e validate, ma non le esegue su database reale.\n\n')
    
    p.add_run('INTEGRAZIONE PIANIFICATA:\n').bold = True
    
    steps = [
        'Installazione MongoDB locale con dati sample',
        'Setup JCO Framework (Java)',
        'Wrapper Python → JCO per esecuzione query',
        'Visualizzazione risultati JSON nel frontend',
        'Test end-to-end: NL → JCoQL → Esecuzione → Risultati'
    ]
    
    for step in steps:
        doc.add_paragraph(f'• {step}', style='List Bullet')
    
    # Rinumera sezioni successive
    # (manualmente: 7. Stato Avanzamento, 8. Prossimi Passi, 9. Conclusioni)
    
    # Salva
    doc.save(filename)
    print(f"✅ Report aggiornato con sezione MongoDB: {filename}")

if __name__ == "__main__":
    add_mongodb_section()