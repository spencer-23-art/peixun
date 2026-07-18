import os

_ocr_engine = None

def get_ocr_engine():
    """获取 OCR 引擎实例。

    D4: 复用 ocr_handler.init_ppocrv6() 的引擎初始化逻辑，消除重复代码。
    若 ocr_handler 不可用（如 Celery Worker 独立环境缺少完整依赖），
    自动降级为基本 RapidOCR 实例，确保功能不受影响。
    """
    global _ocr_engine
    if _ocr_engine is None:
        try:
            # 懒加载避免循环导入；复用 ocr_handler 已初始化的全局引擎
            from ocr_handler import init_ppocrv6
            _ocr_engine = init_ppocrv6()
        except Exception as e:
            print(f"[Warning] Failed to reuse ocr_handler engine, falling back to default: {e}")
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR(use_angle_cls=False)
    return _ocr_engine
