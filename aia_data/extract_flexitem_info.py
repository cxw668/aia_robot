import requests
from bs4 import BeautifulSoup
import json
import sys
import time
import re

# 设置输出编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

base_url = "https://www.aia.com.cn"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def fetch_page(url, timeout=10):
    """从URL获取页面内容"""
    try:
        full_url = base_url + url if url.startswith('/') else url
        
        response = requests.get(full_url, headers=headers, timeout=timeout)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            return response.text
        else:
            return None
            
    except Exception as e:
        return None

def extract_tabs_from_ol(html_content):
    """从ol元素中提取tabs"""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    tabs = []
    
    # 查找所有ol元素
    ols = soup.find_all('ol')
    
    for ol in ols:
        # 查找ol内的所有a标签
        links = ol.find_all('a')
        
        for link in links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            
            if text and href:
                tabs.append({
                    "name": text,
                    "url": href
                })
    
    return tabs

def extract_flexitem_info(html_content):
    """从flexitem中提取公司信息"""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    flexitems = []
    
    # 查找所有flexitem
    items = soup.find_all('div', class_='cmp-flexitem')
    
    for item in items:
        try:
            # 查找h6标题
            h6_elem = item.find('h6', class_='cmp-title__text')
            title = h6_elem.get_text(strip=True) if h6_elem else ""
            
            # 查找p标签中的内容
            p_elem = item.find('p')
            
            if not p_elem:
                continue
            
            # 提取地址
            address_elem = p_elem.find('span', class_='viewmap_address')
            address = address_elem.get_text(strip=True) if address_elem else ""
            
            # 提取服务时间
            time_elem = p_elem.find('span', class_='viewmap_time')
            service_time = time_elem.get_text(strip=True) if time_elem else ""
            
            # 提取电话
            tel_elem = p_elem.find('a', class_='viewmap_tel')
            phone = tel_elem.get_text(strip=True) if tel_elem else ""
            
            # 提取所有文本内容
            full_text = p_elem.get_text(strip=True)
            
            if title or address or service_time:
                flexitem_data = {
                    "title": title,
                    "address": address,
                    "service_time": service_time,
                    "phone": phone,
                    "full_text": full_text
                }
                flexitems.append(flexitem_data)
        except Exception as e:
            continue
    
    return flexitems

def extract_region_data(region_url, region_name):
    """提取单个地区的完整数据"""
    
    print(f"  Fetching {region_name}...")
    
    html_content = fetch_page(region_url, timeout=10)
    
    if not html_content:
        print(f"  [SKIP] Failed to fetch {region_name}")
        return None
    
    # 提取flexitem信息
    flexitems = extract_flexitem_info(html_content)
    
    if not flexitems:
        print(f"  [SKIP] No flexitem info found for {region_name}")
        return None
    
    region_data = {
        "region_name": region_name,
        "region_url": region_url,
        "total_flexitems": len(flexitems),
        "flexitems": flexitems
    }
    
    print(f"  [OK] {region_name}: {len(flexitems)} flexitems")
    return region_data

def main():
    """主函数"""
    
    # 首先从上海页面获取所有地区tabs
    print("Step 1: Fetching region tabs from Shanghai page...\n")
    
    shanghai_url = '/zh-cn/fuwu/shanghai'
    html_content = fetch_page(shanghai_url, timeout=10)
    
    if not html_content:
        print("[ERROR] Failed to fetch Shanghai page")
        return
    
    tabs = extract_tabs_from_ol(html_content)
    print(f"Found {len(tabs)} regions\n")
    
    # 提取所有地区的flexitem数据
    print("Step 2: Extracting flexitem data from all regions...\n")
    
    all_regions_data = []
    
    for idx, tab in enumerate(tabs, 1):
        region_name = tab['name']
        region_url = tab['url']
        
        print(f"[{idx}/{len(tabs)}] {region_name}")
        
        region_data = extract_region_data(region_url, region_name)
        
        if region_data:
            all_regions_data.append(region_data)
        
        # 避免请求过快
        time.sleep(1)
    
    # 保存所有地区数据
    print(f"\nStep 3: Saving data...\n")
    
    output_data = {
        "page_name": "友邦人寿分公司页面信息",
        "total_regions": len(all_regions_data),
        "regions": all_regions_data
    }
    
    output_file = '分公司页面.json'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] Saved data to {output_file}")
    
    # 统计信息
    total_flexitems = sum(r['total_flexitems'] for r in all_regions_data)
    print(f"\n[SUMMARY]")
    print(f"  Total regions: {len(all_regions_data)}")
    print(f"  Total flexitems: {total_flexitems}")
    
    # 打印预览
    print(f"\n[PREVIEW]")
    for region in all_regions_data[:2]:
        print(f"\n{region['region_name']} ({region['total_flexitems']} flexitems):")
        for item in region['flexitems'][:2]:
            print(f"  Title: {item['title']}")
            print(f"  Address: {item['address'][:60]}")
            print(f"  Service Time: {item['service_time']}")
            if item['phone']:
                print(f"  Phone: {item['phone']}")

if __name__ == "__main__":
    main()
