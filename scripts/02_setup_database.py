"""
Setup the PostgreSQL database for NYC Taxi data.
Uses PostgreSQL COPY for fast bulk loading (production pattern).
"""

import os
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import polars as pl

load_dotenv()

# Database connection
host = os.getenv("POSTGRES_HOST")
port = os.getenv("POSTGRES_PORT")
database = os.getenv("POSTGRES_DB")
user = os.getenv("POSTGRES_USER")
password = os.getenv("POSTGRES_PASSWORD")

connection_string = f"postgresql://{user}:{password}@{host}:{port}/{database}"
engine = create_engine(connection_string)

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"
PARQUET_FILE = DATA_DIR / "yellow_tripdata_2024_01.parquet"
CSV_FILE = DATA_DIR / "yellow_tripdata_2024_01.csv"


def create_table():
    """Create the taxi_trips table with schema comments."""
    
    create_table_sql = """
    DROP TABLE IF EXISTS taxi_trips;

    CREATE TABLE taxi_trips (
        vendor_id INTEGER,
        pickup_datetime TIMESTAMP,
        dropoff_datetime TIMESTAMP,
        passenger_count INTEGER,
        trip_distance REAL,
        ratecode_id INTEGER,
        store_and_fwd_flag TEXT,
        pickup_location_id INTEGER,
        dropoff_location_id INTEGER,
        payment_type INTEGER,
        fare_amount REAL,
        extra REAL,
        mta_tax REAL,
        tip_amount REAL,
        tolls_amount REAL,
        improvement_surcharge REAL,
        total_amount REAL,
        congestion_surcharge REAL,
        airport_fee REAL
    );

    COMMENT ON TABLE taxi_trips IS 'NYC Yellow Taxi trip records from January 2024';
    COMMENT ON COLUMN taxi_trips.vendor_id IS 'TPEP provider: 1=Creative Mobile, 2=VeriFone';
    COMMENT ON COLUMN taxi_trips.pickup_datetime IS 'Date and time when meter was engaged';
    COMMENT ON COLUMN taxi_trips.dropoff_datetime IS 'Date and time when meter was disengaged';
    COMMENT ON COLUMN taxi_trips.passenger_count IS 'Number of passengers in the vehicle';
    COMMENT ON COLUMN taxi_trips.trip_distance IS 'Trip distance in miles';
    COMMENT ON COLUMN taxi_trips.ratecode_id IS 'Rate code: 1=Standard, 2=JFK, 3=Newark, 4=Nassau, 5=Negotiated, 6=Group';
    COMMENT ON COLUMN taxi_trips.payment_type IS 'Payment: 1=Credit card, 2=Cash, 3=No charge, 4=Dispute';
    COMMENT ON COLUMN taxi_trips.fare_amount IS 'Time-and-distance fare in USD';
    COMMENT ON COLUMN taxi_trips.tip_amount IS 'Tip amount (credit card payments only)';
    COMMENT ON COLUMN taxi_trips.total_amount IS 'Total amount charged to passenger';
    COMMENT ON COLUMN taxi_trips.pickup_location_id IS 'TLC Taxi Zone where trip started';
    COMMENT ON COLUMN taxi_trips.dropoff_location_id IS 'TLC Taxi Zone where trip ended';
    """

    print("Creating table schema...")
    
    with engine.connect() as conn:
        for statement in create_table_sql.split(';'):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
        conn.commit()
    
    print("Table created.")


def convert_to_csv():
    """Convert Parquet to CSV with correct column names."""
    
    if CSV_FILE.exists():
        print(f"CSV already exists: {CSV_FILE}")
        return
    
    print(f"Converting Parquet to CSV...")
    
    df = pl.read_parquet(PARQUET_FILE)
    
    # Rename columns to match table schema
    column_mapping = {
        "VendorID": "vendor_id",
        "tpep_pickup_datetime": "pickup_datetime",
        "tpep_dropoff_datetime": "dropoff_datetime",
        "passenger_count": "passenger_count",
        "trip_distance": "trip_distance",
        "RatecodeID": "ratecode_id",
        "store_and_fwd_flag": "store_and_fwd_flag",
        "PULocationID": "pickup_location_id",
        "DOLocationID": "dropoff_location_id",
        "payment_type": "payment_type",
        "fare_amount": "fare_amount",
        "extra": "extra",
        "mta_tax": "mta_tax",
        "tip_amount": "tip_amount",
        "tolls_amount": "tolls_amount",
        "improvement_surcharge": "improvement_surcharge",
        "total_amount": "total_amount",
        "congestion_surcharge": "congestion_surcharge",
        "Airport_fee": "airport_fee",
    }
    
    df = df.rename(column_mapping)
    df.write_csv(CSV_FILE)
    
    print(f"CSV created: {CSV_FILE}")
    print(f"Size: {CSV_FILE.stat().st_size / 1024 / 1024:.1f} MB")


def load_data():
    """Load CSV into PostgreSQL using COPY (fast bulk load)."""
    
    print(f"\nLoading data using PostgreSQL COPY...")
    
    # Get raw connection
    raw_conn = engine.raw_connection()
    
    try:
        cursor = raw_conn.cursor()
        
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            # Skip header row
            next(f)
            cursor.copy_from(
                f,
                'taxi_trips',
                sep=',',
                null=''
            )
        
        raw_conn.commit()
        cursor.close()
    finally:
        raw_conn.close()
    
    # Verify count
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM taxi_trips"))
        count = result.scalar()
        print(f"Loaded {count:,} rows")


def create_indexes():
    """Create indexes for faster queries."""
    
    print("\nCreating indexes...")
    
    indexes = [
        "CREATE INDEX idx_pickup_datetime ON taxi_trips(pickup_datetime)",
        "CREATE INDEX idx_pickup_location ON taxi_trips(pickup_location_id)",
        "CREATE INDEX idx_payment_type ON taxi_trips(payment_type)",
    ]
    
    with engine.connect() as conn:
        for idx_sql in indexes:
            idx_name = idx_sql.split("idx_")[1].split(" ")[0]
            print(f"  Creating {idx_name}...")
            conn.execute(text(idx_sql))
        conn.commit()
    
    print("Indexes created.")


if __name__ == "__main__":
    print("=" * 50)
    print("NYC Taxi Database Setup")
    print("=" * 50)
    
    create_table()
    convert_to_csv()
    load_data()
    create_indexes()
    
    print("\n" + "=" * 50)
    print("Setup complete!")
    print("Next: Run 03_verify_setup.py to validate")
    print("=" * 50)
    
    engine.dispose()