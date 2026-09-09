# Autodesk Inventor Workstation Agent (Port 8001) - Pure PowerShell .NET Edition
# Zero dependencies required. Uses native Windows HttpListener and Inventor COM API.

param(
    [int]$Port = 8001
)

$host.UI.RawUI.WindowTitle = "Autodesk Inventor AI Agent (Port $Port)"
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "       Autodesk Inventor Workstation Agent (Port $Port)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor White
Write-Host " Native Windows .NET HttpListener & Inventor COM Integration" -ForegroundColor Gray
Write-Host " Listening on: http://0.0.0.0:$Port/" -ForegroundColor Yellow
Write-Host " Leave this window open while using the Text-to-CAD Workbench." -ForegroundColor White
Write-Host "======================================================================" -ForegroundColor Cyan

$listener = New-Object System.Net.HttpListener
$prefix = "http://+:$Port/"
$listener.Prefixes.Add($prefix)

try {
    $listener.Start()
} catch {
    Write-Warning "Could not bind to $prefix. Falling back to localhost..."
    $listener = New-Object System.Net.HttpListener
    $listener.Prefixes.Add("http://*:$Port/")
    $listener.Start()
}

Write-Host "`n[INFO] Workstation Agent is ONLINE and waiting for CAD jobs...`n" -ForegroundColor Green

$saveFolder = [System.IO.Path]::Combine($env:USERPROFILE, "Documents", "OmniCAD_Models")
if (-not (Test-Path $saveFolder)) {
    New-Item -ItemType Directory -Path $saveFolder -Force | Out-Null
}

function Get-InventorSession {
    try {
        $inv = [System.Runtime.InteropServices.Marshal]::GetActiveObject("Inventor.Application")
        return $inv
    } catch {
        try {
            $invType = [System.Type]::GetTypeFromProgID("Inventor.Application")
            $inv = [System.Activator]::CreateInstance($invType)
            $inv.Visible = $true
            return $inv
        } catch {
            return $null
        }
    }
}

while ($listener.IsListening) {
    try {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response

        # Add CORS Headers
        $response.Headers.Add("Access-Control-Allow-Origin", "*")
        $response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        $response.Headers.Add("Access-Control-Allow-Headers", "*")

        if ($request.HttpMethod -eq "OPTIONS") {
            $response.StatusCode = 200
            $response.Close()
            continue
        }

        $urlPath = $request.Url.AbsolutePath
        $method = $request.HttpMethod

        # Health Check
        if ($urlPath -eq "/health" -and $method -eq "GET") {
            $inv = Get-InventorSession
            $invConnected = ($inv -ne $null)
            $invVer = if ($invConnected) { $inv.SoftwareVersion.DisplayName } else { "Not Running" }
            $docCount = if ($invConnected) { $inv.Documents.Count } else { 0 }

            $jsonObj = @{
                status = "online"
                workstation = "192.168.11.150"
                inventor_connected = $invConnected
                inventor_version = $invVer
                active_documents = $docCount
                engine = "PowerShell .NET HttpListener"
            }
            $jsonBytes = [System.Text.Encoding]::UTF8.GetBytes(($jsonObj | ConvertTo-Json -Compress))
            $response.ContentType = "application/json"
            $response.ContentLength64 = $jsonBytes.Length
            $response.OutputStream.Write($jsonBytes, 0, $jsonBytes.Length)
            $response.Close()
            continue
        }

        # Open in Inventor Endpoint
        if ($urlPath -eq "/api/inventor/open" -and $method -eq "POST") {
            $reader = New-Object System.IO.StreamReader($request.InputStream, $request.ContentEncoding)
            $body = $reader.ReadToEnd()
            $reqData = $body | ConvertFrom-Json

            $stepUrl = $reqData.step_url
            $partName = if ($reqData.part_name) { $reqData.part_name } else { "model" }
            $createAssembly = [bool]$reqData.create_assembly

            Write-Host "[CAD-JOB] Received dispatch: $partName (Assembly: $createAssembly)" -ForegroundColor Yellow
            Write-Host "          Downloading STEP: $stepUrl" -ForegroundColor Gray

            $localStep = [System.IO.Path]::Combine($saveFolder, "$partName.step")
            
            # Download STEP file
            try {
                $wc = New-Object System.Net.WebClient
                $wc.DownloadFile($stepUrl, $localStep)
            } catch {
                Write-Host "[ERROR] Failed to download STEP: $($_.Exception.Message)" -ForegroundColor Red
                $errObj = @{ success = $false; message = "Failed to download STEP file from $($stepUrl): $($_.Exception.Message)" }
                $errBytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.StatusCode = 400
                $response.ContentType = "application/json"
                $response.OutputStream.Write($errBytes, 0, $errBytes.Length)
                $response.Close()
                continue
            }

            # Connect to Inventor
            $inv = Get-InventorSession
            if ($null -eq $inv) {
                Write-Host "[ERROR] Autodesk Inventor is not running and could not be launched." -ForegroundColor Red
                $errObj = @{ success = $false; message = "Autodesk Inventor is not running on 192.168.11.150" }
                $errBytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.StatusCode = 503
                $response.ContentType = "application/json"
                $response.OutputStream.Write($errBytes, 0, $errBytes.Length)
                $response.Close()
                continue
            }

            try {
                Write-Host "[INVENTOR] Opening STEP solid into native Inventor workspace..." -ForegroundColor Cyan
                $doc = $inv.Documents.Open($localStep)

                if ($createAssembly) {
                    $iptPath = [System.IO.Path]::Combine($saveFolder, "${partName}_part.ipt")
                    $doc.SaveAs($iptPath, $false)
                    $doc.Close($true)

                    # Create Assembly (.iam) - kAssemblyDocumentObject = 12291
                    $asmDoc = $inv.Documents.Add(12291, "", $true)
                    $tg = $inv.TransientGeometry
                    $matrix = $tg.CreateMatrix()
                    $asmDoc.ComponentDefinition.Occurrences.Add($iptPath, $matrix)

                    $iamPath = [System.IO.Path]::Combine($saveFolder, "$partName.iam")
                    $asmDoc.SaveAs($iamPath, $false)
                    $inv.ActiveView.Fit()
                    $inv.Visible = $true

                    Write-Host "[SUCCESS] Created Assembly: $iamPath" -ForegroundColor Green
                    $resObj = @{
                        success = $true
                        message = "Opened and saved native Autodesk Inventor Assembly (.iam)"
                        file_path = $iamPath
                        file_type = "Assembly (.iam)"
                        inventor_version = $inv.SoftwareVersion.DisplayName
                        open_documents_count = $inv.Documents.Count
                    }
                } else {
                    $iptPath = [System.IO.Path]::Combine($saveFolder, "$partName.ipt")
                    $doc.SaveAs($iptPath, $false)
                    $inv.ActiveView.Fit()
                    $inv.Visible = $true

                    Write-Host "[SUCCESS] Created Part: $iptPath" -ForegroundColor Green
                    $resObj = @{
                        success = $true
                        message = "Opened and saved native Autodesk Inventor Part (.ipt)"
                        file_path = $iptPath
                        file_type = "Part (.ipt)"
                        inventor_version = $inv.SoftwareVersion.DisplayName
                        open_documents_count = $inv.Documents.Count
                    }
                }

                $resBytes = [System.Text.Encoding]::UTF8.GetBytes(($resObj | ConvertTo-Json -Compress))
                $response.StatusCode = 200
                $response.ContentType = "application/json"
                $response.OutputStream.Write($resBytes, 0, $resBytes.Length)
                $response.Close()
            } catch {
                Write-Host "[ERROR] COM execution error: $_" -ForegroundColor Red
                $errObj = @{ success = $false; message = "Inventor COM error: $_" }
                $errBytes = [System.Text.Encoding]::UTF8.GetBytes(($errObj | ConvertTo-Json -Compress))
                $response.StatusCode = 500
                $response.ContentType = "application/json"
                $response.OutputStream.Write($errBytes, 0, $errBytes.Length)
                $response.Close()
            }
            continue
        }

        # Unknown Route
        $response.StatusCode = 404
        $response.Close()
    } catch {
        Write-Warning "Request handling exception: $_"
    }
}
