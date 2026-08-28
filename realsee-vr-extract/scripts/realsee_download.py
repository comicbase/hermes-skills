#!/usr/bin/env python3
"""Download all 360° panoramas (cube faces + synthesized equirectangular) from a realsee VR page.

Usage:
    python3 realsee_download.py "https://open.realsee.com/ke/<workCode>/<token>/" [output_dir]

Example:
    python3 realsee_download.py "https://open.realsee.com/ke/<workCode>/<token>/" ~/Downloads/house

Outputs, per observation point:
    <out>/panoNN_floorF/              # original 6 cube faces (front/back/left/right/up/down.jpg)
    <out>/panoNN_floorF_360.jpg       # synthesized equirectangular 360° photo
"""
import json, os, subprocess, sys, concurrent.futures, urllib.request

UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://open.realsee.com/'}
FACES = ['front', 'back', 'left', 'right', 'up', 'down']
# CRITICAL: face order must be rludfb = right,left,up,down,front,back. Realsee's left/right
# faces match v360's convention directly — NO swap. (Swapping to left,right produces a
# left-right-swapped panorama. Verified via pixel correlation against the source face images.)
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


def dl(url, path):
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r, open(path, 'wb') as f:
                f.write(r.read())
            return
        except Exception as e:
            last = e
    raise last


def scene(job):
    p, idx, floor, out = job
    d = os.path.join(out, f'pano{idx:02d}_floor{floor + 1}')
    os.makedirs(d, exist_ok=True)
    for face in FACES:
        path = os.path.join(d, f'{face}.jpg')
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            dl(p[face] + '?imageMogr2/format/jpg', path)
    equi = os.path.join(out, f'pano{idx:02d}_floor{floor + 1}_360.jpg')
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
    data = fetch_json(url)
    pano = data['firstscreen']['defaultWork']['panorama']
    obs = data['firstscreen']['defaultWork']['observers']
    os.makedirs(out, exist_ok=True)
    jobs = [(pano['list'][i], i, obs[i]['floor_index'], out) for i in range(len(pano['list']))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(scene, jobs))
    print('DONE', len(jobs), 'panoramas ->', os.path.abspath(out))


if __name__ == '__main__':
    main()
