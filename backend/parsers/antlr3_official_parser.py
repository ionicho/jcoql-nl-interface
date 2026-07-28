#!/usr/bin/env python3
"""
ANTLR3 Official Parser Wrapper
Parser ufficiale dei professori (JCoProjectTeam/JcoQL)
"""
import re
from typing import Tuple, List
from .parser_interface import ParserInterface, ValidationError
from .java_parser_wrapper import validate_with_java_parser

class ANTLR3OfficialParser(ParserInterface):
    """
    Parser ANTLR3 ufficiale (prof JCoProjectTeam)
    
    Usa JAR compilato dal repository ufficiale:
    https://github.com/JcoProjectTeam/JcoQL
    
    Wrapper Python → Java subprocess
    """
    
    def __init__(self):
        """Inizializza parser"""
        self.mode = "java"
        print("✅ ANTLR3 Official Parser attivo (Java subprocess)")
    
    def validate(self, query: str) -> Tuple[bool, List[ValidationError]]:
        """
        Valida query usando parser Java ufficiale
        
        Args:
            query: Query JCoQL da validare
            
        Returns:
            (is_valid, errors)
        """
        
        result = validate_with_java_parser(query)
        
        errors = []
        
        # Converti errori in ValidationError
        for err_msg in result.get('errors', []):
            # Parse formato: "1.\tSyntax Error 1 at [1, 1]: ..."
            # Estrai line e column (heuristic)
            line = 1
            column = 0
            
            # Prova estrarre da "at [line, col]"
            import re
            match = re.search(r'at \[(\d+), (\d+)\]', err_msg)
            if match:
                line = int(match.group(1))
                column = int(match.group(2))
            
            errors.append(ValidationError(
                line=line,
                column=column,
                message=err_msg
            ))
        
        return result['is_valid'], errors
    
    def get_parse_tree(self, query: str):
        """
        ANTLR3 non espone parse tree facilmente via subprocess
        Return None (non implementato)
        """
        return None
    
    @property
    def parser_name(self) -> str:
        return "ANTLR3 Official Parser (Prof JCoProjectTeam)"
    
    @property
    def parser_version(self) -> str:
        return "4.0.12b (ANTLR 3.4)"