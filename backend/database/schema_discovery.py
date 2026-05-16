#!/usr/bin/env python3
"""
Schema Discovery Automatico da MongoDB
Simula comportamento MongoDB Compass
"""
from pymongo import MongoClient
from collections import defaultdict
import json

class MongoSchemaDiscoverer:
    def __init__(self, mongo_uri="mongodb://localhost:27017", database="jcoql_test"):
        self.client = MongoClient(mongo_uri)
        self.db = self.client[database]
    
    def discover_schema(self, sample_size=100):
        """
        Scopre schema di tutte le collections
        Analizza sample_size documenti per collection
        """
        schema = {}
        
        # Lista tutte le collections
        collections = self.db.list_collection_names()
        
        for collection_name in collections:
            print(f"Analyzing collection: {collection_name}")
            schema[collection_name] = self._analyze_collection(
                collection_name, 
                sample_size
            )
        
        return schema
    
    def _analyze_collection(self, collection_name, sample_size):
        """Analizza una singola collection"""
        collection = self.db[collection_name]
        
        # Conta documenti totali
        total_docs = collection.count_documents({})
        
        # Campiona documenti
        sample = list(collection.find().limit(sample_size))
        
        if not sample:
            return {
                "total_documents": 0,
                "fields": {}
            }
        
        # Analizza campi
        fields_info = defaultdict(lambda: {
            'types': set(),
            'count': 0,
            'examples': []
        })
        
        for doc in sample:
            self._extract_fields(doc, fields_info)
        
        # Converti in formato finale
        fields = {}
        for field_path, info in fields_info.items():
            fields[field_path] = {
                'types': list(info['types']),
                'frequency': info['count'] / len(sample),
                'examples': info['examples'][:3]  # Prime 3 esempi
            }
        
        return {
            "total_documents": total_docs,
            "sampled_documents": len(sample),
            "fields": fields
        }
    
    def _extract_fields(self, doc, fields_info, prefix=""):
        """Estrae tutti i campi da documento (inclusi nested)"""
        for key, value in doc.items():
            # Skip _id (MongoDB internal)
            if key == '_id':
                continue
            
            field_path = f"{prefix}.{key}" if prefix else key
            
            # Determina tipo
            value_type = self._get_type(value)
            
            fields_info[field_path]['types'].add(value_type)
            fields_info[field_path]['count'] += 1
            
            # Aggiungi esempio se non array/object
            if value_type not in ['array', 'object']:
                if len(fields_info[field_path]['examples']) < 3:
                    fields_info[field_path]['examples'].append(value)
            
            # Se object nested, ricorsione
            if isinstance(value, dict):
                self._extract_fields(value, fields_info, field_path)
            
            # Se array di objects, analizza primo elemento
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                self._extract_fields(value[0], fields_info, field_path)
    
    def _get_type(self, value):
        """Determina tipo MongoDB"""
        if isinstance(value, bool):
            return 'boolean'
        elif isinstance(value, int):
            return 'integer'
        elif isinstance(value, float):
            return 'number'
        elif isinstance(value, str):
            return 'string'
        elif isinstance(value, list):
            return 'array'
        elif isinstance(value, dict):
            return 'object'
        elif value is None:
            return 'null'
        else:
            return 'unknown'
    
    def format_for_llm(self, schema):
        """Formatta schema per prompt LLM"""
        formatted = []
        
        for collection, info in schema.items():
            formatted.append(f"\nCollection: {collection}")
            formatted.append(f"Documents: {info['total_documents']}")
            formatted.append("Fields:")
            
            for field, field_info in sorted(info['fields'].items()):
                types = ", ".join(field_info['types'])
                freq = field_info['frequency'] * 100
                examples = field_info.get('examples', [])
                
                line = f"  - {field}: {types}"
                
                if freq < 100:
                    line += f" ({freq:.0f}% present)"
                
                if examples:
                    examples_str = ", ".join([str(e)[:30] for e in examples[:2]])
                    line += f" (e.g., {examples_str})"
                
                formatted.append(line)
        
        return "\n".join(formatted)
    
    def save_schema(self, schema, filepath="backend/database/mongodb_schema_discovered.json"):
        """Salva schema su file"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(schema, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Schema saved to: {filepath}")
    
    def close(self):
        """Chiudi connessione"""
        self.client.close()


# TEST
if __name__ == "__main__":
    print("🔍 MongoDB Schema Discovery - like Compass!\n")
    
    discoverer = MongoSchemaDiscoverer()
    
    # Scopri schema
    print("Discovering schema from MongoDB...")
    schema = discoverer.discover_schema(sample_size=100)
    
    # Mostra schema formattato
    print("\n" + "="*60)
    print(discoverer.format_for_llm(schema))
    print("="*60)
    
    # Salva schema
    discoverer.save_schema(schema)
    
    discoverer.close()
    
    print("\n✅ Schema discovery complete!")