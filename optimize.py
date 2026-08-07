import os
import sys
import json
import tarfile
import stat
import subprocess
import urllib.request

GITHUB_API_URL = "https://api.github.com/repos/XIU2/CloudflareSpeedTest/releases/latest"
ARCHIVE_NAME = "cf.tar.gz"
TARGET_DIR = "."

def get_latest_download_url():
    print("正在初始化下载测速工具...")
    print("正在尝试通过 GitHub API 动态获取最新版本链接...")
    
    # 构造请求，加入 User-Agent 避免被 GitHub API 拦截
    req = urllib.request.Request(
        GITHUB_API_URL, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            assets = data.get("assets", [])
            for asset in assets:
                name = asset.get("name", "")
                # 匹配 Linux x86_64 (amd64) 版本
                if "linux_amd64.tar.gz" in name:
                    download_url = asset.get("browser_download_url")
                    print(f"动态获取成功: {download_url}")
                    return download_url
    except Exception as e:
        print(f"获取最新版本链接失败: {e}")
    return None

def download_file(url, save_path):
    print(f"正在下载: {url}")
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req) as response, open(save_path, 'wb') as out_file:
            out_file.write(response.read())
        print(f"下载成功: {save_path}")
        return True
    except Exception as e:
        print(f"下载失败: {e}")
        return False

def extract_and_verify(archive_path, target_dir):
    print("正在解压文件...")
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=target_dir)
        print("解压完成。")
    except Exception as e:
        print(f"解压失败: {e}")
        return None

    # 获取解压后的目录结构，便于在 GitHub Actions 日志中排查
    files_in_dir = os.listdir(target_dir)
    print("解压目录中的文件列表:", files_in_dir)

    # 1. 尝试匹配已知的默认文件名
    possible_names = ["cfst_linux_amd64", "CloudflareSpeedTest"]
    matched_file = None

    for name in possible_names:
        if name in files_in_dir:
            matched_file = name
            break

    # 2. 如果没有精确匹配，采用模糊匹配（防备后续官方再次调整文件名）
    if not matched_file:
        for file in files_in_dir:
            file_lower = file.lower()
            # 增加对 "cfst" 缩写的匹配支持
            if "cloudflare" in file_lower or "speedtest" in file_lower or "cfst" in file_lower:
                # 排除非执行文件
                if not file.endswith(('.tar.gz', '.txt', '.md', '.csv', '.py')):
                    matched_file = file
                    break

    if matched_file:
        exec_path = os.path.join(target_dir, matched_file)
        try:
            # 3. 赋予执行权限 (相当于 chmod +x)
            st = os.stat(exec_path)
            os.chmod(exec_path, st.st_mode | stat.S_IEXEC)
            print(f"成功找到程序并已赋予执行权限: {exec_path}")
            return exec_path
        except Exception as e:
            print(f"赋予执行权限失败: {e}")
            return None
    else:
        print("错误：未在解压目录中找到符合条件的测速可执行程序。")
        return None

def run_speed_test(exec_path):
    print("正在运行测速工具...")
    
    # 测速参数，可根据需求修改：
    # -n 200: 测试线程数
    # -t 4: 延迟测试次数
    # -dn 10: 测速下载数量
    # -sl 5: 设定的下载下限速度
    cmd = [exec_path, "-n", "200", "-t", "4", "-dn", "10", "-sl", "5"]
    
    try:
        # 启动子进程，并在控制台实时输出其运行日志
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            print(line, end="")
        process.wait()
        
        if process.returncode == 0:
            print("测速运行成功完成。")
            return True
        else:
            print(f"测速运行结束，但存在异常，退出码: {process.returncode}")
            return False
    except Exception as e:
        print(f"运行测速工具时发生异常: {e}")
        return False

def main():
    # 1. 获取最新版本下载链接
    download_url = get_latest_download_url()
    if not download_url:
        sys.exit(1)

    # 2. 下载压缩包
    if not download_file(download_url, ARCHIVE_NAME):
        sys.exit(1)

    # 3. 解压并匹配可执行二进制文件
    exec_path = extract_and_verify(ARCHIVE_NAME, TARGET_DIR)
    if not exec_path:
        sys.exit(1)

    # 4. 执行测速
    if not run_speed_test(exec_path):
        sys.exit(1)

    print("工作流任务执行完毕。")

if __name__ == "__main__":
    main()
