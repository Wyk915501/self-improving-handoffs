# handoff_toast.ps1 - Windows toast with optional jump buttons.
# ASCII-only file; all text arrives via environment variables:
#   HN_TITLE, HN_BODY            toast title / body (body may contain newlines)
#   HN_BUTTON                    label of the dismiss button (default "OK")
#   HN_PERSIST                   "1" = reminder scenario (stays until dismissed); anything else = normal toast
#   HN_BTN1_LABEL / HN_BTN1_ARG  optional buttons 1..3: label + URI opened on click (protocol activation)
#   HN_APPID                     optional AppUserModelID to send as; falls back to PowerShell's own id if it fails
# Exit 0 = handed to the OS; non-zero = not delivered.
$ErrorActionPreference = 'Stop'
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    function Esc([string]$s) { if ($null -eq $s) { return '' } return [System.Security.SecurityElement]::Escape($s) }

    $title   = Esc $env:HN_TITLE
    $body    = Esc $env:HN_BODY
    $dismiss = Esc $(if ($env:HN_BUTTON) { $env:HN_BUTTON } else { 'OK' })
    $scenario = if ($env:HN_PERSIST -eq '1') { ' scenario="reminder"' } else { '' }

    $actions = ''
    foreach ($i in 1, 2, 3) {
        $label = (Get-Item -Path ('env:HN_BTN{0}_LABEL' -f $i) -ErrorAction SilentlyContinue).Value
        $arg = (Get-Item -Path ('env:HN_BTN{0}_ARG' -f $i) -ErrorAction SilentlyContinue).Value
        if ($label -and $arg) {
            $actions += '<action content="' + (Esc $label) + '" arguments="' + (Esc $arg) + '" activationType="protocol"/>'
        }
    }
    $actions += '<action content="' + $dismiss + '" arguments="dismiss" activationType="system"/>'

    $xml = '<toast' + $scenario + '><visual><binding template="ToastGeneric">' +
           '<text>' + $title + '</text>' +
           '<text hint-maxLines="6">' + $body + '</text>' +
           '</binding></visual><actions>' + $actions + '</actions></toast>'

    $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $doc.LoadXml($xml)
    $toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
    $fallback = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    if ($env:HN_APPID) {
        try {
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:HN_APPID).Show($toast)
            exit 0
        } catch {
            $toast = [Windows.UI.Notifications.ToastNotification]::new($doc)  # a shown toast cannot be reused
        }
    }
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($fallback).Show($toast)
    exit 0
} catch {
    Write-Error $_
    exit 1
}
