import os
import sys
import tarfile
import urllib.request
import csv
import json

# 带 User-Agent 的安全下载函数
def download_file(url, filename):
    print(f"正在从以下地址下载: {url}")
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
        print(f"下载写入文件失败: {e}")
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

# 2. 配置并合并 IP 列表（普通 IP + 大厂专属 IP）
print("正在配置 IP 列表...")
PREMIUM_CIDRS = [
    "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", 
    "162.159.0.0/16", "108.162.192.0/18", "198.41.128.0/17"
]

official_ip_url = "https://raw.githubusercontent.com/XIU2/CloudflareSpeedTest/master/ip.txt"
try:
    print("正在下载公开普通 IP 库...")
    download_file(official_ip_url, "ip_temp.txt")
    
    all_ips = set()
    with open("ip_temp.txt", "r", encoding="utf-8") as f_temp:
        for line in f_temp:
            ip_line = line.strip()
            if ip_line and not ip_line.startswith("#"):
                all_ips.add(ip_line)
                
    for cidr in PREMIUM_CIDRS:
        all_ips.add(cidr)
        
    with open("ip.txt", "w", encoding="utf-8") as f_final:
        f_final.write("\n".join(sorted(list(all_ips))))
        
    print(f"IP 库配置完成，共计 {len(all_ips)} 个网段。")
    if os.path.exists("ip_temp.txt"):
        os.remove("ip_temp.txt")
except Exception as e:
    print(f"普通 IP 库下载失败 ({e})，将仅使用大厂专属 IP 段...")
    with open("ip.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(PREMIUM_CIDRS))

# 3. 定义各个目标地区及对应的 Cloudflare 节点机场三字码 (Colo)
# 对每个地区进行独立强制过滤测速，彻底解决 Actions 定位偏差
REGIONS = {
    'HK': {'name': '香港 (Hong Kong)', 'cf': 'HKG', 'file': 'HK.txt'},
    'JP': {'name': '日本 (Japan)', 'cf': 'NRT,HND,KIX', 'file': 'JP.txt'},
    'TW': {'name': '台湾 (Taiwan)', 'cf': 'TPE,KHH', 'file': 'TW.txt'},
    'SG': {'name': '新加坡 (Singapore)', 'cf': 'SIN', 'file': 'SG.txt'},
    'KR': {'name': '韩国 (South Korea)', 'cf': 'ICN', 'file': 'KR.txt'},
    'TH': {'name': '泰国 (Thailand)', 'cf': 'BKK', 'file': 'TH.txt'},
    'US': {'name': '美国 (United States)', 'cf': 'LAX,SJC,SFO,SEA,ORD,DFW,MIA,IAD,JFK', 'file': 'US.txt'}
}

combined_lines = []
combined_lines.append("# Cloudflare 优选 IP 列表 (独立测速汇总)")
combined_lines.append("# 测速数据基于 GitHub Actions 运行环境，仅供参考\n")

# 4. 循环针对每个地区进行测速和结果提取
for key, region in REGIONS.items():
    csv_file = f"result_{key}.csv"
    # -cf: 强制测速工具仅筛选该地区的节点 IP 进行测试
    # -dn 20: 提取该地区延迟最低的前 20 个 IP 进行实际下载测速
    cmd = f"./{binary_name} -f ip.txt -cf {region['cf']} -n 300 -dn 20 -dt 4 -o {csv_file}"
    print(f"\n==========================================")
    print(f"正在进行目标地区测速: {region['name']} ...")
    print(f"执行命令: {cmd}")
    os.system(cmd)
    
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
            os.remove(csv_file)  # 清理临时测速数据
        except Exception as e:
            print(f"读取或解析 {csv_file} 失败: {e}")
            
    # 5. 生成该地区的独立 TXT 文件
    country_file_lines = []
    country_file_lines.append(f"# Cloudflare 优选 IP - {region['name']}")
    country_file_lines.append("# 格式: IP:端口 - 延迟 - 速度 - 节点\n")
    
    combined_lines.append(f"=== {region['name']} (Top 20) ===")
    
    if not ips:
        no_ip_msg = "未在此次测速中匹配到该地区的有效节点。\n"
        combined_lines.append(no_ip_msg)
        country_file_lines.append(no_ip_msg)
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
        
        for item in sorted_ips:
            line = f"{item['ip']}:{item['port']} - 延迟: {item['latency']}ms - 速度: {item['speed']} MB/s - 节点: {item['colo']}"
            combined_lines.append(line)
            country_file_lines.append(line)
        combined_lines.append("") # 汇总文件地区间隔

    # 写入单个地区的独立 txt 文件
    try:
        with open(region['file'], "w", encoding="utf-8") as f_sub:
            f_sub.write("\n".join(country_file_lines))
        print(f"【成功】单地区优选文件已生成: {region['file']} (获取到 {len(ips)} 个节点)")
    except Exception as e:
        print(f"写入单地区文件 {region['file']} 失败: {e}")

# 6. 写入汇总文件
try:
    with open("cloudflare_ips.txt", "w", encoding="utf-8") as f_all:
        f_all.write("\n".join(combined_lines))
    print("\n==========================================")
    print("【成功】汇总文件 cloudflare_ips.txt 写入完毕。")
except Exception as e:
    print(f"写入汇总文件失败: {e}")
