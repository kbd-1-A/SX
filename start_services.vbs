
Set WshShell = CreateObject("WScript.Shell")
' 启动后端服务
WshShell.Run "cmd /c cd /d e:时序ackend & uvicorn app.main:app --port 8000", 1, False
' 等待2秒让后端启动
WScript.Sleep 3000
' 启动前端服务
WshShell.Run "cmd /c cd /d e:时序rontend & npm run dev", 1, False
