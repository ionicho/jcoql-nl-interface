#!/usr/bin/env python3
"""
ANTLR4 Custom Parser Wrapper
Parser convertito da ANTLR3 a ANTLR4
"""
from typing import Tuple, List
from .parser_interface import ParserInterface, ValidationError
from .validator import validate_jcoql_query  # tuo validator attuale

class ANTLR4CustomParser(ParserInterface):
    """Parser ANTLR4 custom (convertito)"""
    
    def validate(self, query: str) -> Tuple[bool, List[ValidationError]]:
        """Valida con parser ANTLR4 custom"""
        result = validate_jcoql_query(query)
        
        # Converti errori in formato standard
        errors = []
        if not result['is_valid']:
            for err in result.get('errors', []):
                errors.append(ValidationError(
                    line=err.get('line', 0),
                    column=err.get('column', 0),
                    message=err.get('message', 'Unknown error')
                ))
        
        return result['is_valid'], errors
    
    def get_parse_tree(self, query: str) -> str:
        """
        Restituisce parse tree

        Richiama validate_jcoql_query() una seconda volta (già chiamata
        dentro validate()) — se validate() e get_parse_tree() vengono
        invocati in sequenza sulla stessa query, il parsing avviene due
        volte invece di una.
        """
        result = validate_jcoql_query(query)
        return result.get('parse_tree', '')
    
    @property
    def parser_name(self) -> str:
        return "ANTLR4 Custom Parser"
    
    @property
    def parser_version(self) -> str:
        return "4.9.3 (Converted from ANTLR3)"