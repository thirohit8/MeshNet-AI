import sqlite3

# Connect to SQLite database
connection = sqlite3.connect("emergency.db")

# Create cursor
cursor = connection.cursor()

# Create emergency contacts table
cursor.execute("""
CREATE TABLE IF NOT EXISTS emergency_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state TEXT NOT NULL,
    district TEXT NOT NULL,
    agency TEXT NOT NULL,
    name TEXT,
    phone TEXT NOT NULL
)
""")

# Save changes
connection.commit()

print("Emergency contacts table created successfully!")

# Close connection
connection.close()
