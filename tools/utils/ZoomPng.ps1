# ASCII-only: zoom a region of a PNG for close inspection.
# Usage: ZoomPng.ps1 -In <png> -Out <png> [-Scale 3] [-X 0] [-Y 0] [-W 0] [-H 0]
param(
    [Parameter(Mandatory = $true)][string]$In,
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$Scale = 3,
    [int]$X = 0,
    [int]$Y = 0,
    [int]$W = 0,
    [int]$H = 0
)
Add-Type -AssemblyName System.Drawing
$src = [System.Drawing.Bitmap]::FromFile($In)
if ($W -le 0) { $W = $src.Width - $X }
if ($H -le 0) { $H = $src.Height - $Y }
$crop = $src.Clone([System.Drawing.Rectangle]::new($X, $Y, $W, $H), $src.PixelFormat)
$zw = $W * $Scale
$zh = $H * $Scale
$zoom = New-Object System.Drawing.Bitmap -ArgumentList $zw, $zh
$g = [System.Drawing.Graphics]::FromImage($zoom)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
$g.DrawImage($crop, 0, 0, $zw, $zh)
$g.Dispose()
$zoom.Save($Out)
$zoom.Dispose()
$crop.Dispose()
$src.Dispose()
Write-Output ("ZOOMED {0}x{1} -> {2}" -f $zw, $zh, $Out)
