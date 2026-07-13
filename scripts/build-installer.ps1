$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$stage = Join-Path $root "build-resources"
$backendStage = Join-Path $stage "backend"
$helperStage = Join-Path $stage "windows-helper"
$weasyStage = Join-Path $stage "weasyprint"
$msysRoot = "C:\msys64\mingw64"

if (-not (Test-Path $python)) {
    throw "Ambiente Python nao encontrado em $python"
}
if (-not (Test-Path (Join-Path $msysRoot "bin\libpango-1.0-0.dll"))) {
    throw "Dependencias do WeasyPrint nao encontradas em $msysRoot"
}

Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $backendStage, $helperStage, $weasyStage | Out-Null

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name gestor-nfse-backend `
    --distpath $backendStage `
    --workpath (Join-Path $root "backend\build\pyinstaller") `
    --specpath (Join-Path $root "backend\build") `
    --paths (Join-Path $root "backend\src") `
    --collect-all nfse_desktop `
    --collect-all gov_nfse `
    --collect-all danfse_brasil `
    --collect-all weasyprint `
    --collect-all openpyxl `
    --hidden-import nfse_desktop.api `
    (Join-Path $root "backend\packaging_entry.py")

& dotnet publish `
    (Join-Path $root "windows-cert-helper\Nfse.WindowsCertificates.csproj") `
    --configuration Release `
    --runtime win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    --output $helperStage

New-Item -ItemType Directory -Path `
    (Join-Path $weasyStage "bin"), `
    (Join-Path $weasyStage "etc"), `
    (Join-Path $weasyStage "share") | Out-Null
Copy-Item (Join-Path $msysRoot "bin\*.dll") (Join-Path $weasyStage "bin")
Copy-Item (Join-Path $msysRoot "etc\fonts") (Join-Path $weasyStage "etc\fonts") -Recurse
Copy-Item (Join-Path $msysRoot "share\fontconfig") (Join-Path $weasyStage "share\fontconfig") -Recurse

Push-Location $root
try {
    npm run build
    npx electron-builder --win nsis --x64
}
finally {
    Pop-Location
}
