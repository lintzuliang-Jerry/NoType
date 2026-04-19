Dim fso, dir, shell
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.Run "cmd /c """ & dir & "\run.bat""", 0, False
