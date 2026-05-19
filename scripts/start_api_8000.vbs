Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "E:\AI_Project\opencode_workspace\KB1"
WshShell.Run """C:\Python314\pythonw.exe"" ""E:\AI_Project\opencode_workspace\KB1\scripts\serve_api_runner.py""", 0, False
