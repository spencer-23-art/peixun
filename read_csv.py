import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Try different encodings
for enc in ['utf-8-sig', 'gb2312', 'gbk', 'gb18030', 'utf-16']:
    try:
        with open('06.03.csv', 'r', encoding=enc) as f:
            content = f.read()
        print(f"=== Encoding: {enc} ===")
        print(content[:2000])
        print()
        break
    except Exception as e:
        print(f"{enc}: {e}")
