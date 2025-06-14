from cachetools import TTLCache

# สร้างแคชสำหรับแต่ละ module
asset2_cache = TTLCache(maxsize=1, ttl=21600)
asset3_cache = TTLCache(maxsize=1, ttl=21600)

def clear_all_caches():
    """Clear all asset caches"""
    asset2_cache.clear()
    asset3_cache.clear()