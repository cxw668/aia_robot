import requests
from bs4 import BeautifulSoup
import json
import sys
import time

# 设置输出编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

base_url = "https://www.aia.com.cn"
api_url = "https://cws.aia.com.cn/mypage/productpublish/list"

def create_session():
    """创建一个会话对象来维持Cookie"""
    session = requests.Session()
    return session

def visit_main_page(session):
    """访问主页面以获取初始Cookie"""
    
    print("Step 1: Visiting main page to establish session...\n")
    
    try:
        url = base_url + "/zh-cn"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
        }
        
        response = session.get(url, headers=headers, timeout=10)
        
        print(f"Status: {response.status_code}")
        print(f"Cookies: {session.cookies.get_dict()}\n")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"[ERROR] {e}\n")
        return False

def visit_product_page(session):
    """访问产品页面以获取相关Cookie"""
    
    print("Step 2: Visiting product page...\n")
    
    try:
        url = base_url + "/zh-cn/gongkaixinxipilou/jibenxinxi/chanpinjibenxinxi/zaishouchanpin"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
            "Referer": base_url + "/zh-cn"
        }
        
        response = session.get(url, headers=headers, timeout=10)
        
        print(f"Status: {response.status_code}")
        print(f"Current Cookies: {session.cookies.get_dict()}\n")
        
        return response.status_code == 200
        
    except Exception as e:
        print(f"[ERROR] {e}\n")
        return False

def fetch_products_with_session(session, status, page_index=0, page_size=100):
    """使用会话调用API获取产品列表"""
    
    print(f"Step 3: Fetching {status} products from API...\n")
    
    payload = {
        "like": "",
        "status": status,
        "page": {
            "pageSize": str(page_size),
            "index": page_index
        }
    }
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "Origin": "https://www.aia.com.cn",
        "Referer": "https://www.aia.com.cn/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site"
    }
    
    try:
        print(f"Sending request to API...")
        print(f"Current session cookies: {session.cookies.get_dict()}\n")
        
        response = session.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=15
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}\n")
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Response received")
            print(f"Response: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}\n")
            return data
        else:
            print(f"[ERROR] HTTP {response.status_code}")
            print(f"Response: {response.text[:500]}\n")
            return None
            
    except Exception as e:
        print(f"[ERROR] {str(e)[:200]}\n")
        return None

def extract_products(response_data):
    """提取产品数据"""
    
    products = []
    
    if not response_data:
        return products
    
    try:
        if isinstance(response_data, dict):
            if response_data.get('success') == False or response_data.get('success') == 'false':
                print(f"API Error: {response_data.get('error_message', 'Unknown error')}")
                return products
            
            if 'data' in response_data:
                items = response_data['data']
            elif 'list' in response_data:
                items = response_data['list']
            else:
                print(f"Response keys: {list(response_data.keys())}")
                return products
        else:
            items = response_data
        
        if not isinstance(items, list):
            return products
        
        for item in items:
            if isinstance(item, dict):
                product = {
                    "id": item.get('id', ''),
                    "name": item.get('name', item.get('productName', '')),
                    "code": item.get('code', item.get('productCode', '')),
                    "status": item.get('status', ''),
                    "type": item.get('type', item.get('productType', '')),
                    "description": item.get('description', item.get('remark', ''))
                }
                products.append(product)
        
        return products
        
    except Exception as e:
        print(f"[ERROR] Failed to extract products: {e}")
        return products

def main():
    """主函数"""
    
    print("=== Fetching Products with Session ===\n")
    
    # 创建会话
    session = create_session()
    
    # 访问主页面
    if not visit_main_page(session):
        print("[ERROR] Failed to visit main page")
        return
    
    time.sleep(1)
    
    # 访问产品页面
    if not visit_product_page(session):
        print("[ERROR] Failed to visit product page")
        return
    
    time.sleep(1)
    
    # 获取在售产品
    response_on_sale = fetch_products_with_session(session, "在售", page_index=0, page_size=100)
    products_on_sale = extract_products(response_on_sale) if response_on_sale else []
    
    print(f"Found {len(products_on_sale)} on-sale products\n")
    
    time.sleep(1)
    
    # 获取停售产品
    response_discontinued = fetch_products_with_session(session, "停售", page_index=0, page_size=100)
    products_discontinued = extract_products(response_discontinued) if response_discontinued else []
    
    print(f"Found {len(products_discontinued)} discontinued products\n")
    
    # 组织数据
    output_data = {
        "page_category": "产品基本信息",
        "total_products": len(products_on_sale) + len(products_discontinued),
        "categories": [
            {
                "status": "在售",
                "total": len(products_on_sale),
                "products": products_on_sale
            },
            {
                "status": "停售",
                "total": len(products_discontinued),
                "products": products_discontinued
            }
        ]
    }
    
    # 保存数据
    output_file = '产品基本信息.json'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    
    print(f"[OK] Saved data to {output_file}")
    
    # 统计信息
    print(f"\n[SUMMARY]")
    print(f"  On-sale products: {len(products_on_sale)}")
    print(f"  Discontinued products: {len(products_discontinued)}")
    print(f"  Total products: {len(products_on_sale) + len(products_discontinued)}")

if __name__ == "__main__":
    main()
