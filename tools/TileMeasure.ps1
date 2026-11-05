# ASCII-only: measure how much of our Alt-Tab tile the composite image fills.
# Our composite contains a big WHITE region (mspaint canvas) reaching the right
# edge of the window. If the tile image fills the tile, white must touch the
# tile's right border; a gap = DWM displays the bitmap smaller than the tile.
Add-Type -AssemblyName System.Drawing

function Measure-Tile([string]$png, [int]$tx, [int]$ty, [int]$tw, [int]$th, [string]$tag) {
    $big = [System.Drawing.Bitmap]::FromFile($png)
    Write-Output "--- $tag tile=($tx,$ty) ${tw}x$th ---"
    # scan each row for rightmost white pixel (>=240,240,240) and leftmost
    for ($dy = 10; $dy -lt $th - 5; $dy += [int]([Math]::Max(1, [Math]::Floor($th / 8)))) {
        $rightWhite = -1; $leftWhite = -1
        for ($dx = 0; $dx -lt $tw; $dx++) {
            $c = $big.GetPixel($tx + $dx, $ty + $dy)
            if ($c.R -ge 240 -and $c.G -ge 240 -and $c.B -ge 240) {
                if ($leftWhite -eq -1) { $leftWhite = $dx }
                $rightWhite = $dx
            }
        }
        Write-Output ("row y+{0,3}: white span [{1} .. {2}] of {3}" -f $dy, $leftWhite, $rightWhite, $tw)
    }
    $big.Dispose()
}

# capture 1 (normal state): our tile approx (205,395) 155x110
Measure-Tile "$env:TEMP\wm_alttab2.png" 205 395 155 110 "NORMAL"
# capture 2 (minimized): our tile approx (1637,555) 155x118
Measure-Tile "$env:TEMP\wm_alttab_min.png" 1637 555 155 118 "MINIMIZED"
Write-Output MEASURE_DONE
