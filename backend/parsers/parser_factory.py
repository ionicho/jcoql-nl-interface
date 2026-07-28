#!/usr/bin/env python3
"""
Parser Factory - Crea il parser richiesto
"""
from typing import List
from .parser_interface import ParserInterface, ParserType
from .antlr4_custom_parser import ANTLR4CustomParser
from .antlr3_official_parser import ANTLR3OfficialParser

class ParserFactory:
    """Factory per creare parser"""
    
    @staticmethod
    def create_parser(parser_type: ParserType) -> ParserInterface:
        """
        Crea parser del tipo specificato
        
        Args:
            parser_type: Tipo di parser
            
        Returns:
            Istanza del parser
            
        Raises:
            ValueError: Se tipo non supportato
        """
        if parser_type == ParserType.ANTLR4_CUSTOM:
            return ANTLR4CustomParser()
        
        elif parser_type == ParserType.ANTLR3_OFFICIAL:
            return ANTLR3OfficialParser()
        
        else:
            raise ValueError(f"Parser type {parser_type} not supported")
    
    @staticmethod
    def get_available_parsers() -> List[str]:
        """Lista parser disponibili"""
        return [p.value for p in ParserType]