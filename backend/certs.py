"""Self-signed certificate (valid for localhost + this laptop's LAN IPs) for --https mode."""
import datetime, ipaddress, pathlib

DIR = pathlib.Path(__file__).resolve().parent / 'certs'


def ensure_cert(ips):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    DIR.mkdir(exist_ok=True)
    cert_p, key_p, ips_p = DIR / 'locus.crt', DIR / 'locus.key', DIR / 'ips.txt'
    if cert_p.exists() and key_p.exists() and ips_p.exists() and ips_p.read_text() == ','.join(ips):
        return cert_p, key_p
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'locus-local')])
    san = [x509.DNSName('localhost'), x509.IPAddress(ipaddress.ip_address('127.0.0.1'))] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(san), critical=False).sign(key, hashes.SHA256()))
    cert_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_p.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    ips_p.write_text(','.join(ips))
    return cert_p, key_p
