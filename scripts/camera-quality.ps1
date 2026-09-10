# Uses the existing DPAPI camera account; never prints credentials or SOAP bodies.
[CmdletBinding()]
param([switch]$Apply, [string]$DataRoot='C:\Alex\data\tapo-cat-monitor')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$catCamera=Get-Content (Join-Path $DataRoot 'camera.json') -Raw | ConvertFrom-Json
$catCredential=Import-Clixml (Join-Path $env:LOCALAPPDATA 'TapoCatMonitor\camera.credential.xml')
$catHostAddress=[System.Net.IPAddress]::Parse([string]$catCamera.ip).ToString()
$catDeviceUrl="http://${catHostAddress}:2020/onvif/device_service"
function Invoke-CameraSoap([string]$Url,[string]$Body) {
    $catNonce=[Guid]::NewGuid().ToByteArray()
    $catCreated=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
    $catPassword=$catCredential.GetNetworkCredential().Password
    $catBytes=$catNonce+[Text.Encoding]::UTF8.GetBytes($catCreated+$catPassword)
    $catHasher=[Security.Cryptography.SHA1]::Create()
    try { $catDigest=[Convert]::ToBase64String($catHasher.ComputeHash($catBytes)) } finally { $catHasher.Dispose() }
    $catUser=[Security.SecurityElement]::Escape($catCredential.UserName)
    $catNonceText=[Convert]::ToBase64String($catNonce)
    $catEnvelope=@"
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema"><s:Header><wsse:Security s:mustUnderstand="1" xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"><wsse:UsernameToken><wsse:Username>$catUser</wsse:Username><wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">$catDigest</wsse:Password><wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">$catNonceText</wsse:Nonce><wsu:Created xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">$catCreated</wsu:Created></wsse:UsernameToken></wsse:Security></s:Header><s:Body>$Body</s:Body></s:Envelope>
"@
    try {
        $catResponse=Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Post -ContentType 'application/soap+xml; charset=utf-8' -Body $catEnvelope -TimeoutSec 15
        $catDocument=[xml]$catResponse.Content
        if ($catDocument.SelectSingleNode("//*[local-name()='Fault']")) { throw 'Camera SOAP fault' }
        return $catDocument
    } catch { throw 'Camera ONVIF request failed. Use Tapo Camera Settings > Video & Display > Video Quality > 2K QHD (4MP), then verify the live stream.' }
    finally { $catPassword=$null; $catBytes=$null; $catEnvelope=$null }
}
try {
    $catCapabilities=Invoke-CameraSoap $catDeviceUrl '<tds:GetCapabilities><tds:Category>Media</tds:Category></tds:GetCapabilities>'
    $catMediaUrl=$catCapabilities.SelectSingleNode("//*[local-name()='Media']/*[local-name()='XAddr']").InnerText
    if (([uri]$catMediaUrl).Host -ne $catHostAddress) { throw 'Camera returned an unexpected media host.' }
    $catConfigurations=Invoke-CameraSoap $catMediaUrl '<trt:GetVideoEncoderConfigurations/>'
    $catConfiguration=$catConfigurations.SelectNodes("//*[local-name()='Configurations']") | Where-Object { $_.SelectSingleNode("*[local-name()='Encoding']").InnerText -eq 'H264' } | Sort-Object { [int]$_.SelectSingleNode("*[local-name()='Resolution']/*[local-name()='Width']").InnerText } -Descending | Select-Object -First 1
    if (!$catConfiguration) { throw 'No H264 encoder configuration found.' }
    $catToken=[Security.SecurityElement]::Escape($catConfiguration.GetAttribute('token'))
    $catOptions=Invoke-CameraSoap $catMediaUrl "<trt:GetVideoEncoderConfigurationOptions><trt:ConfigurationToken>$catToken</trt:ConfigurationToken></trt:GetVideoEncoderConfigurationOptions>"
    $catResolutions=@($catOptions.SelectNodes("//*[local-name()='H264']/*[local-name()='ResolutionsAvailable']") | ForEach-Object { @{width=[int]$_.SelectSingleNode("*[local-name()='Width']").InnerText;height=[int]$_.SelectSingleNode("*[local-name()='Height']").InnerText} })
    $catBefore=@{width=[int]$catConfiguration.SelectSingleNode("*[local-name()='Resolution']/*[local-name()='Width']").InnerText;height=[int]$catConfiguration.SelectSingleNode("*[local-name()='Resolution']/*[local-name()='Height']").InnerText;fps=[int]$catConfiguration.SelectSingleNode("*[local-name()='RateControl']/*[local-name()='FrameRateLimit']").InnerText}
    if ($Apply) {
        if (!($catResolutions | Where-Object { $_.width -eq 2560 -and $_.height -eq 1440 })) { throw 'Camera does not advertise 2560x1440 via ONVIF. Set Video Quality in Tapo and verify.' }
        $catFpsMax=[int]$catOptions.SelectSingleNode("//*[local-name()='H264']/*[local-name()='FrameRateRange']/*[local-name()='Max']").InnerText
        if ($catFpsMax -lt 15) { throw 'Camera encoder does not advertise 15 fps.' }
        $catConfiguration.SelectSingleNode("*[local-name()='Resolution']/*[local-name()='Width']").InnerText='2560'
        $catConfiguration.SelectSingleNode("*[local-name()='Resolution']/*[local-name()='Height']").InnerText='1440'
        $catConfiguration.SelectSingleNode("*[local-name()='RateControl']/*[local-name()='FrameRateLimit']").InnerText='15'
        $catNew=$catConfigurations.CreateElement('trt','Configuration','http://www.onvif.org/ver10/media/wsdl')
        foreach ($catAttr in $catConfiguration.Attributes) { $catNew.SetAttribute($catAttr.Name,$catAttr.Value) }
        foreach ($catChild in $catConfiguration.ChildNodes) { $null=$catNew.AppendChild($catChild.CloneNode($true)) }
        $null=Invoke-CameraSoap $catMediaUrl ('<trt:SetVideoEncoderConfiguration>'+$catNew.OuterXml+'<trt:ForcePersistence>true</trt:ForcePersistence></trt:SetVideoEncoderConfiguration>')
        Write-Output 'Requested 2560x1440 at 15 fps. Verify completed source clips with ffprobe.'
    }
    @{before=$catBefore;supported_resolutions=$catResolutions;applied=[bool]$Apply} | ConvertTo-Json -Depth 4
} finally { $catCredential=$null }
