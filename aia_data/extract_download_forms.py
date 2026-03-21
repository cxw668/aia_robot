import requests
from bs4 import BeautifulSoup
import json
import sys
import re

# 设置输出编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

base_url = "https://www.aia.com.cn"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_page(url):
    """从URL获取页面内容"""
    try:
        full_url = base_url + url if url.startswith('/') else url
        print(f"Fetching page from {full_url}...")
        
        response = requests.get(full_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            response.encoding = 'utf-8'
            print(f"[SUCCESS] Page fetched successfully")
            return response.text
        else:
            print(f"[ERROR] HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

def extract_download_items(html_content):
    """从HTML内容中提取下载项"""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    download_items = []
    
    # 查找所有包含下载文件的链接
    # 查找所有href包含/content/dam/的链接（这是AEM DAM资源路径）
    all_links = soup.find_all('a', href=True)
    
    for link in all_links:
        href = link.get('href', '')
        
        # 过滤出下载链接（包含/content/dam/或.pdf/.doc等文件扩展名）
        if '/content/dam/' in href or any(href.endswith(ext) for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
            # 提取文本作为文件名
            filename = link.get_text(strip=True)
            
            # 如果没有文本，尝试从href提取文件名
            if not filename:
                filename = href.split('/')[-1]
            
            if href and filename:
                # 处理相对URL
                if href.startswith('/'):
                    full_url = base_url + href
                else:
                    full_url = href
                
                download_item = {
                    "filename": filename,
                    "url": href,
                    "full_url": full_url
                }
                download_items.append(download_item)
    
    # 去重（基于URL）
    seen_urls = set()
    unique_items = []
    for item in download_items:
        if item['url'] not in seen_urls:
            seen_urls.add(item['url'])
            unique_items.append(item)
    
    return unique_items

def save_download_data(items, output_file):
    """保存下载数据为JSON文件"""
    
    # 组织数据结构
    download_data = {
        "page_name": "表单下载",
        "total_items": len(items),
        "items": items
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(download_data, f, ensure_ascii=False, indent=2)
    
    print(f"[SUCCESS] Extracted {len(items)} download items")
    print(f"[SUCCESS] Download data saved to {output_file}")

def main():
    """主函数"""
    input_url = '/zh-cn/fuwu/biaodanxiazai/tuanxian'
    output_file = '表单下载-团险.json'
    
    print(f"Extracting download items from {input_url}...\n")
    
    # 获取页面内容
    html_content = fetch_page(input_url)
    
    if not html_content:
        print("[ERROR] Failed to fetch page content")
        return
    
    # 提取下载项
    items = extract_download_items(html_content)
    
    if not items:
        print("[WARNING] No download items found")
        return
    
    # 保存数据
    save_download_data(items, output_file)
    
    # 打印预览
    print("\n[PREVIEW]")
    for i, item in enumerate(items[:10], 1):
        print(f"\n{i}. Filename: {item['filename']}")
        print(f"   URL: {item['url']}")
    
    if len(items) > 10:
        print(f"\n... and {len(items) - 10} more items")

if __name__ == "__main__":
    main()
