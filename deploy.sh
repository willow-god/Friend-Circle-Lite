#!/bin/bash

# 获取当前脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 定义日志文件路径
# CRON_LOG_FILE="$SCRIPT_DIR/cron_grab.log"
# API_LOG_FILE="$SCRIPT_DIR/api_grab.log"

# # 定义要执行的命令
# COMMAND="python3 $SCRIPT_DIR/run.py"

# # 定义定时任务的执行间隔（例如每四小时一次）
# INTERVAL="4"

# 添加定时任务到 crontab
# (crontab -l 2>/dev/null; echo "0 */$INTERVAL * * * $COMMAND >> $CRON_LOG_FILE 2>&1 && echo '运行成功'") | crontab -

# echo "===================================="
# echo "定时爬取 成功设置，时间间隔：4h"
# echo "定时任务日志：$CRON_LOG_FILE"
# echo "===================================="



#!/bin/bash

# 获取当前脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 定义 API 服务的启动命令
API_COMMAND="python3 $SCRIPT_DIR/server.py"

echo "===================================="

# 后台运行服务端，将数据映射到API
echo "****正在启动API服务****"
nohup $API_COMMAND &>/dev/null &
API_PID=$!
sleep 5  # 等待API服务启动，可能需要调整等待时间

echo "API 服务已启动：http://localhost:1223"
echo "API 服务进程号：$API_PID"
echo "API 服务关闭命令：kill -9 $API_PID"
echo "文档地址：https://blog.liushen.fun/posts/4dc716ec/"
echo "===================================="

# 用户选择是否执行爬取
read -p "选择操作：0 - 退出, 1 - 执行一次爬取: " USER_CHOICE

if [ "$USER_CHOICE" -eq 1 ]; then
    echo "****正在执行一次爬取****"
    python3 $SCRIPT_DIR/run.py
    echo "****爬取成功****"
else
    echo "退出选项被选择，掰掰！"

echo "===================================="
echo "定时抓取的部分请自行设置，如果有宝塔等面板可以按照说明直接添加，如果没有宝塔可以查看本脚本上面屏蔽的部分，自行添加到 crontab 中"
echo "===================================="

fi
