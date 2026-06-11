import sqlite3
import requests

conn = sqlite3.connect('peixun.db')
c = conn.cursor()
c.execute("SELECT id, role, username FROM users WHERE role = 'admin' LIMIT 1")
row = c.fetchone()
conn.close()

if not row:
    print("NO ADMIN USER")
    exit()

token = f"{row[0]}:{row[1]}:{row[2]}"
print(f"Token: {token}")

r = requests.get('http://localhost:8000/api/admin/restore_records', headers={'Authorization': token})
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:3000]}")
