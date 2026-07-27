import sqlite3

# Connect to database
connection = sqlite3.connect("emergency.db")
cursor = connection.cursor()


def search_contacts():
    print("\nEmergency Contact Search")
    print("-----------------------")

    keyword = input("Enter state, district, or agency: ")

    cursor.execute("""
    SELECT * FROM emergency_contacts
    WHERE state LIKE ?
    OR district LIKE ?
    OR agency LIKE ?
    """,
    (
        f"%{keyword}%",
        f"%{keyword}%",
        f"%{keyword}%"
    ))

    results = cursor.fetchall()

    if results:
        print("\nSearch Results:")
        for contact in results:
            print("-----------------------")
            print("State:", contact[1])
            print("District:", contact[2])
            print("Agency:", contact[3])
            print("Name:", contact[4])
            print("Phone:", contact[5])
    else:
        print("\nNo emergency contacts found.")


search_contacts()

connection.close()
