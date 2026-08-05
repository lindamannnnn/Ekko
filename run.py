#!/usr/bin/env python3
"""课评系统 启动入口（P2 起统一走 create_app 工厂）。"""
import os
import sys
from pathlib import Path

# 把项目根与 src 加入路径，保证 `app` / `extensions` / `models` 可作为顶层包导入
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from app import create_app

# 允许在 run.py 同级放一份 config 覆盖（可选）
_config = None
_cfg_path = Path(__file__).resolve().parent / 'app_config.py'
if _cfg_path.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location('app_config', _cfg_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _config = {k: v for k, v in vars(mod).items()
               if k.isupper() and not k.startswith('_')}

app = create_app(_config)

# 开发期：模板改动实时生效，无需重启进程（non-debug 默认会缓存模板）
app.config['TEMPLATES_AUTO_RELOAD'] = True


def main():
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    print(f"课评系统 已启动: http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    main()
