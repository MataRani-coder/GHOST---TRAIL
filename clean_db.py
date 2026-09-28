"""
Clean the tracker DB:
  - Remove all old Person_X generic entries
  - Keep only properly named identities (Ganesh, Lakshya, etc.)
  - Also wipe sighting_logs to start fresh
"""
import sqlite3

db_path = "tracker.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Show what's in there
rows = conn.execute("SELECT id, name FROM registered_identities").fetchall()
print("Before cleanup:")
for r in rows:
    print(f"  ID={r['id']}, name={r['name']}")

# Delete all generic Person_X entries
deleted = conn.execute(
    "DELETE FROM registered_identities WHERE name LIKE 'Person_%'"
).rowcount
conn.commit()
print(f"\nDeleted {deleted} generic Person_X entries.")

# Also clean sighting logs (they reference the old generic IDs)
n_sightings = conn.execute("SELECT COUNT(*) FROM sighting_logs").fetchone()[0]
conn.execute("DELETE FROM sighting_logs")
conn.commit()
print(f"Cleared {n_sightings} sighting log entries.")

# Show what remains
rows = conn.execute("SELECT id, name FROM registered_identities").fetchall()
print("\nAfter cleanup (registered identities):")
for r in rows:
    print(f"  ID={r['id']}, name={r['name']}")

conn.close()
print("\nDone! DB is clean.")
