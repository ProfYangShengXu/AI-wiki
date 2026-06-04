%windir%\System32\WindowsPowerShell\v1.0\powershell.exe -Command "
$WS = New-Object -ComObject WScript.Shell;
$SC = $WS.CreateShortcut('C:\Users\45140\OneDrive\Desktop\StudyWiki-Agent.lnk');
$SC.TargetPath = 'C:\Users\45140\OneDrive\Desktop\code\AIwiki2.0\start_studywiki.bat';
$SC.WorkingDirectory = 'C:\Users\45140\OneDrive\Desktop\code\AIwiki2.0';
$SC.Description = 'StudyWiki-Agent 本地 Wiki 知识库';
$SC.WindowStyle = 1;
$SC.Save();
Write-Host '快捷方式已创建!'
"