# Open an SSM tunnel to the RemediGenius Community Edition (RemediGenius-CE) dashboard on the Spot instance.
param(
    [string]$Region = 'us-east-1',
    [string]$Name = 'remedigenius-ce',
    [int]$LocalPort = 9125,
    [switch]$ShowLogin,
    [switch]$WithLogin,
    # Community Hermes WebUI (MIT, https://github.com/nesquena/hermes-webui), same login; not maintained by RemediGenius.
    [switch]$WebUI
)
if ($WebUI -and -not $PSBoundParameters.ContainsKey('LocalPort')) { $LocalPort = 9126 }
$remotePort = if ($WebUI) { 8787 } else { 9120 }
$ErrorActionPreference = 'Stop'
$instanceId = & aws autoscaling describe-auto-scaling-groups --region $Region --auto-scaling-group-names $Name --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId | [0]' --output text
if ($LASTEXITCODE -ne 0 -or $instanceId -eq 'None') { throw 'No RemediGenius-CE instance is running. Start the stack and wait for SSM.' }
$pluginDirectory = 'C:\Program Files\Amazon\SessionManagerPlugin\bin'
if (Test-Path -LiteralPath $pluginDirectory) { $env:PATH = "$pluginDirectory;$env:PATH" }
if ($ShowLogin -or $WithLogin) {
    Write-Host 'Private dashboard credentials follow. Keep them out of chat and screenshots. Your organization may log SSM sessions.'
    & aws ssm start-session --region $Region --target $instanceId --document-name AWS-StartInteractiveCommand --parameters 'command="sudo cat /data/hermes/remedigenius-login.json"'
    if ($LASTEXITCODE -ne 0) { throw 'Could not retrieve the dashboard login through SSM.' }
    if (-not $WithLogin) { return }
}
if ($WebUI) {
    Write-Host "Hermes WebUI (community project, MIT, github.com/nesquena/hermes-webui): http://127.0.0.1:$LocalPort/  (same password)"
} else {
    Write-Host "RemediGenius-CE: http://127.0.0.1:$LocalPort/chat?profile=remedigenius"
}
Write-Host 'Keep this tunnel open. -WithLogin shows the login and opens the tunnel; -ShowLogin shows only the login; -WebUI opens the WebUI instead of the dashboard.'
& aws ssm start-session --region $Region --target $instanceId --document-name AWS-StartPortForwardingSession --parameters "portNumber=$remotePort,localPortNumber=$LocalPort"

