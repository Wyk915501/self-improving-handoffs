# Run in PowerShell (not Git Bash). Replace <PYTHON>, <DOCS>, <CONFIG_DIR>. Times are MACHINE-LOCAL: check your OS timezone first.
$py = '<PYTHON>'
$dir = '<DOCS>\规范\交接写时门'
$tbl = '<DOCS>\工作传递\协作教训.md'
$wt = '<DOCS>\工作传递'
$docs = '<DOCS>'
$s = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -StartWhenAvailable
$aDaily = New-ScheduledTaskAction -Execute $py -Argument ('-X utf8 "' + $dir + '\handoff_lessons.py" daily "' + $tbl + '" --docs "' + $docs + '" --config-dir "<CONFIG_DIR>"') -WorkingDirectory $docs
$tDaily = New-ScheduledTaskTrigger -Daily -At 21:00   # = Beijing 09:00 when the machine runs UTC-4; adjust
Register-ScheduledTask -TaskName 'HandoffDaily' -Action $aDaily -Trigger $tDaily -Settings $s -Force | Out-Null
$aNotify = New-ScheduledTaskAction -Execute $py -Argument ('-X utf8 "' + $dir + '\handoff_notify.py" check "' + $tbl + '" --with-scan "' + $wt + '" --scan-hours 8') -WorkingDirectory $docs
$tNotify = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours(8) -RepetitionInterval (New-TimeSpan -Hours 4) -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask -TaskName 'HandoffNotify' -Action $aNotify -Trigger $tNotify -Settings $s -Force | Out-Null
Get-ScheduledTask -TaskName 'Handoff*' | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; '{0} next={1}' -f $_.TaskName, $i.NextRunTime }
