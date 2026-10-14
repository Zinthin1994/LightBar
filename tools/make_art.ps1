# Generates the Steam library artwork for the LightBar tile (run on Windows).
#   powershell -ExecutionPolicy Bypass -File tools\make_art.ps1
Add-Type -AssemblyName System.Drawing
$out = Join-Path (Split-Path -Parent $PSScriptRoot) 'app\art'
New-Item -ItemType Directory -Force $out | Out-Null

$bg1 = [System.Drawing.Color]::FromArgb(255, 10, 12, 17)
$bg2 = [System.Drawing.Color]::FromArgb(255, 24, 29, 41)
# LED colors left to right: Steam blue -> purple -> pink
$stops = @(@(26, 159, 255), @(155, 61, 255), @(255, 61, 200))

function Led-Color([double]$t) {
  $seg = [Math]::Min(1, [Math]::Floor($t * 2)); $f = $t * 2 - $seg
  $a = $stops[$seg]; $b = $stops[$seg + 1]
  return [System.Drawing.Color]::FromArgb(255, [int]($a[0] + ($b[0] - $a[0]) * $f), [int]($a[1] + ($b[1] - $a[1]) * $f), [int]($a[2] + ($b[2] - $a[2]) * $f))
}

function Round-Rect($x, $y, $w, $h, $r) {
  $p = New-Object System.Drawing.Drawing2D.GraphicsPath
  $p.AddArc($x, $y, $r, $r, 180, 90); $p.AddArc($x + $w - $r, $y, $r, $r, 270, 90)
  $p.AddArc($x + $w - $r, $y + $h - $r, $r, $r, 0, 90); $p.AddArc($x, $y + $h - $r, $r, $r, 90, 90)
  $p.CloseFigure()
  return $p
}

function New-Canvas($w, $h, [bool]$transparent = $false) {
  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.SmoothingMode = 'AntiAlias'; $g.TextRenderingHint = 'AntiAliasGridFit'
  if (-not $transparent) {
    $rect = New-Object System.Drawing.Rectangle 0, 0, $w, $h
    $g.FillRectangle((New-Object System.Drawing.Drawing2D.LinearGradientBrush $rect, $bg2, $bg1, 90), $rect)
  }
  return @($bmp, $g)
}

# The Steam Machine front: a dark slab with the 17-LED light bar glowing under it.
function Draw-Machine($g, $cx, $cy, $w) {
  $h = $w * 0.62; $x = $cx - $w / 2; $y = $cy - $h / 2
  $barY = $y + $h * 0.80; $barW = $w * 0.84; $barX = $cx - $barW / 2
  # glow
  $glow = New-Object System.Drawing.Drawing2D.GraphicsPath
  $glow.AddEllipse($cx - $w * 0.75, $barY - $w * 0.22, $w * 1.5, $w * 0.44)
  $pg = New-Object System.Drawing.Drawing2D.PathGradientBrush $glow
  $pg.CenterColor = [System.Drawing.Color]::FromArgb(110, 120, 100, 255)
  $pg.SurroundColors = @([System.Drawing.Color]::FromArgb(0, 120, 100, 255))
  $g.FillPath($pg, $glow)
  # body
  $body = Round-Rect $x $y $w $h ($w * 0.08)
  $rect = New-Object System.Drawing.RectangleF $x, $y, $w, $h
  $g.FillPath((New-Object System.Drawing.Drawing2D.LinearGradientBrush $rect, ([System.Drawing.Color]::FromArgb(255, 38, 42, 52)), ([System.Drawing.Color]::FromArgb(255, 14, 16, 21)), 90), $body)
  $g.DrawPath((New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 52, 58, 72)), ([Math]::Max(1, $w * 0.006))), $body)
  # light bar
  $n = 17; $gap = $barW * 0.012; $ledW = ($barW - $gap * ($n - 1)) / $n; $ledH = [Math]::Max(3, $w * 0.028)
  for ($i = 0; $i -lt $n; $i++) {
    $c = Led-Color ($i / ($n - 1))
    $lx = $barX + $i * ($ledW + $gap)
    $halo = New-Object System.Drawing.Drawing2D.GraphicsPath
    $halo.AddEllipse($lx - $ledW, $barY - $ledH * 2.5, $ledW * 3, $ledH * 6)
    $hb = New-Object System.Drawing.Drawing2D.PathGradientBrush $halo
    $hb.CenterColor = [System.Drawing.Color]::FromArgb(150, $c.R, $c.G, $c.B)
    $hb.SurroundColors = @([System.Drawing.Color]::FromArgb(0, $c.R, $c.G, $c.B))
    $g.FillPath($hb, $halo)
    $g.FillPath((New-Object System.Drawing.SolidBrush $c), (Round-Rect $lx ($barY - $ledH / 2) $ledW $ledH ([Math]::Max(2, $ledH * 0.6))))
  }
}

function Draw-Text($g, $text, $x, $y, $px, [string]$align = 'center') {
  $font = New-Object System.Drawing.Font 'Segoe UI', $px, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
  $fmt = New-Object System.Drawing.StringFormat
  $fmt.Alignment = if ($align -eq 'left') { 'Near' } else { 'Center' }
  $fmt.LineAlignment = 'Center'
  $g.DrawString($text, $font, (New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(250, 255, 255, 255))), $x, $y, $fmt)
}

function Save($c, $name) { $c[0].Save((Join-Path $out $name), [System.Drawing.Imaging.ImageFormat]::Png); $c[1].Dispose(); $c[0].Dispose() }

# icon 256
$c = New-Canvas 256 256 $true
$g = $c[1]
$tile = Round-Rect 8 8 240 240 64
$g.FillPath((New-Object System.Drawing.SolidBrush $bg2), $tile)
$g.SetClip($tile)
Draw-Machine $g 128 128 190
Save $c 'icon.png'

# portrait 600x900
$c = New-Canvas 600 900
Draw-Machine $c[1] 300 380 420
Draw-Text $c[1] 'LightBar' 300 690 92
Save $c 'portrait.png'

# wide 920x430
$c = New-Canvas 920 430
Draw-Machine $c[1] 270 215 330
Draw-Text $c[1] 'LightBar' 480 215 96 'left'
Save $c 'wide.png'

# hero 1920x620 (no text: Steam draws the logo over it)
$c = New-Canvas 1920 620
Draw-Machine $c[1] 1400 310 560
Save $c 'hero.png'

# logo 800x220 transparent
$c = New-Canvas 800 220 $true
Draw-Text $c[1] 'LightBar' 400 110 140
Save $c 'logo.png'

Get-ChildItem $out | Select-Object Name, Length
