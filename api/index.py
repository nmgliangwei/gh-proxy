# -*- coding: utf-8 -*-
import re
import requests
from requests.exceptions import (
    ChunkedEncodingError,
    ContentDecodingError, ConnectionError, StreamConsumedError)
from requests.utils import (
    stream_decode_response_unicode, iter_slices, CaseInsensitiveDict)
from urllib3.exceptions import (
    DecodeError, ReadTimeoutError, ProtocolError)
from urllib.parse import quote, parse_qs, urlparse

# config
jsdelivr = 0
size_limit = 1024 * 1024 * 1024 * 999

white_list = ''
black_list = ''
pass_list = ''

ASSET_URL = 'https://hunshcn.github.io/gh-proxy'

white_list = [tuple([x.replace(' ', '') for x in i.split('/')]) for i in white_list.split('\n') if i]
black_list = [tuple([x.replace(' ', '') for x in i.split('/')]) for i in black_list.split('\n') if i]
pass_list = [tuple([x.replace(' ', '') for x in i.split('/')]) for i in pass_list.split('\n') if i]

CHUNK_SIZE = 1024 * 10

# 缓存资源
_index_html = None
_icon_r = None


def get_index_html():
    global _index_html
    if _index_html is None:
        try:
            _index_html = requests.get(ASSET_URL, timeout=10).text
        except Exception:
            _index_html = '<html><body><h1>GitHub Proxy</h1></body></html>'
    return _index_html


def get_icon():
    global _icon_r
    if _icon_r is None:
        try:
            _icon_r = requests.get(ASSET_URL + '/favicon.ico', timeout=10).content
        except Exception:
            _icon_r = b''
    return _icon_r


exp1 = re.compile(r'^(?:https?://)?github\.com/(?P<author>.+?)/(?P<repo>.+?)/(?:releases|archive)/.*$')
exp2 = re.compile(r'^(?:https?://)?github\.com/(?P<author>.+?)/(?P<repo>.+?)/(?:blob|raw)/.*$')
exp3 = re.compile(r'^(?:https?://)?github\.com/(?P<author>.+?)/(?P<repo>.+?)/(?:info|git-).*$')
exp4 = re.compile(r'^(?:https?://)?raw\.(?:githubusercontent|github)\.com/(?P<author>.+?)/(?P<repo>.+?)/.+?/.+$')
exp5 = re.compile(r'^(?:https?://)?gist\.(?:githubusercontent|github)\.com/(?P<author>.+?)/.+?/.+$')

requests.sessions.default_headers = lambda: CaseInsensitiveDict()


def iter_content(response, chunk_size=1, decode_unicode=False):
    """rewrite requests function, set decode_content with False"""

    def generate():
        if hasattr(response.raw, 'stream'):
            try:
                for chunk in response.raw.stream(chunk_size, decode_content=False):
                    yield chunk
            except ProtocolError as e:
                raise ChunkedEncodingError(e)
            except DecodeError as e:
                raise ContentDecodingError(e)
            except ReadTimeoutError as e:
                raise ConnectionError(e)
        else:
            while True:
                chunk = response.raw.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        response._content_consumed = True

    if response._content_consumed and isinstance(response._content, bool):
        raise StreamConsumedError()
    elif chunk_size is not None and not isinstance(chunk_size, int):
        raise TypeError("chunk_size must be an int, it is instead a %s." % type(chunk_size))

    reused_chunks = iter_slices(response._content, chunk_size)
    stream_chunks = generate()
    chunks = reused_chunks if response._content_consumed else stream_chunks

    if decode_unicode:
        chunks = stream_decode_response_unicode(chunks, response)

    return chunks


def check_url(u):
    for exp in (exp1, exp2, exp3, exp4, exp5):
        m = exp.match(u)
        if m:
            return m
    return False


def build_response(status_code, body=None, headers=None, is_base64=False):
    """构建响应对象"""
    resp = {'statusCode': status_code}
    if headers:
        resp['headers'] = headers
    else:
        resp['headers'] = {'Content-Type': 'text/html; charset=utf-8'}
    if body:
        resp['body'] = body
        if is_base64:
            resp['isBase64Encoded'] = True
    return resp


def handler(path, method, headers, query_string, body):
    """Main handler"""
    u = path if path.startswith('http') else 'https://' + path
    if u.rfind('://', 3, 9) == -1:
        u = u.replace('s:/', 's://', 1)

    pass_by = False
    m = check_url(u)

    if m:
        m = tuple(m.groups())
        if white_list:
            for i in white_list:
                if m[:len(i)] == i or (i[0] == '*' and len(m) == 2 and m[1] == i[1]):
                    break
            else:
                return build_response(403, 'Forbidden by white list.')

        for i in black_list:
            if m[:len(i)] == i or (i[0] == '*' and len(m) == 2 and m[1] == i[1]):
                return build_response(403, 'Forbidden by black list.')

        for i in pass_list:
            if m[:len(i)] == i or (i[0] == '*' and len(m) == 2 and m[1] == i[1]):
                pass_by = True
                break
    else:
        return build_response(403, 'Invalid input.')

    # 处理重定向到 jsDelivr
    if (jsdelivr or pass_by) and exp2.match(u):
        u = u.replace('/blob/', '@', 1).replace('github.com', 'cdn.jsdelivr.net/gh', 1)
        return build_response(302, headers={'Location': u})

    if (jsdelivr or pass_by) and exp4.match(u):
        u = re.sub(r'(\.com/.*?/.+?)/(.+?/)', r'\1@\2', u, 1)
        _u = u.replace('raw.githubusercontent.com', 'cdn.jsdelivr.net/gh', 1)
        u = u.replace('raw.github.com', 'cdn.jsdelivr.net/gh', 1) if _u == u else _u
        return build_response(302, headers={'Location': u})

    # 代理请求
    if exp2.match(u):
        u = u.replace('/blob/', '/raw/', 1)

    if pass_by:
        url = u + query_string
        if url.startswith('https:/') and not url.startswith('https://'):
            url = 'https://' + url[7:]
        return build_response(302, headers={'Location': url})

    u = quote(u, safe='/:')
    return proxy(u, method, headers, query_string, body, False)


def proxy(u, method, headers, query_string, body, allow_redirects=False):
    """Proxy request"""
    r_headers = dict(headers)

    # 移除不必要的头
    for h in ['Host', 'host', 'Content-Length', 'content-length']:
        r_headers.pop(h, None)

    try:
        url = u + query_string
        if url.startswith('https:/') and not url.startswith('https://'):
            url = 'https://' + url[7:]

        r = requests.request(
            method=method,
            url=url,
            data=body,
            headers=r_headers,
            stream=True,
            allow_redirects=allow_redirects,
            timeout=30
        )

        response_headers = dict(r.headers)

        # 检查文件大小
        if 'Content-length' in r.headers:
            try:
                if int(r.headers['Content-length']) > size_limit:
                    return build_response(302, headers={'Location': url})
            except (ValueError, TypeError):
                pass

        # 收集内容
        content = b''
        try:
            for chunk in iter_content(r, chunk_size=CHUNK_SIZE):
                if chunk:
                    content += chunk
                    # Vercel 响应大小限制（约6MB）
                    if len(content) > 5 * 1024 * 1024:
                        return build_response(302, headers={'Location': url})
        except Exception:
            pass

        # 处理重定向
        if 'Location' in r.headers:
            _location = r.headers.get('Location')
            if check_url(_location):
                response_headers['Location'] = '/' + _location
                return build_response(r.status_code, headers=response_headers)
            else:
                return proxy(_location, method, headers, '', body, True)

        return build_response(r.status_code, content, response_headers, True)

    except Exception as e:
        error_msg = 'server error: ' + str(e)
        return build_response(500, error_msg, {'Content-Type': 'text/html; charset=utf-8'})


def handler_root(method, headers, query_string):
    """Handle root path"""
    if query_string and 'q=' in query_string:
        try:
            params = parse_qs(query_string)
            if 'q' in params and params['q']:
                q = params['q'][0]
                return build_response(302, headers={'Location': '/' + q})
        except Exception:
            pass

    return build_response(200, get_index_html(), {'Content-Type': 'text/html; charset=utf-8'})


# Vercel 入口函数
def handler_wrapper(request):
    """
    Vercel Serverless Function 入口
    request 参数来自 Vercel 运行时
    """
    try:
        path = request.path.lstrip('/') if hasattr(request, 'path') else ''
        method = request.method if hasattr(request, 'method') else 'GET'
        headers = dict(request.headers) if hasattr(request, 'headers') else {}
        query_string = (request.url.split('?', 1)[1] if '?' in request.url else '') if hasattr(request, 'url') else ''
        body = request.data if hasattr(request, 'data') else b''

        if not path or path == '':
            return handler_root(method, headers, query_string)
        elif path == 'favicon.ico':
            icon = get_icon()
            return build_response(200, icon, {'Content-Type': 'image/vnd.microsoft.icon'}, True)
        else:
            return handler(path, method, headers, query_string, body)

    except Exception as e:
        return build_response(500, 'Error: ' + str(e), {'Content-Type': 'text/html; charset=utf-8'})


# 导出为 Vercel 函数
import json


def index(request):
    """Vercel HTTP Handler"""
    try:
        # 解析请求
        path = request.path.lstrip('/') if request.path else ''
        method = request.method
        headers = dict(request.headers)
        query_string = request.url.split('?', 1)[1] if '?' in request.url else ''
        body = request.get_data()

        # 路由处理
        if not path or path == '':
            result = handler_root(method, headers, query_string)
        elif path == 'favicon.ico':
            icon = get_icon()
            return (200, icon, {'Content-Type': 'image/vnd.microsoft.icon'}, True)
        else:
            result = handler(path, method, headers, query_string, body)

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return build_response(500, 'Error: ' + str(e))