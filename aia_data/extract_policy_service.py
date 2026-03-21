import requests
from bs4 import BeautifulSoup
import json
import sys

# 设置输出编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

base_url = "https://www.aia.com.cn"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def fetch_policy_service_page(url):
    """从URL获取保单服务页面"""
    try:
        full_url = base_url + url if url.startswith('/') else url
        print(f"  Fetching: {full_url}...")
        
        response = requests.get(full_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            response.encoding = 'utf-8'
            return response.text
        else:
            print(f"  [ERROR] HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None

def extract_accordion_items(html_content):
    """从HTML内容中提取所有accordion项"""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    accordion_items = []
    
    # 查找所有accordion项
    items = soup.find_all('div', class_='cmp-accordion__item')
    
    for item in items:
        # 提取标题 - 从button的span中获取
        title_elem = item.find('span')
        title = title_elem.get_text(strip=True) if title_elem else ""
        
        # 提取内容 - 从cmp-accordion__body中获取
        body_elem = item.find('div', class_='cmp-accordion__body')
        
        content = ""
        if body_elem:
            # 获取所有段落
            paragraphs = body_elem.find_all('p')
            content_list = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if text:
                    content_list.append(text)
            content = "\n".join(content_list)
        
        if title:
            accordion_item = {
                "title": title,
                "content": content
            }
            accordion_items.append(accordion_item)
    
    return accordion_items

def save_policy_service_data(all_services, output_file):
    """保存保单服务数据为JSON文件"""
    
    # 组织数据结构
    policy_service_data = {
        "service_categories": all_services
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(policy_service_data, f, ensure_ascii=False, indent=2)
    
    total_items = sum(len(service['items']) for service in all_services)
    print(f"\n[SUCCESS] Extracted {total_items} total policy service items")
    print(f"[SUCCESS] Policy service data saved to {output_file}")

def main():
    """主函数"""
    # 多个URL数组
    input_urls = [
        "/zh-cn/fuwu/fuwuzhinan/baodanfuwu",
        "/zh-cn/fuwu/fuwuzhinan/xuqijizhanghuguanli",
        "/zh-cn/fuwu/fuwuzhinan/nianjin",
        "/zh-cn/fuwu/fuwuzhinan/baoxianjihuabiangeng",
        "/zh-cn/fuwu/fuwuzhinan/tuibao",
        "/zh-cn/fuwu/fuwuzhinan/wannengxian",
        "/zh-cn/fuwu/fuwuzhinan/hetong",
        "/zh-cn/fuwu/fuwuzhinan/jiekuan"
    ]
    
    output_file = '保单服务.json'
    
    print(f"Extracting policy service data from {len(input_urls)} URLs...\n")
    
    all_services = []
    
    # 遍历每个URL
    for idx, url in enumerate(input_urls, 1):
        print(f"[{idx}/{len(input_urls)}] Processing: {url}")
        
        # 获取页面内容
        html_content = fetch_policy_service_page(url)
        
        if not html_content:
            print(f"  [SKIP] Failed to fetch page")
            continue
        
        # 提取accordion数据
        items = extract_accordion_items(html_content)
        
        if items:
            # 从URL提取服务名称
            service_name = url.split('/')[-1]
            
            service_data = {
                "service_name": service_name,
                "url": url,
                "total_items": len(items),
                "items": items
            }
            all_services.append(service_data)
            print(f"  [OK] Extracted {len(items)} items")
        else:
            print(f"  [WARNING] No items found")
    
    if not all_services:
        print("[ERROR] No data extracted from any URL")
        return
    
    # 保存数据
    save_policy_service_data(all_services, output_file)
    
    # 打印预览
    print("\n[PREVIEW]")
    for service in all_services[:2]:
        print(f"\nService: {service['service_name']} ({service['total_items']} items)")
        for item in service['items'][:2]:
            content_preview = item['content'][:60].replace('\n', ' ')
            print(f"  - {item['title']}: {content_preview}...")

if __name__ == "__main__":
    main()
