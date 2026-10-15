param(
    [string]$Region = 'us-east-1',
    [string]$Name = 'rgce-native',
    [int]$LocalPort = 9121,
    [switch]$ShowLogin,
    [switch]$WithLogin
)
$ErrorActionPreference = 'Stop'
if ($ShowLogin -or $WithLogin) {
    $loginJson = & aws secretsmanager get-secret-value --region $Region --secret-id "$Name/dashboard" --query SecretString --output text
    if ($LASTEXITCODE -ne 0) { throw 'Could not retrieve native Hermes login.' }
    $login = $loginJson | ConvertFrom-Json
    Write-Host "Username: $($login.username)"
    Write-Host "Password: $($login.password)"
    Write-Host 'This is the dashboard login, not your model-provider API key. Keep it private.'
    if (-not $WithLogin) { return }
}
$instanceId = & aws autoscaling describe-auto-scaling-groups --region $Region --auto-scaling-group-names $Name --query 'AutoScalingGroups[0].Instances[?LifecycleState==`InService`].InstanceId | [0]' --output text
if ($LASTEXITCODE -ne 0 -or $instanceId -eq 'None') { throw 'No native Hermes instance is running.' }
$pluginDirectory = 'C:\Program Files\Amazon\SessionManagerPlugin\bin'
if (Test-Path -LiteralPath $pluginDirectory) { $env:PATH = "$pluginDirectory;$env:PATH" }
Write-Host "Native Hermes: http://127.0.0.1:$LocalPort - choose ce-desk after signing in."
Write-Host 'Keep this tunnel open. Use -WithLogin to show the login and open the tunnel together; -ShowLogin shows only the login.'
& aws ssm start-session --region $Region --target $instanceId --document-name AWS-StartPortForwardingSession --parameters "portNumber=9120,localPortNumber=$LocalPort"
