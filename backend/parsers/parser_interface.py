#!/usr/bin/env python3
"""
Parser Interface - Abstract Base Class
Permette di switchare tra diversi parser JCoQL
"""
from abc import ABC, abstractmethod
from typing import Tuple, List, Dict
from enum import Enum

class ParserType(Enum):
    ANTLR4_CUSTOM = "antlr4_custom"
    ANTLR3_OFFICIAL = "antlr3_official"
    # Futuri parser
    # ANTLR4_OFFICIAL = "antlr4_official"
    # TREE_SITTER = "tree_sitter"

class ValidationError:
    def __init__(self, line: int, column: int, message: str):
        self.line = line
        self.column = column
        self.message = message
    
    def to_dict(self) -> Dict:
        return {
            'line': self.line,
            'column': self.column,
            'message': self.message
        }

class ParserInterface(ABC):
    """Abstract base class per parser JCoQL"""
    
    @abstractmethod
    def validate(self, query: str) -> Tuple[bool, List[ValidationError]]:
        """
        Valida query JCoQL
        
        Args:
            query: Query JCoQL da validare
            
        Returns:
            (is_valid, errors)
        """
        pass
    
    @abstractmethod
    def get_parse_tree(self, query: str) -> str:
        """
        Restituisce parse tree (opzionale, per debug)
        
        Args:
            query: Query JCoQL
            
        Returns:
            Parse tree come stringa
        """
        pass
    
    @property
    @abstractmethod
    def parser_name(self) -> str:
        """Nome del parser"""
        pass
    
    @property
    @abstractmethod
    def parser_version(self) -> str:
        """Versione del parser"""
        pass