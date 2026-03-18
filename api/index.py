import sys
import os

# 添加根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app

# Vercel Python runtime 会自动识别并使用 Flask app 实例
