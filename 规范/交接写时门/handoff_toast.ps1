# handoff_toast.ps1 - Windows toast with optional jump buttons.
# ASCII-only file; all text arrives via environment variables:
#   HN_XML                       complete toast XML built by the caller (handoff_notify.build_toast_xml); when set,
#                                the legacy variables below are ignored. When NOT set, behaviour is byte-for-byte the
#                                old one (external callers such as antd_scan.py keep working unchanged).
#   HN_TITLE, HN_BODY            toast title / body (body may contain newlines)            [legacy]
#   HN_BUTTON                    label of the dismiss button (default "OK")                 [legacy]
#   HN_PERSIST                   "1" = reminder scenario (stays until dismissed)            [legacy]
#   HN_BTN1_LABEL / HN_BTN1_ARG  optional buttons 1..3: label + URI opened on click        [legacy]
#   HN_APPID                     optional AppUserModelID to send as; falls back to PowerShell's own id if it fails
#   HN_TAG / HN_GROUP            optional: a newer toast with the same tag+group replaces the older one (<=63 chars)
#   HN_EXPIRE_MIN                optional: minutes until the toast leaves Action Center
#   HN_SUPPRESS                  optional: "1" = go straight to Action Center without a banner
#   HN_DRYRUN_OUT                tests only: parse the XML with the same parser (invalid XML exits 1), then write it
#                                (UTF-8) to this path and exit 0 without showing anything
# Exit 0 = handed to the OS; non-zero = not delivered. Decoration failures (tag/expiry) never block delivery.
$ErrorActionPreference = 'Stop'
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    function Esc([string]$s) { if ($null -eq $s) { return '' } return [System.Security.SecurityElement]::Escape($s) }

    if ($env:HN_XML) {
        $xml = $env:HN_XML
    } else {
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
    }

    $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
    $doc.LoadXml($xml)
    if ($env:HN_DRYRUN_OUT) {
        [IO.File]::WriteAllText($env:HN_DRYRUN_OUT, $xml, (New-Object Text.UTF8Encoding $false))
        exit 0
    }

    function Decorate($t) {
        try {
            if ($env:HN_TAG) { $tg = $env:HN_TAG; if ($tg.Length -gt 63) { $tg = $tg.Substring(0, 63) }; $t.Tag = $tg }
            if ($env:HN_GROUP) { $gp = $env:HN_GROUP; if ($gp.Length -gt 63) { $gp = $gp.Substring(0, 63) }; $t.Group = $gp }
            if ($env:HN_EXPIRE_MIN) { $t.ExpirationTime = [DateTimeOffset]::Now.AddMinutes([int]$env:HN_EXPIRE_MIN) }
            if ($env:HN_SUPPRESS -eq '1') { $t.SuppressPopup = $true }
        } catch { }
    }

    $toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
    Decorate $toast
    $fallback = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    if ($env:HN_APPID) {
        try {
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:HN_APPID).Show($toast)
            exit 0
        } catch {
            $toast = [Windows.UI.Notifications.ToastNotification]::new($doc)  # a shown toast cannot be reused
            Decorate $toast
        }
    }
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($fallback).Show($toast)
    exit 0
} catch {
    Write-Error $_
    exit 1
}
