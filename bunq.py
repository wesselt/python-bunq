import base64
import json
import requests
import uuid
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

with open('VERSION') as f:
    __version__ = f.read().strip()


class API(object):
    """Wrapper around the bunq API."""

    def __init__(self, prvkey_pem, token='', srvkey_pem=''):
        """Create an object with authentication information

        :param privkey_pem: user private rsa key in PEM format
        :type privkey_pem: str or bytes
        :param token: almost always a session token
        :type token: str
        :param srvkey_pem: server public rsa key in PEM format
        :type srvkey_pem: str or bytes

        """
        self.token = token
        self.uri = 'https://api.bunq.com'
        self.api_version = 'v1'

        if not isinstance(prvkey_pem, bytes):
            prvkey_pem = prvkey_pem.encode()

        self.private_key = serialization.load_pem_private_key(
            prvkey_pem,
            password=None,
            backend=default_backend()
        )

        if srvkey_pem:
            if not isinstance(srvkey_pem, bytes):
                srvkey_pem = srvkey_pem.encode()

            self.server_key = serialization.load_pem_public_key(
                srvkey_pem,
                backend=default_backend()
            )

    def query(self, endpoint, payload={}, method='', verify=False):
        """Send API query to backend

        If no payload is given, method defaults to GET request, otherwise POST.
        When PUT or DELETE is needed, please give method.

        :param endpoint: API call endpoint, including query string
        :type endpoint: str
        :param payload: API request attributes
        :type payload: dict
        :param method: HTTP request method
        :type method: str
        :param verify: set to True to enable response verification
        :type verify: bool

        """
        request_id = str(uuid.uuid1())

        if not method:
            if not payload:
                method = 'GET'
            else:
                method = 'POST'

        if not endpoint.startswith('/'):
            endpoint = '/%s/%s' % (self.api_version, endpoint)
        elif not endpoint.startswith('/' + self.api_version):
            endpoint = '/%s%s' % (self.api_version, endpoint)
        action = '%s %s' % (method, endpoint)
        url = '%s%s' % (self.uri, endpoint)

        headers = {
            'Cache-Control': 'no-cache',
            'User-Agent': 'python-bunq-api/' + __version__,
            'X-Bunq-Client-Request-Id': request_id,
            'X-Bunq-Geolocation': '0 0 0 0 NL',
            'X-Bunq-Language': 'en_US',
            'X-Bunq-Region': 'nl_NL'
        }

        if self.token:
            headers['X-Bunq-Client-Authentication'] = self.token

        msg = '%s\n%s\n\n' % (
            action,
            '\n'.join(['%s: %s' % (k, v) for k, v in sorted(headers.items())])
        )

        if payload:
            msg += json.dumps(payload)

        headers['X-Bunq-Client-Signature'] = self.sign(msg)

        if payload:
            r = requests.post(url, headers=headers, json=payload)
        else:
            r = requests.get(url, headers=headers)

        if verify:
            valid = self.verify(r)

        return r

    def sign(self, msg):
        """Create signature for message

        :param msg: data to be signed, usually action, headers and body
        :type msg: str

        """
        return base64.b64encode(
            self.private_key.sign(
                msg.encode(),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        ).decode()

    def verify(self, res):
        """Verify response from server

        :param res: request to be verified
        :type res: requests.models.Response

        """
        if not self.server_key:
            print('No server public key defined, skipping verification')
            return

        srv_headers = [
            'X-Bunq-Client-Request-Id',
            'X-Bunq-Client-Response-Id'
        ]

        msg = '%s\n%s\n\n%s' % (
            res.status_code,
            '\n'.join(
                ['%s: %s' % (k, v) for k, v in sorted(
                    res.headers.items()
                ) if k in srv_headers]
            ),
            res.text
        )

        signature = base64.b64decode(res.headers['X-Bunq-Server-Signature'])

        try:
            server_key.verify(
                signature,
                msg.encode(),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        except InvalidSignature:
            print('Message failed verification, data might be tampered with')
            return False
        else:
            return True

    def pubkey(self):
        """Return PEM representation of public part of RSA key pair."""
        return self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
