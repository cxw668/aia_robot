import sys
from pathlib import Path
Path = Path(__file__).resolve().parent.parent
if str(Path) not in sys.path:
    sys.path.insert(0, str(Path))
modules = ['app.config','app.database','app.cache','app.env_loader','app.main','app.knowledge_base','app.knowledge_base.core','app.knowledge_base.retrieval.engine','app.routers.knowledge']
import importlib
for m in modules:
    try:
        importlib.import_module(m)
        print(m, 'OK')
    except Exception as e:
        print(m, 'ERROR', type(e).__name__, e)
