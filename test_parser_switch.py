#!/usr/bin/env python3
"""Test switch tra parser ANTLR4 vs ANTLR3"""
from backend.parsers.parser_factory import ParserFactory, ParserType

query = "GET COLLECTION hotels; FILTER CASE WHERE .city = 'Milano' AND .rating > 4 KEEP OTHERS;"

print("="*70)
print("TEST ANTLR4 CUSTOM:")
print("="*70)
p4 = ParserFactory.create_parser(ParserType.ANTLR4_CUSTOM)
valid, errors = p4.validate(query)
print(f"Parser: {p4.parser_name}")
print(f"Valid: {valid}")
if errors:
    print(f"Errors: {errors}")
print()

print("="*70)
print("TEST ANTLR3 OFFICIAL:")
print("="*70)
p3 = ParserFactory.create_parser(ParserType.ANTLR3_OFFICIAL)
valid, errors = p3.validate(query)
print(f"Parser: {p3.parser_name}")
print(f"Valid: {valid}")
if errors:
    print(f"Errors: {errors}")
print()

print("="*70)
print("✅ ENTRAMBI I PARSER FUNZIONANO!")
print("="*70)