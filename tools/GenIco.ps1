# ASCII-only: generate multi-size .ico via compiled C# (PS pipeline unrolls byte[]).
param([string]$OutIco = "D:\AddOns\WindowMerger\assets\WindowMerger.ico",
      [string]$OutPng = "$env:TEMP\wm_appicon_256.png")
Add-Type -AssemblyName System.Drawing
Add-Type -ReferencedAssemblies System.Drawing -TypeDefinition @"
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;
public static class IcoGen {
    static Bitmap Render(int s) {
        var bmp = new Bitmap(s, s);
        using (var g = Graphics.FromImage(bmp)) {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.Clear(Color.Transparent);
            double f = s / 256.0;
            // rounded rect x,y=37.3333 w,h=128 rx=4 fill #F85032
            using (var path = new GraphicsPath()) {
                double x = 37.3333 * f, y = 37.3333 * f, w = 128 * f, h = 128 * f, r = 4 * f, d = 2 * r;
                path.AddArc((float)x, (float)y, (float)d, (float)d, 180, 90);
                path.AddArc((float)(x + w - d), (float)y, (float)d, (float)d, 270, 90);
                path.AddArc((float)(x + w - d), (float)(y + h - d), (float)d, (float)d, 0, 90);
                path.AddArc((float)x, (float)(y + h - d), (float)d, (float)d, 90, 90);
                path.CloseFigure();
                using (var br = new SolidBrush(Color.FromArgb(255, 0xF8, 0x50, 0x32))) g.FillPath(br, path);
            }
            // circle cx,cy=154.667 r=64 fill #FDC830 (after rect = on top)
            double cx = 154.667 * f, cr = 64 * f;
            using (var br = new SolidBrush(Color.FromArgb(255, 0xFD, 0xC8, 0x30)))
                g.FillEllipse(br, (float)(cx - cr), (float)(cx - cr), (float)(2 * cr), (float)(2 * cr));
        }
        return bmp;
    }
    static byte[] BmpEntry(Bitmap bmp) {
        int s = bmp.Width;
        var rect = new Rectangle(0, 0, s, s);
        var data = bmp.LockBits(rect, ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
        var pixels = new byte[4 * s * s];
        for (int row = 0; row < s; row++)
            Marshal.Copy(new IntPtr(data.Scan0.ToInt64() + row * data.Stride), pixels, (s - 1 - row) * s * 4, s * 4);
        bmp.UnlockBits(data);
        int andStride = (s + 31) / 32 * 4;
        var ms = new MemoryStream();
        using (var bw = new BinaryWriter(ms)) {
            bw.Write((uint)40); bw.Write((int)s); bw.Write((int)(s * 2));
            bw.Write((ushort)1); bw.Write((ushort)32); bw.Write((uint)0);
            bw.Write((uint)(pixels.Length + andStride * s));
            bw.Write((int)0); bw.Write((int)0);
            bw.Write(pixels);
            bw.Write(new byte[andStride * s]);
        }
        return ms.ToArray();
    }
    static byte[] PngEntry(Bitmap bmp) {
        var ms = new MemoryStream();
        bmp.Save(ms, ImageFormat.Png);
        return ms.ToArray();
    }
    public static string Generate(string outIco, string outPng) {
        int[] sizes = { 16, 24, 32, 48, 64, 72, 96, 128, 256 };
        var entries = new System.Collections.Generic.List<Tuple<int, byte[]>>();
        foreach (int s in sizes) {
            using (var bmp = Render(s)) {
                entries.Add(Tuple.Create(s, s >= 256 ? PngEntry(bmp) : BmpEntry(bmp)));
                if (s == 256) bmp.Save(outPng, ImageFormat.Png);
            }
        }
        var dir = Path.GetDirectoryName(outIco);
        if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
        using (var bw = new BinaryWriter(new FileStream(outIco, FileMode.Create))) {
            bw.Write((ushort)0); bw.Write((ushort)1); bw.Write((ushort)entries.Count);
            int offset = 6 + 16 * entries.Count;
            foreach (var e in entries) {
                byte b = e.Item1 >= 256 ? (byte)0 : (byte)e.Item1;
                bw.Write(b); bw.Write(b); bw.Write((byte)0); bw.Write((byte)0);
                bw.Write((ushort)1); bw.Write((ushort)32);
                bw.Write((uint)e.Item2.Length); bw.Write((uint)offset);
                offset += e.Item2.Length;
            }
            foreach (var e in entries) bw.Write(e.Item2);
        }
        var info = new FileInfo(outIco);
        return string.Format("ICO_WRITTEN {0} bytes, {1} sizes", info.Length, entries.Count);
    }
}
"@
[IcoGen]::Generate($OutIco, $OutPng)
Write-Output ("ICO_FILE " + $OutIco)
Write-Output ("PREVIEW " + $OutPng)
