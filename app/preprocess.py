import cv2
import numpy as np

def resize_image_max_edge(img: np.ndarray, max_edge: int = 1024) -> np.ndarray:
    """图片缩放，限制最长边不超过 max_edge"""
    h, w = img.shape[:2]
    if max(h, w) <= max_edge:
        return img
    
    if h > w:
        new_h = max_edge
        new_w = int(w * (max_edge / h))
    else:
        new_w = max_edge
        new_h = int(h * (max_edge / w))
        
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

def preprocess_image(img: np.ndarray) -> np.ndarray:
    """Step 1 基础图像预处理: 保持彩色 BGR，进行轻微亮度自适应均衡以保留颜色特征"""
    # 采用 Lab 空间的 CLAHE 增强，既增强了对比度，又 100% 保留了彩色信息
    if len(img.shape) == 3:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl, a, b))
        enhanced = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
        return enhanced
    return img

def get_strategy_b(img: np.ndarray) -> np.ndarray:
    """Strategy Version B: 彩色图像锐化以增强文字轮廓"""
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    sharpened = cv2.filter2D(img, -1, kernel)
    return sharpened

def get_strategy_c(img: np.ndarray) -> np.ndarray:
    """Strategy Version C: 彩色图像自适应对比度拉伸"""
    # 稍微提升对比度与亮度
    enhanced = cv2.convertScaleAbs(img, alpha=1.15, beta=8)
    return enhanced
