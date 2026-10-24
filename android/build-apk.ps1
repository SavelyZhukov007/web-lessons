<#
 Сборка debug APK на Windows (PowerShell 5+):
   powershell -ExecutionPolicy Bypass -File .\build-apk.ps1 [-Install] [-ServerUrl http://192.168.1.50:8000] [-JavaHome <JDK21>] [-SdkRoot <Sdk>] [-InstallSdkPackages] [-CheckOnly]
 JDK 21+ и Android SDK ищутся автоматически (scripts/env.mjs): JAVA_HOME (если >=21), C:\Program Files\Eclipse Adoptium\jdk-21*, Microsoft, Zulu, Android Studio jbr...
 JAVA_HOME выставляется ТОЛЬКО для процесса сборки — системный JDK 17 не трогаем.
 -Install  после сборки ставит APK на подключённое устройство/эмулятор через adb.
#>
param(
  [string]$JavaHome,
  [string]$SdkRoot,
  [string]$ServerUrl,
  [switch]$Install,
  [switch]$InstallSdkPackages,
  [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if ($JavaHome) { $env:JAVA_HOME = $JavaHome }
if ($SdkRoot)  { $env:ANDROID_HOME = $SdkRoot; $env:ANDROID_SDK_ROOT = $SdkRoot }
if ($ServerUrl) { $env:APP_DEFAULT_SERVER = $ServerUrl }

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Не найден node. Нужен Node.js 22+ (https://nodejs.org)." }
$nodeMajor = [int](node -p "process.versions.node.split('.')[0]")
if ($nodeMajor -lt 22) { throw "Нужен Node.js 22+ (сейчас $(node -v))." }

if ($InstallSdkPackages) {
  $sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
  $sm = Join-Path $sdk 'cmdline-tools\latest\bin\sdkmanager.bat'
  if (-not (Test-Path $sm)) { throw "Нет $sm — поставь 'Android SDK Command-line Tools (latest)' в SDK Manager." }
  ("y`n" * 30) | & $sm --licenses | Out-Null
  & $sm "platform-tools" "platforms;android-36" "build-tools;36.0.0"
}

if ($CheckOnly) { npm run apk:release-check } else { npm install; npm run apk }
if ($LASTEXITCODE -ne 0) { throw "Сборка не удалась (код $LASTEXITCODE)" }
if ($CheckOnly) { return }

$apk = (Get-ChildItem (Join-Path $PSScriptRoot 'dist') -Filter 'clubs-schedule-debug-*.apk' | Sort-Object LastWriteTime | Select-Object -Last 1).FullName  # имя содержит версию
Write-Host "APK: $apk"
if ($Install) {
  $adb = Get-Command adb -ErrorAction SilentlyContinue
  if (-not $adb) {
    $sdk = if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
    $adbPath = Join-Path $sdk 'platform-tools\adb.exe'
  } else { $adbPath = $adb.Source }
  & $adbPath devices
  & $adbPath install -r $apk
  & $adbPath shell monkey -p ru.kipfin.clubs -c android.intent.category.LAUNCHER 1
}
