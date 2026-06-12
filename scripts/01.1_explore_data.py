"""
Explore the NYC Taxi data before loading into database.
Always inspect data before loading - you need to understand its structure.
"""

import polars as pl
from pathlib import Path

# Find our downloaded file
DATA_FILE = Path(__file__).parent.parent.parent / "data" / "raw" / "yellow_tripdata_2024_01.parquet"

print(f"Reading: {DATA_FILE}")
print("=" * 50)

# Read the parquet file
df = pl.read_parquet(DATA_FILE)

# Basic info
print(f"\nRows: {len(df):,}")
print(f"Columns: {len(df.columns)}")

# Show column names and types
print("\n--- COLUMNS AND TYPES ---")
for col in df.schema:
    print(f"  {col}: {df.schema[col]}")

# Show first few rows
print("\n--- SAMPLE DATA (first 5 rows) ---")
print(df.head())

# Basic statistics
print("\n--- QUICK STATS ---")
print(f"Date range: {df['tpep_pickup_datetime'].min()} to {df['tpep_pickup_datetime'].max()}")
print(f"Avg fare: ${df['fare_amount'].mean():.2f}")
print(f"Avg trip distance: {df['trip_distance'].mean():.2f} miles")