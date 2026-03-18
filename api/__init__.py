import sys
import os

# 添加根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from main import app

# Vercel Serverless Function 入口
def handler(request):
    """Vercel Serverless Function handler"""
    return app(request.environ, lambda *args: None)
