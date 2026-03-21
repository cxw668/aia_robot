from bs4 import BeautifulSoup
import json
import sys

# 设置输出编码
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def extract_service_menu(html_file):
    """从HTML文件中提取所有a标签的链接和标题"""
    
    # 读取HTML文件
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    menu_items = []
    
    # 提取所有a标签
    links = soup.find_all('a')
    
    for link in links:
        href = link.get('href', '')
        title = link.get('title', '')
        text = link.get_text(strip=True)
        
        # 只保留有href和title的链接
        if href and title:
            menu_item = {
                "title": title,
                "url": href,
                "text": text
            }
            menu_items.append(menu_item)
    
    return menu_items

def save_menu_data(menu_items, output_file):
    """保存菜单数据为JSON文件"""
    
    # 按层级组织菜单
    menu_structure = {
        "total_items": len(menu_items),
        "items": menu_items
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(menu_structure, f, ensure_ascii=False, indent=2)
    
    print(f"[SUCCESS] Extracted {len(menu_items)} menu items")
    print(f"[SUCCESS] Menu data saved to {output_file}")

def main():
    """主函数"""
    input_file = 'test.html'
    output_file = '客户服务菜单.json'
    
    print(f"Extracting menu data from {input_file}...")
    
    # 提取菜单数据
    menu_items = extract_service_menu(input_file)
    
    # 保存菜单数据
    save_menu_data(menu_items, output_file)
    
    # 打印前几项作为预览
    print("\n[PREVIEW]")
    for i, item in enumerate(menu_items[:5], 1):
        print(f"{i}. {item['title']} -> {item['url']}")
    
    if len(menu_items) > 5:
        print(f"... and {len(menu_items) - 5} more items")

if __name__ == "__main__":
    main()
