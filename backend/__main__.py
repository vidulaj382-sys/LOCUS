"""python -m backend [--port 8000] [--https]"""
import argparse, os, pathlib, sys

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--https', action='store_true', help='serve over HTTPS with a self-signed cert (Web Bluetooth needs a secure context)')
    a = ap.parse_args()
    os.environ['LOCUS_PORT'] = str(a.port)
    os.environ['LOCUS_SCHEME'] = 'https' if a.https else 'http'
    import uvicorn
    kw = {}
    if a.https:
        from .main import lan_ips
        from .certs import ensure_cert
        cert, key = ensure_cert(lan_ips())
        kw = dict(ssl_certfile=str(cert), ssl_keyfile=str(key))
    uvicorn.run('backend.main:app', host=a.host, port=a.port, log_level='warning', **kw)
