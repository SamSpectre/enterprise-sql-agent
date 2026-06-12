"""
Verify the database setup is correct.
Run sample queries to confirm data is accessible.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# Connection
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
database = os.getenv("POSTGRES_DB")
user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")

connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
engine = create_engine(connection_string)

print("=" * 50)
print("Database Verification")
print("=" * 50)

with engine.connect() as conn:
    
    # 1. Row count
    result = conn.execute(text("SELECT COUNT(*) FROM taxi_trips"))
    count = result.scalar()
    print(f"\n1. Total rows: {count:,}")
    
    # 2. Date range
    result = conn.execute(text("""
        SELECT 
            MIN(pickup_datetime) as first_trip,
            MAX(pickup_datetime) as last_trip
        FROM taxi_trips
    """))
    row = result.fetchone()
    print(f"2. Date range: {row[0]} to {row[1]}")
    
    # 3. Sample query - Average fare by payment type
    print("\n3. Average fare by payment type:")
    result = conn.execute(text("""
        SELECT 
            payment_type,
            COUNT(*) as trips,
            ROUND(AVG(fare_amount)::numeric, 2) as avg_fare
        FROM taxi_trips
        GROUP BY payment_type
        ORDER BY trips DESC
    """))
    for row in result:
        payment_name = {1: "Credit Card", 2: "Cash", 3: "No Charge", 4: "Dispute"}.get(row[0], f"Unknown({row[0]})")
        print(f"   {payment_name}: {row[1]:,} trips, ${row[2]} avg fare")
    
    # 4. Busiest pickup locations
    print("\n4. Top 5 busiest pickup locations:")
    result = conn.execute(text("""
        SELECT pickup_location_id, COUNT(*) as trips
        FROM taxi_trips
        GROUP BY pickup_location_id
        ORDER BY trips DESC
        LIMIT 5
    """))
    for row in result:
        print(f"   Location {row[0]}: {row[1]:,} trips")
    
    # 5. Check table comments exist (important for AI agent)
    print("\n5. Table comments (for AI context):")
    result = conn.execute(text("""
        SELECT obj_description('taxi_trips'::regclass, 'pg_class')
    """))
    table_comment = result.scalar()
    print(f"   Table: {table_comment}")

print("\n" + "=" * 50)
print("Verification complete. Database ready for AI agent.")
print("=" * 50)

engine.dispose()