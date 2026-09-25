"""URL downloads must not reach internal addresses (SSRF), directly or via redirects."""
import asyncio
import datetime
import ipaddress
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from workers import sources
from workers.sources import URLHandler


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect-to-metadata":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            self.end_headers()
            return
        body = b"%PDF-1.4 " + (b"x" * 4096 if self.path == "/big.pdf" else b"") + b"host=" + self.headers["Host"].encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def http_server():
    server = _serve(HTTPServer(("127.0.0.1", 0), _Handler))
    yield server.server_port
    server.shutdown()


@pytest.fixture
def allow_loopback(monkeypatch):
    """Treat loopback as public so tests can talk to the local server."""
    original = sources._is_public_ip
    monkeypatch.setattr(sources, "_is_public_ip", lambda ip: ip.is_loopback or original(ip))


@pytest.fixture
def resolve_to(monkeypatch):
    """Make every hostname resolve to the given addresses."""
    def set_addresses(*addresses):
        async def fake_getaddrinfo(self, host, port, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses]
        monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", fake_getaddrinfo)
    return set_addresses


def download(url, tmp_path):
    return asyncio.run(URLHandler().download(url, tmp_path))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
        "100.64.0.1", "0.0.0.0", "224.0.0.1", "::1", "fe80::1", "fd00::1",
        "::ffff:127.0.0.1", "64:ff9b::a9fe:a9fe", "2002:a9fe:a9fe::1",
    ],
)
def test_non_public_addresses_are_rejected(address):
    assert not sources._is_public_ip(ipaddress.ip_address(address))


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946", "64:ff9b::5db8:d822"])
def test_public_addresses_are_allowed(address):
    assert sources._is_public_ip(ipaddress.ip_address(address))


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x.pdf",
        "http://localhost/x.pdf",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/x.pdf",
        "http://[::ffff:127.0.0.1]/x.pdf",
        "http://2130706433/x.pdf",  # 127.0.0.1 as a decimal integer
        "file:///etc/passwd",
        "ftp://example.com/x.pdf",
        "http://user:pass@example.com/x.pdf",
    ],
)
def test_blocked_urls(url, tmp_path):
    with pytest.raises(Exception):
        download(url, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_hostname_resolving_to_internal_address_is_blocked(resolve_to, tmp_path):
    resolve_to("93.184.216.34", "10.0.0.5")  # one bad address is enough to refuse
    with pytest.raises(Exception, match="non-public"):
        download("http://mixed.example/x.pdf", tmp_path)


def test_redirect_hops_are_revalidated(http_server, allow_loopback, tmp_path):
    with pytest.raises(Exception, match="non-public"):
        download(f"http://127.0.0.1:{http_server}/redirect-to-metadata", tmp_path)


def test_download_keeps_original_host_header(http_server, allow_loopback, tmp_path):
    path = download(f"http://localhost:{http_server}/doc.pdf", tmp_path)
    assert path.read_bytes().endswith(f"host=localhost:{http_server}".encode())


def test_idn_host_is_sent_in_ascii_form(http_server, allow_loopback, resolve_to, tmp_path):
    resolve_to("127.0.0.1")
    path = download(f"http://bücher.example:{http_server}/doc.pdf", tmp_path)
    assert path.read_bytes().endswith(f"host=xn--bcher-kva.example:{http_server}".encode())


def test_falls_back_to_next_validated_address(http_server, allow_loopback, resolve_to, tmp_path):
    resolve_to("127.0.0.2", "127.0.0.1")  # nothing listens on 127.0.0.2
    path = download(f"http://multi.example:{http_server}/doc.pdf", tmp_path)
    assert path.read_bytes().startswith(b"%PDF")


def test_size_limit_aborts_and_removes_partial_file(http_server, allow_loopback, monkeypatch, tmp_path):
    monkeypatch.setattr(sources.get_settings(), "max_file_size_mb", 0.001)  # ~1 KB
    with pytest.raises(Exception, match="maximum size"):
        download(f"http://127.0.0.1:{http_server}/big.pdf", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_https_connects_to_pinned_ip_with_original_sni(allow_loopback, resolve_to, monkeypatch, tmp_path):
    hostname = "docs.example.test"
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ))

    seen_sni = []
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    context.sni_callback = lambda sock, server_name, ctx: seen_sni.append(server_name)
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    _serve(server)

    resolve_to("127.0.0.1")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        sources.httpx, "AsyncClient",
        lambda **kwargs: real_client(verify=str(cert_file), trust_env=False, **kwargs),
    )
    try:
        out = tmp_path / "out"
        path = download(f"https://{hostname}:{server.server_port}/doc.pdf", out)
    finally:
        server.shutdown()

    assert path.read_bytes().startswith(b"%PDF")
    assert seen_sni == [hostname]  # certificate was verified for the original hostname
