import requests
import json
import sys
import time

# 设置输出编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

api_url = "https://cws.aia.com.cn/mypage/productpublish/list"

def fetch_products(status, page_index=0, page_size=100, cookies=None):
    """从API获取产品列表"""
    
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
        print(f"Fetching {status} products (page {page_index})...")
        
        response = requests.post(
            api_url, 
            json=payload,
            headers=headers,
            cookies=cookies,
            timeout=15
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] Response received")
            return data
        else:
            print(f"[ERROR] HTTP {response.status_code}")
            print(f"Response: {response.text[:300]}\n")
            return None
            
    except Exception as e:
        print(f"[ERROR] {str(e)[:200]}\n")
        return None

def extract_products_from_response(response_data):
    """从API响应中提取产品数据"""
    
    products = []
    
    try:
        if not response_data:
            return products
        
        # 检查响应结构
        if isinstance(response_data, dict):
            # 检查是否成功
            if response_data.get('success') == False or response_data.get('success') == 'false':
                print(f"API Error: {response_data.get('error_message', 'Unknown error')}")
                return products
            
            if 'data' in response_data:
                items = response_data['data']
            elif 'list' in response_data:
                items = response_data['list']
            elif 'result' in response_data:
                items = response_data['result']
            else:
                print(f"Response keys: {list(response_data.keys())}")
                return products
        elif isinstance(response_data, list):
            items = response_data
        else:
            return products
        
        if not isinstance(items, list):
            print(f"Items is not a list: {type(items)}")
            return products
        
        print(f"Found {len(items)} items in response")
        
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
    
    print("=== Fetching Products from API ===\n")
    
    # 设置Cookie
    cookies = {
        "acw_tc": "0a01015417740824668537447e007415c80647724def88f115ca6cd599645b"
    }
    
    # 获取在售产品
    print("Step 1: Fetching 在售 products...\n")
    
    response_on_sale = fetch_products("在售", page_index=0, page_size=100, cookies=cookies)
    products_on_sale = extract_products_from_response(response_on_sale) if response_on_sale else []
    
    print(f"Found {len(products_on_sale)} on-sale products\n")
    
    time.sleep(1)
    
    # 获取停售产品
    print("Step 2: Fetching 停售 products...\n")
    
    response_discontinued = fetch_products("停售", page_index=0, page_size=100, cookies=cookies)
    products_discontinued = extract_products_from_response(response_discontinued) if response_discontinued else []
    
    print(f"Found {len(products_discontinued)} discontinued products\n")
    
    # 组织数据
    print("Step 3: Organizing data...\n")
    
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
    
    # 打印预览
    if products_on_sale:
        print(f"\n[PREVIEW - 在售产品 (前5个)]")
        for i, product in enumerate(products_on_sale[:5], 1):
            print(f"{i}. {product['name']}")
            if product['code']:
                print(f"   Code: {product['code']}")
    
    if products_discontinued:
        print(f"\n[PREVIEW - 停售产品 (前5个)]")
        for i, product in enumerate(products_discontinued[:5], 1):
            print(f"{i}. {product['name']}")
            if product['code']:
                print(f"   Code: {product['code']}")

if __name__ == "__main__":
    main()
