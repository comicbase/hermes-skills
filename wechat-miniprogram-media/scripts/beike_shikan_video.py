#!/usr/bin/env python3
"""贝壳找房小程序「实勘视频」抓取器。

输入从微信缓存里捞到的 player/list URL(或等价参数),按 houseCode 过滤出属于该房源的
视频,打印清单并可下载原片。

用法:
    # 1) 只列清单
    python3 beike_shikan_video.py --url '<player/list URL>' --house-code <houseCode>

    # 2) 下载第 1 条原片到指定目录
    python3 beike_shikan_video.py --url '<...>' --house-code <houseCode> --download 1 --out ~/Downloads

    # 3) 没有完整 URL 时手工给参数
    python3 beike_shikan_video.py --content-ids <contentId1>,<contentId2> \
        --content-list <contentId0>,<contentId1>,<contentId2> \
        --open-id <openId> --house-code <houseCode>
"""
import argparse, json, os, re, sys, urllib.parse, urllib.request

UA = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 '
      'Mobile/15E148 MicroMessenger/8.0.49(0x18003127) NetType/WIFI Language/zh_CN')
API = ('https://gw-mp.api.ke.com/mercy_api/proxyApi/i.content.api.ke.com'
       '/content/xcx/player/list')


def parse_cached_url(url):
    """缓存里的 URL 常被截断成 sign= ,直接拆 query。"""
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    return {k: v[0] for k, v in q.items()}


def build_url(p):
    params = {
        'contentIds': p['contentIds'],
        'contentList': p.get('contentList', p['contentIds']),
        'friendShare': '2',
        'source': p.get('source', 'ershoudetail'),
        'openId': p['openId'],
        'agentId': '',
        'shareUcid': '',
        'preLook': 'false',
        'pageNo': str(p.get('pageNo', 1)),
        'queryId': '[]',
        'env': 'weapp',
        'risk_business_type': 'scene-risk-video-flow',
    }
    if p.get('risk_data_id'):
        params['risk_data_id'] = p['risk_data_id']
    return API + '?' + urllib.parse.urlencode(params, safe=',%[]')


def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Referer': 'https://servicewechat.com/wxcfd8224218167d98/626/page-frame.html',
        'Accept': 'application/json',
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode('utf-8'))


def download(url, path):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA, 'Referer': 'https://m.ke.com/'})
    with urllib.request.urlopen(req, timeout=300) as r, open(path, 'wb') as f:
        total = int(r.headers.get('Content-Length') or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f'\r  {done/1048576:.1f}/{total/1048576:.1f} MB', end='', flush=True)
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', help='缓存里捞到的 player/list URL')
    ap.add_argument('--content-ids')
    ap.add_argument('--content-list')
    ap.add_argument('--open-id')
    ap.add_argument('--house-code', required=True, help='要匹配的房源 houseCode')
    ap.add_argument('--download', type=int, help='下载第 n 条(从 1 开始)')
    ap.add_argument('--hd', action='store_true', help='下载 HD 而不是 origin')
    ap.add_argument('--rename', action='store_true',
                    help='重命名为「实勘视频NN_说明_时长」;默认保留 CDN 原名')
    ap.add_argument('--out', default='.')
    a = ap.parse_args()

    if a.url:
        p = parse_cached_url(a.url)
    else:
        if not (a.content_ids and a.open_id):
            sys.exit('需要 --url 或 --content-ids + --open-id')
        p = {'contentIds': a.content_ids, 'contentList': a.content_list or a.content_ids,
             'openId': a.open_id}

    data = fetch(build_url(p))
    if data.get('errno') != 0:
        sys.exit(f'接口报错: {data}')
    items = data.get('data', {}).get('list', [])
    print(f'返回 {len(items)} 条视频\n')

    mine = []
    for it in items:
        v = it.get('video', {})
        pc = it.get('placeCard', {})
        owner = pc.get('entityId')
        ok = str(owner) == str(a.house_code)
        print(f"[{len(mine)+1 if ok else '-'}] {v.get('videoType')} | {v.get('duration')}s | "
              f"{v.get('width')}x{v.get('height')} | {v.get('summary')}")
        print(f"    entityId={owner} resblock={pc.get('resblockName')} "
              f"{'✓ 匹配' if ok else '✗ 非本房源'}")
        if ok:
            mine.append((it, v, pc))

    if not mine:
        sys.exit('没有匹配到该 houseCode 的视频')

    if a.download:
        it, v, pc = mine[a.download - 1]
        url = v['url'] if a.hd else (v['resource'].get('origin') or v['url'])
        base = os.path.basename(urllib.parse.urlsplit(url).path) or 'video.mp4'
        if a.rename:
            name = f"实勘视频{a.download:02d}_{v.get('summary','')}_{v.get('duration')}s"
            name = re.sub(r'[/\\:*?"<>|]', '_', name)
            name += ('_HD' if a.hd else '_原片') + (os.path.splitext(base)[1] or '.mp4')
        else:
            name = base  # 默认保留 CDN 原始文件名,用户不喜欢重命名
        os.makedirs(a.out, exist_ok=True)
        path = os.path.join(a.out, name)
        print(f'\n下载: {url}\n  -> {path}')
        download(url, path)
        print(f'完成 {os.path.getsize(path)/1048576:.1f} MB')

        meta = [{'类型': x[1].get('videoType'), '说明': x[1].get('summary'),
                 'contentId': x[1].get('id'), '时长秒': x[1].get('duration'),
                 '分辨率': f"{x[1].get('width')}x{x[1].get('height')}",
                 '作者': x[0].get('author', {}).get('name'),
                 'houseCode': x[2].get('entityId'), '小区': x[2].get('resblockName')}
                for x in mine]
        with open(os.path.join(a.out, '视频信息.json'), 'w') as f:
            json.dump({'houseCode': a.house_code, '视频': meta}, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
