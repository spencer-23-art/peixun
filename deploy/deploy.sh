#!/bin/bash
set -e

REPO_URL="$1"
BRANCH="${2:-main}"
PROJECT_DIR="/root/peixun"

echo "===== 培训系统一键部署脚本 ====="
echo ""

# ---------- 1. 系统依赖 ----------
echo "[1/7] 安装系统依赖..."
apt update -y
apt install -y python3 python3-pip git redis-server libgl1-mesa-glx libglib2.0-0

# ---------- 2. 拉取代码 ----------
echo "[2/7] 同步代码..."
if [ -d "$PROJECT_DIR/.git" ]; then
    echo "  项目已存在，执行 git pull..."
    cd "$PROJECT_DIR"
    git pull origin "$BRANCH"
else
    if [ -z "$REPO_URL" ]; then
        echo "错误: 首次部署需要提供 GitHub 仓库地址"
        echo "用法: bash deploy.sh https://github.com/你的用户名/peixun.git [分支名]"
        exit 1
    fi
    echo "  首次部署，克隆仓库..."
    git clone -b "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
    cd "$PROJECT_DIR"
fi

# ---------- 3. Python 依赖 ----------
echo "[3/7] 安装 Python 依赖..."
pip3 install -r requirements.txt

# ---------- 4. 创建必要目录 ----------
echo "[4/7] 创建数据目录..."
mkdir -p uploads/temp_ids
mkdir -p uploads/cards
mkdir -p shiti

# ---------- 5. 确保 Redis 已启动 ----------
echo "[5/7] 启动 Redis..."
systemctl enable redis-server
systemctl start redis-server
echo "  Redis 状态: $(systemctl is-active redis-server)"

# ---------- 6. 安装 systemd 服务 ----------
echo "[6/7] 安装 systemd 服务..."
cp deploy/peixun-celery.service /etc/systemd/system/
cp deploy/peixun-web.service    /etc/systemd/system/
systemctl daemon-reload
systemctl enable peixun-celery
systemctl enable peixun-web
systemctl restart peixun-celery
sleep 3
systemctl restart peixun-web

# ---------- 7. 检查状态 ----------
echo ""
echo "[7/7] 服务状态检查:"
echo "---------------------------------------"
echo "Redis:         $(systemctl is-active redis-server)"
echo "Celery Worker: $(systemctl is-active peixun-celery)"
echo "FastAPI Web:   $(systemctl is-active peixun-web)"
echo "---------------------------------------"
echo ""
echo "===== 部署完成！====="
echo ""
echo "常用命令:"
echo "  查看状态:     systemctl status peixun-web"
echo "  查看Web日志:  journalctl -u peixun-web -f"
echo "  查看OCR日志:  journalctl -u peixun-celery -f"
echo "  重启Web:      systemctl restart peixun-web"
echo "  重启Celery:   systemctl restart peixun-celery"
echo "  停止全部:     systemctl stop peixun-web peixun-celery"
echo ""
echo "  更新代码后:   cd /root/peixun && git pull && systemctl restart peixun-celery peixun-web"
echo ""
echo "服务已设置为开机自动启动。访问地址: http://$(hostname -I | awk '{print $1}'):8000"
