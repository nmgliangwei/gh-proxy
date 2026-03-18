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
# 分支文件使用jsDelivr镜像的开关，0为关闭，默认关闭
jsdelivr = 0
size_limit = 1024 * 1024 * 1024 * 999  # 允许的文件大小，默认999GB，相当于无限制了

"""
  先生效白名单再匹配黑名单，pass_list匹配到的会直接302到jsdelivr而忽略设置
  生效顺序 白->黑->pass，可以前往https://github.com/hunshcn/gh-proxy/issues/41 查看示例
  每个规则一行，可以封禁某个用户的所有仓库，也可以封禁某个用户的特定仓库，下方用黑名单示例，白名单同理
  user1 # 封禁user1的所有仓库
  user1/repo1 # 封禁user1的repo1
  */repo1 # 封禁所有叫做repo1的仓库
"""
white_list = '''
'''
black_list = '''
'''
pass_list = '''
'''

ASSET_URL = 'https://hunshcn.github.io/gh-proxy'  # 主页

white_list = [tuple([x.replace(' ', '') for x in i.split('/')]) for i in white_list.split('\n') if i]
black_list = [tuple([x.replace(' ', '') for x in i.split('/')]) for i in black_list.split('\n') if i]
pass_list = [tuple([x.replace(' ', '') for x in i.split('/')]) for i in pass_list.split('\n') if i]

CHUNK_SIZE = 1024 * 10

# 缓存资源以避免每次请求都重新加载
_index_html = None
_icon_r = None


def get_index_html():
    global _index_html
    if _index_html is None:
        try:
            _index_html = requests.get(ASSET_URL, timeout=10).text
        except:
            _index_html = '<html><body>GitHub Proxy</body></html>'
    return _index_html


def get_icon():
    global _icon_r
    if _icon_r is None:
        try:
            _icon_r = requests.get(ASSET_URL + '/favicon.ico', timeout=10).content
        except:
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
        # Special case for urllib3.
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
            # Standard file-like object.
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
    # simulate reading small chunks of the content
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


def handler(path, method, headers, query_string, body):
    """
    Main handler for Vercel Serverless Function
    """
    u = path if path.startswith('http') else 'https://' + path
    if u.rfind('://', 3, 9) == -1:
        u = u.replace('s:/', 's://', 1)  # 处理协议问题

    pass_by = False
    m = check_url(u)
    if m:
        m = tuple(m.groups())
        if white_list:
            for i in white_list:
                if m[:len(i)] == i or i[0] == '*' and len(m) == 2 and m[1] == i[1]:
                    break
            else:
                return {
                    'statusCode': 403,
                    'body': 'Forbidden by white list.',
                    'headers': {'Content-Type': 'text/plain'}
                }
        for i in black_list:
            if m[:len(i)] == i or i[0] == '*' and len(m) == 2 and m[1] == i[1]:
                return {
                    'statusCode': 403,
                    'body': 'Forbidden by black list.',
                    'headers': {'Content-Type': 'text/plain'}
                }
        for i in pass_list:
            if m[:len(i)] == i or i[0] == '*' and len(m) == 2 and m[1] == i[1]:
                pass_by = True
                break
    else:
        return {
            'statusCode': 403,
            'body': 'Invalid input.',
            'headers': {'Content-Type': 'text/plain'}
        }

    if (jsdelivr or pass_by) and exp2.match(u):
        u = u.replace('/blob/', '@', 1).replace('github.com', 'cdn.jsdelivr.net/gh', 1)
        return {
            'statusCode': 302,
            'headers': {'Location': u}
        }
    elif (jsdelivr or pass_by) and exp4.match(u):
        u = re.sub(r'(\.com/.*?/.+?)/(.+?/)', r'\1@\2', u, 1)
        _u = u.replace('raw.githubusercontent.com', 'cdn.jsdelivr.net/gh', 1)
        u = u.replace('raw.github.com', 'cdn.jsdelivr.net/gh', 1) if _u == u else _u
        return {
            'statusCode': 302,
            'headers': {'Location': u}
        }
    else:
        if exp2.match(u):
            u = u.replace('/blob/', '/raw/', 1)
        if pass_by:
            url = u + query_string
            if url.startswith('https:/') and not url.startswith('https://'):
                url = 'https://' + url[7:]
            return {
                'statusCode': 302,
                'headers': {'Location': url}
            }
        u = quote(u, safe='/:')
        return proxy(u, method, headers, query_string, body, False)


def proxy(u, method, headers, query_string, body, allow_redirects=False):
    """代理请求"""
    response_headers = {}
    r_headers = dict(headers)
    if 'Host' in r_headers:
        r_headers.pop('Host')
    if 'host' in r_headers:
        r_headers.pop('host')

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

        if 'Content-length' in r.headers and int(r.headers['Content-length']) > size_limit:
            return {
                'statusCode': 302,
                'headers': {'Location': url}
            }

        # 对于小文件，直接返回；对于大文件，流式传输
        content = b''
        try:
            for chunk in iter_content(r, chunk_size=CHUNK_SIZE):
                if chunk:
                    content += chunk
                    # Vercel 的限制是 6MB，如果内容过大则返回重定向
                    if len(content) > 5 * 1024 * 1024:  # 5MB 限制
                        return {
                            'statusCode': 302,
                            'headers': {'Location': url}
                        }
        except Exception:
            pass

        if 'Location' in r.headers:
            _location = r.headers.get('Location')
            if check_url(_location):
                response_headers['Location'] = '/' + _location
                return {
                    'statusCode': r.status_code,
                    'headers': response_headers
                }
            else:
                return proxy(_location, method, headers, '', body, True)

        return {
            'statusCode': r.status_code,
            'headers': response_headers,
            'body': content,
            'isBase64Encoded': True
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': 'server error ' + str(e),
            'headers': {'Content-Type': 'text/html; charset=UTF-8'}
        }


def handler_root(method, headers, query_string):
    """处理根路径请求"""
    if query_string and 'q=' in query_string:
        # 提取查询参数
        import urllib.parse
        params = urllib.parse.parse_qs(urllib.parse.urlparse('?' + query_string).query)
        if 'q' in params:
            q = params['q'][0]
            return {
                'statusCode': 302,
                'headers': {'Location': '/' + q}
            }

    return {
        'statusCode': 200,
        'body': get_index_html(),
        'headers': {'Content-Type': 'text/html; charset=UTF-8'}
    }


async def main_handler(request):
    """
    Vercel Serverless Function 入口
    """
    path = request.get('path', '').lstrip('/')
    method = request.get('method', 'GET')
    headers = request.get('headers', {})
    query_string = request.get('queryString', '')
    body = request.get('body', b'')

    if not path or path == '':
        return handler_root(method, headers, query_string)

    if path == 'favicon.ico':
        icon = get_icon()
        return {
            'statusCode': 200,
            'body': icon,
            'headers': {'Content-Type': 'image/vnd.microsoft.icon'},
            'isBase64Encoded': True
        }

    return handler(path, method, headers, query_string, body)