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

def extract_landingcard_details(html_content):
    """从HTML中提取landingcard详细信息"""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    cards_data = []
    
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
            
            # 提取标题 - h1
            title_elem = link.find('h1', class_='cmp-landingcard__title')
            title = title_elem.get_text(strip=True) if title_elem else ""
            
            # 提取描述 - div class=cmp-landingcard__description
            desc_elem = link.find('div', class_='cmp-landingcard__description')
            description = desc_elem.get_text(strip=True) if desc_elem else ""
            
            # 尝试提取h6（如果存在）
            h6_elem = link.find('h6')
            h6_text = h6_elem.get_text(strip=True) if h6_elem else ""
            
            # 尝试提取p（如果存在）
            p_elem = link.find('p')
            p_text = p_elem.get_text(strip=True) if p_elem else ""
            
            if title and href:
                full_url = base_url + href if href.startswith('/') else href
                card_data = {
                    "title": title,
                    "description": description[:150] if description else "",
                    "h6": h6_text,
                    "p": p_text,
                    "url": href,
                    "full_url": full_url
                }
                cards_data.append(card_data)
        except Exception as e:
            continue
    
    return cards_data

def extract_region_data(region_url, region_name):
    """提取单个地区的数据"""
    
    print(f"  Fetching {region_name}...")
    
    html_content = fetch_page(region_url, timeout=10)
    
    if not html_content:
        print(f"  [SKIP] Failed to fetch {region_name}")
        return None
    
    # 提取landingcard详细信息
    cards_data = extract_landingcard_details(html_content)
    
    if not cards_data:
        print(f"  [SKIP] No cards found for {region_name}")
        return None
    
    region_data = {
        "region_name": region_name,
        "region_url": region_url,
        "total_cards": len(cards_data),
        "cards": cards_data
    }
    
    print(f"  [OK] {region_name}: {len(cards_data)} cards")
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
    
    # 提取所有地区的数据
    print("Step 2: Extracting landingcard data from all regions...\n")
    
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
        "page_name": "友邦人寿分公司页面详情",
        "total_regions": len(all_regions_data),
        "regions": all_regions_data
    }
    
    output_file = '分公司页面.json'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] Saved data to {output_file}")
    
    # 统计信息
    total_cards = sum(r['total_cards'] for r in all_regions_data)
    print(f"\n[SUMMARY]")
    print(f"  Total regions: {len(all_regions_data)}")
    print(f"  Total cards: {total_cards}")
    
    # 打印预览
    print(f"\n[PREVIEW]")
    for region in all_regions_data[:2]:
        print(f"\n{region['region_name']} ({region['total_cards']} cards):")
        for card in region['cards'][:2]:
            print(f"  Title: {card['title'][:60]}")
            print(f"  Description: {card['description'][:60]}")
            if card['h6']:
                print(f"  H6: {card['h6'][:40]}")
            if card['p']:
                print(f"  P: {card['p'][:40]}")

if __name__ == "__main__":
    main()
