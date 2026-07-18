import os
import sys
import cv2
import numpy as np
import traceback
from .celery_app import celery_app
from .utils import load_image_from_path
from .preprocess import resize_image_max_edge, preprocess_image, get_strategy_b, get_strategy_c
from .detector import detect_idcard_corners
from .warp import perspective_warp
from .ocr_fusion import run_multi_strategy_ocr
from .config import TEMP_IDS_DIR

@celery_app.task(bind=True, time_limit=30) # 稳定性硬性超时控制（首次冷启动需加载模型，预留30秒）
def ocr_idcard_task(self, image_path: str):
    """
    Celery 异步处理身份证 OCR 任务的核心流程 (Step 1 ~ Step 8)
    """
    task_id = self.request.id
    
    if not os.path.exists(image_path):
        return {
            "status": "failed",
            "error": "Image file not found"
        }
        
    try:
        img_bgr = load_image_from_path(image_path)
        if img_bgr is None or img_bgr.size == 0:
            raise ValueError("Failed to load/decode image.")
        # 2. 图像预缩放以控制内存 (最长边 <= 1024)
        img_bgr = resize_image_max_edge(img_bgr, 1024)
        
        # 2.5 竖图检测：若图片是竖屏的（w < h），先旋转 90 度为横屏，防止后续裁剪和透视变换严重拉伸变形
        h_orig, w_orig = img_bgr.shape[:2]
        if w_orig < h_orig:
            img_bgr = cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE)
        
        # 3. 优先使用 document-preprocessor 进行旋转与裁切（灰度预处理延迟到 contour 回退时才计算）
        warped_bgr = None
        used_preprocessor = False
        
        try:
            from document_preprocessor import DocumentPreprocessor
            import PIL.Image
            
            print("[Detector] Running document-preprocessor...")
            preprocessor = DocumentPreprocessor()
            pil_img = PIL.Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
            pil_warped = preprocessor.detect_and_warp_document(pil_img)
            
            # 如果返回的图像不是原始图像，说明成功识别并裁切了文档
            if pil_warped is not pil_img:
                warped_bgr = cv2.cvtColor(np.array(pil_warped), cv2.COLOR_RGB2BGR)
                
                # 如果裁切出来的卡面是竖屏状态，先旋转90度成横屏，再进行缩放，防止图像被强行拉伸变形
                h_w, w_w = warped_bgr.shape[:2]
                if h_w > w_w:
                    warped_bgr = cv2.rotate(warped_bgr, cv2.ROTATE_90_CLOCKWISE)
                    
                # 调整到标准的 856x540 比例
                warped_bgr = cv2.resize(warped_bgr, (856, 540))
                used_preprocessor = True
                print("[Detector] document-preprocessor successfully cropped the document.")
        except Exception as e:
            print(f"[Detector] document-preprocessor failed: {e}")
            
        # 5. 失败后，优先尝试基于 OCR 文字框进行精确锚点定位与裁切
        if not used_preprocessor:
            print("[Detector] document-preprocessor failed. Trying OCR-box-guided crop...")
            try:
                _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if _project_root not in sys.path:
                    sys.path.insert(0, _project_root)
                from app.ocr import get_ocr_engine
                from ocr_handler import _crop_by_ocr_boxes
                engine = get_ocr_engine()
                ocr_res, _ = engine(img_bgr)
                ocr_cropped = _crop_by_ocr_boxes(img_bgr, ocr_res)
                if ocr_cropped is not None and ocr_cropped.shape[:2] != img_bgr.shape[:2]:
                    # 检查是否是竖屏状态，如果是先旋转成横屏再缩放，防止拉伸变形
                    h_c, w_c = ocr_cropped.shape[:2]
                    if h_c > w_c:
                        ocr_cropped = cv2.rotate(ocr_cropped, cv2.ROTATE_90_CLOCKWISE)
                    warped_bgr = cv2.resize(ocr_cropped, (856, 540))
                    used_preprocessor = True
                    print("[Detector] OCR-box-guided crop successfully cropped the document.")
            except Exception as e:
                print(f"[Detector] OCR-box-guided crop failed: {e}")

        # 5.5 如果依然失败，由 OpenCV 接手经典 Contour 旋转裁切
        if not used_preprocessor:
            print("[Detector] OCR-box-guided crop failed or not applicable. Falling back to OpenCV contours.")
            img_gray = preprocess_image(img_bgr)  # 仅在 contour 回退时才做灰度预处理
            corners = detect_idcard_corners(img_gray)
            warped_bgr = perspective_warp(img_bgr, corners)
            
            # 旋转规整检查，防止竖向卡面被拉扁
            h_w, w_w = warped_bgr.shape[:2]
            if h_w > w_w:
                warped_bgr = cv2.rotate(warped_bgr, cv2.ROTATE_90_CLOCKWISE)
            warped_bgr = cv2.resize(warped_bgr, (856, 540))
        
        # 5.6 方向与旋转矫正 (确保图片为横向且正向，以便进行不带方向参数的 OCR 识别)
        from .orient import orient_card_result
        warped_bgr = orient_card_result(warped_bgr)
        
        # 6. 生成多策略图片三个版本
        # version_a: 基础预处理
        warped_a = preprocess_image(warped_bgr)
        # version_b: 基础预处理 + 锐化
        warped_b = get_strategy_b(warped_a)
        # version_c: 基础预处理 + 对比度拉伸
        warped_c = get_strategy_c(warped_a)
        
        # 7. 运行三图 OCR 并进行多策略融合评分与字段融合决策
        fused_result = run_multi_strategy_ocr(warped_a, warped_b, warped_c)
        
        # 8. 保存扭正裁切后的身份证照片供后续持久化，返回其相对路径
        cropped_filename = f"crop_{task_id}.jpg"
        cropped_path = os.path.join(TEMP_IDS_DIR, cropped_filename).replace('\\', '/')
        cv2.imencode('.jpg', warped_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])[1].tofile(cropped_path)
        
        fused_result["temp_id_card_img"] = cropped_path
        
        # 统一输出格式，添加 id_card 字段以适配前端读取要求
        if "id_number" in fused_result:
            fused_result["id_card"] = fused_result["id_number"]
        
        # 9. 清理上传的原始临时图片
        if os.path.exists(image_path):
            try: os.remove(image_path)
            except: pass
            
        return fused_result
        
    except Exception as e:
        print(f"[Celery-Task-Error] Exception during OCR task: {e}")
        traceback.print_exc()
        
        # 清理原始临时图片
        if os.path.exists(image_path):
            try: os.remove(image_path)
            except: pass
            
        raise e
