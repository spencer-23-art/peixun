import cv2
import numpy as np

def order_points(pts: np.ndarray) -> np.ndarray:
    """
    对输入的4个角点排序，顺序为: [左上, 右上, 右下, 左下]
    """
    rect = np.zeros((4, 2), dtype=np.float32)
    
    # x+y 最小的是左上，最大的是右下
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    
    # y-x 最小（或者 x-y 最大）的是右上，y-x 最大的是左下
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    
    return rect

def perspective_warp(img: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """
    Step 3: 透视变换矫正，输出标准 856x540 的身份证裁剪面
    """
    # 1. 规范输入坐标点顺序
    ordered_corners = order_points(corners)
    
    # 2. 定义目标物理尺寸 (856 x 540)
    dst_width = 856
    dst_height = 540
    
    dst_pts = np.array([
        [0, 0],
        [dst_width - 1, 0],
        [dst_width - 1, dst_height - 1],
        [0, dst_height - 1]
    ], dtype=np.float32)
    
    # 3. 计算透视变换矩阵
    M = cv2.getPerspectiveTransform(ordered_corners, dst_pts)
    
    # 4. 执行透视拉伸扭正
    warped = cv2.warpPerspective(img, M, (dst_width, dst_height))
    return warped
