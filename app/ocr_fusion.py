import re
import numpy as np
from typing import List, Dict, Tuple, Any
from .ocr import get_ocr_engine
from .postprocess import NATIONS, normalize_text, correct_id_number, match_nation

def extract_fields_from_ocr(lines: List[str]) -> Dict[str, str]:
    """从 OCR 文本行中抽取出结构化字段"""
    fields = {
        "name": "",
        "id_number": "",
        "gender": "",
        "nation": "",
        "address": ""
    }
    
    address_lines = []
    
    for line in lines:
        cleaned = normalize_text(line)
        if not cleaned:
            continue
            
        # 1. 识别身份证号
        # 身份证可能混入 OCR 错别字符，我们用正则抓取包含字母和数字的长字符串
        id_match = re.search(r'[0-9A-Za-zIlOoSzS]{15,18}', cleaned)
        if id_match and not fields["id_number"]:
            candidate = id_match.group(0)
            corrected = correct_id_number(candidate)
            if 15 <= len(corrected) <= 18:
                fields["id_number"] = corrected
                
        # 2. 识别姓名
        name_match = re.search(r'(姓名|姓名是|名|姓)[:：]?\s*([\u4e00-\u9fa5]{2,4})', cleaned)
        if name_match and not fields["name"]:
            fields["name"] = name_match.group(2)
        
        # 3. 识别性别与民族
        if "性别" in cleaned or "男" in cleaned or "女" in cleaned:
            if "女" in cleaned:
                fields["gender"] = "女"
            elif "男" in cleaned:
                fields["gender"] = "男"
                
        # 民族匹配
        for n in NATIONS:
            if n in cleaned or f"{n}族" in cleaned:
                fields["nation"] = n
                break
                
        # 4. 收集地址关键词
        if any(kw in cleaned for kw in ["省", "市", "自治区", "县", "区", "镇", "乡", "村", "组", "号", "街", "路", "楼", "室"]):
            # 排除包含“姓名”、“性别”、“民族”、“号码”等干扰项的行
            if not any(exclude in cleaned for exclude in ["姓名", "性别", "民族", "公民", "身份", "号码"]):
                address_lines.append(cleaned)
                
    # 5. 二次兜底姓名：如果没通过关键字匹配到姓名，找前3行里最像姓名（2-4个汉字且不包含关键字）的文本
    if not fields["name"]:
        for line in lines[:3]:
            cleaned = normalize_text(line)
            if re.match(r'^[\u4e00-\u9fa5]{2,4}$', cleaned):
                if not any(kw in cleaned for kw in ["姓名", "性别", "民族", "出生", "住址", "公民"]):
                    fields["name"] = cleaned
                    break
                    
    # 合并地址
    if address_lines:
        # 去重并拼接
        unique_address = []
        for addr in address_lines:
            # 简单清洗前缀，如 "住址", "地址"
            addr = re.sub(r'^(住址|地址|常住地址)[:：]?', '', addr)
            if addr not in unique_address:
                unique_address.append(addr)
        fields["address"] = "".join(unique_address)
        
    return fields

def verify_id_checksum(id_num: str) -> bool:
    """18位身份证校验和"""
    if len(id_num) != 18:
        return False
    factor = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    check_table = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']
    try:
        total = sum(int(id_num[i]) * factor[i] for i in range(17))
        return check_table[total % 11].upper() == id_num[17].upper()
    except Exception:
        return False

def calculate_ocr_score(fields: Dict[str, str], lines: List[str]) -> float:
    """Step 6: OCR 评分算法"""
    score = 0.0
    
    # 1. 身份证号评分 (权重最高)
    id_num = fields["id_number"]
    if id_num:
        if verify_id_checksum(id_num):
            score += 50.0  # 校验和通过直接 +50
        else:
            score += 15.0  # 格式符合 18 位但校验和失败 +15
            
    # 2. 字段完整性评分
    present_fields = sum(1 for v in fields.values() if v)
    score += present_fields * 4.0  # 每个存在字段 +4 分，最高 20 分
    
    # 3. 噪声惩罚 (扣分)
    # 检测乱码（连续特殊符号）
    for line in lines:
        garbage_match = re.findall(r'[^\u4e00-\u9fa5a-zA-Z0-9]', line)
        score -= len(garbage_match) * 0.5  # 杂音扣分
        
    return max(0.0, score)

def fuse_ocr_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Step 7: 字段级融合决策。
    不是简单选取整行最高分，而是将 A/B/C 三个策略的优势字段融合成最终版本。
    """
    fused = {
        "name": "",
        "id_number": "",
        "gender": "",
        "nation": "",
        "address": "",
        "confidence": 0.0,
        "used_strategy": "fusion_v1"
    }
    
    # 1. 身份证号码融合（合法校验和优先）
    # 寻找通过校验和校验的身份证号
    valid_id = None
    for r in results:
        id_num = r["fields"]["id_number"]
        if id_num and verify_id_checksum(id_num):
            valid_id = id_num
            break
    
    if valid_id:
        fused["id_number"] = valid_id
    else:
        # 没有通过校验的，采用非空的最长身份证号码候选值以增加容错性
        id_candidates = [r["fields"]["id_number"] for r in results if r["fields"]["id_number"]]
        if id_candidates:
            fused["id_number"] = max(id_candidates, key=len)
        else:
            fused["id_number"] = ""
        
    # 2. 性别自动提取：基于融合的身份证第 17 位（单数男，双数女），规则绝对优先
    if fused["id_number"] and len(fused["id_number"]) == 18:
        try:
            gender_digit = int(fused["id_number"][16])
            fused["gender"] = "男" if gender_digit % 2 != 0 else "女"
        except ValueError:
            pass
            
    if not fused["gender"]:
        # 身份证缺损，根据文字投票
        gender_votes = [r["fields"]["gender"] for r in results if r["fields"]["gender"]]
        if gender_votes:
            fused["gender"] = max(set(gender_votes), key=gender_votes.count)
            
    # 3. 姓名融合：一致性与最高分优先
    names = [r["fields"]["name"] for r in results if r["fields"]["name"]]
    if names:
        # 投票多数优先，若平票则根据整体评分最高版
        fused["name"] = max(set(names), key=names.count)
        
    # 4. 民族融合：匹配 56 民族为硬约束
    nations = [r["fields"]["nation"] for r in results if r["fields"]["nation"]]
    valid_nations = [match_nation(nat) for nat in nations if match_nation(nat)]
    if valid_nations:
        fused["nation"] = max(set(valid_nations), key=valid_nations.count)
    else:
        fused["nation"] = ""  # 无法识别民族，留空由前端默认选择
        
    # 5. 地址融合：最长可信文本优先（防止信息缺损）
    addresses = [r["fields"]["address"] for r in results if r["fields"]["address"]]
    if addresses:
        fused["address"] = max(addresses, key=len)
        
    # 6. 计算融合综合置信度
    max_score = max(r["score"] for r in results) if results else 0.0
    # 校验和通过直接获得高置信度
    base_conf = 0.85 if fused["id_number"] and verify_id_checksum(fused["id_number"]) else 0.50
    # 字段完整性加分
    data_fields = ["name", "id_number", "gender", "nation", "address"]
    present_fields = sum(1 for k in data_fields if fused.get(k))
    fused["confidence"] = round(min(0.99, base_conf + (present_fields * 0.02) + (max_score * 0.001)), 2)
    
    return fused

def run_multi_strategy_ocr(img_a: np.ndarray, img_b: np.ndarray, img_c: np.ndarray) -> Dict[str, Any]:
    """
    对 preprocessed / sharpened / thresholded 3个图分别运行 OCR，并融合评分。
    """
    engine = get_ocr_engine()
    
    versions = [
        {"name": "version_a", "img": img_a},
        {"name": "version_b", "img": img_b},
        {"name": "version_c", "img": img_c}
    ]
    
    results = []
    
    for ver in versions:
        img = ver["img"]
        # 执行 RapidOCR 预测
        try:
            ocr_res, _ = engine(img)
            lines = [line[1] for line in ocr_res] if ocr_res else []
        except Exception as e:
            print(f"[OCR] Strategy {ver['name']} failed: {e}")
            lines = []
            
        fields = extract_fields_from_ocr(lines)
        score = calculate_ocr_score(fields, lines)
        
        # 加上多版本一致性加分
        results.append({
            "version": ver["name"],
            "fields": fields,
            "score": score,
            "raw_lines": lines
        })
        
    # 一致性奖励：如果两个版本得出相同的身份证号，给他们各加分以示鼓励
    id_nums = [r["fields"]["id_number"] for r in results if r["fields"]["id_number"]]
    if len(id_nums) > 1:
        most_common_id = max(set(id_nums), key=id_nums.count)
        if id_nums.count(most_common_id) >= 2:
            for r in results:
                if r["fields"]["id_number"] == most_common_id:
                    r["score"] += 10.0
                    
    # 执行字段级融合
    final_result = fuse_ocr_results(results)
    return final_result
