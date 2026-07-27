import sqlite3
import json

# Connect to database
connection = sqlite3.connect("emergency.db")
cursor = connection.cursor()

# Open JSON file
with open("sample_data.json", "r") as file:
    emergency_data = json.load(file)

# Insert emergency contacts
for contact in emergency_data:
    cursor.execute("""
    INSERT INTO emergency_contacts
    (state, district, agency, name, phone)
    VALUES (?, ?, ?, ?, ?)
    """,
    (
        contact["state"],
        contact["district"],
        contact["agency"],
        contact["name"],
        contact["phone"]
    ))

# Save changes
connection.commit()

print("Emergency data imported successfully!")

# Close connection
connection.close()
