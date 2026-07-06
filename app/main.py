import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from celery.result import AsyncResult
from .celery_app import celery_app
from .tasks import ocr_idcard_task
from .config import TEMP_IDS_DIR

app = FastAPI(title="Redesigned ID Card OCR Service")

@app.post("/idcard/ocr")
async def submit_ocr_task(file: UploadFile = File(...)):
    """
    提交身份证 OCR 识别任务
    1. 保存文件至临时文件目录
    2. 投递任务至 Celery 队列进行异步计算
    3. 立即返回 task_id，保障接口秒级响应
    """
    # 验证文件类型
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.bmp']:
        raise HTTPException(status_code=400, detail="Unsupported image format. Allowed: jpg, jpeg, png, bmp")
        
    os.makedirs(TEMP_IDS_DIR, exist_ok=True)
    temp_filename = f"ocr_raw_{uuid.uuid4().hex}{ext}"
    temp_path = os.path.join(TEMP_IDS_DIR, temp_filename).replace('\\', '/')
    
    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
            
        # 投递异步任务到 Celery
        task = ocr_idcard_task.delay(temp_path)
        
        return {"task_id": task.id}
    except Exception as e:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except: pass
        raise HTTPException(status_code=500, detail=f"Failed to submit task: {str(e)}")

@app.get("/idcard/result/{task_id}")
async def get_ocr_result(task_id: str):
    """
    查询异步 OCR 处理结果
    返回状态: pending | success | failed
    """
    res = AsyncResult(task_id, app=celery_app)
    
    if res.status == 'SUCCESS':
        return {
            "status": "success",
            "data": res.result
        }
    elif res.status in ['PENDING', 'RECEIVED', 'STARTED', 'RETRY']:
        return {
            "status": "pending"
        }
    else:
        # FAILURE, REVOKED, etc.
        return {
            "status": "failed",
            "error": str(res.result) if res.result else "Unknown task execution failure"
        }
