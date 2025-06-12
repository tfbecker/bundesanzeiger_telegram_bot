#!/usr/bin/env python3
"""
Test script to verify database path configuration works correctly
"""

import os
import sys
import sqlite3

# Add the parent directory to the Python path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'scripts'))

def test_database_setup():
    """Test that the database can be created and accessed"""
    
    # Set up database path like the MCP server does
    data_dir = os.path.join(project_root, "data")
    os.makedirs(data_dir, exist_ok=True)
    db_path = os.path.join(data_dir, "financial_cache.db")
    
    print(f"Project root: {project_root}")
    print(f"Data directory: {data_dir}")
    print(f"Database path: {db_path}")
    
    # Test SQLite connection
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"Database opened successfully")
            print(f"Found tables: {[table[0] for table in tables]}")
            
            # Test a simple query
            cursor.execute("SELECT COUNT(*) FROM financial_data")
            count = cursor.fetchone()[0]
            print(f"Records in financial_data: {count}")
            
        return True
    except Exception as e:
        print(f"Database error: {e}")
        return False

def test_bundesanzeiger_import():
    """Test that Bundesanzeiger can be imported and initialized"""
    
    try:
        # Set the database path environment variable
        data_dir = os.path.join(project_root, "data")
        db_path = os.path.join(data_dir, "financial_cache.db")
        os.environ['DB_PATH'] = db_path
        
        try:
            from scripts.bundesanzeiger import Bundesanzeiger
            print("Successfully imported Bundesanzeiger from scripts")
        except ImportError as e:
            print(f"Failed to import from scripts: {e}")
            try:
                from bundesanzeiger import Bundesanzeiger
                print("Successfully imported Bundesanzeiger directly")
            except ImportError as e2:
                print(f"Could not import Bundesanzeiger: {e2}")
                return False
        
        bundesanzeiger = Bundesanzeiger()
        print("Successfully initialized Bundesanzeiger instance")
        
        return True
    except Exception as e:
        print(f"Import/initialization error: {e}")
        return False

if __name__ == "__main__":
    print("Testing database setup...")
    db_success = test_database_setup()
    
    print("\nTesting Bundesanzeiger import...")
    import_success = test_bundesanzeiger_import()
    
    if db_success and import_success:
        print("\n✅ All tests passed! MCP server should work correctly.")
    else:
        print("\n❌ Some tests failed. Check the errors above.") 