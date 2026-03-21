import json
import os
from pathlib import Path

def create_data_summary():
    """创建数据提取总结"""
    
    data_dir = Path('.')
    
    summary = {
        "project": "友邦人寿官网数据提取",
        "extraction_date": "2026-03-21",
        "total_files": 0,
        "data_sources": []
    }
    
    # 扫描所有JSON文件
    json_files = list(data_dir.glob('*.json'))
    
    for json_file in sorted(json_files):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            file_size = json_file.stat().st_size
            
            # 统计数据
            if isinstance(data, dict):
                if 'total_regions' in data:
                    item_count = data['total_regions']
                    item_type = "地区"
                elif 'total_products' in data:
                    item_count = data['total_products']
                    item_type = "产品"
                elif 'total_news' in data:
                    item_count = data['total_news']
                    item_type = "新闻"
                elif 'regions' in data:
                    item_count = len(data['regions'])
                    item_type = "分公司"
                else:
                    item_count = len(data)
                    item_type = "项"
            else:
                item_count = len(data)
                item_type = "项"
            
            source_info = {
                "filename": json_file.name,
                "size_kb": round(file_size / 1024, 2),
                "item_count": item_count,
                "item_type": item_type,
                "description": data.get('page_name', data.get('page_category', ''))
            }
            
            summary["data_sources"].append(source_info)
            summary["total_files"] += 1
            
        except Exception as e:
            print(f"Error reading {json_file}: {e}")
    
    return summary

def main():
    """主函数"""
    
    print("=== 数据提取总结 ===\n")
    
    summary = create_data_summary()
    
    print(f"项目: {summary['project']}")
    print(f"提取日期: {summary['extraction_date']}")
    print(f"总文件数: {summary['total_files']}\n")
    
    print("=" * 80)
    print(f"{'文件名':<30} {'大小(KB)':<12} {'数据量':<15} {'类型':<10}")
    print("=" * 80)
    
    total_size = 0
    total_items = 0
    
    for source in summary['data_sources']:
        print(f"{source['filename']:<30} {source['size_kb']:<12} {source['item_count']:<15} {source['item_type']:<10}")
        total_size += source['size_kb']
        total_items += source['item_count']
    
    print("=" * 80)
    print(f"{'总计':<30} {total_size:<12.2f} {total_items:<15}")
    print("=" * 80)
    
    print("\n详细信息:\n")
    
    for i, source in enumerate(summary['data_sources'], 1):
        print(f"{i}. {source['filename']}")
        print(f"   描述: {source['description']}")
        print(f"   大小: {source['size_kb']} KB")
        print(f"   数据量: {source['item_count']} {source['item_type']}\n")
    
    # 保存总结
    summary_file = '数据提取总结.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    print(f"总结已保存到: {summary_file}")

if __name__ == "__main__":
    main()
