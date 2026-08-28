#!/usr/bin/env python3
"""下载贝壳/如视(realsee)房源媒体：视频 + 图片 + N个观察点6面原始图 + 每点合成360°全景照。

用法:
    python3 download_realsee_media.py "https://open.realsee.com/ke/<workCode>/<token>/" [输出目录]

依赖: 仅标准库 + ffmpeg(需有 v360 滤镜)。
"""
import json, os, re, subprocess, sys, concurrent.futures, urllib.request

UA = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://open.realsee.com/',
      'Accept-Language': 'zh-CN,zh;q=0.9'}

FACES = ['front', 'back', 'left', 'right', 'up', 'down']      # realsee 原始6面
VFACES = ['right', 'left', 'up', 'down', 'front', 'back']      # v360 c6x1 面顺序


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def parse_html(html):
    t = html.decode('utf-8', 'replace')
    idx = t.find('"firstscreen"')
    if idx < 0:
        raise RuntimeError('未找到 firstscreen 数据')
    start = t.rfind('<!--', 0, idx)
    end = t.find('-->', idx)
    return json.loads(t[start + 4:end].strip())


def dl(url, path, retries=3):
    last = None
    for _ in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r, \
                    open(path, 'wb') as f:
                f.write(r.read())
            return
        except Exception as e:
            last = e
    raise RuntimeError(f'下载失败 {url}: {last}')


def dl_videos(hi, out):
    """houseInfo.multimedia 里的视频(小区视频)"""
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
            print(f'  [视频] {name} <- {u}', flush=True)
            dl(u, path)
    return vids


def dl_images(hi, out):
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
    # 1) 下载 6 面原始图 (avif -> jpg 服务端转码)
    for face in FACES:
        path = os.path.join(d, f'{face}.jpg')
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            dl(p[face] + '?imageMogr2/format/jpg', path)
    # 2) 合成 360° 全景照
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
        sys.exit(1)
    url = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.expanduser('~'), 'Downloads', 'realsee_media')
    os.makedirs(out, exist_ok=True)

    print('抓取页面...', flush=True)
    data = parse_html(fetch(url))
    hi = data['firstscreen']['houseInfo']
    pano = data['firstscreen']['defaultWork']['panorama']
    obs = data['firstscreen']['defaultWork']['observers']
    print(f"房源: {hi.get('title')} | houseCode={hi.get('houseCode')} "
          f"| 观察点={pano['count']}", flush=True)

    vids = dl_videos(hi, out)
    imgs = dl_images(hi, out)
    print(f'视频 {len(vids)} 个, 图片 {len(imgs)} 张', flush=True)

    print(f'下载 {pano["count"]} 个观察点 6 面图 + 合成全景...', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        done = list(ex.map(lambda i: scene(i, pano, obs, out), range(pano['count'])))
    print(f'完成 {len(done)} 个观察点 -> {out}')


if __name__ == '__main__':
    main()
