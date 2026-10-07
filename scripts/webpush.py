"""
Web Push sender (the standard browsers and iPhones use for website notifications), free, no app, no Claude.

The phone signs up on the site (Settings > "Turn on result alerts"); its sign-up is kept on the "Alerts" tab of
the visit-log Sheet. This file encrypts a message for one sign-up and hands it to Apple/Google/Mozilla's push
service, which delivers it. Standards: RFC 8291 (encryption, "aes128gcm") and RFC 8292 (VAPID: proves the
message comes from 72 Central). Only needs the `cryptography` package.
"""
import base64, hashlib, hmac, json, os, time, urllib.error, urllib.parse, urllib.request
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SITE = "https://tlock72.github.io/72-central/"


def b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def raw_public(key):
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def hkdf(salt, ikm, info, n):
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:n]


def encrypt(payload, p256dh, auth):
    ua_pub, secret = b64d(p256dh), b64d(auth)
    mine = ec.generate_private_key(ec.SECP256R1())
    as_pub = raw_public(mine)
    shared = mine.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    ikm = hkdf(secret, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    salt = os.urandom(16)
    cek = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    return salt + (4096).to_bytes(4, "big") + bytes([len(as_pub)]) + as_pub + body


def vapid(endpoint, private_b64):
    key = ec.derive_private_key(int.from_bytes(b64d(private_b64), "big"), ec.SECP256R1())
    u = urllib.parse.urlsplit(endpoint)
    head = b64e(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64e(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": SITE}).encode())
    r, s = decode_dss_signature(key.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    jwt = f"{head}.{claims}.{b64e(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return f"vapid t={jwt}, k={b64e(raw_public(key))}"


def send(sub, message, private_b64):
    """sub = {endpoint, p256dh, auth}; message = dict shown by sw.js. Returns the push service's HTTP status
    (201 = delivered to the push service; 404/410 = this sign-up has expired and can be dropped)."""
    req = urllib.request.Request(sub["endpoint"], method="POST", data=encrypt(json.dumps(message).encode(), sub["p256dh"], sub["auth"]),
                                 headers={"Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
                                          "TTL": "86400", "Urgency": "high", "Authorization": vapid(sub["endpoint"], private_b64)})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
