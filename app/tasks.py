import os
import sys
import traceback

from .celery_app import celery_app


def _load_shared_ocr_handler():
    """让 Celery 和主服务始终复用同一套身份证裁切、方向判断和识别逻辑。"""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from ocr_handler import ocr_idcard_process

    return ocr_idcard_process


@celery_app.task(bind=True, time_limit=60)
def ocr_idcard_task(self, image_path: str):
    """异步处理身份证 OCR，并兼容前端使用的两种身份证号字段名。"""
    if not os.path.exists(image_path):
        return {
            "status": "failed",
            "error": "Image file not found",
        }

    try:
        ocr_idcard_process = _load_shared_ocr_handler()
        result = ocr_idcard_process(image_path)

        id_number = result.get("id_card") or result.get("id_number") or ""
        result["id_card"] = id_number
        result["id_number"] = id_number
        return result
    except Exception as exc:
        print(f"[Celery-Task-Error] 身份证 OCR 任务失败: {type(exc).__name__}")
        traceback.print_exc()
        raise
    finally:
        if os.path.exists(image_path):
            try:
                os.remove(image_path)
            except OSError:
                pass
