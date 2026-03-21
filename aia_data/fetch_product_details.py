import requests
from bs4 import BeautifulSoup
import json
import time
import re

base_url = "https://www.aia.com.cn"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def extract_product_details(html_content, product_name):
    """从产品详情页HTML中提取结构化数据"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    product_detail = {
        "name": product_name,
        "description": "",
        "features": [],
        "benefits": [],
        "coverage": [],
        "sections": []
    }
    
    # 提取页面标题/描述
    title_elem = soup.find('h1')
    if title_elem:
        product_detail["name"] = title_elem.get_text(strip=True)
    
    # 提取主要描述段落
    description_elems = soup.find_all('p', class_=['cmp-text', 'text-content'])
    if description_elems:
        product_detail["description"] = description_elems[0].get_text(strip=True)
    
    # 提取特性/优势 (通常在列表中)
    feature_lists = soup.find_all(['ul', 'ol'], class_=['feature-list', 'benefits-list', 'cmp-list'])
    for idx, feature_list in enumerate(feature_lists[:3]):
        items = feature_list.find_all('li')
        section_features = [item.get_text(strip=True) for item in items]
        if section_features:
            product_detail["features"].extend(section_features)
    
    # 提取所有主要内容区块
    content_sections = soup.find_all(['section', 'div'], class_=['cmp-section', 'content-section', 'product-section'])
    for section in content_sections[:5]:
        section_title = section.find(['h2', 'h3'])
        section_data = {
            "title": section_title.get_text(strip=True) if section_title else "未命名",
            "content": []
        }
        
        # 提取该区块内的所有文本内容
        paragraphs = section.find_all('p')
        for p in paragraphs:
            text = p.get_text(strip=True)
            if text:
                section_data["content"].append(text)
        
        # 提取该区块内的列表项
        list_items = section.find_all('li')
        for li in list_items:
            text = li.get_text(strip=True)
            if text:
                section_data["content"].append(text)
        
        if section_data["content"]:
            product_detail["sections"].append(section_data)
    
    # 提取保障范围/覆盖内容
    coverage_elem = soup.find(['div', 'section'], class_=['coverage', 'protection', 'guarantee'])
    if coverage_elem:
        coverage_items = coverage_elem.find_all(['li', 'p'])
        product_detail["coverage"] = [item.get_text(strip=True) for item in coverage_items]
    
    return product_detail

def fetch_product_details(product_url, product_name):
    """获取单个产品详情页"""
    try:
        full_url = base_url + product_url
        print(f"正在获取: {product_name} ({full_url})")
        
        response = requests.get(full_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            response.encoding = 'utf-8'
            details = extract_product_details(response.text, product_name)
            print(f"✅ 成功获取: {product_name}")
            return details
        else:
            print(f"❌ 获取失败 {product_name}: HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ 错误 {product_name}: {e}")
        return None

def fetch_recommended_products_from_api(category_url, category_name):
    """从API接口获取推荐产品数据"""
    try:
        # 将URL转换为.model.json格式
        # 例如: /zh-cn/baoxian/jibingbaozhang -> /zh-cn/baoxian/jibingbaozhang.model.json
        api_url = category_url + ".model.json"
        full_url = base_url + api_url
        
        print(f"正在获取推荐产品: {category_name} ({full_url})")
        
        response = requests.get(full_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            response.encoding = 'utf-8'
            data = response.json()
            
            # 提取推荐产品列表
            recommended_products = []
            
            # 根据API返回的数据结构提取产品
            if isinstance(data, dict):
                # 查找包含产品列表的字段
                for key in ['products', 'items', 'data', 'list']:
                    if key in data and isinstance(data[key], list):
                        recommended_products = data[key]
                        break
                
                # 如果没有找到标准字段，尝试直接使用data
                if not recommended_products and 'productfilterlist' in data:
                    recommended_products = data['productfilterlist']
            elif isinstance(data, list):
                recommended_products = data
            
            print(f"✅ 成功获取 {len(recommended_products)} 个推荐产品")
            return recommended_products
        else:
            print(f"❌ 获取失败 {category_name}: HTTP {response.status_code}")
            return []
            
    except Exception as e:
        print(f"❌ 错误 {category_name}: {e}")
        return []

def fetch_all_products():
    """获取所有产品详情和推荐产品"""
    with open('products_data.json', 'r', encoding='utf-8') as f:
        products_data = json.load(f)
    
    all_products = {
        "personal_insurance": [],
        "group_insurance": [],
        "recommended_products": {}
    }
    
    # 获取个险产品详情
    print("\n【获取个险产品详情】")
    for product in products_data["personal_insurance"]:
        details = fetch_product_details(product["url"], product["name"])
        if details:
            all_products["personal_insurance"].append(details)
        time.sleep(2)  # 避免请求过快
    
    # 获取团险产品详情
    print("\n【获取团险产品详情】")
    for product in products_data["group_insurance"]:
        details = fetch_product_details(product["url"], product["name"])
        if details:
            all_products["group_insurance"].append(details)
        time.sleep(2)
    
    # 获取推荐产品（从API接口）
    print("\n【获取推荐产品】")
    
    # 从个险产品中获取推荐产品
    for product in products_data["personal_insurance"]:
        category_name = product["name"]
        category_url = product["url"]
        recommended = fetch_recommended_products_from_api(category_url, category_name)
        if recommended:
            all_products["recommended_products"][category_name] = recommended
        time.sleep(2)
    
    # 保存完整数据
    with open('complete_products_data.json', 'w', encoding='utf-8') as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    
    print("\n✅ 完整产品数据已保存到 complete_products_data.json")
    return all_products

if __name__ == "__main__":
    fetch_all_products()
