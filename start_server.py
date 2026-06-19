"""本地开发启动入口。

main.py 末尾已自带相同的 uvicorn 启动逻辑，这里仅作转发，
保留 `python start_server.py` 这一既有启动命令，避免维护两份入口。
"""
if __name__ == '__main__':
    print("启动服务中...")
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
