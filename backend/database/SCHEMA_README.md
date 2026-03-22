# Schema MongoDB - JCoQL+ Test Database

Database di test per validazione interfaccia NL → JCoQL+

---

## Collections

### 1. hotels (20 documenti)
Strutture ricettive italiane

**Campi principali:**
- `location.city`: Milano, Roma, Firenze, Venezia, Napoli, Torino, Bologna
- `rating`: 3.0 - 5.0
- `price_per_night`: 80 - 300 €
- `stars`: 3 - 5
- `parking`, `wifi`, `breakfast_included`: boolean

**Query esempio:**
```jcoql
GET COLLECTION hotels;
FILTER CASE WHERE .location.city = 'Milano' AND .rating > 4.0
KEEP OTHERS;
```

---

### 2. products (30 documenti)
Prodotti e-commerce

**Categorie:** electronics, clothing, books, food, sports

**Campi principali:**
- `category`: string
- `price`: 20 - 2000 €
- `stock`: 0 - 100
- `discount`: 0 - 30%
- `rating`: 3.0 - 5.0

**Query esempio:**
```jcoql
GET COLLECTION products;
FILTER CASE WHERE .category = 'electronics' AND .price < 500
KEEP OTHERS;
```

---

### 3. users (25 documenti)
Utenti registrati

**Campi principali:**
- `age`: 18 - 65
- `city`: Città italiane
- `premium`: boolean
- `active`: boolean
- `email_verified`: boolean

**Query esempio:**
```jcoql
GET COLLECTION users;
FILTER CASE WHERE .age >= 18 AND .premium = true
KEEP OTHERS;
```

---

### 4. orders (20 documenti)
Ordini e-commerce

**Status:** pending, confirmed, shipped, delivered, cancelled

**Campi principali:**
- `total`: 50 - 1000 €
- `status`: string
- `priority`: low, normal, high, urgent

**Query esempio:**
```jcoql
GET COLLECTION orders;
FILTER CASE WHERE .status = 'shipped' AND .total > 200
KEEP OTHERS;
```

---

### 5. restaurants (15 documenti)
Ristoranti

**Cucine:** Italian, Japanese, Chinese, French, Mexican

**Campi principali:**
- `city`: Città italiane
- `rating`: 3.5 - 5.0
- `price_range`: $, $$, $$$, $$$$
- `status`: open/closed

**Query esempio:**
```jcoql
GET COLLECTION restaurants;
FILTER CASE WHERE .city = 'Roma' AND .rating > 4.0
KEEP OTHERS;
```

---

## Statistiche

- **Totale documenti:** 110
- **Totale collection:** 5
- **Campi nested:** location, coordinates, items, reviews
- **Campi boolean:** 12
- **Range valori:** Realistici per contesto italiano

---

## Caricamento in MongoDB
```bash
mongoimport --db jcoql_test --collection hotels --file data_hotels.json --jsonArray
mongoimport --db jcoql_test --collection products --file data_products.json --jsonArray
mongoimport --db jcoql_test --collection users --file data_users.json --jsonArray
mongoimport --db jcoql_test --collection orders --file data_orders.json --jsonArray
mongoimport --db jcoql_test --collection restaurants --file data_restaurants.json --jsonArray
```