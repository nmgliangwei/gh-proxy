# -*- coding: utf-8 -*-
import re
import os
import sys

# 在导入 flask 之前先修复可能的兼容性问题
# 检查并修复 http.server 模块
try:
    from http.server import BaseHTTPRequestHandler
except ImportError:
    pass

import requests
from flask import Flask, Response, redirect, request
from requests.exceptions import (
    ChunkedEncodingError,
    ContentDecodingError, ConnectionError, StreamConsumedError)
from requests.utils import (
    stream_decode_response_unicode, iter_slices, CaseInsensitiveDict)
from urllib3.exceptions import (
    DecodeError, ReadTimeoutError, ProtocolError)
from urllib.parse import quote

app = Flask(__name__)

# 全局异常处理器
@app.errorhandler(Exception)
def handle_exception(e):
    """全局异常处理器"""
    import traceback
    error_msg = f"Error: {str(e)}\nTraceback: {traceback.format_exc()}"
    print(error_msg, file=sys.stderr)
    return Response(f'Server Error: {str(e)}', status=500, content_type='text/plain')

# config
jsdelivr = 0
size_limit = 1024 * 1024 * 1024 * 999

white_list = '''
'''
black_list = '''
'''
pass_list = '''
'''

ASSET_URL = 'https://hunshcn.github.io/gh-proxy'

# 默认首页，避免启动时网络请求
DEFAULT_INDEX_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GH Proxy</title>
</head>
<body>
    <h1>GH Proxy</h1>
    <p>GitHub 加速代理服务</p>
</body>
</html>'''

white_list = [tuple([x.replace(' ', '') for x in i.split('/')]) for i in white_list.split('\n') if i]
black_list = [tuple([x.replace(' ', '') for x in i.split('/')]) for i in black_list.split('\n') if i]
pass_list = [tuple([x.replace(' ', '') for x in i.split('/')]) for i in pass_list.split('\n') if i]

CHUNK_SIZE = 1024 * 10

# 懒加载静态资源
_index_html = None
_icon_r = None

def get_index_html():
    global _index_html
    if _index_html is None:
        try:
            _index_html = requests.get(ASSET_URL, timeout=5).text
        except Exception:
            _index_html = DEFAULT_INDEX_HTML
    return _index_html

def get_icon_r():
    global _icon_r
    if _icon_r is None:
        try:
            _icon_r = requests.get(ASSET_URL + '/favicon.ico', timeout=5).content
        except Exception:
            _icon_r = b''
    return _icon_r

# 启动日志
print("GH Proxy application starting...", file=sys.stderr)
print(f"Python version: {sys.version}", file=sys.stderr)
print(f"VERCEL env: {os.environ.get('VERCEL', 'Local')}", file=sys.stderr)
try:
    import flask
    print(f"Flask version: {flask.__version__}", file=sys.stderr)
except:
    pass
try:
    import requests
    print(f"Requests version: {requests.__version__}", file=sys.stderr)
except:
    pass
try:
    import urllib3
    print(f"urllib3 version: {urllib3.__version__}", file=sys.stderr)
except:
    pass

@app.route('/health')
def health():
    """健康检查端点"""
    return Response('OK', status=200, content_type='text/plain')

@app.route('/')
def index():
    if 'q' in request.args:
        return redirect('/' + request.args.get('q'))
    return get_index_html()