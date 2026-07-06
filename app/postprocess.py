import re

# 中国56个民族列表
NATIONS = {
    "汉", "壮", "维吾尔", "回", "苗", "满", "彝", "土家", "藏", "蒙古", "布依", "侗", "瑶", "白", "哈尼", 
    "朝鲜", "黎", "哈萨克", "傣", "畲", "傈僳", "东乡", "仡佬", "拉祜", "佤", "水", "纳西", "羌", "土", 
    "仫佬", "锡伯", "柯尔克孜", "景颇", "达斡尔", "撒拉", "布朗", "毛南", "塔吉克", "普米", "阿昌", "怒", 
    "鄂温克", "京", "基诺", "德昂", "保安", "俄罗斯", "裕固", "乌孜别克", "门巴", "鄂伦春", "独龙", 
    "赫哲", "高山", "珞巴", "塔塔尔"
}

def normalize_text(text: str) -> str:
    """
    🧼 Step 8: OCR后处理，字段标准化。
    去除空格、换行符和常见的无用特殊符号。
    """
    if not text:
        return ""
    # 过滤掉换行符，去前后空白
    text = text.replace('\n', '').replace('\r', '').strip()
    # 过滤非主流特殊字符（保留中文、英文、数字和常用身份证/地址字符）
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\(\)\uff08\uff09xX\-]', '', text)
    return text

def correct_id_number(id_str: str) -> str:
    """
    身份证号修复：
    O/o/0误识别修复，I/l/1误识别修复，Z/2误识别修复。
    最后将可能的小写 x 规范为大写 X。
    """
    if not id_str:
        return ""
        
    # 去除多余的符号
    id_str = id_str.strip().replace(" ", "")
    
    # 常用混淆字符字典式替换映射
    replace_dict = {
        'O': '0', 'o': '0',
        'I': '1', 'l': '1', 'i': '1',
        'z': '2', 'Z': '2',
        'S': '5', 's': '5',
        'b': '6',
        'g': '9',
    }
    
    chars = list(id_str)
    for i in range(len(chars)):
        # 前17位必须是数字
        if i < 17:
            if chars[i] in replace_dict:
                chars[i] = replace_dict[chars[i]]
        else:
            # 第18位可以是数字或X/x
            if chars[i] in replace_dict and replace_dict[chars[i]] in ['0', '1', '2', '5']:
                chars[i] = replace_dict[chars[i]]
            elif chars[i] == 'x':
                chars[i] = 'X'
                
    # 重新拼接
    corrected = "".join(chars)
    # 正则提取18位数字或末尾为X的长度限制
    match = re.search(r'\d{17}[\dX]', corrected)
    return match.group(0) if match else corrected

def match_nation(text: str) -> str:
    """
    校验识别结果中是否能够匹配56个合法民族。
    支持形式如 “汉”、“汉族”，去除“族”字并与标准集校验。
    """
    if not text:
        return ""
    # 去除“族”字前缀/后缀
    clean_text = text.replace("族", "").strip()
    if clean_text in NATIONS:
        return clean_text
    return ""
