#!/usr/bin/env python3
"""Download all media from a realsee VR page: videos + images + per-observation-point cube
faces + synthesized equirectangular 360° panoramas.

Usage:
    python3 realsee_download.py "https://open.realsee.com/ke/<workCode>/<token>/" [output_dir]

Dependencies: stdlib + ffmpeg (needs the v360 filter).
"""
import json, os, subprocess, sys, concurrent.futures, urllib.request

UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://open.realsee.com/',
      'Accept-Language': 'zh-CN,zh;q=0.9'}

FACES = ['front', 'back', 'left', 'right', 'up', 'down']      # realsee cube-face keys
# CRITICAL: v360 c6x1 face order = rludfb = right,left,up,down,front,back. NO swap.
VFACES = ['right', 'left', 'up', 'down', 'front', 'back']


def fetch_json(url):
    req = urllib.request.Request(url, headers=UA)
    html = urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'replace')
    idx = html.find('"firstscreen"')
    if idx < 0:
        raise SystemExit('no firstscreen JSON in page (dead link / redirect / captcha)')
    start = html.rfind('<!--', 0, idx)
    end = html.find('-->', idx)
    return json.loads(html[start + 4:end].strip())


def dl(url, path, retries=3):
    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=90) as r, open(path, 'wb') as f:
                f.write(r.read())
            return
        except Exception as e:
            last = e
    raise RuntimeError(f'download failed {url}: {last}')


def dl_videos(hi, out):
    """Community (小区) videos from houseInfo.multimedia[type=video]."""
    vids = []
    for m in hi.get('multimedia', []):
        if m.get('type') != 'video':
            continue
        for it in m.get('list', []):
            u = it.get('url', '')
            if u.endswith('.mp4'):
                vids.append((it.get('title') or m.get('title') or 'video', u))
    for i, (name, u) in enumerate(vids):
        path = os.path.join(out, f'视频_{i:02d}_{name}.mp4')
        if not os.path.exists(path):
            dl(u, path)
    return vids


def dl_images(hi, out):
    """Community images from houseInfo.multimedia[type=image]."""
    imgs = []
    for m in hi.get('multimedia', []):
        if m.get('type') != 'image':
            continue
        for it in m.get('list', []):
            u = it.get('url', '')
            if u:
                imgs.append(u)
    for i, u in enumerate(imgs):
        path = os.path.join(out, f'图片_{i:02d}.jpg')
        if not os.path.exists(path):
            dl(u, path)
    return imgs


def scene(idx, pano, obs, out):
    p = pano['list'][idx]
    floor = obs[idx]['floor_index'] if idx < len(obs) else 0
    d = os.path.join(out, f'观察点{idx:02d}_第{floor + 1}层')
    os.makedirs(d, exist_ok=True)
    for face in FACES:
        path = os.path.join(d, f'{face}.jpg')
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            dl(p[face] + '?imageMogr2/format/jpg', path)
    equi = os.path.join(out, f'观察点{idx:02d}_第{floor + 1}层_全景360.jpg')
    if not os.path.exists(equi):
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y']
        for face in VFACES:
            cmd += ['-i', os.path.join(d, f'{face}.jpg')]
        cmd += ['-filter_complex', '[0][1][2][3][4][5]hstack=6[c];[c]v360=c6x1:e',
                '-q:v', '3', equi]
        subprocess.run(cmd, check=True)
    return idx


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    url = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else 'realsee_output'
    os.makedirs(out, exist_ok=True)
    data = fetch_json(url)
    hi = data['firstscreen']['houseInfo']
    pano = data['firstscreen']['defaultWork']['panorama']
    obs = data['firstscreen']['defaultWork']['observers']
    vids = dl_videos(hi, out)
    imgs = dl_images(hi, out)
    print(f'{len(vids)} videos, {len(imgs)} images', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(lambda i: scene(i, pano, obs, out), range(pano['count'])))
    print('DONE', pano['count'], 'panoramas ->', os.path.abspath(out))


if __name__ == '__main__':
    main()
