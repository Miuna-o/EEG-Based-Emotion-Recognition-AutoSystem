"""从现有品牌几何图形生成 ICO，并准备固定版本的官方 WebView2 SDK。"""
from pathlib import Path
import urllib.request
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.4314.35'


def icon():
    scale = 16
    image = Image.new('RGBA', (44 * scale, 44 * scale))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 44 * scale - 1, 44 * scale - 1), radius=14 * scale, fill='#176455')
    draw.rounded_rectangle((0, 22 * scale, 24 * scale, 44 * scale - 1), radius=5 * scale, fill='#176455')
    for y in (15, 22, 29):
        segments = [((8,y),(14,y-8),(19,y+8),(25,y)), ((25,y),(31,y-8),(34,y-3),(36,y))]
        points = []
        for a,b,c,d in segments:
            for i in range(101):
                t = i / 100
                points.append(tuple(scale*((1-t)**3*a[j]+3*(1-t)**2*t*b[j]+3*(1-t)*t*t*c[j]+t**3*d[j]) for j in (0,1)))
        draw.line(points, fill='#E7F6EB', width=round(2.4*scale), joint='curve')
        for x,py in (points[0],points[-1]):
            radius=1.2*scale
            draw.ellipse((x-radius,py-radius,x+radius,py+radius),fill='#E7F6EB')
    folder=ROOT/'desktop/assets'
    folder.mkdir(parents=True,exist_ok=True)
    image.resize((256,256),Image.Resampling.LANCZOS).save(folder/'xinlan.ico',sizes=[(s,s) for s in (16,24,32,48,64,128,256)])
    image.resize((64, 64), Image.Resampling.LANCZOS).save(ROOT/'frontend/src/assets/xinlan.png')


def main():
    icon()
    feed=ROOT/'.desktop-build/feed'
    feed.mkdir(parents=True,exist_ok=True)
    package=feed/f'microsoft.web.webview2.{VERSION}.nupkg'
    if not package.exists():
        pending=package.with_suffix('.pending')
        urllib.request.urlretrieve(f'https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/{VERSION}/{package.name}',pending)
        pending.replace(package)
    print('心澜图标与固定版本桌面 SDK 已准备。')


if __name__=='__main__':main()
