#!/usr/bin/env python3
"""
ANTLR3 Official Parser Wrapper
Parser ufficiale dei professori (Java)
"""
import subprocess
import json
from typing import Tuple, List
from pathlib import Path
from .parser_interface import ParserInterface, ValidationError

class ANTLR3OfficialParser(ParserInterface):
    """Parser ANTLR3 ufficiale (Java)"""
    
    def __init__(self, jar_path: str = None):
        """
        Args:
            jar_path: Path al JAR del parser ufficiale
        """
        self.jar_path = jar_path or self._find_jar()
        if not self.jar_path:
            raise FileNotFoundError("Parser JAR non trovato!")
    
    def _find_jar(self) -> str:
        """Cerca il JAR del parser"""
        # TODO: Implementa ricerca automatica
        # Per ora placeholder
        return "backend/parsers/jcoql-parser-official.jar"
    
    def validate(self, query: str) -> Tuple[bool, List[ValidationError]]:
        """
        Valida chiamando parser Java via subprocess
        
        Strategia:
        1. Scrive query in file temporaneo
        2. Chiama Java parser
        3. Legge risultato JSON
        """
        try:
            # Crea file temporaneo con query
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.jcoql', delete=False) as f:
                f.write(query)
                temp_file = f.name
            
            # Chiama parser Java
            result = subprocess.run(
                ['java', '-jar', self.jar_path, 'validate', temp_file],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Parse output JSON
            if result.returncode == 0:
                output = json.loads(result.stdout)
                errors = []
                
                if not output.get('valid', False):
                    for err in output.get('errors', []):
                        errors.append(ValidationError(
                            line=err.get('line', 0),
                            column=err.get('column', 0),
                            message=err.get('message', '')
                        ))
                
                return output.get('valid', False), errors
            else:
                # Errore nell'esecuzione
                return False, [ValidationError(0, 0, f"Parser error: {result.stderr}")]
                
        except subprocess.TimeoutExpired:
            return False, [ValidationError(0, 0, "Parser timeout")]
        except Exception as e:
            return False, [ValidationError(0, 0, f"Exception: {str(e)}")]
        finally:
            # Cleanup
            import os
            if 'temp_file' in locals():
                os.unlink(temp_file)
    
    def get_parse_tree(self, query: str) -> str:
        """Parse tree (non implementato per ora)"""
        return "Parse tree not available for ANTLR3 parser"
    
    @property
    def parser_name(self) -> str:
        return "ANTLR3 Official Parser (Java)"
    
    @property
    def parser_version(self) -> str:
        return "3.x (JCoProjectTeam)"
    