from flask import Flask, Response
import sys

# 创建一个简单的 Flask 应用
app = Flask(__name__)

@app.route('/')
def index():
    return 'GH Proxy is running on Vercel'

@app.route('/health')
def health():
    return Response('OK', status=200, content_type='text/plain')

@app.route('/<path:u>')
def handler(u):
    return f'Proxy handler for {u}'

# Vercel 需要导出一个名为 'app' 或 'application' 的 WSGI 应用
application = app

# 如果直接运行，启动开发服务器
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)