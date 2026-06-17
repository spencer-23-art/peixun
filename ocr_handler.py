import os
import re
import uuid
import shutil
import time
import datetime
import sqlite3
import cv2
import numpy as np
from PIL import Image, ImageOps
from pathlib import Path
from docx import Document
from docx.shared import Inches
from modelscope import snapshot_download
from rapidocr_onnxruntime import RapidOCR
from rapidocr_onnxruntime.utils import read_yaml, concat_model_path

# ================= 1. PP-OCRv6 Tiny 模型加载与 OCR 引擎 =================
OCR_ENGINE = None
OCR_ENGINE_NO_CLS = None
DB_PATH = 'peixun.db'
UPLOAD_DIR = 'uploads'
TEMP_IDS_DIR = os.path.join(UPLOAD_DIR, 'temp_ids')
CARDS_DIR = os.path.join(UPLOAD_DIR, 'cards')
IDCARD_SAVE_DIR = os.path.join(UPLOAD_DIR, 'idcards')

# 创建必要目录
os.makedirs(TEMP_IDS_DIR, exist_ok=True)
os.makedirs(CARDS_DIR, exist_ok=True)
os.makedirs(IDCARD_SAVE_DIR, exist_ok=True)

def init_ppocrv6():
    global OCR_ENGINE
    if OCR_ENGINE is not None:
        return OCR_ENGINE

    print("[Info] 正在加载并初始化 PP-OCRv6 Tiny 1.5m 模型...")
    try:
        # 自动下载/获取模型本地路径
        det_dir = snapshot_download('PaddlePaddle/PP-OCRv6_tiny_det_onnx')
        rec_dir = snapshot_download('PaddlePaddle/PP-OCRv6_tiny_rec_onnx')
        
        det_path = os.path.join(det_dir, 'inference.onnx')
        rec_path = os.path.join(rec_dir, 'inference.onnx')
        
        # 1. 自动从 inference.yml 中提取正确的 PP-OCRv6 字典并保存为 txt 字典文件
        import yaml
        yml_path = os.path.join(rec_dir, 'inference.yml')
        with open(yml_path, 'r', encoding='utf-8') as f:
            yml_content = yaml.safe_load(f)
        char_list = yml_content['PostProcess']['character_dict']
        
        dict_txt_path = os.path.join(UPLOAD_DIR, 'dict_ppocrv6.txt').replace('\\', '/')
        with open(dict_txt_path, 'w', encoding='utf-8') as df:
            for char in char_list:
                df.write(char + '\n')
        
        # 2. 构造自定义配置
        import rapidocr_onnxruntime
        root_dir = Path(rapidocr_onnxruntime.__file__).resolve().parent
        config = read_yaml(str(root_dir / 'config.yaml'))
        config = concat_model_path(config)
        
        config['Det']['model_path'] = det_path
        config['Rec']['model_path'] = rec_path
        config['Rec']['keys_path'] = dict_txt_path
        
        # 3. 初始化模块
        TextDetector = RapidOCR.init_module(config['Det']['module_name'], config['Det']['class_name'])
        text_detector = TextDetector(config['Det'])
        
        TextRecognizer = RapidOCR.init_module(config['Rec']['module_name'], config['Rec']['class_name'])
        text_recognizer = TextRecognizer(config['Rec'])
        
        TextClassifier = RapidOCR.init_module(config['Cls']['module_name'], config['Cls']['class_name'])
        text_cls = TextClassifier(config['Cls'])
        
        # 4. 封装成完整的 RapidOCR
        OCR_ENGINE = RapidOCR()
        OCR_ENGINE.text_detector = text_detector
        OCR_ENGINE.text_recognizer = text_recognizer
        OCR_ENGINE.text_cls = text_cls
        OCR_ENGINE.use_text_det = True
        OCR_ENGINE.use_angle_cls = True
        
        print("[Success] PP-OCRv6 Tiny ONNX 引擎加载成功！")
        return OCR_ENGINE
    except Exception as e:
        print(f"[Warning] 无法加载 PP-OCRv6，回退至默认 OCR 模型: {e}")
        OCR_ENGINE = RapidOCR()
        return OCR_ENGINE

def init_ppocrv6_no_cls():
    """初始化一个关闭 angle_cls 的 OCR 引擎，专用于方向检测"""
    global OCR_ENGINE_NO_CLS
    if OCR_ENGINE_NO_CLS is not None:
        return OCR_ENGINE_NO_CLS
    
    # 确保主引擎已加载（以便复用其初始化后的字典和流程）
    main_engine = init_ppocrv6()
    
    try:
        import rapidocr_onnxruntime
        root_dir = Path(rapidocr_onnxruntime.__file__).resolve().parent
        config = read_yaml(str(root_dir / 'config.yaml'))
        config = concat_model_path(config)
        
        # 复用主引擎的模型路径
        if hasattr(main_engine, 'text_detector') and hasattr(main_engine.text_detector, 'model_path'):
            config['Det']['model_path'] = main_engine.text_detector.model_path
        if hasattr(main_engine, 'text_recognizer') and hasattr(main_engine.text_recognizer, 'model_path'):
            config['Rec']['model_path'] = main_engine.text_recognizer.model_path
        if hasattr(main_engine, 'text_recognizer') and hasattr(main_engine.text_recognizer, 'keys_path'):
            config['Rec']['keys_path'] = main_engine.text_recognizer.keys_path
            
        OCR_ENGINE_NO_CLS = RapidOCR()
        if hasattr(main_engine, 'text_detector'):
            OCR_ENGINE_NO_CLS.text_detector = main_engine.text_detector
        if hasattr(main_engine, 'text_recognizer'):
            OCR_ENGINE_NO_CLS.text_recognizer = main_engine.text_recognizer
        if hasattr(main_engine, 'text_cls'):
            OCR_ENGINE_NO_CLS.text_cls = main_engine.text_cls
            
        OCR_ENGINE_NO_CLS.use_text_det = True
        OCR_ENGINE_NO_CLS.use_angle_cls = False # 关键：不使用角度分类器
        
        print("[Success] PP-OCRv6 No-CLS 引擎加载成功（用于方向判定）！")
        return OCR_ENGINE_NO_CLS
    except Exception as e:
        print(f"[Warning] 无法加载 PP-OCRv6 No-CLS，回退至默认 OCR 模型: {e}")
        OCR_ENGINE_NO_CLS = RapidOCR()
        OCR_ENGINE_NO_CLS.use_angle_cls = False
        return OCR_ENGINE_NO_CLS

# ================= 2. 图像裁剪核心算法 (移植自 run.py) =================
TARGET_ASPECT_RATIO = 3.37 / 2.13

def _order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def _expand_quad(quad, img_shape, scale_x=1.03, scale_y=1.05):
    if quad is None:
        return None
    pts = np.asarray(quad, dtype="float32")
    center = np.mean(pts, axis=0)
    expanded = pts.copy()
    expanded[:, 0] = center[0] + (expanded[:, 0] - center[0]) * scale_x
    expanded[:, 1] = center[1] + (expanded[:, 1] - center[1]) * scale_y
    h, w = img_shape[:2]
    expanded[:, 0] = np.clip(expanded[:, 0], 0, w - 1)
    expanded[:, 1] = np.clip(expanded[:, 1], 0, h - 1)
    return _order_points(expanded)

def _four_point_transform(image, pts):
    rect = _order_points(pts)
    (tl, tr, br, bl) = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))
    if max_width <= 0 or max_height <= 0:
        return None
    dst = np.array(
        [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
        dtype="float32",
    )
    m = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, m, (max_width, max_height), borderValue=(255, 255, 255))

def normalize_card_orientation(warped):
    if warped is None:
        return None
    h, w = warped.shape[:2]
    if h == 0 or w == 0:
        return warped
    if h > w:
        warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)
    return warped

def _scan_content_bound(signal, threshold, max_trim, forward=True, min_run=3):
    length = len(signal)
    if length == 0:
        return 0 if forward else -1
    start = 0 if forward else length - 1
    stop = min(max_trim, length - 1)
    step = 1 if forward else -1
    run = 0
    last_idx = start
    for offset in range(stop + 1):
        idx = start + offset * step
        if float(signal[idx]) >= threshold:
            run += 1
            if run >= min_run:
                return idx - (min_run - 1) * step
        else:
            run = 0
        last_idx = idx
    return last_idx

def trim_document_borders(img, max_trim_ratio=0.005):
    if img is None or img.size == 0:
        return img
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    h, w = gray.shape[:2]
    if h < 20 or w < 20:
        return img
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(grad_x, grad_y)
    band = max(3, int(min(h, w) * 0.02))
    bg_samples = np.concatenate([
        gray[:band, :].reshape(-1),
        gray[-band:, :].reshape(-1),
        gray[:, :band].reshape(-1),
        gray[:, -band:].reshape(-1),
    ])
    bg_level = float(np.median(bg_samples))
    diff = cv2.absdiff(gray, np.full_like(gray, int(round(bg_level))))
    col_signal = np.percentile(diff, 80, axis=0) + np.percentile(grad, 80, axis=0) * 0.6
    row_signal = np.percentile(diff, 80, axis=1) + np.percentile(grad, 80, axis=1) * 0.6
    col_threshold = max(float(np.median(col_signal) + np.std(col_signal) * 1.2), 8.0)
    row_threshold = max(float(np.median(row_signal) + np.std(row_signal) * 1.2), 8.0)
    max_trim_x = max(2, int(w * max_trim_ratio))
    max_trim_y = max(2, int(h * max_trim_ratio))
    left = _scan_content_bound(col_signal, col_threshold, max_trim_x, forward=True)
    right = _scan_content_bound(col_signal, col_threshold, max_trim_x, forward=False)
    top = _scan_content_bound(row_signal, row_threshold, max_trim_y, forward=True)
    bottom = _scan_content_bound(row_signal, row_threshold, max_trim_y, forward=False)
    if right - left < w * 0.5 or bottom - top < h * 0.5:
        return img
    if left <= 0 and top <= 0 and right >= w - 1 and bottom >= h - 1:
        return img
    return img[top:bottom + 1, left:right + 1]

def _estimate_content_bbox(img):
    if img is None or img.size == 0:
        return None
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    h, w = gray.shape[:2]
    if h < 20 or w < 20:
        return (0, 0, w - 1, h - 1)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    grad_x = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(grad_x, grad_y)
    bg_level = float(np.median(np.concatenate([
        blur[:3, :].reshape(-1),
        blur[-3:, :].reshape(-1),
        blur[:, :3].reshape(-1),
        blur[:, -3:].reshape(-1),
    ])))
    diff = cv2.absdiff(blur, np.full_like(blur, int(round(bg_level))))
    col_signal = np.percentile(diff, 80, axis=0) + np.percentile(grad, 80, axis=0) * 0.6
    row_signal = np.percentile(diff, 80, axis=1) + np.percentile(grad, 80, axis=1) * 0.6
    col_threshold = max(float(np.median(col_signal) + np.std(col_signal) * 0.8), 6.0)
    row_threshold = max(float(np.median(row_signal) + np.std(row_signal) * 0.8), 6.0)
    xs = np.where(col_signal >= col_threshold)[0]
    ys = np.where(row_signal >= row_threshold)[0]
    if len(xs) < 2 or len(ys) < 2:
        return None
    left = max(0, int(xs[0]))
    right = min(w - 1, int(xs[-1]))
    top = max(0, int(ys[0]))
    bottom = min(h - 1, int(ys[-1]))
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)

def _mean_region(mat, x1, y1, x2, y2):
    h, w = mat.shape[:2]
    x1 = max(0, min(w, int(round(x1))))
    x2 = max(0, min(w, int(round(x2))))
    y1 = max(0, min(h, int(round(y1))))
    y2 = max(0, min(h, int(round(y2))))
    if x2 <= x1 or y2 <= y1:
        return 0.0
    return float(np.mean(mat[y1:y2, x1:x2]))

def _score_id_front_layout(img):
    if img is None or img.size == 0 or len(img.shape) != 3:
        return 0.0
    h0, w0 = img.shape[:2]
    if h0 < 40 or w0 < 60:
        return 0.0
    work = img
    if max(h0, w0) > 640:
        scale = 640.0 / max(h0, w0)
        work = cv2.resize(img, None, fx=scale, fy=scale)
    h, w = work.shape[:2]
    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    s = hsv[:, :, 1].astype(np.float32) / 255.0
    dark = np.clip((185.0 - gray.astype(np.float32)) / 185.0, 0.0, 1.0)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    grad_x = cv2.Sobel(blur, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(blur, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(grad_x, grad_y)
    if grad.max() > 0:
        grad = np.clip(grad / max(float(np.percentile(grad, 95)), 1.0), 0.0, 1.0)
    photo_energy = s * 0.45 + dark * 0.35 + grad * 0.20
    text_energy = dark * 0.75 + grad * 0.25
    right_photo = _mean_region(photo_energy, w * 0.54, h * 0.18, w * 0.98, h * 0.90)
    left_photo = _mean_region(photo_energy, w * 0.02, h * 0.10, w * 0.46, h * 0.82)
    bottom_text = _mean_region(text_energy, w * 0.08, h * 0.62, w * 0.92, h * 0.96)
    top_text = _mean_region(text_energy, w * 0.08, h * 0.04, w * 0.92, h * 0.38)
    return (right_photo - left_photo) * 4200.0 + (bottom_text - top_text) * 2400.0

def _score_card_uprightness(img, is_special_cert=False):
    if img is None or img.size == 0:
        return -1e9
    bbox = _estimate_content_bbox(img)
    if bbox is None:
        return -1e9
    left, top, right, bottom = bbox
    h, w = img.shape[:2]
    bw = max(1, right - left + 1)
    bh = max(1, bottom - top + 1)
    area_ratio = (bw * bh) / max(float(h * w), 1.0)
    center_x = (left + right) / 2.0
    center_y = (top + bottom) / 2.0
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )
    mass = mask.astype(np.float32) / 255.0
    mid_y = h // 2
    mid_x = w // 2
    top_mass = float(np.sum(mass[:mid_y, :]))
    bottom_mass = float(np.sum(mass[mid_y:, :]))
    left_mass = float(np.sum(mass[:, :mid_x]))
    right_mass = float(np.sum(mass[:, mid_x:]))
    score = area_ratio * 1200.0
    if not is_special_cert:
        score += (bottom_mass - top_mass) / max(h * w, 1.0) * 1800.0
        score += (right_mass - left_mass) / max(h * w, 1.0) * 1200.0
        score += (center_y / max(h, 1.0)) * 380.0
        score += (center_x / max(w, 1.0)) * 220.0
        score += _score_id_front_layout(img)
    else:
        score += area_ratio * 400.0
    return score

def _orient_card_result(img, is_special_cert=False):
    if img is None or img.size == 0:
        return img
    h, w = img.shape[:2]
    if h > w:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if is_special_cert:
        return img
    score0 = _score_card_uprightness(img, is_special_cert=False)
    rot180 = cv2.rotate(img, cv2.ROTATE_180)
    score180 = _score_card_uprightness(rot180, is_special_cert=False)
    if score180 > score0 + 80:
        return rot180
    return img

def _orient_card_by_content_box(img, is_special_cert=False):
    if img is None or img.size == 0:
        return img
    if is_special_cert:
        return img
    bbox = _estimate_content_bbox(img)
    if bbox is None:
        return img
    left, top, right, bottom = bbox
    box_w = right - left + 1
    box_h = bottom - top + 1
    if box_h > box_w * 1.08:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    return img

def pad_image_to_ratio(img):
    h, w = img.shape[:2]
    current_ratio = w / h
    if 1.4 < current_ratio < 1.7:
        return img
    if current_ratio < TARGET_ASPECT_RATIO:
        new_w = int(h * TARGET_ASPECT_RATIO)
        pad = (new_w - w) // 2
        return cv2.copyMakeBorder(img, 0, 0, pad, pad, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    else:
        new_h = int(w / TARGET_ASPECT_RATIO)
        pad = (new_h - h) // 2
        return cv2.copyMakeBorder(img, pad, pad, 0, 0, cv2.BORDER_CONSTANT, value=[255, 255, 255])

def _find_best_card_quad(contours, img_area, min_area_ratio, max_area_ratio, min_ratio, max_ratio, target_ratio, strict_ratio=True):
    best = None
    best_score = 0.0
    for c in contours:
        area = cv2.contourArea(c)
        if area < img_area * min_area_ratio or area > img_area * max_area_ratio:
            continue
        hull = cv2.convexHull(c)
        peri = cv2.arcLength(hull, True)
        if peri == 0:
            continue
        approx = cv2.approxPolyDP(hull, 0.015 * peri, True)
        if len(approx) != 4:
            approx = cv2.approxPolyDP(hull, 0.03 * peri, True)
        use_min_rect = True
        if len(approx) == 4:
            candidate_approx = approx.reshape(4, 2)
            is_rect = True
            for i in range(4):
                pt1, pt2, pt3 = candidate_approx[i], candidate_approx[(i+1)%4], candidate_approx[(i+2)%4]
                v1, v2 = pt1 - pt2, pt3 - pt2
                cos_a = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-5)
                angle = np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0)))
                if abs(angle - 90) > 12:
                    is_rect = False
                    break
            if is_rect:
                candidate = candidate_approx
                use_min_rect = False
        if use_min_rect:
            min_rect = cv2.minAreaRect(hull)
            candidate = cv2.boxPoints(min_rect)
        rect = _order_points(candidate.astype("float32"))
        rw = np.linalg.norm(rect[1] - rect[0])
        rh = np.linalg.norm(rect[3] - rect[0])
        if rh <= 0 or rw <= 0:
            continue
        ratio = rw / rh if rw > rh else rh / rw
        if strict_ratio and (ratio < min_ratio or ratio > max_ratio):
            continue
        ratio_score = max(0.0, 1.0 - abs(ratio - target_ratio) / target_ratio)
        rect_area = rw * rh
        rectangularity = area / rect_area if rect_area > 0 else 0
        area_ratio = area / img_area
        score = ratio_score * 1000.0 + area_ratio * 600.0 + rectangularity * 300.0
        if score > best_score:
            best_score = score
            best = rect
    return best

def crop_by_card_contour(img, is_special_cert=False):
    if img is None or img.size == 0:
        return None
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    h, w = gray.shape[:2]
    img_area = h * w
    if img_area == 0:
        return None
    min_area_ratio = 0.05
    max_area_ratio = 0.99
    min_ratio, max_ratio = 1.35, 1.85

    best = None
    gray_b = cv2.bilateralFilter(gray, 11, 17, 17)
    for low, high in [(30, 200), (20, 100), (10, 50)]:
        edged = cv2.Canny(gray_b, low, high)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edged = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        best = _find_best_card_quad(
            contours, img_area, min_area_ratio, max_area_ratio, min_ratio, max_ratio, TARGET_ASPECT_RATIO, strict_ratio=True
        )
        if best is not None:
            break

    if best is None:
        for block_size in [51, 71, 91]:
            thresh = cv2.adaptiveThreshold(gray_b, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                          cv2.THRESH_BINARY_INV, block_size, 10)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=3)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            best = _find_best_card_quad(
                contours, img_area, min_area_ratio, max_area_ratio, min_ratio, max_ratio, TARGET_ASPECT_RATIO, strict_ratio=False
            )
            if best is not None:
                break

    if best is None:
        return None

    warped = _four_point_transform(img, best)
    if warped is None:
        return None
    warped = normalize_card_orientation(warped)
    return warped

def _detect_id_card_body_quad(img):
    if img is None or img.size == 0 or len(img.shape) != 3:
        return None
    h, w = img.shape[:2]
    img_area = float(h * w)
    if img_area <= 0:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]
    l = lab[:, :, 0]
    a = lab[:, :, 1]
    b = lab[:, :, 2]
    low_sat = cv2.inRange(s, 0, 120)
    bright = cv2.inRange(v, 90, 255)
    warm_a = cv2.inRange(a, 110, 165)
    warm_b = cv2.inRange(b, 110, 180)
    soft_l = cv2.inRange(l, 90, 250)
    mask = cv2.bitwise_and(low_sat, bright)
    mask = cv2.bitwise_and(mask, soft_l)
    warm_mask = cv2.bitwise_and(warm_a, warm_b)
    mask = cv2.bitwise_or(mask, warm_mask)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    edges = cv2.Canny(gray, 40, 140)
    edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
    mask = cv2.bitwise_or(mask, edges)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    quad = _find_best_card_quad(
        contours,
        img_area,
        min_area_ratio=0.08,
        max_area_ratio=0.95,
        min_ratio=1.35,
        max_ratio=1.90,
        target_ratio=TARGET_ASPECT_RATIO,
        strict_ratio=False,
    )
    if quad is None:
        return None
    rect = _order_points(np.asarray(quad, dtype="float32"))
    rw = np.linalg.norm(rect[1] - rect[0])
    rh = np.linalg.norm(rect[3] - rect[0])
    if rw <= 0 or rh <= 0:
        return None
    ratio = rw / rh if rw >= rh else rh / rw
    if abs(ratio - TARGET_ASPECT_RATIO) > 0.45:
        return None
    fill_ratio = _quad_polygon_area(rect) / img_area
    if fill_ratio < 0.08 or fill_ratio > 0.95:
        return None
    return rect

def _quad_polygon_area(quad):
    try:
        return float(abs(cv2.contourArea(np.asarray(quad, dtype="float32"))))
    except Exception:
        return 0.0

def _crop_id_card_image(img):
    if img is None:
        return img
    try:
        quad = _detect_id_card_body_quad(img)
        if quad is not None:
            body = _four_point_transform(img, _expand_quad(quad, img.shape, scale_x=1.03, scale_y=1.05))
            if body is not None and body.size != 0:
                body = normalize_card_orientation(body)
                body = _orient_card_by_content_box(body, is_special_cert=False)
                body = _orient_card_result(body, is_special_cert=False)
                body = trim_document_borders(body, max_trim_ratio=0.005)
                return pad_image_to_ratio(body)
        contour_result = crop_by_card_contour(img, is_special_cert=False)
        if contour_result is not None:
            ch, cw = contour_result.shape[:2]
            ih, iw = img.shape[:2]
            if ch * cw < ih * iw * 0.95:
                contour_result = normalize_card_orientation(contour_result)
                contour_result = _orient_card_by_content_box(contour_result, is_special_cert=False)
                contour_result = _orient_card_result(contour_result, is_special_cert=False)
                contour_result = trim_document_borders(contour_result, max_trim_ratio=0.005)
                return pad_image_to_ratio(contour_result)
        work = img.copy()
        work = normalize_card_orientation(work)
        work = _orient_card_by_content_box(work, is_special_cert=False)
        work = _orient_card_result(work, is_special_cert=False)
        work = trim_document_borders(work, max_trim_ratio=0.01)
        return pad_image_to_ratio(work)
    except Exception:
        return img

# ================= 3. 信息智能解析 =================
def clean_name_string(name_str):
    name_str = str(name_str).replace(" ", "").replace("　", "")
    if "葡" in name_str and "葡萄" not in name_str:
        name_str = name_str.replace("葡", "蔺")
    return name_str

def is_valid_name(_text_raw, text_cleaned):
    if not (2 <= len(text_cleaned) <= 4):
        return False
    strict_labels = ["姓名", "性别", "民族", "出生", "住址", "号码", "公民身份", "身份"]
    if text_cleaned in strict_labels:
        return False
    if any(char.isdigit() for char in text_cleaned):
        return False
    return True

def extract_nation(full_text):
    nations = ["汉", "壮", "满", "回", "苗", "维吾尔", "土家", "彝", "蒙古", "藏", "布依", "侗", "瑶", "朝鲜", "白", "哈尼", "哈萨克", "黎", "傣", "畲", "傈僳", "东乡", "拉祜", "水", "佤", "纳西", "羌", "土", "仫佬", "锡伯", "柯尔克孜", "达斡尔", "景颇", "毛南", "撒拉", "布朗", "塔吉克", "阿昌", "普米", "鄂温克", "怒", "京", "基诺", "德昂", "保安", "俄罗斯", "裕固", "乌孜别克", "门巴", "鄂伦春", "独龙", "塔塔尔", "赫哲", "高山", "珞巴", "仡佬"]
    for n in nations:
        if n in full_text:
            return n + "族"
    return "汉族"

def smart_extract_info(ocr_results):
    if not ocr_results:
        return "", "", ""
    lines_clean = [line[1].replace(" ", "") for line in ocr_results]
    full_text_clean = "".join(lines_clean).upper()
    id_number = ""
    id_match = re.search(r'([1-9]\d{5}[12]\d{3}[01]\d[0123]\d{4}[\dXx])', full_text_clean)
    if not id_match:
        corrected = full_text_clean.replace('O', '0').replace('Z', '2').replace('I', '1').replace('S', '5')
        id_match = re.search(r'([1-9]\d{5}[12]\d{3}[01]\d[0123]\d{4}[\dXx])', corrected)
    if id_match:
        id_number = id_match.group(1).upper()

    name = ""
    
    # 策略 1: 直接匹配包含“姓名”的文本行
    for i, line in enumerate(ocr_results):
        text = str(line[1]).replace(" ", "").replace(":", "").replace("：", "")
        if "姓名" in text:
            # 如果这行字不止“姓名”两个字，例如“姓名张三”
            if len(text) > 2:
                candidate = text.replace("姓名", "")
                candidate = re.sub(r'[^\u4e00-\u9fa5]', '', candidate)
                if 2 <= len(candidate) <= 4 and not any(k in candidate for k in ["性别", "民族", "出生", "住址", "号码"]):
                    name = candidate
                    break
            # 如果这行只有“姓名”，找它同行的右侧框，或者下一行
            else:
                box_name = np.array(line[0])
                name_y = np.mean(box_name[:, 1])
                name_x_max = np.max(box_name[:, 0])
                
                # 寻找右侧同行且最近的框
                best_right_cand = ""
                best_right_dist = 9999
                for r_line in ocr_results:
                    r_text = str(r_line[1]).replace(" ", "")
                    if r_text == text:
                        continue
                    r_box = np.array(r_line[0])
                    r_y = np.mean(r_box[:, 1])
                    r_x_min = np.min(r_box[:, 0])
                    
                    # 同行（y轴差值小于15）且在右边
                    if abs(r_y - name_y) < 15 and r_x_min > name_x_max - 5:
                        dist = r_x_min - name_x_max
                        if dist < best_right_dist:
                            best_right_dist = dist
                            best_right_cand = re.sub(r'[^\u4e00-\u9fa5]', '', r_text)
                            
                if best_right_cand and 2 <= len(best_right_cand) <= 4 and not any(k in best_right_cand for k in ["性别", "民族", "出生", "住址"]):
                    name = best_right_cand
                    break
                    
                # 或者是下一行
                if i + 1 < len(ocr_results):
                    next_text = str(ocr_results[i + 1][1]).replace(" ", "")
                    cleaned = re.sub(r'[^\u4e00-\u9fa5]', '', next_text)
                    if 2 <= len(cleaned) <= 4 and not any(k in cleaned for k in ["性别", "民族", "出生", "住址"]):
                        name = cleaned
                        break

    # 策略 2: 基于“性别”或“民族”的 y 坐标向上寻找
    if not name or len(name) < 2:
        gender_box_y = -1
        for line in ocr_results:
            text = str(line[1]).replace(" ", "")
            if "性别" in text or "民族" in text:
                box = np.array(line[0])
                gender_box_y = np.mean(box[:, 1])
                break
                
        if gender_box_y != -1:
            best_name_candidate = ""
            best_name_y_diff = 9999
            for line in ocr_results:
                text = str(line[1]).replace(" ", "")
                box = np.array(line[0])
                cy = np.mean(box[:, 1])
                
                # 高度差必须大于 15 像素，避免把同行的“民族汉”误认作姓名
                if 15 < (gender_box_y - cy) < 200: 
                    clean_text = text.replace("姓名", "").replace("名", "")
                    clean_text = re.sub(r'[^\u4e00-\u9fa5]', '', clean_text)
                    if 2 <= len(clean_text) <= 4 and not any(k in clean_text for k in ["性别", "民族", "出生", "住址"]):
                        if (gender_box_y - cy) < best_name_y_diff:
                            best_name_y_diff = gender_box_y - cy
                            best_name_candidate = clean_text
            if best_name_candidate:
                name = best_name_candidate

    # 策略 3: 兜底方案，取前几行
    if not name or len(name) < 2:
        for line_text in lines_clean[:3]:
            cleaned = re.sub(r'[^\u4e00-\u9fa5]', '', line_text).replace("姓名", "", 1)
            if 2 <= len(cleaned) <= 4 and not any(k in cleaned for k in ["性别", "民族", "出生", "住址", "号码", "身份"]):
                name = cleaned
                break

    # 终极黑名单过滤与清洗
    name = clean_name_string(name)
    invalid_keywords = ["性别", "民族", "出生", "住址", "号码", "公民", "身份", "汉族", "别男", "别女"]
    if any(k in name for k in invalid_keywords):
        name = ""
    if name in ["汉", "男", "女", "汉族", "族", "男新", "女新", "姓名", "姓名名", "名"]:
        name = ""

    nation = extract_nation(full_text_clean)
    return name[:5] if len(name) >= 2 else "", id_number, nation

def _read_and_auto_orient(image_path):
    """用 PIL 读取图片并自动应用 EXIF 方向信息（修正手机竖拍/横拍旋转），返回 OpenCV BGR 图像"""
    try:
        pil_img = Image.open(image_path)
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode != 'RGB':
            pil_img = pil_img.convert('RGB')
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception:
        # fallback: 直接用 OpenCV 读取（不处理 EXIF）
        return cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_COLOR)

def _crop_by_ocr_boxes(img, ocr_results):
    """用 OCR 检测到的所有文字框的外接矩形来裁剪卡面区域，比轮廓检测更可靠"""
    if not ocr_results or len(ocr_results) < 2:
        return img
    
    all_points = []
    for line in ocr_results:
        box = np.array(line[0])
        all_points.extend(box.tolist())
    
    all_points = np.array(all_points)
    min_x = int(np.min(all_points[:, 0]))
    max_x = int(np.max(all_points[:, 0]))
    min_y = int(np.min(all_points[:, 1]))
    max_y = int(np.max(all_points[:, 1]))
    
    h, w = img.shape[:2]
    text_w = max_x - min_x
    text_h = max_y - min_y
    
    # 文字区域太小说明检测有问题，不裁剪
    if text_w < w * 0.15 or text_h < h * 0.15:
        return img
    
    # 向外扩展 15%，包含卡片边框
    pad_x = int(text_w * 0.15)
    pad_y = int(text_h * 0.15)
    
    x1 = max(0, min_x - pad_x)
    y1 = max(0, min_y - pad_y)
    x2 = min(w, max_x + pad_x)
    y2 = min(h, max_y + pad_y)
    
    # 如果裁剪区域和原图差不多大，说明卡占满整个画面，不需要裁剪
    crop_area = (x2 - x1) * (y2 - y1)
    if crop_area > h * w * 0.92:
        return img
    
    cropped = img[y1:y2, x1:x2]
    if cropped.size == 0:
        return img
    return cropped

def _anchor_orientation_score(ocr_results):
    """
    双锚点方向评分：
    锚点1: "姓名" 两个字（每张身份证正面都印有）
    锚点2: 18位身份证号
    
    正确方向: "姓名"在图片上方(y小), 身份证号在图片下方(y大)
    
    返回: 正数=方向正确且可信, 负数=方向颠倒, 0=无法判断
    数值越大越可信
    """
    if not ocr_results:
        return 0
    
    xingming_y = None
    id_number_y = None
    
    for line in ocr_results:
        text = str(line[1]).replace(" ", "").replace("　", "")
        box = np.array(line[0])
        cy = float(np.mean(box[:, 1]))
        
        # 锚点1: "姓名" 标签
        if "姓名" in text:
            xingming_y = cy
        
        # 锚点2: 18位身份证号
        cleaned = text.upper().replace('O', '0').replace('Z', '2').replace('I', '1').replace('S', '5')
        if re.search(r'[1-9]\d{5}[12]\d{3}[01]\d[0123]\d{4}[\dXx]', cleaned):
            id_number_y = cy
    
    if xingming_y is not None and id_number_y is not None:
        # 姓名y < 身份证号y → 正确方向 → 正值
        # 姓名y > 身份证号y → 颠倒 → 负值
        return id_number_y - xingming_y
    
    # 只找到一个锚点，给个微弱信号
    if xingming_y is not None:
        return 0.1  # 至少能找到姓名标签
    return 0

def ocr_idcard_process(image_path):
    engine = init_ppocrv6()
    
    # ===== Step 1: 读取图像（支持 EXIF 自动旋转） =====
    img_cv = _read_and_auto_orient(image_path)
    if img_cv is None:
        raise ValueError("无法解析身份证图片。")
    
    # ===== Step 2: Canny 裁切卡面 =====
    img_cropped = crop_by_card_contour(img_cv, is_special_cert=False)
    if img_cropped is None:
        # 回退：直接使用原图并规范化为横图
        img_cropped = img_cv.copy()
        h, w = img_cropped.shape[:2]
        if h > w:
            img_cropped = cv2.rotate(img_cropped, cv2.ROTATE_90_CLOCKWISE)
        img_cropped = pad_image_to_ratio(img_cropped)
    
    # ===== Step 3: 用带 cls 的引擎提取最终文字 =====
    ocr_res, _ = engine(img_cropped)
    name, id_card, nation = smart_extract_info(ocr_res)
    
    # ===== Step 4: 保存裁剪结果 =====
    cropped_filename = f"crop_{uuid.uuid4().hex}.jpg"
    cropped_path = os.path.join(TEMP_IDS_DIR, cropped_filename).replace('\\', '/')
    cv2.imencode('.jpg', img_cropped, [int(cv2.IMWRITE_JPEG_QUALITY), 90])[1].tofile(cropped_path)
    
    return {
        "name": name,
        "id_card": id_card,
        "nation": nation,
        "temp_id_card_img": cropped_path
    }


# ================= 4. Word 登记卡自动生成 =================
def _center_text_in_spaces(text, total_spaces):
    width = sum(2 if ord(c) > 127 else 1 for c in text)
    if width >= total_spaces:
        return text
    left_pad = (total_spaces - width) // 2
    right_pad = total_spaces - width - left_pad
    return (" " * left_pad) + text + (" " * right_pad)

def generate_record_card(record_data, id_card_img_path):
    """
    根据登记卡模板生成 word 登记卡
    record_data: dict, 必须包含 姓名, 性别, 年龄, 联系电话, 岗位, 常住地址
    id_card_img_path: 裁剪后的身份证路径
    """
    template_path = '登记卡.docx'
    
    # 自动备份/提取桌面的登记卡模板
    if not os.path.exists(template_path):
        desktop_dir = os.path.join(os.environ.get('USERPROFILE', 'C:/Users/Administrator'), 'Desktop')
        src_template = os.path.join(desktop_dir, '身份证', '登记卡.docx')
        if os.path.exists(src_template):
            shutil.copy2(src_template, template_path)
            print("[Info] 从桌面身份证文件夹中成功复制 [登记卡.docx] 模板。")
        else:
            raise FileNotFoundError("本地和桌面上未找到 [登记卡.docx] 模板文件，请确认放置！")
            
    # 生成随机的目标 word 路径
    card_filename = f"card_{record_data['姓名']}_{uuid.uuid4().hex}.docx"
    output_path = os.path.join(CARDS_DIR, card_filename).replace('\\', '/')
    
    doc = Document(template_path)
    now = datetime.datetime.now()
    
    replacements = {
        '[[NAME]]': record_data.get('工作单位', ''),
        '[[name]]': record_data.get('工作单位', ''),
        '[[COMPANY]]': record_data.get('工作单位', ''),
        '[[GENDER]]': record_data.get('性别', ''),
        '[[AGE]]': str(record_data.get('年龄', '')),
        '[[PHONE]]': str(record_data.get('联系电话', '')),
        '[[YEAR]]': str(now.year),
        '[[MONTH]]': str(now.month),
        '[[DAY]]': str(now.day)
    }
    
    replaced_img = False
    paragraphs = [p for p in doc.paragraphs] + [p for t in doc.tables for r in t.rows for c in r.cells for p in c.paragraphs]
    
    def merge_similar_runs(paragraph):
        if len(paragraph.runs) <= 1:
            return
        i = 0
        while i < len(paragraph.runs) - 1:
            r1 = paragraph.runs[i]
            r2 = paragraph.runs[i+1]
            if (r1.underline == r2.underline and 
                r1.bold == r2.bold and 
                r1.italic == r2.italic and 
                r1.font.name == r2.font.name and 
                r1.font.size == r2.font.size):
                r1.text = r1.text + r2.text
                p_element = paragraph._element
                p_element.remove(r2._element)
                continue
            i += 1

    for p in paragraphs:
        merge_similar_runs(p)
            
        text = p.text.strip()
        if text == "工种":
            p.clear()
            r1 = p.add_run("工种")
            r1.font.name = "宋体"
            job_val = record_data.get("岗位", "普工")
            r2 = p.add_run(_center_text_in_spaces(job_val, 41))
            r2.font.name = "宋体"
            r2.underline = True
            continue
        elif text == "现住址":
            p.clear()
            r1 = p.add_run("现住址")
            r1.font.name = "宋体"
            addr_val = record_data.get("常住地址", "四川华庭生活区")
            r2 = p.add_run(_center_text_in_spaces(addr_val, 37))
            r2.font.name = "宋体"
            r2.underline = True
            continue
            
        if '[[ANCHOR_ID_CARD_HERE]]' in p.text and not replaced_img and id_card_img_path and os.path.exists(id_card_img_path):
            p.clear()
            run = p.add_run()
            # 尺寸：3.37" * 2.13" 身份证金牌尺寸
            run.add_picture(id_card_img_path, width=Inches(3.37), height=Inches(2.13))
            try:
                p.alignment = 1  # 居中对齐
            except:
                pass
            replaced_img = True
            
        for k, v in replacements.items():
            if k in p.text:
                for run in p.runs:
                    if k in run.text:
                        run.text = run.text.replace(k, v)
                        
    doc.save(output_path)
    return output_path

# ================= 5. 定期清理守护线程 =================
def cleanup_old_words():
    now = time.time()
    one_week_ago = now - 7 * 24 * 3600  # 一周前
    
    import glob
    
    # 1. 扫描 cards 目录下的 docx，并更新数据库
    if os.path.exists(CARDS_DIR):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for docx_file in glob.glob(os.path.join(CARDS_DIR, "*.docx")):
            try:
                mtime = os.path.getmtime(docx_file)
                if mtime < one_week_ago:
                    os.remove(docx_file)
                    filename = os.path.basename(docx_file)
                    cursor.execute("UPDATE records SET word_path = NULL WHERE word_path LIKE ?", (f"%{filename}",))
                    print(f"[Cleanup] 已成功自动清理 7 天前的登记卡 Word 文件: {filename}")
            except Exception as e:
                print(f"[Error] 自动清理文件 {docx_file} 失败: {e}")
        conn.commit()
        conn.close()
        
    # 2. 扫描 idcards 目录下的裁剪后持久化身份证照片，也仅保留一周
    if os.path.exists(IDCARD_SAVE_DIR):
        for id_img_file in glob.glob(os.path.join(IDCARD_SAVE_DIR, "*")):
            try:
                mtime = os.path.getmtime(id_img_file)
                if mtime < one_week_ago:
                    os.remove(id_img_file)
                    print(f"[Cleanup] 已成功自动清理 7 天前的身份证裁剪照片: {os.path.basename(id_img_file)}")
            except Exception as e:
                print(f"[Error] 自动清理身份证照片 {id_img_file} 失败: {e}")
                
    # 3. 扫描 temp_ids 目录下的临时身份证照片，删除超过 1 天的
    if os.path.exists(TEMP_IDS_DIR):
        one_day_ago = now - 24 * 3600
        for temp_img in glob.glob(os.path.join(TEMP_IDS_DIR, "*")):
            try:
                mtime = os.path.getmtime(temp_img)
                if mtime < one_day_ago:
                    os.remove(temp_img)
                    print(f"[Cleanup] 已成功自动清理超过 1 天的临时身份证照片: {os.path.basename(temp_img)}")
            except Exception as e:
                print(f"[Error] 自动清理临时图片 {temp_img} 失败: {e}")

def start_cleanup_thread():
    def loop():
        while True:
            try:
                cleanup_old_words()
            except Exception as e:
                print(f"[Error] Cleanup thread exception: {e}")
            time.sleep(12 * 3600)  # 每 12 小时检查一次
            
    t = threading_thread = __import__('threading').Thread(target=loop, daemon=True)
    t.start()
    print("[Info] 过期登记卡清理守护线程已成功开启（周期: 12小时）。")
