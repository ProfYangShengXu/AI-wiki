$desktop = [Environment]::GetFolderPath('Desktop')
$project = "C:\Users\45140\OneDrive\Desktop\code\AIwiki2.0"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$desktop\StudyWiki-Agent.lnk")
$Shortcut.TargetPath = "$project\StudyWiki-Agent.bat"
$Shortcut.WorkingDirectory = $project
$Shortcut.Description = "StudyWiki-Agent - 本地 Wiki 知识库 AI Agent"
$Shortcut.WindowStyle = 1
$Shortcut.Save()

Write-Host "快捷方式已创建: $desktop\StudyWiki-Agent.lnk"
