Set WshShell = CreateObject("WScript.Shell")
batPath = "c:\Users\finan\OneDrive\READET~1\AU6E27~1\INICIA~1.BAT"
WshShell.Run "cmd /c """ & batPath & """", 0, False
