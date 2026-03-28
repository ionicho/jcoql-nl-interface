#!/usr/bin/env python3
"""
JCoQL Query Executor
Traduce query JCoQL in MongoDB e le esegue
"""
import re
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
from pymongo.errors import PyMongoError

class JCoQLExecutor:
    """Esecutore query JCoQL su MongoDB"""
    
    def __init__(self, mongo_uri: str = "mongodb://localhost:27017", database: str = "jcoql_test"):
        """
        Inizializza connessione MongoDB
        
        Args:
            mongo_uri: URI MongoDB
            database: Nome database
        """
        self.client = MongoClient(mongo_uri)
        self.db = self.client[database]
    
    def execute(self, jcoql_query: str) -> Dict[str, Any]:
        """
        Esegue query JCoQL su MongoDB
        
        Args:
            jcoql_query: Query JCoQL validata
            
        Returns:
            {
                'success': bool,
                'results': list,
                'count': int,
                'error': str (se success=False)
            }
        """
        try:
            # 1. Parse query JCoQL
            parsed = self._parse_jcoql(jcoql_query)
            
            # 2. Traduci in MongoDB query
            mongo_query = self._translate_to_mongodb(parsed)
            
            # 3. Esegui su MongoDB
            collection = self.db[parsed['collection']]
            results = list(collection.find(mongo_query['filter']))
            
            # 4. Converti ObjectId in string per JSON
            for doc in results:
                if '_id' in doc:
                    doc['_id'] = str(doc['_id'])
            
            return {
                'success': True,
                'results': results,
                'count': len(results),
                'mongo_query': mongo_query
            }
            
        except Exception as e:
            return {
                'success': False,
                'results': [],
                'count': 0,
                'error': str(e)
            }
    
    def _parse_jcoql(self, query: str) -> Dict[str, Any]:
        """
        Parse query JCoQL semplice
        
        Supporta:
        GET COLLECTION nome;
        FILTER CASE WHERE condizioni KEEP OTHERS;
        """
        query = query.strip()
        
        # Estrai collection
        collection_match = re.search(r'GET\s+COLLECTION\s+(\w+)', query, re.IGNORECASE)
        if not collection_match:
            raise ValueError("Query deve iniziare con GET COLLECTION")
        
        collection_name = collection_match.group(1)
        
        # Estrai WHERE clause (opzionale)
        where_match = re.search(r'WHERE\s+(.+?)\s+(?:KEEP|DROP)', query, re.IGNORECASE | re.DOTALL)
        
        where_clause = where_match.group(1).strip() if where_match else None
        
        return {
            'collection': collection_name,
            'where': where_clause
        }
    
    def _translate_to_mongodb(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Traduce parsed JCoQL in MongoDB query
        
        Args:
            parsed: Output di _parse_jcoql
            
        Returns:
            {'filter': {...}}
        """
        if not parsed['where']:
            # Nessun filtro: restituisci tutto
            return {'filter': {}}
        
        # Traduci WHERE clause
        mongo_filter = self._translate_where(parsed['where'])
        
        return {'filter': mongo_filter}
    
    def _translate_where(self, where_clause: str) -> Dict[str, Any]:
        """
        Traduce WHERE clause JCoQL in MongoDB filter
        
        Esempi:
        .city = 'Milano' → {'city': 'Milano'}
        .rating > 4.0 → {'rating': {'$gt': 4.0}}
        .city = 'Milano' AND .rating > 4.0 → {'$and': [...]}
        """
        
        # Rimuovi spazi extra
        where_clause = ' '.join(where_clause.split())
        
        # Gestisci AND
        if ' AND ' in where_clause.upper():
            parts = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)
            conditions = [self._translate_condition(p.strip()) for p in parts]
            return {'$and': conditions}
        
        # Gestisci OR
        if ' OR ' in where_clause.upper():
            parts = re.split(r'\s+OR\s+', where_clause, flags=re.IGNORECASE)
            conditions = [self._translate_condition(p.strip()) for p in parts]
            return {'$or': conditions}
        
        # Condizione singola
        return self._translate_condition(where_clause)
    
    def _translate_condition(self, condition: str) -> Dict[str, Any]:
        """
        Traduce singola condizione
        
        Esempi:
        .city = 'Milano' → {'city': 'Milano'}
        .rating > 4.0 → {'rating': {'$gt': 4.0}}
        .location.city = 'Roma' → {'location.city': 'Roma'}
        .price IN_RANGE [100, 200] → {'price': {'$gte': 100, '$lte': 200}}
        """
        
        # IN_RANGE
        range_match = re.match(r'\.(\S+)\s+IN_RANGE\s*\[\s*([^,]+)\s*,\s*([^\]]+)\s*\]', condition, re.IGNORECASE)
        if range_match:
            field = range_match.group(1)
            min_val = self._parse_value(range_match.group(2).strip())
            max_val = self._parse_value(range_match.group(3).strip())
            return {field: {'$gte': min_val, '$lte': max_val}}
        
        # Operatori confronto
        operators = {
            '>=': '$gte',
            '<=': '$lte',
            '>': '$gt',
            '<': '$lt',
            '!=': '$ne',
            '=': '$eq'
        }
        
        for op_str, op_mongo in operators.items():
            if f' {op_str} ' in condition:
                parts = condition.split(f' {op_str} ', 1)
                field = parts[0].strip().lstrip('.')
                value = self._parse_value(parts[1].strip())
                
                if op_mongo == '$eq':
                    return {field: value}
                else:
                    return {field: {op_mongo: value}}
        
        raise ValueError(f"Condizione non supportata: {condition}")
    
    def _parse_value(self, value_str: str) -> Any:
        """
        Parse valore da stringa
        
        Esempi:
        'Milano' → 'Milano'
        4.0 → 4.0
        true → True
        """
        value_str = value_str.strip()
        
        # Stringa (tra apici)
        if value_str.startswith("'") and value_str.endswith("'"):
            return value_str[1:-1]
        
        # Boolean
        if value_str.lower() == 'true':
            return True
        if value_str.lower() == 'false':
            return False
        
        # Numero float
        if '.' in value_str:
            try:
                return float(value_str)
            except:
                pass
        
        # Numero int
        try:
            return int(value_str)
        except:
            pass
        
        # Fallback: stringa
        return value_str
    
    def close(self):
        """Chiudi connessione MongoDB"""
        self.client.close()

# Test
if __name__ == "__main__":
    executor = JCoQLExecutor()
    
    # Test query
    queries = [
        "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Milano' KEEP OTHERS;",
        "GET COLLECTION hotels; FILTER CASE WHERE .rating > 4.0 KEEP OTHERS;",
        "GET COLLECTION hotels; FILTER CASE WHERE .location.city = 'Milano' AND .rating > 4.0 KEEP OTHERS;",
        "GET COLLECTION products; FILTER CASE WHERE .price IN_RANGE [100, 500] KEEP OTHERS;"
    ]
    
    for query in queries:
        print(f"\n{'='*70}")
        print(f"JCoQL: {query[:60]}...")
        result = executor.execute(query)
        print(f"Success: {result['success']}")
        print(f"Count: {result['count']}")
        if result['success'] and result['count'] > 0:
            print(f"First result: {list(result['results'][0].keys())}")
    
    executor.close()