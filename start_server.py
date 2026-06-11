import sys
import os

import uvicorn
print("启动服务中...")
uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

