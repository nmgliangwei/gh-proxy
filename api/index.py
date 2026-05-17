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
from urllib.parse import quote

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


def app(environ, start_response):
    """WSGI application for Vercel"""
    try:
        method = environ['REQUEST_METHOD']
        path = environ.get('PATH_INFO', '/').lstrip('/')
        query_string = environ.get('QUERY_STRING', '')

        # 获取请求头
        headers = {}
        for key, value in environ.items():
            if key.startswith('HTTP_'):
                header_name = key[5:].replace('_', '-').lower()
                headers[header_name] = value

        # 获取请求体
        try:
            content_length = int(environ.get('CONTENT_LENGTH', 0))
        except ValueError:
            content_length = 0

        body = b''
        if content_length > 0:
            body = environ['wsgi.input'].read(content_length)

        # 根路径
        if not path or path == '':
            if query_string and 'q=' in query_string:
                from urllib.parse import parse_qs
                params = parse_qs(query_string)
                if 'q' in params:
                    q = params['q'][0]
                    start_response('302 Found', [('Location', '/' + q)])
                    return [b'']

            html = get_index_html()
            start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
            return [html.encode('utf-8')]

        # favicon
        if path == 'favicon.ico':
            icon = get_icon()
            start_response('200 OK', [('Content-Type', 'image/vnd.microsoft.icon')])
            return [icon]

        # 主要代理逻辑
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
                    start_response('403 Forbidden', [('Content-Type', 'text/plain')])
                    return [b'Forbidden by white list.']

            for i in black_list:
                if m[:len(i)] == i or (i[0] == '*' and len(m) == 2 and m[1] == i[1]):
                    start_response('403 Forbidden', [('Content-Type', 'text/plain')])
                    return [b'Forbidden by black list.']

            for i in pass_list:
                if m[:len(i)] == i or (i[0] == '*' and len(m) == 2 and m[1] == i[1]):
                    pass_by = True
                    break
        else:
            start_response('403 Forbidden', [('Content-Type', 'text/plain')])
            return [b'Invalid input.']

        # jsDelivr 重定向
        if (jsdelivr or pass_by) and exp2.match(u):
            u = u.replace('/blob/', '@', 1).replace('github.com', 'cdn.jsdelivr.net/gh', 1)
            start_response('302 Found', [('Location', u)])
            return [b'']

        if (jsdelivr or pass_by) and exp4.match(u):
            u = re.sub(r'(\.com/.*?/.+?)/(.+?/)', r'\1@\2', u, 1)
            _u = u.replace('raw.githubusercontent.com', 'cdn.jsdelivr.net/gh', 1)
            u = u.replace('raw.github.com', 'cdn.jsdelivr.net/gh', 1) if _u == u else _u
            start_response('302 Found', [('Location', u)])
            return [b'']

        # Git clone 协议（info/refs、git-upload-pack 等）无法在 Serverless 环境代理
        # 直接重定向到原始 GitHub URL，避免内存溢出崩溃
        if exp3.match(u):
            url = u + ('?' + query_string if query_string else '')
            start_response('302 Found', [('Location', url)])
            return [b'']

        # 代理处理
        if exp2.match(u):
            u = u.replace('/blob/', '/raw/', 1)

        if pass_by:
            url = u + ('?' + query_string if query_string else '')
            if url.startswith('https:/') and not url.startswith('https://'):
                url = 'https://' + url[7:]
            start_response('302 Found', [('Location', url)])
            return [b'']

        u = quote(u, safe='/:')

        # 代理请求
        r_headers = dict(headers)
        for h in ['Host', 'host', 'Content-Length', 'content-length']:
            r_headers.pop(h, None)

        try:
            url = u + ('?' + query_string if query_string else '')
            if url.startswith('https:/') and not url.startswith('https://'):
                url = 'https://' + url[7:]

            r = requests.request(
                method=method,
                url=url,
                data=body,
                headers=r_headers,
                stream=True,
                allow_redirects=False,
                timeout=30
            )

            response_headers = list(r.headers.items())

            # 收集内容
            content = b''
            for chunk in iter_content(r, chunk_size=CHUNK_SIZE):
                if chunk:
                    content += chunk
                    if len(content) > 5 * 1024 * 1024:
                        start_response('302 Found', [('Location', url)])
                        return [b'']

            start_response(f'{r.status_code} OK', response_headers)
            return [content]

        except Exception as e:
            start_response('500 Internal Server Error', [('Content-Type', 'text/html; charset=utf-8')])
            return [('Error: ' + str(e)).encode('utf-8')]

    except Exception as e:
        start_response('500 Internal Server Error', [('Content-Type', 'text/html; charset=utf-8')])
        return [('Error: ' + str(e)).encode('utf-8')]