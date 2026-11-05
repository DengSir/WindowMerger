# ASCII-only: crop our tile + neighbor tile (row 3) for precise size comparison.
Add-Type -AssemblyName System.Drawing
function Crop-Zoom([string]$png, [int]$x, [int]$y, [int]$w, [int]$h, [string]$out) {
    $big = [System.Drawing.Bitmap]::FromFile($png)
    $crop = $big.Clone([System.Drawing.Rectangle]::new($x, $y, $w, $h), $big.PixelFormat)
    $zoom = New-Object System.Drawing.Bitmap(($w * 3), ($h * 3))
    $gz = [System.Drawing.Graphics]::FromImage($zoom)
    $gz.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::NearestNeighbor
    $gz.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::Half
    $gz.DrawImage($crop, 0, 0, $zoom.Width, $zoom.Height)
    $gz.Dispose()
    $zoom.Save($out)
    $zoom.Dispose()
    $crop.Dispose()
    $big.Dispose()
}
# row 3: ours = last tile; neighbor = NewBeeBox. Actual px = displayed x1.28.
Crop-Zoom "$env:TEMP\wm_ft_1.png" 1990 840 170 170 "$env:TEMP\wm_tile3_ours.png"
Crop-Zoom "$env:TEMP\wm_ft_1.png" 1595 840 230 170 "$env:TEMP\wm_tile3_nb.png"
Write-Output CROPS_DONE
