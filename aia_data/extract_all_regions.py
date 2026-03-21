import requests
from bs4 import BeautifulSoup
import json
import sys
import time

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
            print(f"  [ERROR] HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"  [ERROR] {str(e)[:80]}")
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

def extract_news_cards(html_content):
    """从HTML中提取landingcard新闻卡片"""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    news_items = []
    
    # 查找所有landingcard
    cards = soup.find_all('div', class_='landingcard')
    
    for card in cards:
        try:
            # 查找a标签
            link = card.find('a')
            if not link:
                continue
            
            href = link.get('href', '')
            if not href:
                continue
            
            # 提取标题 - h1 class=cmp-landingcard__title
            title_elem = link.find('h1', class_='cmp-landingcard__title')
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # 提取描述 - div class=cmp-landingcard__description
            desc_elem = link.find('div', class_='cmp-landingcard__description')
            description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            if title and href:
                full_url = base_url + href if href.startswith('/') else href
                news_items.append({
                    "title": title,
                    "description": description[:150] if description else "",
                    "url": href,
                    "full_url": full_url
                })
        except Exception as e:
            continue
    
    return news_items

def extract_region_data(region_url, region_name):
    """提取单个地区的数据"""
    
    print(f"  Fetching {region_name}...")
    
    html_content = fetch_page(region_url, timeout=10)
    
    if not html_content:
        print(f"  [SKIP] Failed to fetch {region_name}")
        return None
    
    # 提取新闻卡片
    news_items = extract_news_cards(html_content)
    
    if not news_items:
        print(f"  [SKIP] No news items found for {region_name}")
        return None
    
    region_data = {
        "region_name": region_name,
        "region_url": region_url,
        "total_news": len(news_items),
        "news_items": news_items
    }
    
    print(f"  [OK] {region_name}: {len(news_items)} news items")
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
    
    # 提取所有地区的新闻数据
    print("Step 2: Extracting news data from all regions...\n")
    
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
        "page_name": "友邦人寿分公司",
        "total_regions": len(all_regions_data),
        "regions": all_regions_data
    }
    
    output_file = '所有分公司页面.json'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] Saved data to {output_file}")
    
    # 统计信息
    total_news = sum(r['total_news'] for r in all_regions_data)
    print(f"\n[SUMMARY]")
    print(f"  Total regions: {len(all_regions_data)}")
    print(f"  Total news items: {total_news}")
    
    # 打印预览
    print(f"\n[PREVIEW]")
    for region in all_regions_data[:3]:
        print(f"\n{region['region_name']} ({region['total_news']} news):")
        for news in region['news_items'][:2]:
            print(f"  - {news['title'][:60]}")

if __name__ == "__main__":
    main()
