# ASCII-only: crop our Alt-Tab tiles with corrected (x1.28) coordinates.
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

# estimates were from a 2000px-wide view; actual file is 2560 -> x1.28
Crop-Zoom "$env:TEMP\wm_alttab2.png"    252 496 210 150 "$env:TEMP\wm_tile_normal.png"
Crop-Zoom "$env:TEMP\wm_alttab_min.png" 2090 700 210 150 "$env:TEMP\wm_tile_min.png"
Write-Output CROPS_DONE
