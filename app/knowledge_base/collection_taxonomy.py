"""
收集和管理知识库中可用的分类信息
"""


def get_available_categories() -> set[str]:
    """
    获取向量库中可用的所有分类
    
    Returns:
        set[str]: 包含所有可用分类名称的集合
    """
    from app.knowledge_base.retrieval_data_source import get_client
    
    client = get_client()
    
    try:
        # 从向量库中获取所有唯一的分类
        # response = client.scroll(
        #     collection_name="aia_knowledge_base",
        #     scroll_filter=None,
        #     limit=1,  # 只需要获取一些样例点来检查结构
        #     with_payload=True,
        #     with_vectors=False
        # )
        
        # 获取所有可能的分类值
        all_categories = set()
        offset = None
        
        while True:
            records, offset = client.scroll(
                collection_name="aia_knowledge_base",
                scroll_filter=None,
                limit=1000,
                with_payload=True,
                with_vectors=False,
                offset=offset
            )
            
            if not records:
                break
                
            for record in records:
                category = record.payload.get("category")
                if category:
                    all_categories.add(category)
                    
            if offset is None:
                break
                
        return all_categories
    except Exception as e:
        print(f"Warning: Could not fetch categories from vector DB: {e}")
        return {}