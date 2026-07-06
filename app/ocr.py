import os
import yaml
from modelscope import snapshot_download
from rapidocr_onnxruntime import RapidOCR
from .config import UPLOAD_DIR

_ocr_engine = None

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        print("[Info] Celery Worker: Loading PP-OCRv6 Tiny 1.5m model...")
        try:
            # 下载模型并获取路径
            det_dir = snapshot_download('PaddlePaddle/PP-OCRv6_tiny_det_onnx')
            rec_dir = snapshot_download('PaddlePaddle/PP-OCRv6_tiny_rec_onnx')
            
            det_path = os.path.join(det_dir, 'inference.onnx')
            rec_path = os.path.join(rec_dir, 'inference.onnx')
            
            # 解析 yml 并获取字典列表
            yml_path = os.path.join(rec_dir, 'inference.yml')
            with open(yml_path, 'r', encoding='utf-8') as f:
                yml_content = yaml.safe_load(f)
            char_list = yml_content['PostProcess']['character_dict']
            
            # 写入本地字典文件
            dict_txt_path = os.path.join(UPLOAD_DIR, 'dict_ppocrv6.txt').replace('\\', '/')
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            with open(dict_txt_path, 'w', encoding='utf-8') as df:
                for char in char_list:
                    df.write(char + '\n')
            
            # 引入 monkey patch 解决 rapidocr_onnxruntime 对 rec_keys_path 参数传递的 Bug
            import rapidocr_onnxruntime.utils
            orig_update_rec_params = rapidocr_onnxruntime.utils.UpdateParameters.update_rec_params

            def patched_update_rec_params(self, config, rec_dict):
                res_config = orig_update_rec_params(self, config, rec_dict)
                if 'rec_keys_path' in rec_dict:
                    res_config['keys_path'] = rec_dict['rec_keys_path']
                return res_config

            rapidocr_onnxruntime.utils.UpdateParameters.update_rec_params = patched_update_rec_params

            # 初始化 ONNX 运行环境（CPU 单例）
            _ocr_engine = RapidOCR(
                det_model_path=det_path,
                rec_model_path=rec_path,
                rec_keys_path=dict_txt_path,
                use_angle_cls=False
            )
            print("[Success] PP-OCRv6 ONNX engine successfully initialized.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[Warning] Failed to initialize PP-OCRv6: {e}")
            # 降级尝试默认 RapidOCR
            _ocr_engine = RapidOCR(use_angle_cls=False)
    return _ocr_engine
