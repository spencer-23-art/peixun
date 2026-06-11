import requests
import sys
sys.stdout.reconfigure(encoding='utf-8')

r = requests.get('http://localhost:8000/admin')
html = r.text

checks = [
    ("switchAdminTab function", "function switchAdminTab(tab)"),
    ("pending branch complete", "classList.add('active');\n        if (btnExcel) btnExcel.style.display = 'none';\n        if (btnGate) btnGate.style.display = 'none';\n        if (btnRestore) btnRestore.style.display = 'none';\n        loadPendingUsers();"),
    ("restore branch complete", "loadRestoreRecords();"),
    ("loadRestoreRecords", "async function loadRestoreRecords"),
    ("renderRestoreRecords", "function renderRestoreRecords"),
    ("selectedRestoreRecordsMap", "selectedRestoreRecordsMap = new Map"),
    ("restore-tbody", 'id="restore-tbody"'),
]

print("=== Admin HTML Checks ===")
for name, pattern in checks:
    found = pattern in html
    print(f"[{'OK' if found else 'FAIL'}] {name}")

# Check for broken code
broken1 = "admin-content-pending').cl    //"
broken2 = "${escapeHtml(r.company"
print(f"\n[{'FAIL' if broken1 in html else 'OK'}] No broken switchAdminTab")
print(f"[{'FAIL' if broken2 in html else 'OK'}] No stale template literals")

# Extract and print the switchAdminTab function
start = html.find("function switchAdminTab(tab)")
if start >= 0:
    snippet = html[start:start+800]
    print(f"\n=== switchAdminTab snippet ===")
    print(snippet)
