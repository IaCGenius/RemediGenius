# Open an SSM tunnel to the RemediGenius Community Edition (RemediGenius-CE) dashboard on the Spot instance.
param(
    [string]$Region = 'us-east-1',
    [string]$Name = 'remedigenius-ce',
    [int]$LocalPort = 9125,
    [switch]$ShowLogin,
    [switch]$WithLogin
)
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
Write-Host "RemediGenius-CE: http://127.0.0.1:$LocalPort/chat?profile=remedigenius"
Write-Host 'Keep this tunnel open. Use -WithLogin to show the login and open the tunnel together; -ShowLogin shows only the login.'
& aws ssm start-session --region $Region --target $instanceId --document-name AWS-StartPortForwardingSession --parameters "portNumber=9120,localPortNumber=$LocalPort"

