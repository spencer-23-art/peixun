import cv2
import numpy as np

def load_image_from_bytes(file_bytes: bytes) -> np.ndarray:
    """从二进制字节流中解码出 OpenCV BGR 图像"""
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img

def load_image_from_path(file_path: str) -> np.ndarray:
    """从本地路径安全加载 BGR 图像（支持中文路径）"""
    img = cv2.imdecode(np.fromfile(file_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    return img
