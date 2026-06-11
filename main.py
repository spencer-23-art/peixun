import os
import sqlite3
import shutil
import hmac
import hashlib
import uuid
import time
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header, Depends
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import openpyxl
import csv
import zipfile

DB_PATH = 'peixun.db'
UPLOAD_DIR = 'uploads'

SECRET_KEY = b"PEIXUN_SYSTEM_SECRET_SIGNING_KEY_2026"

def encrypt_pwd(raw_pwd: str) -> str:
    salt = uuid.uuid4().hex
    hashed = hashlib.sha256((raw_pwd + salt).encode('utf-8')).hexdigest()
    return f"{salt}${hashed}"

def verify_pwd(raw_pwd: str, stored_pwd_str: str) -> bool:
    try:
        salt, hashed = stored_pwd_str.split("$")
        check_hashed = hashlib.sha256((raw_pwd + salt).encode('utf-8')).hexdigest()
        return hmac.compare_digest(check_hashed, hashed)
    except ValueError:
        return hmac.compare_digest(raw_pwd, stored_pwd_str)

def generate_token(user_id: int, role: str, username: str) -> str:
    timestamp = int(time.time())
    payload = f"{user_id}:{role}:{username}:{timestamp}"
    signature = hmac.new(SECRET_KEY, payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"

def verify_token(token: str) -> dict:
    try:
        parts = token.split(":")
        if len(parts) != 5:
            return None
        user_id, role, username, timestamp, signature = parts
        payload = f"{user_id}:{role}:{username}:{timestamp}"
        expected_signature = hmac.new(SECRET_KEY, payload.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected_signature, signature):
            return None
        token_time = int(timestamp)
        current_time = int(time.time())
        if current_time - token_time > 7 * 24 * 3600:
            return None
        return {
            "id": int(user_id),
            "role": role,
            "username": username
        }
    except Exception:
        return None

def get_config(key: str, default: str) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM configs WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default

def is_exam_open() -> bool:
    from datetime import timedelta
    # 强制以北京时间 (UTC+8) 校验，不受服务器本地时区设置影响
    beijing_now = datetime.utcnow() + timedelta(hours=8)
    now_time = beijing_now.time()
    
    start_str = get_config('exam_start_time', '08:00:00')
    end_str = get_config('exam_end_time', '12:00:00')
    
    try:
        start_time = datetime.strptime(start_str, "%H:%M:%S").time()
        end_time = datetime.strptime(end_str, "%H:%M:%S").time()
    except Exception:
        start_time = datetime.strptime("08:00:00", "%H:%M:%S").time()
        end_time = datetime.strptime("12:00:00", "%H:%M:%S").time()
        
    return start_time <= now_time <= end_time

# 初始化数据库
def init_db():
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL, -- 登录手机号/用户名
        password TEXT NOT NULL,
        real_name TEXT NOT NULL,
        company TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', -- pending, approved, rejected
        role TEXT NOT NULL DEFAULT 'user' -- user, admin
    )
    ''')
    
    # 录入信息表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        photo_path TEXT,
        name TEXT,
        nation TEXT,
        id_card TEXT,
        phone TEXT,
        address TEXT,
        job TEXT,
        education TEXT,
        region_auth TEXT,
        gender TEXT,
        age INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    ''')
    
    # 默认管理员
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (username, password, real_name, company, status, role) VALUES (?, ?, ?, ?, ?, ?)",
            ('admin', encrypt_pwd('admin123'), '系统管理员', '管理部', 'approved', 'admin')
        )
        
    # 检测并为 records 表添加 is_gate_downloaded 列自愈逻辑
    try:
        cursor.execute("ALTER TABLE records ADD COLUMN is_gate_downloaded INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # 检测并为 records 表添加 gate_restore_status 列自愈逻辑
    try:
        cursor.execute("ALTER TABLE records ADD COLUMN gate_restore_status TEXT DEFAULT NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # 检测并为 records 表添加 is_restore_downloaded 列自愈逻辑
    try:
        cursor.execute("ALTER TABLE records ADD COLUMN is_restore_downloaded INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    # 答题记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS exam_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        company TEXT NOT NULL,
        exam_type TEXT NOT NULL,
        score INTEGER NOT NULL,
        answered_count INTEGER NOT NULL,
        correct_count INTEGER NOT NULL,
        duration TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # 答题详情表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS exam_details (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_record_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        user_answer TEXT NOT NULL,
        correct_answer TEXT NOT NULL,
        is_correct INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(exam_record_id) REFERENCES exam_records(id)
    )
    ''')
    # 系统配置表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS configs (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    ''')
    cursor.execute("INSERT OR IGNORE INTO configs (key, value) VALUES ('exam_start_time', '08:00:00')")
    cursor.execute("INSERT OR IGNORE INTO configs (key, value) VALUES ('exam_end_time', '12:00:00')")
        
    conn.commit()
    conn.close()

init_db()

app = FastAPI(title="培训信息录入系统")

@app.middleware("http")
async def log_requests(request, call_next):
    import time, sys
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    print(f"DEBUG_REQ: {request.method} {request.url.path} {request.query_params} - Status: {response.status_code} - Duration: {duration:.2f}s")
    sys.stdout.flush()
    return response

# 身份证解析逻辑
def parse_id_card(id_card_num):
    if not id_card_num or len(id_card_num) != 18:
        return "未知", 0
    try:
        birth_year_str = id_card_num[6:10]
        birth_year = int(birth_year_str)
        # 获取当前年份
        current_year = datetime.now().year
        age = current_year - birth_year
        
        gender_digit = int(id_card_num[16])
        gender = "男" if gender_digit % 2 != 0 else "女"
        return gender, age
    except Exception:
        return "未知", 0

# 鉴权依赖
def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录或未授权")
    
    token_info = verify_token(authorization)
    if not token_info:
        raise HTTPException(status_code=401, detail="无效的授权Token或凭证已过期")
    
    try:
        user_id = token_info["id"]
        username = token_info["username"]
        
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ? AND username = ?", (user_id, username))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")
            
        if user['status'] != 'approved' and user['role'] != 'admin':
            raise HTTPException(status_code=403, detail="账号尚未被审批通过，请耐心等待")
            
        return user
    except Exception:
        raise HTTPException(status_code=401, detail="授权认证失败")

def get_admin_user(current_user = Depends(get_current_user)):
    if current_user['role'] != 'admin':
        raise HTTPException(status_code=403, detail="无管理员权限")
    return current_user

# ---------------- API 接口 ----------------

@app.post("/api/save_ppt")
def save_ppt(html_content: str = Form(...)):
    try:
        static_dir = os.path.abspath("static")
        ppt_path = os.path.abspath(os.path.join(static_dir, "ppt.html"))
        with open(ppt_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return {"code": 200, "message": "保存成功！"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存失败: {str(e)}")

@app.post("/api/register")
def register(username: str = Form(...), password: str = Form(...), real_name: str = Form(...), company: str = Form(...)):
    if not real_name.strip():
        raise HTTPException(status_code=400, detail="真实姓名不能为空")
    if not username.strip():
        raise HTTPException(status_code=400, detail="联系电话/用户名不能为空")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (username, password, real_name, company, status, role) VALUES (?, ?, ?, ?, 'pending', 'user')",
            (username.strip(), encrypt_pwd(password.strip()), real_name.strip(), company.strip())
        )
        conn.commit()
        return {"code": 200, "message": "注册成功，请等待管理员审批！"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="该账号（电话）已存在，请直接登录")
    finally:
        conn.close()

@app.post("/api/login")
def login(username: str = Form(...), password: str = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    
    if not user or not verify_pwd(password, user['password']):
        conn.close()
        raise HTTPException(status_code=400, detail="用户名或密码错误")
        
    # 平滑升级明文密码
    if '$' not in user['password']:
        try:
            cursor.execute("UPDATE users SET password = ? WHERE id = ?", (encrypt_pwd(password), user['id']))
            conn.commit()
        except Exception:
            pass
            
    conn.close()
    
    if user['status'] == 'pending' and user['role'] != 'admin':
        return {"code": 300, "message": "您的注册申请正在审批中，暂无法登录。"}
        
    if user['status'] == 'rejected':
        return {"code": 301, "message": "您的注册申请已被拒绝，请重新注册或联系管理员。"}
        
    # 返回安全的 HMAC 签名 Token
    token = generate_token(user['id'], user['role'], user['username'])
    return {
        "code": 200,
        "message": "登录成功",
        "data": {
            "token": token,
            "role": user['role'],
            "real_name": user['real_name'],
            "company": user['company']
        }
    }

# 获取当前用户状态
@app.get("/api/user/status")
def user_status(current_user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # 额外去 records 表查询该用户最近提交的一条数据以用于回填（民族、常住地址、工种、学历、区域权限）
    cursor.execute('''
    SELECT nation, address, job, education, region_auth 
    FROM records 
    WHERE user_id = ? 
    ORDER BY id DESC LIMIT 1
    ''', (current_user['id'],))
    last_record = cursor.fetchone()
    conn.close()
    
    saved_data = {}
    if last_record:
        saved_data = {
            "nation": last_record["nation"],
            "address": last_record["address"],
            "job": last_record["job"],
            "education": last_record["education"],
            "region_auth": last_record["region_auth"]
        }
    else:
        # 如果是首次录入（没有历史记录），则为空
        saved_data = {
            "nation": "",
            "address": "",
            "job": "",
            "education": "",
            "region_auth": ""
        }

    return {
        "code": 200,
        "data": {
            "id": current_user["id"],
            "username": current_user["username"],
            "real_name": current_user["real_name"],
            "company": current_user["company"],
            "status": current_user["status"],
            "role": current_user["role"],
            "saved_fields": saved_data
        }
    }

# 获取待审批用户列表（仅管理员）
# 获取所有注册普通用户列表（包括 pending, approved, rejected，仅管理员）
@app.get("/api/admin/pending")
def get_pending_users(admin = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, real_name, company, status FROM users WHERE role != 'admin'")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"code": 200, "data": users}

# 审批操作（仅管理员）
@app.post("/api/admin/approve")
def approve_user(user_id: int = Form(...), action: str = Form(...), admin = Depends(get_admin_user)):
    if action not in ['approved', 'rejected']:
        raise HTTPException(status_code=400, detail="非法审批操作")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = ? WHERE id = ?", (action, user_id))
    conn.commit()
    conn.close()
    return {"code": 200, "message": "审批成功"}

# 删除注册用户（仅管理员，物理删除以防再度登录）
@app.post("/api/admin/user/delete")
def delete_user(user_id: int = Form(...), admin = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 安全检查，防止删除管理员
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="用户不存在")
    if user[0] == 'admin':
        conn.close()
        raise HTTPException(status_code=400, detail="无权删除管理员账户")
        
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"code": 200, "message": "用户删除成功"}

# 删除培训人员记录（仅管理员，物理删除关联照片）
@app.post("/api/admin/record/delete")
def delete_record(record_id: int = Form(...), admin = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. 获取照片路径，以便随后进行物理删除
    cursor.execute("SELECT photo_path FROM records WHERE id = ?", (record_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="该人员记录不存在")
        
    photo_path = row[0]
    
    # 2. 从数据库删除记录
    cursor.execute("DELETE FROM records WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
    
    # 3. 物理删除照片文件
    if photo_path and os.path.exists(photo_path):
        try:
            os.remove(photo_path)
        except Exception:
            pass
            
    return {"code": 200, "message": "记录删除成功"}


# 管理员修改普通用户信息（仅管理员）
@app.post("/api/admin/user/update")
def admin_update_user(
    user_id: int = Form(...),
    username: str = Form(...),
    real_name: str = Form(...),
    password: str = Form(None),
    admin = Depends(get_admin_user)
):
    username = username.strip()
    real_name = real_name.strip()
    
    if not username:
        raise HTTPException(status_code=400, detail="申请账号（电话）不能为空")
    if not real_name:
        raise HTTPException(status_code=400, detail="真实姓名不能为空")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # 安全检查，防止把管理员账户改成别人的普通账号，或者改动管理员名字
        cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="该用户不存在")
        if user[0] == 'admin':
            raise HTTPException(status_code=400, detail="无权修改系统管理员账号")
            
        # 查重
        cursor.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, user_id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="该账号（电话）已被其他用户使用")
            
        # 更新数据
        if password and password.strip():
            cursor.execute(
                "UPDATE users SET username = ?, real_name = ?, password = ? WHERE id = ?",
                (username, real_name, encrypt_pwd(password.strip()), user_id)
            )
        else:
            cursor.execute(
                "UPDATE users SET username = ?, real_name = ? WHERE id = ?",
                (username, real_name, user_id)
            )
        conn.commit()
        return {"code": 200, "message": "用户信息修改成功！"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"数据库更新失败: {str(e)}")
    finally:
        conn.close()

# 管理员快速修改培训人员的区域权限
@app.post("/api/admin/record/update_region")
def admin_update_region(
    record_id: int = Form(...),
    region_auth: str = Form(...),
    admin = Depends(get_admin_user)
):
    if not region_auth.strip():
        raise HTTPException(status_code=400, detail="区域权限不能为空")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 检查记录是否存在
    cursor.execute("SELECT id FROM records WHERE id = ?", (record_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="记录不存在")
        
    cursor.execute("UPDATE records SET region_auth = ? WHERE id = ?", (region_auth.strip(), record_id))
    conn.commit()
    conn.close()
    return {"code": 200, "message": "区域权限更改成功"}

# 录入培训数据
@app.post("/api/record")
async def create_record(
    name: str = Form(...),
    nation: str = Form(...),
    id_card: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    job: str = Form(...),
    education: str = Form(...),
    region_auth: str = Form(""),
    photo: UploadFile = File(...),
    current_user = Depends(get_current_user)
):
    if len(id_card) != 18 or id_card[10] not in ('0', '1'):
        raise HTTPException(status_code=400, detail="身份证号码格式不正确（必须为18位且第11位是0或1）")
        
    # 解析身份证
    gender, age = parse_id_card(id_card)
    
    # 保存照片到 uploads
    file_ext = os.path.splitext(photo.filename)[1].lower()
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif'}
    if not file_ext or file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的图片格式，仅允许 jpg, jpeg, png, gif")
        
    # 限制大小（5MB）
    content = await photo.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="照片文件大小不能超过 5MB")
    await photo.seek(0)
    
    filename = f"{current_user['id']}_{int(datetime.now().timestamp())}{file_ext}"
    photo_path = os.path.join(UPLOAD_DIR, filename).replace('\\', '/')
    
    with open(photo_path, "wb") as f:
        shutil.copyfileobj(photo.file, f)
        
    # 插入记录
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO records (user_id, photo_path, name, nation, id_card, phone, address, job, education, region_auth, gender, age)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (current_user['id'], photo_path, name, nation, id_card, phone, address, job, education, region_auth, gender, age))
    conn.commit()
    conn.close()
    
    return {"code": 200, "message": "信息录入成功！"}

# 获取当前用户录入的历史记录（默认最近10天，支持姓名搜索查全局，仅录入员自己）
@app.get("/api/records")
def get_user_records(name: str = None, current_user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    conditions = ["user_id = ?"]
    params = [current_user['id']]
    
    if name and name.strip():
        conditions.append("name LIKE ?")
        params.append(f"%{name.strip()}%")
    else:
        from datetime import datetime, timedelta
        ten_days_ago = (datetime.now() - timedelta(days=9)).strftime("%Y-%m-%d 00:00:00")
        conditions.append("created_at >= ?")
        params.append(ten_days_ago)
        
    query = f'''
    SELECT * FROM records 
    WHERE {" AND ".join(conditions)}
    ORDER BY created_at DESC
    '''
    cursor.execute(query, params)
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"code": 200, "data": records}

# 修改已录入的信息（仅能修改属于自己的记录）
@app.post("/api/record/update")
async def update_record(
    record_id: int = Form(...),
    name: str = Form(...),
    nation: str = Form(...),
    id_card: str = Form(...),
    phone: str = Form(...),
    address: str = Form(...),
    job: str = Form(...),
    education: str = Form(...),
    region_auth: str = Form(""),
    photo: UploadFile = File(None),
    current_user = Depends(get_current_user)
):
    if len(id_card) != 18 or id_card[10] not in ('0', '1'):
        raise HTTPException(status_code=400, detail="身份证号码格式不正确（必须为18位且第11位是0或1）")
        
    # 解析身份证
    gender, age = parse_id_card(id_card)
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 确认记录存在且属于当前用户
    cursor.execute("SELECT * FROM records WHERE id = ? AND user_id = ?", (record_id, current_user['id']))
    record = cursor.fetchone()
    if not record:
        conn.close()
        raise HTTPException(status_code=403, detail="无权修改此记录，或记录不存在")
        
    photo_path = record['photo_path']
    if photo and photo.filename:
        # 保存新照片
        file_ext = os.path.splitext(photo.filename)[1]
        if not file_ext:
            file_ext = '.jpg'
        filename = f"{current_user['id']}_{int(datetime.now().timestamp())}{file_ext}"
        new_photo_path = os.path.join(UPLOAD_DIR, filename).replace('\\', '/')
        
        with open(new_photo_path, "wb") as f:
            shutil.copyfileobj(photo.file, f)
            
        # 尝试删除旧照片
        if photo_path and os.path.exists(photo_path):
            try:
                os.remove(photo_path)
            except Exception:
                pass
        photo_path = new_photo_path
        
    cursor.execute('''
    UPDATE records 
    SET name = ?, nation = ?, id_card = ?, phone = ?, address = ?, job = ?, education = ?, region_auth = ?, gender = ?, age = ?, photo_path = ?
    WHERE id = ? AND user_id = ?
    ''', (name, nation, id_card, phone, address, job, education, region_auth, gender, age, photo_path, record_id, current_user['id']))
    
    conn.commit()
    conn.close()
    return {"code": 200, "message": "信息修改成功！"}

# 获取所有已审核通过且未删除用户的单位列表（去重，仅管理员）
@app.get("/api/admin/companies")
def get_approved_companies(admin = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT company FROM users WHERE role != 'admin' AND status = 'approved' AND company IS NOT NULL AND company != ''")
    companies = [row[0] for row in cursor.fetchall()]
    conn.close()
    return {"code": 200, "data": companies}

# 获取所有已审核通过用户的单位列表（公开接口，供答题页面使用）
@app.get("/api/companies")
def get_companies():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT company FROM users WHERE role != 'admin' AND status = 'approved' AND company IS NOT NULL AND company != ''")
    companies = [row[0] for row in cursor.fetchall()]
    conn.close()
    return {"code": 200, "data": companies}

# 查看所有已录入的信息（仅管理员，支持按日期区间筛选、工作单位筛选和门禁下载状态排序）
@app.get("/api/admin/records")
def get_all_records(start_date: str = None, end_date: str = None, company: str = None, name: str = None, admin = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    if company and company.strip():
        conditions.append("u.company = ?")
        params.append(company.strip())
        
    if name and name.strip():
        conditions.append("r.name LIKE ?")
        params.append(f"%{name.strip()}%")
    
    start = start_date.strip() if start_date and start_date.strip() else None
    end = end_date.strip() if end_date and end_date.strip() else None
    
    # 默认展示最近10天的数据，如果通过日历查询、输入名字搜索或按单位筛选，则不受此默认限制
    if not start and not end and not (name and name.strip()) and not (company and company.strip()):
        from datetime import timedelta
        today = datetime.now()
        ten_days_ago = today - timedelta(days=9)
        start = ten_days_ago.strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")
        
    if start:
        conditions.append("substr(r.created_at, 1, 10) >= ?")
        params.append(start)
        
    if end:
        conditions.append("substr(r.created_at, 1, 10) <= ?")
        params.append(end)
        
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
        
    query = f'''
    SELECT r.*, u.company as company, u.real_name as recorder_name
    FROM records r 
    LEFT JOIN users u ON r.user_id = u.id 
    {where_clause}
    ORDER BY r.is_gate_downloaded ASC, r.created_at DESC
    '''
    
    cursor.execute(query, params)
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"code": 200, "data": records}

# 门禁导出 - 仅 CSV 导入表 (并更新已下载状态)
@app.get("/api/admin/export/gate/csv")
def export_gate_csv(ids: str = None, admin = Depends(get_admin_user)):
    if not ids:
        raise HTTPException(status_code=400, detail="请选择需要下载的记录")
        
    id_list = [int(x) for x in ids.split(',') if x.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="没有勾选任何有效的人员记录")
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 获取选中的记录
    placeholders = ','.join(['?'] * len(id_list))
    cursor.execute(f'''
    SELECT r.*, u.company as company 
    FROM records r 
    LEFT JOIN users u ON r.user_id = u.id 
    WHERE r.id IN ({placeholders})
    ORDER BY r.is_gate_downloaded ASC, r.created_at DESC
    ''', id_list)
    records = cursor.fetchall()
    
    if not records:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到对应的记录")
        
    # 生成 CSV
    import io
    csv_output = io.StringIO()
    writer = csv.writer(csv_output)
    
    comments = [
        "・ *号为必填项；,,,,,,,,,\n",
        "・ 填写数字编码代替属性值；,,,,,,,,,\n",
        "・ 使用EXCEL编辑导入文件时，请将单元格的格式修改为文本格式，避免数字文本自动转换为科学计数文本；,,,,,,,,,\n",
        ",,,,,,,,,\n",
        "1、姓名*：1～32个字符；不能包含 ' / \\: * ? \" < > | 这些特殊字符；,,,,,,,,,\n",
        "2、性别*：1（男）、2（女）、0（未知）；,,,,,,,,,\n",
        "3、组织路径*：填写从选择导入 of 组织名称开始，至目标组织的完整名称路径；,,,,,,,,,\n",
        "4、证件类型*：111（身份证）、414（护照）、113（户口簿）、335（驾驶证）、131（工作证）、133（学生证）、114（军官证）、990（其他）；,,,,,,,,,\n",
        "5、证件号码*：1~20个字符；只允许输入数字和字母；,,,,,,,,,\n",
        "6、工号：1~32个字符；只允许输入数字、字母和汉字；,,,,,,,,,\n",
        "7、手机号码：1-20位数字；,,,,,,,,,\n",
        "8、拼音：人员姓名拼音；,,,,,,,,,\n",
        "9、所属区域：0 ～128个字符；不能包含 ' / \\ : * ? \" < > | 这些特殊字符；,,,,,,,,,\n",
        "10、卡号：8~20个字符；只允许输入数字和大写字母。,,,,,,,,,\n"
    ]
    
    template_path = '06.03.csv'
    if os.path.exists(template_path):
        try:
            with open(template_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
                header_index = 0
                for idx, line in enumerate(lines):
                    if '*姓名' in line:
                         header_index = idx
                         break
                comments = lines[:header_index]
        except Exception:
            pass
            
    csv_content = "".join(comments)
    csv_output.write(csv_content)
    writer.writerow(['*姓名', '*性别', '*组织路径', '*证件类型', '*证件号码', '工号', '手机号码', '拼音', '所属区域', '卡号'])
    
    for r in records:
        gender_code = '0'
        if r['gender'] == '男':
            gender_code = '1'
        elif r['gender'] == '女':
            gender_code = '2'
            
        org_path = f"{r['company']}/{r['region_auth']}" if r['region_auth'] else r['company']
        
        writer.writerow([
            r['name'],
            gender_code,
            org_path,
            '111',
            r['id_card'],
            '',
            r['phone'],
            '',
            r['region_auth'],
            ''
        ])
        
    csv_data = csv_output.getvalue().encode('gbk', errors='ignore')
    csv_output.close()
    
    # 将门禁下载状态更新为已下载(1)
    cursor.execute(f"UPDATE records SET is_gate_downloaded = 1 WHERE id IN ({placeholders})", id_list)
    conn.commit()
    conn.close()
    
    from fastapi import Response
    import urllib.parse
    
    safe_filename = urllib.parse.quote("培训人员导入表.csv")
    headers = {
        "Content-Disposition": f"attachment; filename*=utf-8''{safe_filename}"
    }
    return Response(content=csv_data, media_type="text/csv", headers=headers)

# 门禁导出 - 仅照片压缩包
@app.get("/api/admin/export/gate/photos")
def export_gate_photos(ids: str = None, admin = Depends(get_admin_user)):
    if not ids:
        raise HTTPException(status_code=400, detail="请选择需要下载的记录")
        
    id_list = [int(x) for x in ids.split(',') if x.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="没有勾选任何有效的人员记录")
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    placeholders = ','.join(['?'] * len(id_list))
    cursor.execute(f'''
    SELECT r.*, u.company as company 
    FROM records r 
    LEFT JOIN users u ON r.user_id = u.id 
    WHERE r.id IN ({placeholders})
    ORDER BY r.is_gate_downloaded ASC, r.created_at DESC
    ''', id_list)
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        raise HTTPException(status_code=404, detail="未找到对应的记录")
        
    import io
    import zipfile
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        added_filenames = set()
        for r in records:
            photo_path = r['photo_path']
            if not photo_path or not os.path.exists(photo_path):
                continue
                
            file_ext = os.path.splitext(photo_path)[1]
            if not file_ext:
                file_ext = '.jpg'
                
            safe_name = "".join([c for c in r['name'] if c not in r'\/:*?"<>|'])
            safe_id = "".join([c for c in r['id_card'] if c not in r'\/:*?"<>|'])
            base_filename = f"{safe_name}_{safe_id}"
            filename = f"{base_filename}{file_ext}"
            
            counter = 1
            while filename in added_filenames:
                filename = f"{base_filename}_{counter}{file_ext}"
                counter += 1
            added_filenames.add(filename)
            zip_file.write(photo_path, arcname=filename)
            
    from fastapi import Response
    import urllib.parse
    
    safe_filename = urllib.parse.quote("培训人员照片.zip")
    headers = {
        "Content-Disposition": f"attachment; filename*=utf-8''{safe_filename}"
    }
    return Response(content=zip_buffer.getvalue(), media_type="application/zip", headers=headers)

# 门禁下载旧版兼容接口 (CSV 导入表和照片打包，支持按 ids 筛选，并更新已下载状态)
@app.get("/api/admin/export/gate")
def export_gate_old_compatible(ids: str = None, admin = Depends(get_admin_user)):
    if not ids:
        raise HTTPException(status_code=400, detail="请选择需要下载的记录")
        
    id_list = [int(x) for x in ids.split(',') if x.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="没有勾选任何有效的人员记录")
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    placeholders = ','.join(['?'] * len(id_list))
    cursor.execute(f'''
    SELECT r.*, u.company as company 
    FROM records r 
    LEFT JOIN users u ON r.user_id = u.id 
    WHERE r.id IN ({placeholders})
    ORDER BY r.is_gate_downloaded ASC, r.created_at DESC
    ''', id_list)
    records = cursor.fetchall()
    
    if not records:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到对应的记录")
        
    import io
    csv_output = io.StringIO()
    writer = csv.writer(csv_output)
    comments = [
        "・ *号为必填项；,,,,,,,,,\n",
        "・ 填写数字编码代替属性值；,,,,,,,,,\n",
        "・ 使用EXCEL编辑导入文件时，请将单元格的格式修改为文本格式，避免数字文本自动转换为科学计数文本；,,,,,,,,,\n",
        ",,,,,,,,,\n",
        "1、姓名*：1～32个字符；不能包含 ' / \\: * ? \" < > | 这些特殊字符；,,,,,,,,,\n",
        "2、性别*：1（男）、2（女）、0（未知）；,,,,,,,,,\n",
        "3、组织路径*：填写从选择导入 of 组织名称开始，至目标组织的完整名称路径；,,,,,,,,,\n",
        "4、证件类型*：111（身份证）、414（护照）、113（户口簿）、335（驾驶证）、131（工作证）、133（学生证）、114（军官证）、990（其他）；,,,,,,,,,\n",
        "5、证件号码*：1~20个字符；只允许输入数字和字母；,,,,,,,,,\n",
        "6、工号：1~32个字符；只允许输入数字、字母和汉字；,,,,,,,,,\n",
        "7、手机号码：1-20位数字；,,,,,,,,,\n",
        "8、拼音：人员姓名拼音；,,,,,,,,,\n",
        "9、所属区域：0 ～128个字符；不能包含 ' / \\ : * ? \" < > | 这些特殊字符；,,,,,,,,,\n",
        "10、卡号：8~20个字符；只允许输入数字和大写字母。,,,,,,,,,\n"
    ]
    template_path = '06.03.csv'
    if os.path.exists(template_path):
        try:
            with open(template_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
                header_index = 0
                for idx, line in enumerate(lines):
                    if '*姓名' in line:
                         header_index = idx
                         break
                comments = lines[:header_index]
        except Exception:
            pass
    csv_content = "".join(comments)
    csv_output.write(csv_content)
    writer.writerow(['*姓名', '*性别', '*组织路径', '*证件类型', '*证件号码', '工号', '手机号码', '拼音', '所属区域', '卡号'])
    
    for r in records:
        gender_code = '0'
        if r['gender'] == '男':
            gender_code = '1'
        elif r['gender'] == '女':
            gender_code = '2'
        org_path = f"{r['company']}/{r['region_auth']}" if r['region_auth'] else r['company']
        writer.writerow([r['name'], gender_code, org_path, '111', r['id_card'], '', r['phone'], '', r['region_auth'], ''])
    csv_data = csv_output.getvalue().encode('gbk', errors='ignore')
    csv_output.close()
    
    import zipfile
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("培训人员导入表.csv", csv_data)
        added_filenames = set()
        for r in records:
            photo_path = r['photo_path']
            if not photo_path or not os.path.exists(photo_path):
                continue
            file_ext = os.path.splitext(photo_path)[1] or '.jpg'
            safe_name = "".join([c for c in r['name'] if c not in r'\/:*?"<>|'])
            safe_id = "".join([c for c in r['id_card'] if c not in r'\/:*?"<>|'])
            base_filename = f"{safe_name}_{safe_id}"
            filename = f"{base_filename}{file_ext}"
            counter = 1
            while filename in added_filenames:
                filename = f"{base_filename}_{counter}{file_ext}"
                counter += 1
            added_filenames.add(filename)
            zip_file.write(photo_path, arcname=filename)
            
    cursor.execute(f"UPDATE records SET is_gate_downloaded = 1 WHERE id IN ({placeholders})", id_list)
    conn.commit()
    conn.close()
    
    from fastapi import Response
    import urllib.parse
    safe_filename = urllib.parse.quote("门禁系统导入包.zip")
    headers = {
        "Content-Disposition": f"attachment; filename*=utf-8''{safe_filename}"
    }
    return Response(content=zip_buffer.getvalue(), media_type="application/zip", headers=headers)

# 导出并下载 Excel (按已有模板的格式，支持按 ids/日期区间 筛选)
@app.get("/api/admin/export/excel")
def export_excel(ids: str = None, start_date: str = None, end_date: str = None, company: str = None, name: str = None, admin = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    if company and company.strip():
        conditions.append("u.company = ?")
        params.append(company.strip())
        
    if name and name.strip():
        conditions.append("r.name LIKE ?")
        params.append(f"%{name.strip()}%")
    
    if ids:
        id_list = [int(x) for x in ids.split(',') if x.strip()]
        placeholders = ','.join(['?'] * len(id_list))
        conditions.append(f"r.id IN ({placeholders})")
        params.extend(id_list)
        
    start = start_date.strip() if start_date and start_date.strip() else None
    end = end_date.strip() if end_date and end_date.strip() else None
    
    if start and not end:
        end = start
    elif end and not start:
        start = end
        
    if start:
        conditions.append("substr(r.created_at, 1, 10) >= ?")
        params.append(start)
        
    if end:
        conditions.append("substr(r.created_at, 1, 10) <= ?")
        params.append(end)
        
    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
        
    query = f'''
    SELECT r.*, u.company as company 
    FROM records r 
    LEFT JOIN users u ON r.user_id = u.id 
    {where_clause}
    ORDER BY r.is_gate_downloaded ASC, r.created_at DESC
    '''
    
    cursor.execute(query, params)
    records = cursor.fetchall()
    conn.close()
    
    template_path = '06.03.xlsx'
    if not os.path.exists(template_path):
        # 如果模板不见了，则重新生成一个空的带表头的 Workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet1"
        ws.append([
            "姓名", "性别", "民族", "年龄", "身份证号码", "联系电话", "现常住地址", "公司名称", 
            "岗位/工种", "学历", "有效期限", "区域权限", "人员在各单位间流动情况", 
            "最近一次培训日期", "特殊工种证有效期", "备注"
        ])
    else:
        wb = openpyxl.load_workbook(template_path)
        ws = wb.active
        
    # 清空除第一行表头外的所有行（以防模板里有之前的数据）
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row)
        
    for r in records:
        row_data = [
            r['name'],
            r['gender'],
            r['nation'],
            r['age'],
            r['id_card'],
            r['phone'],
            r['address'],
            r['company'],
            r['job'],
            r['education'],
            "", # 有效期限
            "", # 区域权限
            "", # 流动情况
            "", # 最近一次培训日期
            "", # 特殊工种证有效期
            ""  # 备注
        ]
        ws.append(row_data)
        
    out_path = 'training_records_export.xlsx'
    wb.save(out_path)
    return FileResponse(out_path, filename="培训人员信息表.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# 导出并下载 CSV (按已有模板的格式)
@app.get("/api/admin/export/csv")
def export_csv(admin = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
    SELECT r.*, u.company as company 
    FROM records r 
    LEFT JOIN users u ON r.user_id = u.id 
    ORDER BY r.created_at DESC
    ''')
    records = cursor.fetchall()
    conn.close()
    
    out_path = 'training_records_export.csv'
    
    # 提取原有模板的注释
    comments = []
    template_path = '06.03.csv'
    if os.path.exists(template_path):
        try:
            with open(template_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
                header_index = 0
                for idx, line in enumerate(lines):
                    if '*姓名' in line:
                        header_index = idx
                        break
                comments = lines[:header_index]
        except Exception:
            pass
            
    if not comments:
        comments = [
            "・ *号为必填项；,,,,,,,,,\n",
            "・ 填写数字编码代替属性值；,,,,,,,,,\n",
            "・ 使用EXCEL编辑导入文件时，请将单元格的格式修改为文本格式，避免数字文本自动转换为科学计数文本；,,,,,,,,,\n",
            ",,,,,,,,,\n",
            "1、姓名*：1～32个字符；不能包含 ' / \\: * ? \" < > | 这些特殊字符；,,,,,,,,,\n",
            "2、性别*：1（男）、2（女）、0（未知）；,,,,,,,,,\n",
            "3、组织路径*：填写从选择导入的组织名称开始，至目标组织的完整名称路径；,,,,,,,,,\n",
            "4、证件类型*：111（身份证）、414（护照）、113（户口簿）、335（驾驶证）、131（工作证）、133（学生证）、114（军官证）、990（其他）；,,,,,,,,,\n",
            "5、证件号码*：1~20个字符；只允许输入数字和字母；,,,,,,,,,\n",
            "6、工号：1~32个字符；只允许输入数字、字母和汉字；,,,,,,,,,\n",
            "7、手机号码：1-20位数字；,,,,,,,,,\n",
            "8、拼音：人员姓名拼音；,,,,,,,,,\n",
            "9、所属区域：0 ～128个字符；不能包含 ' / \\ : * ? \" < > | 这些特殊字符；,,,,,,,,,\n",
            "10、卡号：8~20个字符；只允许输入数字和大写字母。,,,,,,,,,\n"
        ]
        
    with open(out_path, 'w', newline='', encoding='gbk', errors='ignore') as f:
        f.writelines(comments)
        writer = csv.writer(f)
        writer.writerow(['*姓名', '*性别', '*组织路径', '*证件类型', '*证件号码', '工号', '手机号码', '拼音', '所属区域', '卡号'])
        
        for r in records:
            gender_code = '0'
            if r['gender'] == '男':
                gender_code = '1'
            elif r['gender'] == '女':
                gender_code = '2'
                
            org_path = f"{r['company']}/{r['region_auth']}" if r['region_auth'] else r['company']
            
            writer.writerow([
                r['name'],
                gender_code,
                org_path,
                '111', # 证件类型 (身份证)
                r['id_card'],
                '', # 工号
                r['phone'],
                '', # 拼音
                r['region_auth'],
                ''  # 卡号
            ])
            
    return FileResponse(out_path, filename="培训人员导入表.csv", media_type="text/csv")

# 导出并下载照片压缩包（仅管理员）
@app.get("/api/admin/export/photos")
def export_photos(admin = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT photo_path, name, id_card FROM records")
    records = cursor.fetchall()
    conn.close()
    
    out_path = 'photos_export.zip'
    
    if os.path.exists(out_path):
        try:
            os.remove(out_path)
        except Exception:
            pass
            
    with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        added_filenames = set()
        for r in records:
            photo_path = r['photo_path']
            if not photo_path or not os.path.exists(photo_path):
                continue
            
            name = r['name']
            id_card = r['id_card']
            
            # 获取后缀名
            file_ext = os.path.splitext(photo_path)[1]
            if not file_ext:
                file_ext = '.jpg'
                
            # 过滤文件名中的非法字符
            safe_name = "".join([c for c in name if c not in r'\/:*?"<>|'])
            safe_id = "".join([c for c in id_card if c not in r'\/:*?"<>|'])
            
            base_filename = f"{safe_name}_{safe_id}"
            filename = f"{base_filename}{file_ext}"
            
            # 处理重复文件名
            counter = 1
            while filename in added_filenames:
                filename = f"{base_filename}_{counter}{file_ext}"
                counter += 1
                
            added_filenames.add(filename)
            zip_file.write(photo_path, arcname=filename)
            
    return FileResponse(out_path, filename="培训人员照片.zip", media_type="application/zip")

# 获取同单位的所有人员记录（供客户端检索并用于门禁恢复）
@app.get("/api/user/company_records")
def get_company_records(name: str = None, current_user = Depends(get_current_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = '''
    SELECT r.*, u.company as company, u.real_name as recorder_name
    FROM records r
    LEFT JOIN users u ON r.user_id = u.id
    WHERE u.company = ? AND (r.gate_restore_status IS NULL OR r.gate_restore_status != 'pending')
    '''
    params = [current_user['company']]
    
    if name and name.strip():
        query += " AND r.name LIKE ?"
        params.append(f"%{name.strip()}%")
        
    query += " ORDER BY r.created_at DESC"
    
    cursor.execute(query, params)
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"code": 200, "data": records}

# 提交门禁恢复申请（回复门禁）
@app.post("/api/user/record/restore_gate")
def restore_gate(ids: str = Form(...), current_user = Depends(get_current_user)):
    if not ids:
        raise HTTPException(status_code=400, detail="请选择需要恢复门禁的人员")
        
    id_list = [int(x) for x in ids.split(',') if x.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="没有勾选任何有效的人员记录")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 验证这些 records 都属于该用户所在的公司，防越权
    placeholders = ','.join(['?'] * len(id_list))
    check_query = f'''
    SELECT r.id FROM records r
    LEFT JOIN users u ON r.user_id = u.id
    WHERE r.id IN ({placeholders}) AND u.company = ?
    '''
    cursor.execute(check_query, id_list + [current_user['company']])
    allowed_ids = [row[0] for row in cursor.fetchall()]
    
    if len(allowed_ids) != len(id_list):
        conn.close()
        raise HTTPException(status_code=403, detail="部分记录不存在或无权操作")
        
    # 更新 records 的门禁恢复状态
    update_query = f'''
    UPDATE records
    SET gate_restore_status = 'pending', is_restore_downloaded = 0
    WHERE id IN ({placeholders})
    '''
    cursor.execute(update_query, id_list)
    conn.commit()
    conn.close()
    return {"code": 200, "message": "门禁恢复申请提交成功"}

# 查看所有提交了门禁恢复申请的人员记录（仅管理员）
@app.get("/api/admin/restore_records")
def get_restore_records(admin = Depends(get_admin_user)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT r.*, u.company as company, u.real_name as recorder_name
    FROM records r
    LEFT JOIN users u ON r.user_id = u.id
    WHERE r.gate_restore_status = 'pending'
    ORDER BY r.is_restore_downloaded ASC, r.created_at DESC
    ''')
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {"code": 200, "data": records}

# 门禁恢复导出 - 仅 CSV 导入表 (并更新 is_restore_downloaded)
@app.get("/api/admin/export/restore/csv")
def export_restore_csv(ids: str = None, admin = Depends(get_admin_user)):
    if not ids:
        raise HTTPException(status_code=400, detail="请选择需要下载的记录")
        
    id_list = [int(x) for x in ids.split(',') if x.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="没有勾选任何有效的人员记录")
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    placeholders = ','.join(['?'] * len(id_list))
    cursor.execute(f'''
    SELECT r.*, u.company as company 
    FROM records r 
    LEFT JOIN users u ON r.user_id = u.id 
    WHERE r.id IN ({placeholders}) AND r.gate_restore_status = 'pending'
    ORDER BY r.is_restore_downloaded ASC, r.created_at DESC
    ''', id_list)
    records = cursor.fetchall()
    
    if not records:
        conn.close()
        raise HTTPException(status_code=404, detail="未找到对应的恢复申请记录")
        
    import io
    csv_output = io.StringIO()
    writer = csv.writer(csv_output)
    
    comments = [
        "・ *号为必填项；,,,,,,,,,\n",
        "・ 填写数字编码代替属性值；,,,,,,,,,\n",
        "・ 使用EXCEL编辑导入文件时，请将单元格的格式修改为文本格式，避免数字文本自动转换为科学计数文本；,,,,,,,,,\n",
        ",,,,,,,,,\n",
        "1、姓名*：1～32个字符；不能包含 ' / \\: * ? \" < > | 这些特殊字符；,,,,,,,,,\n",
        "2、性别*：1（男）、2（女）、0（未知）；,,,,,,,,,\n",
        "3、组织路径*：填写从选择导入 of 组织名称开始，至目标组织的完整名称路径；,,,,,,,,,\n",
        "4、证件类型*：111（身份证）、414（护照）、113（户口簿）、335（驾驶证）、131（工作证）、133（学生证）、114（军官证）、990（其他）；,,,,,,,,,\n",
        "5、证件号码*：1~20个字符；只允许输入数字和字母；,,,,,,,,,\n",
        "6、工号：1~32个字符；只允许输入数字、字母和汉字；,,,,,,,,,\n",
        "7、手机号码：1-20位数字；,,,,,,,,,\n",
        "8、拼音：人员姓名拼音；,,,,,,,,,\n",
        "9、所属区域：0 ～128个字符；不能包含 ' / \\ : * ? \" < > | 这些特殊字符；,,,,,,,,,\n",
        "10、卡号：8~20个字符；只允许输入数字和大写字母。,,,,,,,,,\n"
    ]
    
    template_path = '06.03.csv'
    if os.path.exists(template_path):
        try:
            with open(template_path, 'r', encoding='gbk') as f:
                lines = f.readlines()
                header_index = 0
                for idx, line in enumerate(lines):
                    if '*姓名' in line:
                         header_index = idx
                         break
                comments = lines[:header_index]
        except Exception:
            pass
            
    csv_content = "".join(comments)
    csv_output.write(csv_content)
    writer.writerow(['*姓名', '*性别', '*组织路径', '*证件类型', '*证件号码', '工号', '手机号码', '拼音', '所属区域', '卡号'])
    
    for r in records:
        gender_code = '0'
        if r['gender'] == '男':
            gender_code = '1'
        elif r['gender'] == '女':
            gender_code = '2'
            
        org_path = f"{r['company']}/{r['region_auth']}" if r['region_auth'] else r['company']
        
        writer.writerow([
            r['name'],
            gender_code,
            org_path,
            '111',
            r['id_card'],
            '',
            r['phone'],
            '',
            r['region_auth'],
            ''
        ])
        
    csv_data = csv_output.getvalue().encode('gbk', errors='ignore')
    csv_output.close()
    
    # 将门禁恢复下载状态更新为已下载(1)
    cursor.execute(f"UPDATE records SET is_restore_downloaded = 1 WHERE id IN ({placeholders})", id_list)
    conn.commit()
    conn.close()
    
    from fastapi import Response
    import urllib.parse
    
    safe_filename = urllib.parse.quote("恢复人员导入表.csv")
    headers = {
        "Content-Disposition": f"attachment; filename*=utf-8''{safe_filename}"
    }
    return Response(content=csv_data, media_type="text/csv", headers=headers)

# 门禁恢复导出 - 仅照片压缩包
@app.get("/api/admin/export/restore/photos")
def export_restore_photos(ids: str = None, admin = Depends(get_admin_user)):
    if not ids:
        raise HTTPException(status_code=400, detail="请选择需要下载的记录")
        
    id_list = [int(x) for x in ids.split(',') if x.strip()]
    if not id_list:
        raise HTTPException(status_code=400, detail="没有勾选任何有效的人员记录")
        
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    placeholders = ','.join(['?'] * len(id_list))
    cursor.execute(f'''
    SELECT r.*, u.company as company 
    FROM records r 
    LEFT JOIN users u ON r.user_id = u.id 
    WHERE r.id IN ({placeholders}) AND r.gate_restore_status = 'pending'
    ORDER BY r.is_restore_downloaded ASC, r.created_at DESC
    ''', id_list)
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        raise HTTPException(status_code=404, detail="未找到对应的记录")
        
    import io
    import zipfile
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        added_filenames = set()
        for r in records:
            photo_path = r['photo_path']
            if not photo_path or not os.path.exists(photo_path):
                continue
                
            file_ext = os.path.splitext(photo_path)[1]
            if not file_ext:
                file_ext = '.jpg'
                
            safe_name = "".join([c for c in r['name'] if c not in r'\/:*?"<>|'])
            safe_id = "".join([c for c in r['id_card'] if c not in r'\/:*?"<>|'])
            base_filename = f"{safe_name}_{safe_id}"
            filename = f"{base_filename}{file_ext}"
            
            counter = 1
            while filename in added_filenames:
                filename = f"{base_filename}_{counter}{file_ext}"
                counter += 1
            added_filenames.add(filename)
            zip_file.write(photo_path, arcname=filename)
            
    from fastapi import Response
    import urllib.parse
    
    safe_filename = urllib.parse.quote("恢复人员照片.zip")
    headers = {
        "Content-Disposition": f"attachment; filename*=utf-8''{safe_filename}"
    }
    return Response(content=zip_buffer.getvalue(), media_type="application/zip", headers=headers)

# ---------------- 考试相关接口 ----------------

# 获取试题（无需登录）
@app.get("/api/get_questions")
def get_questions(file: str):
    if not is_exam_open():
        raise HTTPException(status_code=403, detail="当前非考试开放时间，禁止获取试卷")
    import os
    
    # 安全检查：防止路径遍历
    if '..' in file or '/' in file or '\\' in file:
        raise HTTPException(status_code=400, detail="非法文件名")
    
    # 构建完整路径
    shiti_dir = 'shiti'
    file_path = os.path.join(shiti_dir, file)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="试题文件不存在")
    
    try:
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active
        
        questions = []
        # 表头：题目类型、题目、解析、正确答案、答案A...
        # 跳过第一行表头，从第二行开始读取
        for row in ws.iter_rows(min_row=2, values_only=True):
            if len(row) >= 4 and row[1] and row[3]:
                question_text = str(row[1]).strip()
                
                # 仅返回题目，屏蔽正确答案以防前端网络拦截作弊
                question = {
                    "question": question_text
                }
                questions.append(question)
        
        return {"code": 200, "data": questions}
    except Exception as e:
        print(f"读取试题失败: {e}")
        raise HTTPException(status_code=500, detail="读取试题失败")

# 保存答题记录（防作弊后端判分）
@app.post("/api/save_exam_record")
def save_exam_record(data: dict):
    if not is_exam_open():
        raise HTTPException(status_code=403, detail="当前非考试开放时间，禁止提交答卷")
    try:
        name = data.get('name')
        company = data.get('company')
        exam_type = data.get('exam_type')
        duration = data.get('duration')
        user_answers = data.get('answers', [])  # 格式: [{"question": "xxx", "user_answer": "对/错"}]
        
        if not name or not company or not exam_type:
            raise HTTPException(status_code=400, detail="缺少必要信息")
            
        EXAM_FILE_MAP = {
            '普工': '普工试题(1).xlsx',
            '焊工': '焊工题库(1).xlsx',
            '探伤': '探伤.xlsx',
            '高处作业': '高处作业(1).xlsx',
            '吊装作业': '吊装作业.xlsx',
            '电工': '电工题库.xlsx',
            '叉车': '叉车工.xlsx'
        }
        
        file_name = EXAM_FILE_MAP.get(exam_type)
        if not file_name:
            raise HTTPException(status_code=400, detail="未知的考试类型")
            
        file_path = os.path.join('shiti', file_name)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="题库文件不存在")
            
        # 1. 在后端重新加载正确答案，确保防作弊安全性
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active
        shiti_answers = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            if len(row) >= 4 and row[1] and row[3]:
                question_text = str(row[1]).strip()
                ans = str(row[3]).strip()
                if ans in ['对', '正确', '√', 'T', 'True']:
                    ans = '对'
                elif ans in ['错', '错误', '×', 'F', 'False']:
                    ans = '错'
                shiti_answers[question_text] = ans
                
        # 2. 对比计分
        correct_count = 0
        details = []
        for ua in user_answers:
            q_text = ua.get('question', '').strip()
            user_ans = ua.get('user_answer', '').strip()
            correct_ans = shiti_answers.get(q_text, '')
            
            is_correct_bool = (user_ans == correct_ans) if correct_ans else False
            if is_correct_bool:
                correct_count += 1
                
            details.append({
                "question": q_text,
                "user_answer": user_ans,
                "correct_answer": correct_ans,
                "is_correct": 1 if is_correct_bool else 0
            })
            
        total_questions = len(user_answers)
        score = round((correct_count / total_questions) * 100) if total_questions > 0 else 0
        answered_count = len([a for a in user_answers if a.get('user_answer')])
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 删除同姓名、同单位、同考试科目的旧记录（级联删除详情表记录），以只保留最后一次答题记录
        cursor.execute('''
            SELECT id FROM exam_records 
            WHERE name = ? AND company = ? AND exam_type = ?
        ''', (name, company, exam_type))
        old_records = cursor.fetchall()
        for r in old_records:
            old_id = r[0]
            cursor.execute('DELETE FROM exam_details WHERE exam_record_id = ?', (old_id,))
            cursor.execute('DELETE FROM exam_records WHERE id = ?', (old_id,))
        
        # 插入答题记录
        cursor.execute('''
            INSERT INTO exam_records (name, company, exam_type, score, answered_count, correct_count, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, company, exam_type, score, answered_count, correct_count, duration))
        
        record_id = cursor.lastrowid
        
        # 插入答题详情
        for d in details:
            cursor.execute('''
                INSERT INTO exam_details (exam_record_id, question, user_answer, correct_answer, is_correct)
                VALUES (?, ?, ?, ?, ?)
            ''', (record_id, d["question"], d["user_answer"], d["correct_answer"], d["is_correct"]))
        
        conn.commit()
        conn.close()
        
        return {
            "code": 200, 
            "message": "答题记录保存成功",
            "data": {
                "score": score,
                "correct_count": correct_count,
                "answered_count": answered_count,
                "total_count": total_questions
            }
        }
    except Exception as e:
        print(f"保存答题记录失败: {e}")
        raise HTTPException(status_code=500, detail="保存答题记录与后端判分失败")

# 获取答题记录列表（管理员权限）
@app.get("/api/admin/exam_records")
def get_exam_records(company: str = '', exam_type: str = '', name: str = '', 
                     current_user = Depends(get_admin_user)):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM exam_records WHERE 1=1"
        params = []
        
        if company:
            query += " AND company LIKE ?"
            params.append(f"%{company}%")
        if exam_type:
            query += " AND exam_type = ?"
            params.append(exam_type)
        if name:
            query += " AND name LIKE ?"
            params.append(f"%{name}%")
        
        query += " ORDER BY created_at DESC"
        
        cursor.execute(query, params)
        records = cursor.fetchall()
        
        result = []
        for r in records:
            result.append({
                "id": r['id'],
                "name": r['name'],
                "company": r['company'],
                "exam_type": r['exam_type'],
                "score": r['score'],
                "answered_count": r['answered_count'],
                "correct_count": r['correct_count'],
                "duration": r['duration'],
                "created_at": r['created_at']
            })
        
        conn.close()
        
        return {"code": 200, "data": result}
    except Exception as e:
        print(f"获取答题记录失败: {e}")
        raise HTTPException(status_code=500, detail="获取答题记录失败")

# 获取答题详情（管理员权限）
@app.get("/api/admin/exam_record_detail/{record_id}")
def get_exam_record_detail(record_id: int, current_user = Depends(get_admin_user)):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 获取主记录
        cursor.execute("SELECT * FROM exam_records WHERE id = ?", (record_id,))
        record = cursor.fetchone()
        
        if not record:
            raise HTTPException(status_code=404, detail="答题记录不存在")
        
        # 获取详情
        cursor.execute("SELECT * FROM exam_details WHERE exam_record_id = ? ORDER BY id", (record_id,))
        details = cursor.fetchall()
        
        detail_list = []
        for d in details:
            detail_list.append({
                "question": d['question'],
                "user_answer": d['user_answer'],
                "correct_answer": d['correct_answer'],
                "is_correct": d['is_correct']
            })
        
        conn.close()
        
        return {"code": 200, "data": {
            "id": record['id'],
            "name": record['name'],
            "company": record['company'],
            "exam_type": record['exam_type'],
            "score": record['score'],
            "answered_count": record['answered_count'],
            "correct_count": record['correct_count'],
            "duration": record['duration'],
            "created_at": record['created_at'],
            "details": detail_list
        }}
    except HTTPException:
        raise
    except Exception as e:
        print(f"获取答题详情失败: {e}")
        raise HTTPException(status_code=500, detail="获取答题详情失败")

# ---------------- 静态页面路由 ----------------

# 托管 uploads 目录以查看照片
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/login.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/login", response_class=HTMLResponse)
def get_login():
    with open("static/login.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/client", response_class=HTMLResponse)
def get_client():
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    with open("static/client.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), headers=headers)

@app.get("/admin", response_class=HTMLResponse)
def get_admin():
    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0"
    }
    with open("static/admin.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), headers=headers)

# 获取考试配置（仅管理员）
@app.get("/api/admin/config")
def get_configs_api(admin = Depends(get_admin_user)):
    return {
        "code": 200,
        "data": {
            "exam_start_time": get_config('exam_start_time', '08:00:00')[:5],
            "exam_end_time": get_config('exam_end_time', '12:00:00')[:5]
        }
    }

# 修改考试配置（仅管理员）
@app.post("/api/admin/config")
def save_config_api(
    start_time: str = Form(...),
    end_time: str = Form(...),
    admin = Depends(get_admin_user)
):
    if len(start_time) == 5:
        start_time = f"{start_time}:00"
    if len(end_time) == 5:
        end_time = f"{end_time}:00"
        
    try:
        datetime.strptime(start_time, "%H:%M:%S")
        datetime.strptime(end_time, "%H:%M:%S")
    except ValueError:
        raise HTTPException(status_code=400, detail="时间格式不正确")
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO configs (key, value) VALUES ('exam_start_time', ?)", (start_time,))
        cursor.execute("INSERT OR REPLACE INTO configs (key, value) VALUES ('exam_end_time', ?)", (end_time,))
        conn.commit()
        return {"code": 200, "message": "配置保存成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {str(e)}")
    finally:
        conn.close()

# 考试页面（无需登录）
@app.get("/exam", response_class=HTMLResponse)
def get_exam():
    if not is_exam_open():
        start_str = get_config('exam_start_time', '08:00:00')[:5]
        end_str = get_config('exam_end_time', '12:00:00')[:5]
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>考试未开放</title>
            <style>
                body {{
                    background: #0f172a;
                    color: #e2e8f0;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                }}
                .card {{
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    padding: 40px;
                    border-radius: 16px;
                    text-align: center;
                    max-width: 420px;
                    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
                    backdrop-filter: blur(12px);
                }}
                .icon {{
                    font-size: 3.5rem;
                    margin-bottom: 20px;
                }}
                h1 {{
                    font-size: 1.6rem;
                    margin-bottom: 15px;
                    background: linear-gradient(to right, #f43f5e, #fb7185);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }}
                p {{
                    font-size: 0.95rem;
                    color: #94a3b8;
                    line-height: 1.6;
                    margin: 10px 0;
                }}
                .time-box {{
                    margin-top: 25px;
                    padding: 10px 20px;
                    background: rgba(56, 189, 248, 0.08);
                    border: 1px dashed rgba(56, 189, 248, 0.3);
                    border-radius: 8px;
                    font-weight: 600;
                    color: #38bdf8;
                    display: inline-block;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="icon">🚫</div>
                <h1>当前非考试开放时间</h1>
                <p>在线答题系统目前处于关闭状态。</p>
                <p>为防范乱答题和非考试时段的非授权提交，请在开放时段访问。</p>
                <div class="time-box">每天 {start_str} - {end_str}</div>
            </div>
        </body>
        </html>
        """, status_code=403)
        
    with open("static/exam.html", "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    # 启动服务器
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
