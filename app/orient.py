import cv2
import numpy as np

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
        h, w = img.shape[:2]
        bbox = (0, 0, w - 1, h - 1)
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

def orient_card_result(img, is_special_cert=False):
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
