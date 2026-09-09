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

# Windows User32 P/Invoke for window focus
try {
    Add-Type @"
    using System;
    using System.Runtime.InteropServices;
    public class Win32Window {
        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool SetForegroundWindow(IntPtr hWnd);
        
        [DllImport("user32.dll")]
        public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool BringWindowToTop(IntPtr hWnd);
    }
"@ -ErrorAction SilentlyContinue
} catch {}

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

$saveFolder = [System.IO.Path]::Combine($env:USERPROFILE, "Documents", "OmniCAD")
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

function Focus-InventorWindow([object]$inv) {
    try {
        $inv.Visible = $true
        $inv.WindowState = 2 # kMaximizeWindow = 2
        if ($null -ne $inv.ActiveView) {
            $inv.ActiveView.Fit()
        }
        $hwnd = [IntPtr]$inv.MainFrameHWND
        if ($hwnd -ne [IntPtr]::Zero) {
            [Win32Window]::ShowWindowAsync($hwnd, 3) # 3 = SW_MAXIMIZE
            [Win32Window]::BringWindowToTop($hwnd)
            [Win32Window]::SetForegroundWindow($hwnd)
        }
    } catch {
        Write-Warning "Focus window error: $($_.Exception.Message)"
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
            $isConn = $false
            $invVer = "Not Running"
            $docCount = 0

            if ($null -ne $inv) {
                try {
                    $isConn = $true
                    $invVer = $inv.SoftwareVersion.DisplayName
                    $docCount = $inv.Documents.Count
                } catch {
                    $isConn = $false
                }
            }

            $statusObj = @{
                status = "online"
                engine = "PowerShell .NET HttpListener"
                workstation = "192.168.11.150"
                inventor_connected = $isConn
                inventor_version = $invVer
                active_documents = $docCount
            }

            $jsonStr = $statusObj | ConvertTo-Json -Compress
            $jsonBytes = [System.Text.Encoding]::UTF8.GetBytes($jsonStr)
            $response.ContentType = "application/json"
            $response.StatusCode = 200
            $response.ContentLength64 = $jsonBytes.Length
            $response.OutputStream.Write($jsonBytes, 0, $jsonBytes.Length)
            $response.Close()
            continue
        }

        # Open or Activate in Inventor Endpoint
        if ($urlPath -eq "/api/inventor/open" -and $method -eq "POST") {
            $reader = New-Object System.IO.StreamReader($request.InputStream, $request.ContentEncoding)
            $body = $reader.ReadToEnd()
            $reqData = $body | ConvertFrom-Json

            $stepUrl = $reqData.step_url
            $partName = if ($reqData.part_name) { $reqData.part_name } else { "model" }
            $createAssembly = [bool]$reqData.create_assembly

            Write-Host "[CAD-JOB] Received dispatch: $partName (Assembly: $createAssembly)" -ForegroundColor Yellow

            $localStep = [System.IO.Path]::Combine($saveFolder, "$partName.step")
            $iptPath = [System.IO.Path]::Combine($saveFolder, "$partName.ipt")
            $iamPath = [System.IO.Path]::Combine($saveFolder, "$partName.iam")

            # Download STEP file if URL provided
            if (-not [string]::IsNullOrWhiteSpace($stepUrl)) {
                Write-Host "          Downloading STEP: $stepUrl" -ForegroundColor Gray
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
                if ($createAssembly) {
                    Write-Host "[INVENTOR] Opening/Creating native Assembly..." -ForegroundColor Cyan
                    $targetFile = $null
                    if (Test-Path $iamPath) {
                        $asmDoc = $inv.Documents.Open($iamPath)
                        $targetFile = $iamPath
                    } else {
                        # Open STEP and convert
                        $doc = $inv.Documents.Open($localStep)
                        $partIpt = [System.IO.Path]::Combine($saveFolder, "${partName}_part.ipt")
                        $doc.SaveAs($partIpt, $false)
                        $doc.Close($true)

                        $asmDoc = $inv.Documents.Add(12291, "", $true)
                        $tg = $inv.TransientGeometry
                        $matrix = $tg.CreateMatrix()
                        $asmDoc.ComponentDefinition.Occurrences.Add($partIpt, $matrix)
                        $asmDoc.SaveAs($iamPath, $false)
                        $targetFile = $iamPath
                    }
                    $asmDoc.Activate()
                    Focus-InventorWindow $inv

                    Write-Host "[SUCCESS] Active Assembly: $targetFile" -ForegroundColor Green
                    $resObj = @{
                        success = $true
                        message = "Opened and activated native Autodesk Inventor Assembly (.iam)"
                        file_path = $targetFile
                        file_type = "Assembly (.iam)"
                        inventor_version = $inv.SoftwareVersion.DisplayName
                        open_documents_count = $inv.Documents.Count
                    }
                } else {
                    Write-Host "[INVENTOR] Opening/Activating native Part..." -ForegroundColor Cyan
                    $targetFile = $null
                    if (Test-Path $iptPath) {
                        $doc = $inv.Documents.Open($iptPath)
                        $targetFile = $iptPath
                    } elseif (Test-Path $localStep) {
                        $doc = $inv.Documents.Open($localStep)
                        $doc.SaveAs($iptPath, $false)
                        $targetFile = $iptPath
                    } else {
                        throw "Model file not found ($iptPath or $localStep)"
                    }
                    $doc.Activate()
                    Focus-InventorWindow $inv

                    Write-Host "[SUCCESS] Active Part: $targetFile" -ForegroundColor Green
                    $resObj = @{
                        success = $true
                        message = "Opened and activated native Autodesk Inventor Part (.ipt)"
                        file_path = $targetFile
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
                Write-Host "[ERROR] COM execution error: $($_.Exception.Message)" -ForegroundColor Red
                $errObj = @{ success = $false; message = "Inventor COM error: $($_.Exception.Message)" }
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
        Write-Warning "Request handling exception: $($_.Exception.Message)"
    }
}
