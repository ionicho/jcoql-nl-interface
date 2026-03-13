import sys
from antlr4 import *
from JCoQLLexer import JCoQLLexer
from JCoQLParser import JCoQLParser

def test_jcoql(query):
    # Trasforma la stringa in un flusso di caratteri
    input_stream = InputStream(query)
    
    # Inizializza Lexer e Parser
    lexer = JCoQLLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = JCoQLParser(stream)
    
    # Avvia il parsing dalla regola principale 'start'
    tree = parser.start()
    
    # Se non ci sono errori, stampa il successo
    if parser.getNumberOfSyntaxErrors() == 0:
        print("✅ Query valida! Il parser l'ha letta correttamente.")
        # Stampa l'albero sintattico (opzionale, utile per debug)
        print(tree.toStringTree(recog=parser))
    else:
        print(f"❌ Errore: Trovati {parser.getNumberOfSyntaxErrors()} errori di sintassi.")

if __name__ == '__main__':
    # Esempio di query JCoQL valida
    sample_query = "GET COLLECTION myData AT myDB;"
    test_jcoql(sample_query)