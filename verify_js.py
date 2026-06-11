import requests
import re

r = requests.get('http://localhost:8000/admin')
html = r.text
start = html.find('<script>')
end = html.find('</script>')
script = html[start+8:end]

# Find all function declarations
functions = re.findall(r'function\s+(\w+)', script)
print(f'Functions found ({len(functions)}):')
for f in functions:
    print(f'  - {f}')

# Check for obvious syntax issues  
# Check balanced braces
open_braces = script.count('{')
close_braces = script.count('}')
print(f'\nBrace balance: open={open_braces}, close={close_braces}, diff={open_braces - close_braces}')

# Check if switchAdminTab has all 3 branches
has_records = 'nav-records' in script and 'admin-content-records' in script
has_pending = 'nav-pending' in script and 'admin-content-pending' in script
has_restore = 'nav-restore' in script and 'admin-content-restore' in script
print(f'\nswitchAdminTab branches:')
print(f'  records: {has_records}')
print(f'  pending: {has_pending}')
print(f'  restore: {has_restore}')

# Check key variables
print(f'\nKey variables:')
print(f'  selectedRestoreRecordsMap: {"selectedRestoreRecordsMap" in script}')
print(f'  lastFilteredRestoreRecords: {"lastFilteredRestoreRecords" in script}')
print(f'  checkRestoreRecordsNotification: {"checkRestoreRecordsNotification" in script}')
