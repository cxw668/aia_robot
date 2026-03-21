import requests
from bs4 import BeautifulSoup
import json

base_url = "https://www.aia.com.cn/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def parse_products_from_html(html_content):
    """从HTML中解析个险和团险产品数据"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    products_data = {
        "personal_insurance": [],
        "group_insurance": []
    }
    
    # 解析个险产品 (personal-insurance)
    personal_section = soup.find('div', {'data-target-element': 'personal-insurance'})
    if personal_section:
        items = personal_section.find_all('li', class_='cmp-navigation2__item--level-1')
        for item in items:
            link = item.find('a', class_='cmp-navigation2__item-link-text-level-1')
            if link:
                title = link.get_text(strip=True)
                url = link.get('href', '')
                products_data["personal_insurance"].append({
                    "name": title,
                    "url": url
                })
    
    # 解析团险产品 (group-insurance)
    group_section = soup.find('div', {'data-target-element': 'group-insurance'})
    if group_section:
        items = group_section.find_all('li', class_='cmp-navigation2__item--level-1')
        for item in items:
            link = item.find('a', class_='cmp-navigation2__item-link-text-level-1')
            if link:
                title = link.get_text(strip=True)
                url = link.get('href', '')
                products_data["group_insurance"].append({
                    "name": title,
                    "url": url
                })
    
    return products_data

def fetch_and_parse_products():
    """获取网页并解析产品数据"""
    try:
        response = requests.get(base_url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            print("✅ 网络通畅！成功连接到友邦保险官网。")
            
            # 读取本地HTML文件进行解析
            with open('index.html', 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            products = parse_products_from_html(html_content)
            
            # 输出结构化数据
            print("\n【个险产品】")
            for product in products["personal_insurance"]:
                print(f"  - {product['name']}: {product['url']}")
            
            print("\n【团险产品】")
            for product in products["group_insurance"]:
                print(f"  - {product['name']}: {product['url']}")
            
            # 保存为JSON
            with open('products_data.json', 'w', encoding='utf-8') as f:
                json.dump(products, f, ensure_ascii=False, indent=2)
            
            print("\n✅ 数据已保存到 products_data.json")
            
            return products
        else:
            print(f"❌ 连接失败，HTTP 状态码: {response.status_code}")
            
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    fetch_and_parse_products()
