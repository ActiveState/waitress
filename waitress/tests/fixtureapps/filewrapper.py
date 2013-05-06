import os

here = os.path.dirname(os.path.abspath(__file__))
fn = os.path.join(here, 'groundhog1.jpg')

class KindaFilelike(object):
    def __init__(self, bytes):
        self.bytes = bytes

    def read(self, n):
        bytes = self.bytes[:n]
        self.bytes = self.bytes[n:]
        return bytes

def app(environ, start_response):
    path_info = environ['PATH_INFO']
    if path_info.startswith('/filelike'):
        f = open(fn, 'rb')
        f.seek(0, 2)
        cl = f.tell()
        f.seek(0)
        if path_info == '/filelike':
            headers = [
                ('Content-Length', str(cl)), ('Content-Type', 'image/jpeg')
                ]
        elif path_info == '/filelike_nocl':
            headers = [('Content-Type', 'image/jpeg')]
        elif path_info == '/filelike_shortcl':
            # short content length
            headers = [
                ('Content-Length', '1'), ('Content-Type', 'image/jpeg')
                ]
        else:
            # long content length (/filelike_longcl)
            headers = [
                ('Content-Length', str(cl+10)), ('Content-Type', 'image/jpeg')
                ]
    else:
        data = open(fn, 'rb').read()
        cl = len(data)
        f = KindaFilelike(data)
        if path_info == '/notfilelike':
            headers =  [('Content-Length', str(len(data))),
                        ('Content-Type', 'image/jpeg')]

        elif path_info == '/notfilelike_nocl':
            headers = [('Content-Type', 'image/jpeg')]
        elif path_info == '/notfilelike_shortcl':
            # short content length
            headers = [
                ('Content-Length', '1'), ('Content-Type', 'image/jpeg')
                ]
        else:
            # long content length (/notfilelike_longcl)
            headers = [
                ('Content-Length', str(cl+10)), ('Content-Type', 'image/jpeg')
                ]

    start_response(
        '200 OK',
        headers
        )
    return environ['wsgi.file_wrapper'](f, 8192)

if __name__ == '__main__':
    import logging
    import sys
    class NullHandler(logging.Handler):
        def emit(self, record):
            pass
    h = NullHandler()
    logging.getLogger('waitress').addHandler(h)
    from waitress import serve
    if len(sys.argv) > 1 and sys.argv[1] == '-u':
        kwargs = {'unix_socket': '/tmp/waitress.functional.sock'}
    else:
        kwargs = {'port': 61523}
    serve(app, _quiet=True, **kwargs)
