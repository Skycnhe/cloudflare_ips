import os
import sys
import tarfile
import urllib.request
import csv
import json
import ipaddress
import random

# 带 User-Agent 的安全下载函数
def download_file(url, filename):
    print(f"正在下载: {url}")
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response, open(filename, 'wb') as out_file:
            block_size = 1024 * 8
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                out_file.write(buffer)
        print(f"下载成功: {filename}")
    except Exception as e:
        print(f"下载失败: {e}")
        raise e

# 动态获取最新下载链接，如果失败则回退到稳定版
def get_download_url():
    api_url = "https://api.github.com/repos/XIU2/CloudflareSpeedTest/releases/latest"
    print("正在尝试通过 GitHub API 动态获取最新版本链接...")
    req = urllib.request.Request(
        api_url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            assets = res_data.get('assets', [])
            for asset in assets:
                asset_name = asset.get('name', '')
                if ('cfst' in asset_name or 'CloudflareSpeedTest' in asset_name) and 'linux' in asset_name and 'amd64' in asset_name and asset_name.endswith('.tar.gz'):
                    download_url = asset.get('browser_download_url')
                    if download_url:
                        print(f"动态获取成功: {download_url}")
                        return download_url
    except Exception as e:
        print(f"API 获取失败 ({e})，将启用备用静态版本链接...")

    fallback_url = "https://github.com/XIU2/CloudflareSpeedTest/releases/download/v2.2.5/CloudflareSpeedTest_linux_amd64.tar.gz"
    print(f"启用备用静态链接: {fallback_url}")
    return fallback_url

# 使用 DoH + EDNS 技术动态获取特定地区最优质的 Cloudflare Anycast IP
def get_regional_ips_via_dns(country_code, subnet):
    print(f"正在通过 EDNS 技术为 [{country_code}] 获取定制 Anycast IP...")
    domains = ["dash.cloudflare.com", "zoom.us", "canva.com", "discord.com", "shopify.com"]
    ips = set()
    
    for domain in domains:
        url = f"https://dns.google/resolve?name={domain}&type=A&edns_client_subnet={subnet}"
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                data = json.loads(response.read().decode('utf-8'))
                answers = data.get('Answer', [])
                for ans in answers:
                    if ans.get('type') == 1:  # A 记录
                        ip = ans.get('data')
                        if ip and ip.count('.') == 3:  # 确保是 IPv4
                            ips.add(ip)
        except Exception as e:
            print(f"解析 {domain} 失败: {e}")
            
    result_list = list(ips)
    print(f"[{country_code}] 解析完成，获取到 {len(result_list)} 个专属 IP 节点。")
    return result_list

# === Cloudflare 官方公布的全量 IPv4 地址段 ===
# 包含了全球所有的公开 CDN/Anycast 节点
PREMIUM_CIDRS = [
    "104.16.0.0/13",      # 核心段 1 (涵盖 104.16.x.x - 104.23.x.x)
    "104.24.0.0/14",      # 核心段 2 (涵盖 104.24.x.x - 104.27.x.x)
    "172.64.0.0/13",      # 核心加速路由段 (涵盖 172.64.x.x - 172.71.x.x)
    "162.158.0.0/15",     # 核心 CDN 分发网段 (涵盖 162.158.x.x - 162.159.x.x，包含特殊伙伴段)
    "108.162.192.0/18",   # 企业高防与特定大客户加速段
    "198.41.128.0/17",    # 核心骨干网与优质大厂段
    "173.245.48.0/20",    # 核心 Anycast 网段
    "103.21.244.0/22",    # 亚太方向常态优化网段
    "103.22.200.0/22",    # 亚太地区高连通性网段
    "103.31.4.0/22",      # 亚太及全球骨干连接段
    "141.101.64.0/18",    # 欧洲与全球 Anycast 核心段
    "190.93.240.0/20",    # 美洲与防 Ddos 核心保护段
    "188.114.96.0/20",    # 欧洲高连通性核心加速网段
    "197.234.240.0/22",   # 核心 Anycast 备用段
    "131.0.72.0/22"       # 全球骨干网互联段
]

# 从 CF 全量官方网段中随机抽样 IP，增加候选集的多样性
def sample_ips_from_cf_cidrs(count=75):
    print("正在从 CF 全量官方网段中随机抽样候选 IP...")
    sampled = set()
    for cidr in PREMIUM_CIDRS:
        try:
            net = ipaddress.ip_network(cidr)
            # 计算每个网段需要抽取的数量
            num_to_pick = min(count // len(PREMIUM_CIDRS), net.num_addresses)
            if num_to_pick > 0:
                for _ in range(num_to_pick):
                    # 避免选择网段的网络地址和广播地址
                    rand_idx = random.randint(1, net.num_addresses - 2)
                    sampled.add(str(net[rand_idx]))
        except Exception as e:
            print(f"抽样网段 {cidr} 发生错误: {e}")
    result_list = list(sampled)
    print(f"成功抽样出 {len(result_list)} 个 CF 官方大厂 IP。")
    return result_list

# 1. 下载并解压测速工具
print("正在初始化下载测速工具...")
cf_url = get_download_url()
try:
    download_file(cf_url, "cf.tar.gz")
    with tarfile.open("cf.tar.gz", "r:gz") as tar:
        tar.extractall()
    
    if os.path.exists("cfst"):
        binary_name = "cfst"
    elif os.path.exists("CloudflareSpeedTest"):
        binary_name = "CloudflareSpeedTest"
    else:
        print("错误：未在解压目录中找到测速可执行程序。")
        sys.exit(1)
        
    print(f"检测到测速程序文件名为: {binary_name}")
    os.chmod(binary_name, 0o755)
except Exception as e:
    print(f"测速工具下载或解压失败: {e}")
    sys.exit(1)

# 2. 定义各个目标国家/地区、对应的真实运营商子网段（ECS）及中文简称和文件名
REGIONS = {
    'HK': {'name': '香港 (Hong Kong)', 'zh': '香港', 'subnet': '203.198.23.0/24', 'file': 'HK.txt'},      # 香港电讯
    'JP': {'name': '日本 (Japan)', 'zh': '日本', 'subnet': '210.140.10.0/24', 'file': 'JP.txt'},         # 日本软银
    'TW': {'name': '台湾 (Taiwan)', 'zh': '台湾', 'subnet': '168.95.1.0/24', 'file': 'TW.txt'},          # 台湾中华电信
    'SG': {'name': '新加坡 (Singapore)', 'zh': '新加坡', 'subnet': '165.21.83.0/24', 'file': 'SG.txt'},      # 新加坡电信
    'KR': {'name': '韩国 (South Korea)', 'zh': '韩国', 'subnet': '168.126.63.0/24', 'file': 'KR.txt'},    # 韩国电信
    'TH': {'name': '泰国 (Thailand)', 'zh': '泰国', 'subnet': '203.155.33.0/24', 'file': 'TH.txt'},      # 泰国电信
    'US': {'name': '美国 (United States)', 'zh': '美国', 'subnet': '8.8.8.0/24', 'file': 'US.txt'}       # 美国谷歌
}

# 存放所有国家优选 IP 的列表，格式为 "IP#tag 【中文】 大写"
combined_lines = []

# 3. 循环针对每个地区获取专属 IP、测速和结果提取
for key, region in REGIONS.items():
    print(f"\n==========================================")
    print(f"正在处理目标地区: {region['name']}")
    
    # 获取此地区专用的 Anycast IP (引擎一：DNS 定位)
    regional_ips = get_regional_ips_via_dns(key, region['subnet'])
    
    # 从 CF 官方网段中抽样 IP (引擎二：全量官方网段)
    cf_segment_ips = sample_ips_from_cf_cidrs(count=75)
    
    # 融合成综合测试候选集并去重
    candidate_ips = list(set(regional_ips + cf_segment_ips))
    print(f"混合测试池构建完成，合并去重后共计 {len(candidate_ips)} 个候选 IP。")
        
    # 写入临时的特定地区待测 IP 文件
    temp_ip_file = f"ips_{key}.txt"
    with open(temp_ip_file, "w", encoding="utf-8") as f_temp:
        f_temp.write("\n".join(candidate_ips))
        
    csv_file = f"result_{key}.csv"
    # 对混合候选集进行测速
    cmd = f"./{binary_name} -f {temp_ip_file} -n 100 -dn 12 -dt 4 -o {csv_file}"
    print(f"开始测速...")
    os.system(cmd)
    
    # 清理临时 IP 文本
    if os.path.exists(temp_ip_file):
        os.remove(temp_ip_file)
        
    ips = []
    if os.path.exists(csv_file):
        try:
            with open(csv_file, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader)  # 跳过表头
                for row in reader:
                    if len(row) < 9:
                        continue
                    ips.append({
                        'ip': row[0],
                        'port': row[1],
                        'latency': row[6],
                        'speed': row[7],
                        'colo': row[8].upper()
                    })
            os.remove(csv_file)  # 清理测速 csv
        except Exception as e:
            print(f"读取或解析 {csv_file} 失败: {e}")
            
    # 4. 生成该地区的独立 TXT 文件（格式化输出）
    country_file_lines = []
    
    if not ips:
        # 如果测速结果为空，直接将解析到的原始 IP 作为可用节点写入（保底机制）
        print(f"提示：[{region['name']}] 测速在 Actions 上超时，启用保底机制写入原始 IP。")
        for idx, ip_addr in enumerate(regional_ips[:20], 1):
            line = f"{ip_addr}#{key.lower()}{idx} 【{region['zh']}】 {key}"
            country_file_lines.append(line)
            combined_lines.append(line)
    else:
        # 按照速度从大到小，延迟从小到大排序
        def sort_key(x):
            try:
                s = float(x['speed'])
            except ValueError:
                s = 0.0
            try:
                l = float(x['latency'])
            except ValueError:
                l = 9999.0
            return (s, -l)
            
        sorted_ips = sorted(ips, key=sort_key, reverse=True)[:20]
        
        for idx, item in enumerate(sorted_ips, 1):
            line = f"{item['ip']}#{key.lower()}{idx} 【{region['zh']}】 {key}"
            country_file_lines.append(line)
            combined_lines.append(line)

    # 写入单个地区的独立 txt 文件（纯净版）
    try:
        with open(region['file'], "w", encoding="utf-8") as f_sub:
            f_sub.write("\n".join(country_file_lines))
        print(f"【成功】单地区优选文件已生成: {region['file']}")
    except Exception as e:
        print(f"写入单地区文件 {region['file']} 失败: {e}")

# 5. 写入汇总文件（包含所有国家和地区）
try:
    with open("cloudflare_ips.txt", "w", encoding="utf-8") as f_all:
        f_all.write("\n".join(combined_lines))
    print("\n==========================================")
    print("【成功】汇总文件 cloudflare_ips.txt 写入完毕。")
except Exception as e:
    print(f"写入汇总文件失败: {e}")
