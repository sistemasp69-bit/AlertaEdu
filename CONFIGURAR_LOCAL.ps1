# AlertaEdu: configuracion LOCAL de PostgreSQL. No copia secretos a GitHub.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$projectRef = 'lwjnmebmotcnkjrhhbyl'
$projectUrl = 'https://lwjnmebmotcnkjrhhbyl.supabase.co'
$publishableKey = 'sb_publishable_uQVI9Ls7I2_Lod07SHYqZA_IQejwQM7'
$envPath = Join-Path $PSScriptRoot '.env'

Write-Host ''
Write-Host 'ALERTAEDU - Configurar Supabase' -ForegroundColor Cyan
Write-Host 'La contrasena solo se guarda en el archivo .env de ESTE equipo.'
Write-Host 'En Supabase usa Connect > Session pooler (IPv4, puerto 5432).'

# Preservar otros valores previos (Apps Script, Gmail, etc.) al reconfigurar PostgreSQL.
$settings = [ordered]@{}
if (Test-Path -LiteralPath $envPath) {
    foreach ($line in [System.IO.File]::ReadAllLines($envPath)) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            $settings[$Matches[1]] = $Matches[2]
        }
    }
}

$session = (Read-Host 'Pega URL Session pooler COMPLETA (o ENTER para conexion directa IPv6)').Trim()
$session = $session.Trim('"').Trim("'")
if ([string]::IsNullOrWhiteSpace($session)) {
    $hostUrl = 'db.' + $projectRef + '.supabase.co'
    $dbUser = 'postgres'
    $dbName = 'postgres'
    $dbPort = 5432
    Write-Host 'Se usara conexion directa IPv6. Si falla en Windows, usa Session pooler.' -ForegroundColor Yellow
} else {
    if ($session -notmatch '^postgres(?:ql)?://') {
        throw 'Eso no es una URL: pega postgresql://... desde Connect > Session pooler. No pegues solo la contrasena.'
    }
    $uri = $null
    if (-not [System.Uri]::TryCreate($session, [System.UriKind]::Absolute, [ref]$uri)) {
        throw 'La URL no tiene un formato valido. Copia Connection string completo desde Supabase.'
    }
    if ($uri.Host -notlike '*.pooler.supabase.com') {
        throw 'Selecciona Session pooler en Supabase, no Direct connection.'
    }
    $info = ($uri.UserInfo -split ':')[0]
    if ($info -ne ('postgres.' + $projectRef)) {
        throw 'La Session pooler no corresponde al proyecto AlertaEdu.'
    }
    if ($uri.Port -ne 5432) {
        throw 'Selecciona SESSION pooler (puerto 5432), no Transaction pooler.'
    }
    $hostUrl = $uri.Host
    $dbUser = $info
    $dbName = $uri.AbsolutePath.TrimStart('/')
    if ([string]::IsNullOrWhiteSpace($dbName)) { $dbName = 'postgres' }
    $dbPort = 5432
}

$secret = Read-Host 'Ahora CONTRASENA real de PostgreSQL (escritura oculta)' -AsSecureString
$bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
try { $dbPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
if ([string]::IsNullOrWhiteSpace($dbPassword)) { throw 'No se ingreso la contrasena.' }
if ($dbPassword -match '(?i)YOUR-|YOUR_|\[.*PASSWORD.*\]|^PON_') {
    throw 'Has introducido un marcador de ejemplo, no la contrasena real.'
}
$dbUrl = 'postgresql://' + $dbUser + ':' + [Uri]::EscapeDataString($dbPassword) + '@' + $hostUrl + ':' + $dbPort + '/' + $dbName + '?sslmode=require'

$settings['SUPABASE_URL'] = $projectUrl
$settings['SUPABASE_PUBLISHABLE_KEY'] = $publishableKey
$settings['DATABASE_URL'] = $dbUrl
$settings['ALERTAEDU_BASE_URL'] = 'http://127.0.0.1:8000'
$settings['ALERTAEDU_ENV'] = 'development'
$settings['ALERTAEDU_SEED_DEMO'] = '0'

$gmail = (Read-Host 'Gmail remitente OPCIONAL (Enter para conservar correo anterior)').Trim()
if ($gmail) {
    $gmailSecret = Read-Host 'Contrasena de APLICACION de Gmail (oculta)' -AsSecureString
    $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($gmailSecret)
    try { $gmailPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    if ([string]::IsNullOrWhiteSpace($gmailPassword)) { throw 'No se ingreso la contrasena de aplicacion Gmail.' }
    $settings['ALERTAEDU_SMTP_USER'] = $gmail
    $settings['ALERTAEDU_SMTP_APP_PASSWORD'] = $gmailPassword.Replace(' ', '')
    $settings['ALERTAEDU_EMAIL_PROVIDER'] = 'gmail'
}

$lines = New-Object 'System.Collections.Generic.List[string]'
foreach ($key in $settings.Keys) { $lines.Add($key + '=' + $settings[$key]) }
[System.IO.File]::WriteAllText($envPath, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
Write-Host ''
Write-Host 'OK: .env actualizado en tu computadora (no compartir).' -ForegroundColor Green
Write-Host 'Ahora ejecuta: python VERIFICAR_CONEXION.py'
Write-Host 'Si sale OK, inicia con: .\\INICIAR_WINDOWS.bat'
