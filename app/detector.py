import cv2
import numpy as np

def detect_idcard_corners(img_gray: np.ndarray) -> np.ndarray:
    """
    Step 2: 文档检测，寻找身份证的四个角点。
    使用 OpenCV 双边滤波 + Canny 边缘检测 + 轮廓提取，寻找最大外接四边形。
    document-preprocessor 的调用在 app/tasks.py 中完成，本函数仅负责 Contour 回退路径。
    """
    h, w = img_gray.shape[:2]
    
    # OpenCV 经典 Contour 检测
        
    # 2. OpenCV Contour 轮廓检测
    # 2.1 双边滤波，保边去噪
    filtered = cv2.bilateralFilter(img_gray, 9, 75, 75)
    
    # 2.2 Canny 边缘检测
    edged = cv2.Canny(filtered, 30, 150)
    
    # 2.3 膨胀与闭运算，以连通断开的边缘
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edged, kernel, iterations=1)
    closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, kernel)
    
    # 2.4 寻找所有外廓
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # 2.5 按面积大小排序
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    
    best_poly = None
    max_area = 0
    img_area = w * h
    
    for c in contours:
        area = cv2.contourArea(c)
        # 限制面积不能太小（小于全图 8% 视为杂音）
        if area < (img_area * 0.08):
            continue
            
        # 简化轮廓以求近似多边形
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        
        # 检查是否为凸四边形
        if len(approx) == 4 and cv2.isContourConvex(approx):
            if area > max_area:
                best_poly = approx
                max_area = area
                
    # 3. 输出并归一化四角坐标
    if best_poly is not None:
        pts = best_poly.reshape(4, 2).astype(np.float32)
        return pts
        
    # 4. 兜底：如果完全没有找到四边形，以整张图片边界作为四角点（即保留全图）
    print("[Detector] No clear quadrilateral found. Defaulting to full image boundaries.")
    return np.array([
        [0, 0],
        [w - 1, 0],
        [w - 1, h - 1],
        [0, h - 1]
    ], dtype=np.float32)
