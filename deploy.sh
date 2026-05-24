#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SCRIPT_DIR" || exit 1

python3 run.py

mkdir -p pages
cp -r main static all.json errors.json pages/

echo "===================================="
echo "静态文件已生成到 pages/ 目录"
echo "请将 pages/ 目录作为静态网站根目录部署"
echo "部署后检查 /all.json 是否可访问"
echo "===================================="
