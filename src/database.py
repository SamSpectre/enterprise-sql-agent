"""
Database utilities for the SQL Agent.
Provides functions to query PostgreSQL and get schema information.
"""

from sqlalchemy import create_engine, text
from .config import DATABASE_URL, MAX_QUERY_ROWS

# Create engine once, reuse for all queries
engine = create_engine(DATABASE_URL)


def get_schema_info() -> str:
    """
    Get database schema information.
    This is what the AI agent reads to understand the data structure.
    """
    
    schema_query = """
    SELECT 
        column_name,
        data_type,
        col_description('taxi_trips'::regclass, ordinal_position) as description
    FROM information_schema.columns
    WHERE table_name = 'taxi_trips'
    ORDER BY ordinal_position
    """
    
    with engine.connect() as conn:
        # Get table comment
        result = conn.execute(text(
            "SELECT obj_description('taxi_trips'::regclass, 'pg_class')"
        ))
        table_comment = result.scalar()
        
        # Get column info
        result = conn.execute(text(schema_query))
        columns = result.fetchall()
    
    # Format for the LLM
    schema_text = f"TABLE: taxi_trips\nDESCRIPTION: {table_comment}\n\nCOLUMNS:\n"
    
    for col in columns:
        col_name, data_type, description = col
        desc_text = f" - {description}" if description else ""
        schema_text += f"  {col_name} ({data_type}){desc_text}\n"
    
    return schema_text


def execute_query(sql: str) -> str:
    """
    Execute a SQL query and return results as formatted string.
    This is the tool the AI agent calls to run queries.
    """
    
    # Basic safety check - only allow SELECT
    sql_upper = sql.strip().upper()
    if not sql_upper.startswith("SELECT"):
        return "ERROR: Only SELECT queries are allowed."
    
    # Block dangerous keywords
    dangerous = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE"]
    for keyword in dangerous:
        if keyword in sql_upper:
            return f"ERROR: {keyword} is not allowed."

    print(f"Executing query: {sql}")
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            rows = result.fetchmany(MAX_QUERY_ROWS)
            columns = result.keys()
            
            if not rows:
                return "Query returned no results."
            
            # Format as readable text
            output = f"Results ({len(rows)} rows):\n"
            output += "-" * 40 + "\n"
            
            for row in rows:
                row_dict = dict(zip(columns, row))
                for col, val in row_dict.items():
                    output += f"{col}: {val}\n"
                output += "-" * 40 + "\n"
            
            if len(rows) == MAX_QUERY_ROWS:
                output += f"(Limited to {MAX_QUERY_ROWS} rows)\n"
            
            return output
            
    except Exception as e:
        return f"ERROR: {str(e)}"


if __name__ == "__main__":
    # Test the functions
    print("=== SCHEMA INFO ===")
    print(get_schema_info())
    
    print("\n=== TEST QUERY ===")
    result = execute_query("SELECT COUNT(*) as total_trips FROM taxi_trips")
    print(result)