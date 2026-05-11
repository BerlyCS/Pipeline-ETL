import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# ---------------------------- CONEXIÓN ----------------------------
DB_USER = 'postgres'
DB_PASS = 'alexalex'
DB_HOST = 'localhost'
DB_PORT = '5432'
DB_NAME = 'datawarehouse'
engine = create_engine(f'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}')

# ---------------------------- 1. EXTRACCIÓN ----------------------------
catalog = pd.read_csv('Catalog_Orders.txt', sep=',', quotechar='"')

columnas_web = ['ID', 'INV', 'PCODE', 'DATE', 'CATALOG', 'QTY', 'custnum']
web = pd.read_csv('Web_orders.txt', sep=';', header=None,
                  names=columnas_web, skiprows=1, quotechar='"')
web = web[['ID', 'INV', 'DATE', 'CATALOG', 'PCODE', 'QTY', 'custnum']]

products = pd.read_csv('products.txt', sep=',', quotechar='"')

# ---------------------------- 2. TRANSFORMACIÓN ----------------------------

# 2.1 Parseo de fechas
catalog['DATE'] = pd.to_datetime(catalog['DATE'], format='%m/%y/%d %H:%M:%S', errors='coerce')
web['DATE']     = pd.to_datetime(web['DATE'],     format='%d/%m/%Y %H:%M:%S', errors='coerce')
catalog = catalog.dropna(subset=['DATE'])
web     = web.dropna(subset=['DATE'])

# 2.2 Normalizar CATALOG
catalog_map = {
    'sports': 'Sports', 'sport': 'Sports', 'sporst': 'Sports', 'spots': 'Sports',
    'toys': 'Toys', 'toy': 'Toys', 'tosy': 'Toys', 'tots': 'Toys',
    'gardening': 'Gardening', 'gardning': 'Gardening', 'garden': 'Gardening',
    'gardenings': 'Gardening',
    'pets': 'Pets', 'pet': 'Pets', 'pest': 'Pets', 'pats': 'Pets', 'prts': 'Pets',
    'software': 'Software', 'softwar': 'Software', 'softwars': 'Software',
    'softwares': 'Software',
    'collectibles': 'Collectibles', 'collectible': 'Collectibles',
    'collectable': 'Collectibles', 'colectibles': 'Collectibles',
    'collectables': 'Collectibles',
    ' ,ty4400"': 'Toys',
}

def normalizar_catalogo(valor):
    if not isinstance(valor, str):
        return 'Desconocido'
    limpio = valor.strip().lower().replace('"', '')
    return catalog_map.get(limpio, limpio.capitalize())

catalog['CATALOG'] = catalog['CATALOG'].apply(normalizar_catalogo)
web['CATALOG']     = web['CATALOG'].apply(normalizar_catalogo)

# 2.3 Limpieza de PCODE
def limpiar_pcode(raw):
    if pd.isna(raw):
        return raw
    raw = raw.upper().strip()
    if len(raw) < 2:
        return raw
    prefix = raw[:2]
    if not prefix.isalpha():
        return raw
    resto = raw[2:]
    digitos = []
    for ch in resto:
        if ch.isdigit():
            digitos.append(ch)
        elif ch == 'O':
            digitos.append('0')
    num = ''.join(digitos)
    if len(num) < 3:
        return raw
    if len(num) < 4:
        num = num.zfill(4)
    return prefix + num

arreglos_manuales = {
    'CC220': 'CC2200', 'CC42OO': 'CC4200', 'CC43))': 'CC4300',
    'GD10!)': 'GD1001', 'GD10)!': 'GD1001', 'GD101O': 'GD1010',
    'GD110O': 'GD1100', 'GD11OO': 'GD1100', 'GD12))': 'GD1200',
    'GD12OO': 'GD1200', 'GD13OO': 'GD1300', 'GD15OO': 'GD1500',
    'GD16OO': 'GD1600',
    'PT14OO': 'PT1400', 'PT1OOO': 'PT1000', 'PT2OOO': 'PT2000',
    'SP13OO': 'SP1300', 'SP14OO': 'SP1400',
    'TY16OO': 'TY1600', 'TY17OO': 'TY1700', 'TY1900': 'TY1900',
    'TY19OO': 'TY1900', 'TY21OO': 'TY2100',
    '1.00': 'UNKNOWN',
    'C3200': 'CC3200'
}

catalog['PCODE_clean'] = catalog['PCODE'].apply(limpiar_pcode)
web['PCODE_clean']     = web['PCODE'].apply(limpiar_pcode)
catalog['PCODE_clean'] = catalog['PCODE_clean'].apply(lambda x: arreglos_manuales.get(x, x))
web['PCODE_clean']     = web['PCODE_clean'].apply(lambda x: arreglos_manuales.get(x, x))

products['PCODE'] = products['PCODE'].str.upper().str.strip()

# 2.4 QTY numérico y eliminar nulos
catalog['QTY'] = pd.to_numeric(catalog['QTY'], errors='coerce')
web['QTY']     = pd.to_numeric(web['QTY'], errors='coerce')
catalog = catalog.dropna(subset=['QTY'])
web     = web.dropna(subset=['QTY'])

# 2.5 Unificar cliente
catalog['cust_code'] = catalog['custnum'].apply(
    lambda x: str(int(x)) if pd.notna(x) else 'CAT_DESCONOCIDO')
web['cust_code'] = web['custnum'].astype(str).str.replace('"', '').str.strip()

# ---------------------------- 3. DIMENSIONES ----------------------------
# dim_date
all_dates = pd.concat([catalog['DATE'], web['DATE']]).dropna().unique()
dim_date = pd.DataFrame({'full_date': pd.to_datetime(all_dates)})
dim_date['date_id']   = dim_date['full_date'].dt.strftime('%Y%m%d').astype(int)
dim_date['year']      = dim_date['full_date'].dt.year
dim_date['month']     = dim_date['full_date'].dt.month
dim_date['day']       = dim_date['full_date'].dt.day
dim_date['quarter']   = dim_date['full_date'].dt.quarter
dim_date['day_of_week'] = dim_date['full_date'].dt.dayofweek

# dim_product
dim_product = products[['PCODE', 'TYPE', 'DESCRIP', 'PRICE', 'COST', 'supplier']].copy()
dim_product.columns = ['pcode', 'type', 'descrip', 'price', 'cost', 'supplier']
codigos_ordenes = set(catalog['PCODE_clean']).union(set(web['PCODE_clean']))
faltantes = codigos_ordenes - set(dim_product['pcode'])
if faltantes:
    faltantes_df = pd.DataFrame({'pcode': list(faltantes)})
    dim_product = pd.concat([dim_product, faltantes_df], ignore_index=True, sort=False)
dim_product.reset_index(drop=True, inplace=True)
dim_product.insert(0, 'product_id', range(1, len(dim_product)+1))

# dim_customer
todos_clientes = pd.concat([catalog['cust_code'], web['cust_code']]).unique()
dim_customer = pd.DataFrame({'customer_code': todos_clientes})
dim_customer.insert(0, 'customer_id', range(1, len(dim_customer)+1))

# ---------------------------- 4. TABLA DE HECHOS ----------------------------
date_map    = dim_date.set_index('full_date')['date_id'].to_dict()
product_map = dim_product.set_index('pcode')['product_id'].to_dict()
customer_map = dim_customer.set_index('customer_code')['customer_id'].to_dict()

def construir_hechos(df, fuente):
    df = df.copy()
    df['date_id']     = df['DATE'].map(date_map)
    df['product_id']  = df['PCODE_clean'].map(product_map)
    df['customer_id'] = df['cust_code'].map(customer_map)
    df = df.merge(dim_product[['product_id', 'price', 'cost']], on='product_id', how='left')
    df['source']       = fuente
    df['quantity']     = df['QTY']
    df['sales_amount'] = df['quantity'] * df['price']
    df['cost_amount']  = df['quantity'] * df['cost']
    df = df.dropna(subset=['date_id', 'product_id', 'customer_id'])
    return df[['date_id', 'product_id', 'customer_id', 'source', 'quantity', 'sales_amount', 'cost_amount']]

fact_cat  = construir_hechos(catalog, 'Catalog')
fact_web  = construir_hechos(web, 'Web')
fact_orders = pd.concat([fact_cat, fact_web], ignore_index=True)

# ---------------------------- 5. CARGA ----------------------------
with engine.connect() as conn:
    conn.execute(text("TRUNCATE fact_orders, dim_customer, dim_product, dim_date RESTART IDENTITY CASCADE;"))
    conn.commit()

dim_date.to_sql('dim_date', engine, if_exists='append', index=False)
dim_product.to_sql('dim_product', engine, if_exists='append', index=False)
dim_customer.to_sql('dim_customer', engine, if_exists='append', index=False)
fact_orders.to_sql('fact_orders', engine, if_exists='append', index=False, method='multi')

print("!!!!!!!!!!!!!!!!!!!!!!!!! Pipeline ETL completado con éxito.")