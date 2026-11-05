# ASCII-only: crop our tile region from each captured frame.
Add-Type -AssemblyName System.Drawing
foreach ($i in 1..8) {
    $src = "$env:TEMP\wm_ft_$i.png"
    if (-not (Test-Path $src)) { continue }
    $big = [System.Drawing.Bitmap]::FromFile($src)
    $crop = $big.Clone([System.Drawing.Rectangle]::new(240, 485, 240, 170), $big.PixelFormat)
    $zoom = New-Object System.Drawing.Bitmap(480, 340)
    $gz = [System.Drawing.Graphics]::FromImage($zoom)
    $gz.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $gz.DrawImage($crop, 0, 0, 480, 340)
    $gz.Dispose()
    $zoom.Save("$env:TEMP\wm_ftcrop_$i.png")
    $zoom.Dispose()
    $crop.Dispose()
    $big.Dispose()
}
Write-Output CROPS_OK
