Set ws = CreateObject("WScript.Shell")
ws.Run "powershell -Command ""Start-Process cmd -ArgumentList '/c cd /d """"C:\Users\wurf7\Documents\Programmering\tts-windows"""" && .venv\Scripts\pythonw.exe tray.py' -Verb RunAs""", 0
