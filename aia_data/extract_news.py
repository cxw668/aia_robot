import requests
from bs4 import BeautifulSoup
import json
import sys

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
        print(f"Fetching: {full_url}")
        
        response = requests.get(full_url, headers=headers, timeout=timeout)
        response.encoding = 'utf-8'
        
        if response.status_code == 200:
            print(f"[OK] Page fetched")
            return response.text
        else:
            print(f"[ERROR] HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"[ERROR] {str(e)[:100]}")
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
    
    print(f"Found {len(cards)} news cards")
    
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

def save_data(tabs, news_items, output_file):
    """保存数据为JSON文件"""
    
    data = {
        "page_name": "分公司页面",
        "tabs": tabs,
        "total_news": len(news_items),
        "news_items": news_items
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] Saved {len(tabs)} tabs and {len(news_items)} news items to {output_file}")

def main():
    """主函数"""
    input_url = '/zh-cn/fuwu/shanghai'
    output_file = '分公司页面.json'
    
    print(f"Extracting data from {input_url}...\n")
    
    html_content = fetch_page(input_url, timeout=10)
    
    if not html_content:
        print("[ERROR] Failed to fetch page")
        return
    
    # 提取tabs
    tabs = extract_tabs_from_ol(html_content)
    print(f"[OK] Found {len(tabs)} tabs\n")
    
    # 提取新闻卡片
    news_items = extract_news_cards(html_content)
    
    if not news_items:
        print("[WARNING] No news items found")
        return
    
    # 保存数据
    save_data(tabs, news_items, output_file)
    
    # 打印预览
    print("\n[PREVIEW]")
    print(f"Tabs ({len(tabs)}):")
    for tab in tabs[:5]:
        print(f"  - {tab['name']}: {tab['url']}")
    if len(tabs) > 5:
        print(f"  ... and {len(tabs) - 5} more")
    
    print(f"\nNews Items ({len(news_items)}):")
    for i, item in enumerate(news_items[:3], 1):
        print(f"{i}. {item['title'][:60]}")
        print(f"   {item['description'][:80]}...")

if __name__ == "__main__":
    main()
