
import subprocess
import time
import os

# 启动后端
print("启动后端服务...")
backend_proc = subprocess.Popen(
    ["uvicorn", "app.main:app", "--port", "8000"],
    cwd=r"e:时序ackend",
    shell=True,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print(f"后端PID: {backend_proc.pid}")

time.sleep(3)

# 启动前端
print("启动前端服务...")
frontend_proc = subprocess.Popen(
    "npm run dev",
    cwd=r"e:时序rontend",
    shell=True,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print(f"前端PID: {frontend_proc.pid}")

print("
两个服务已启动，按Ctrl+C停止
")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("正在停止服务...")
    backend_proc.terminate()
    frontend_proc.terminate()
