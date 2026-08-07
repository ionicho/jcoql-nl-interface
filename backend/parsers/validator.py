#!/usr/bin/env python3
"""
JCoQL 4.0 Validator using ANTLR Parser
Validates JCoQL+ query syntax
"""
import sys
from antlr4 import *
from antlr4.error.ErrorListener import ErrorListener
from .JCoQLLexer import JCoQLLexer
from .JCoQLParser import JCoQLParser


class JCoQLErrorListener(ErrorListener):
    """Custom error listener to capture syntax errors"""
    
    def __init__(self):
        super().__init__()
        self.errors = []
    
    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        error_msg = f"Syntax error at line {line}:{column} - {msg}"
        self.errors.append({
            'line': line,
            'column': column,
            'message': msg,
            'offending_symbol': str(offendingSymbol)
        })


def validate_jcoql_query(query_text):
    """
    Validate a JCoQL+ query using ANTLR parser

    Valida usando la grammatica ANTLR4 generata da JCoQL.g4 (JCoQLLexer/
    JCoQLParser in questa stessa cartella), un percorso di validazione
    completamente separato da java_parser_wrapper.py, che invece invoca
    il parser Java ufficiale (ANTLR3) in subprocess. Le due grammatiche
    sono state scritte/convertite indipendentemente, quindi su casi limite
    potrebbero non dare esattamente lo stesso verdetto di validità.
    
    Args:
        query_text (str): JCoQL+ query to validate
    
    Returns:
        dict: {
            'is_valid': bool,
            'errors': list,
            'parse_tree': str (if valid)
        }
    """
    # Create input stream
    input_stream = InputStream(query_text)
    
    # Lexer
    lexer = JCoQLLexer(input_stream)
    lexer.removeErrorListeners()
    lexer_error_listener = JCoQLErrorListener()
    lexer.addErrorListener(lexer_error_listener)
    
    # Token stream
    token_stream = CommonTokenStream(lexer)
    
    # Parser
    parser = JCoQLParser(token_stream)
    parser.removeErrorListeners()
    parser_error_listener = JCoQLErrorListener()
    parser.addErrorListener(parser_error_listener)
    
    # Parse
    try:
        tree = parser.start()
        
        # Check for errors
        all_errors = lexer_error_listener.errors + parser_error_listener.errors
        
        if all_errors or parser.getNumberOfSyntaxErrors() > 0:
            return {
                'is_valid': False,
                'errors': all_errors if all_errors else [{'message': 'Unknown syntax error'}],
                'query': query_text
            }
        else:
            return {
                'is_valid': True,
                'errors': [],
                'parse_tree': tree.toStringTree(recog=parser),
                'query': query_text
            }
    
    except Exception as e:
        return {
            'is_valid': False,
            'errors': [{'message': f"Parse exception: {str(e)}"}],
            'query': query_text
        }


# Test rapido
if __name__ == "__main__":
    # Test query
    test_queries = [
        "GET COLLECTION products;",
        "GET COLLECTION hotels; FILTER CASE WHERE .city = 'Milano' KEEP OTHERS;",
        "GET COLLECTION products; FILTER CASE WHERE .price IN_RANGE [ 100 , 200 ] KEEP OTHERS;",
    ]
    
    print("="*60)
    print("JCOQL 4.0 VALIDATOR - ANTLR PARSER TEST")
    print("="*60)
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n[{i}/{len(test_queries)}] Query: {query[:50]}...")
        result = validate_jcoql_query(query)
        
        if result['is_valid']:
            print("  ✅ VALID")
        else:
            print("  ❌ INVALID")
            for error in result['errors']:
                print(f"     {error['message']}")