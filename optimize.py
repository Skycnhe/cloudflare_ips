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
    # 策略 A：通过 GitHub API 动态获取最新版的 browser_download_url
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

    # 策略 B：若 API 异常，回退使用 v2.2.5 稳定版直接链接
    fallback_url = "https://github.com/XIU2/CloudflareSpeedTest/releases/download/v2.2.5/CloudflareSpeedTest_linux_amd64.tar.gz"
    print(f"启用备用静态链接: {fallback_url}")
    return fallback_url

# 1. 自动选择可用链接并下载测速工具
print("正在初始化下载测速工具...")
cf_url = get_download_url()
try:
    download_file(cf_url, "cf.tar.gz")
    with tarfile.open("cf.tar.gz", "r:gz") as tar:
        tar.extractall()
    
    # 动态检测解压出来的程序名称（兼容新版 cfst 和旧版 CloudflareSpeedTest）
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
    "104.16.0.0/13",    # Cloudflare Enterprise & Business 核心大厂段
    "104.24.0.0/14",    # 商业与企业级合作伙伴段
    "172.64.0.0/13",    # 高优先级 Anycast 路由段
    "162.159.0.0/16",   # 特殊跨国合作伙伴专用路由段
    "108.162.192.0/18", # 企业级高防与加速段
    "198.41.128.0/17"   # 核心企业客户与高可靠性路由段
]

official_ip_url = "https://raw.githubusercontent.com/XIU2/CloudflareSpeedTest/master/ip.txt"
try:
    print("正在下载公开普通 IP 库...")
    download_file(official_ip_url, "ip_temp.txt")
    
    # 合并、去重
    all_ips = set()
    with open("ip_temp.txt", "r", encoding="utf-8") as f_temp:
        for line in f_temp:
            ip_line = line.strip()
            if ip_line and not ip_line.startswith("#"):
                all_ips.add(ip_line)
                
    # 加入大厂优质段
    for cidr in PREMIUM_CIDRS:
        all_ips.add(cidr)
        
    with open("ip.txt", "w", encoding="utf-8") as f_final:
        f_final.write("\n".join(sorted(list(all_ips))))
        
    print(f"IP 库配置完成：已成功合并普通 IP 与大厂专属 IP，共计 {len(all_ips)} 个网段。")
    if os.path.exists("ip_temp.txt"):
        os.remove("ip_temp.txt")
except Exception as e:
    print(f"普通 IP 库下载或合并失败 ({e})，将仅使用大厂专属 IP 段作为备份...")
    with open("ip.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(PREMIUM_CIDRS))

# 3. 运行测速
# -f ip.txt: 指定输入的 IP 段文件
# -n 500: 延迟测速线程数
# -dn 150: 对延迟最低的前 150 个 IP 进行实际下载测速
# -dt 5: 测速时间 5 秒
print("开始进行 IP 测速（普通与大厂混合测试）...")
os.system(f"./{binary_name} -f ip.txt -n 500 -dn 150 -dt 5 -o result.csv")

# 4. 定义国家/地区及其对应的 Cloudflare 节点三字码 (Colo)
COLO_MAP = {
    'HKG': '香港 (Hong Kong)',
    'NRT': '日本 (Japan)', 'HND': '日本 (Japan)', 'KIX': '日本 (Japan)',
    'TPE': '台湾 (Taiwan)', 'KHH': '台湾 (Taiwan)',
    'SIN': '新加坡 (Singapore)',
    'ICN': '韩国 (South Korea)',
    'BKK': '泰国 (Thailand)',
    'LAX': '美国 (United States)', 'SJC': '美国 (United States)', 'SFO': '美国 (United States)',
    'SEA': '美国 (United States)', 'ORD': '美国 (United States)', 'DFW': '美国 (United States)',
    'MIA': '美国 (United States)', 'IAD': '美国 (United States)', 'JFK': '美国 (United States)',
    'EWR': '美国 (United States)', 'ATL': '美国 (United States)', 'PDX': '美国 (United States)'
}

# 单独生成的文件名映射表
FILE_MAP = {
    '香港 (Hong Kong)': 'HK.txt',
    '日本 (Japan)': 'JP.txt',
    '台湾 (Taiwan)': 'TW.txt',
    '新加坡 (Singapore)': 'SG.txt',
    '韩国 (South Korea)': 'KR.txt',
    '泰国 (Thailand)': 'TH.txt',
    '美国 (United States)': 'US.txt'
}

categorized = {val: [] for val in set(COLO_MAP.values())}

# 5. 解析测速结果并分类
if not os.path.exists("result.csv"):
    print("未能生成测速结果文件 result.csv")
    sys.exit(1)

with open("result.csv", mode='r', encoding='utf-8') as f:
    reader = csv.reader(f)
    try:
        header = next(reader)  # 跳过表头
    except StopIteration:
        print("result.csv 为空")
        sys.exit(1)
        
    for row in reader:
        if len(row) < 9:
            continue
        ip = row[0]
        port = row[1]
        latency = row[6]
        speed = row[7]
        colo = row[8].upper()

        # 匹配地区
        matched_country = None
        for key, country_name in COLO_MAP.items():
            if key in colo:
                matched_country = country_name
                break
        
        if matched_country:
            categorized[matched_country].append({
                'ip': ip,
                'port': port,
                'latency': latency,
                'speed': speed,
                'colo': colo
            })

# 6. 格式化输出文件（包括汇总文件和单独分类文件）
combined_lines = []
combined_lines.append("# Cloudflare 优选 IP 列表 (合并普通与大厂 IP - 汇总)")
combined_lines.append("# 测速数据基于 GitHub Actions 运行环境，由于网络环境差异，数据仅供参考\n")

for country, ips in sorted(categorized.items()):
    # 优先按下载速度降序排序，如果速度相同则按延迟升序排序
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

    # 初始化单个地区文件的内容
    country_file_lines = []
    country_file_lines.append(f"# Cloudflare 优选 IP - {country}")
    country_file_lines.append("# 格式: IP:端口 - 延迟 - 速度 - 节点\n")

    combined_lines.append(f"=== {country} (Top 20) ===")

    if not sorted_ips:
        no_ip_msg = "未在此次测速中匹配到该地区的节点。\n"
        combined_lines.append(no_ip_msg)
        country_file_lines.append(no_ip_msg)
    else:
        for idx, item in enumerate(sorted_ips, 1):
            line = f"{item['ip']}:{item['port']} - 延迟: {item['latency']}ms - 速度: {item['speed']} MB/s - 节点: {item['colo']}"
            combined_lines.append(line)
            country_file_lines.append(line)
        combined_lines.append("") # 汇总文件中的地区空行隔开

    # 写入单独的国家/地区 TXT 文件
    filename = FILE_MAP.get(country)
    if filename:
        try:
            with open(filename, "w", encoding="utf-8") as f_sub:
                f_sub.write("\n".join(country_file_lines))
            print(f"已成功写入单地区文件: {filename}")
        except Exception as e:
            print(f"写入单地区文件 {filename} 失败: {e}")

# 7. 写入汇总文件
try:
    with open("cloudflare_ips.txt", "w", encoding="utf-8") as f_all:
        f_all.write("\n".join(combined_lines))
    print("汇总文件 cloudflare_ips.txt 写入完毕")
except Exception as e:
    print(f"写入汇总文件失败: {e}")
