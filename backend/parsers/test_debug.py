from antlr4 import *
from JCoQLLexer import JCoQLLexer
from JCoQLParser import JCoQLParser

# Test ESEMPIO 14 - ESATTO dal file
query14 = """GET COLLECTION customers;
FILTER CASE 
    WHERE ( .city = 'Milano' OR .city = 'Roma' ) AND ( .premium = true )
KEEP OTHERS;"""

# Test ESEMPIO 20 (che FUNZIONA) per confronto
query20 = """GET COLLECTION customers;
FILTER CASE WHERE (.city = 'Milano' OR .city = 'Roma') 
  AND (.tier = 'Premium' OR .tier = 'Gold') 
  AND .active = true;"""

# Test semplificato
query_simple = """GET COLLECTION customers;
FILTER CASE WHERE .premium = true
KEEP OTHERS;"""

queries = [
    ("ESEMPIO 14 (fallisce)", query14),
    ("ESEMPIO 20 (funziona)", query20),
    ("Simple test", query_simple)
]

for name, query in queries:
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    print(f"Query:\n{query}\n")
    
    input_stream = InputStream(query)
    lexer = JCoQLLexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = JCoQLParser(stream)
    
    tree = parser.start()
    
    if parser.getNumberOfSyntaxErrors() == 0:
        print("✅ VALID")
    else:
        print(f"❌ INVALID - {parser.getNumberOfSyntaxErrors()} errors")