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

def extract_product_accordion(html_content):
    """从HTML中提取产品accordion数据"""
    
    soup = BeautifulSoup(html_content, 'html.parser')
    products = []
    
    # 查找所有productaccordion
    accordions = soup.find_all('div', class_='productaccordion')
    
    print(f"Found {len(accordions)} product accordions")
    
    for accordion in accordions:
        try:
            # 查找标题 - button中的span
            button = accordion.find('button')
            title = ""
            if button:
                span = button.find('span')
                title = span.get_text(strip=True) if span else button.get_text(strip=True)
            
            if not title:
                continue
            
            # 查找ul.cmp-accordion__body-items
            ul = accordion.find('ul', class_='cmp-accordion__body-items')
            
            files = []
            if ul:
                # 查找所有li.cmp-accordion__body-item
                items = ul.find_all('li', class_='cmp-accordion__body-item')
                
                for item in items:
                    link = item.find('a')
                    if link:
                        href = link.get('href', '')
                        link_text = link.get_text(strip=True)
                        
                        if href and link_text:
                            files.append({
                                "name": link_text,
                                "url": href
                            })
            
            product_data = {
                "title": title,
                "total_files": len(files),
                "files": files
            }
            
            products.append(product_data)
            
        except Exception as e:
            continue
    
    return products

def extract_page_data(page_url, page_name):
    """提取单个页面的数据"""
    
    print(f"Fetching {page_name}...")
    
    html_content = fetch_page(page_url, timeout=15)
    
    if not html_content:
        print(f"[ERROR] Failed to fetch {page_name}")
        return None
    
    # 提取产品数据
    products = extract_product_accordion(html_content)
    
    if not products:
        print(f"[WARNING] No products found for {page_name}")
        return None
    
    page_data = {
        "page_name": page_name,
        "page_url": page_url,
        "total_products": len(products),
        "products": products
    }
    
    print(f"[OK] {page_name}: {len(products)} products")
    return page_data

def main():
    """主函数"""
    
    print("=== Extracting Product Information ===\n")
    
    # 两个页面的URL
    pages = [
        {
            "url": "/zh-cn/gongkaixinxipilou/jibenxinxi/chanpinjibenxinxi/zaishouchanpin",
            "name": "在售产品"
        },
        {
            "url": "/zh-cn/gongkaixinxipilou/jibenxinxi/chanpinjibenxinxi/tingshoujiqita",
            "name": "停售及其他产品"
        }
    ]
    
    all_pages_data = []
    
    for page in pages:
        page_data = extract_page_data(page["url"], page["name"])
        
        if page_data:
            all_pages_data.append(page_data)
        
        time.sleep(2)
    
    # 保存数据
    print(f"\n=== Saving Data ===\n")
    
    output_data = {
        "page_category": "产品基本信息",
        "total_pages": len(all_pages_data),
        "pages": all_pages_data
    }
    
    output_file = '产品基本信息.json'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] Saved data to {output_file}")
    
    # 统计信息
    total_products = sum(p['total_products'] for p in all_pages_data)
    total_files = sum(sum(prod['total_files'] for prod in p['products']) for p in all_pages_data)
    
    print(f"\n[SUMMARY]")
    print(f"  Total pages: {len(all_pages_data)}")
    print(f"  Total products: {total_products}")
    print(f"  Total files: {total_files}")
    
    # 打印预览
    print(f"\n[PREVIEW]")
    for page in all_pages_data:
        print(f"\n{page['page_name']} ({page['total_products']} products):")
        for product in page['products'][:3]:
            print(f"  - {product['title']}")
            if product['files']:
                print(f"    Files: {product['total_files']}")
                for file in product['files'][:2]:
                    print(f"      * {file['name']}")

if __name__ == "__main__":
    main()
