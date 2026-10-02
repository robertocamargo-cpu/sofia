import socket
import ssl
import urllib.request
import urllib.parse
import http.client
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5, AES
from Crypto.Util.Padding import pad, unpad
from Crypto.Random import get_random_bytes
import time
import re

HOST = '192.168.15.36'
PORT = 80
BASE = f'http://{HOST}'

def raw_http_get(path, host=HOST, port=PORT):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(15)
    s.connect((host, port))
    req = f'GET {path} HTTP/1.0\r\nHost: {host}\r\nConnection: close\r\n\r\n'
    s.sendall(req.encode())
    data = b''
    while True:
        try:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
        except:
            break
    s.close()
    return data

def raw_http_get_raw_body(path, host=HOST, port=PORT):
    """GET and return raw body without HTTP headers."""
    data = raw_http_get(path, host, port)
    # Find end of HTTP headers
    idx = data.find(b'\r\n\r\n')
    if idx >= 0:
        return data[idx+4:]
    return data

class REPClient:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.aes_key = None
        self.session_cookies = None
    
    def _raw_get(self, path):
        """Low-level GET, returns (headers_bytes, body_bytes)."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(15)
        s.connect((self.host, self.port))
        req = f'GET {path} HTTP/1.0\r\nHost: {self.host}\r\nConnection: close\r\n\r\n'
        s.sendall(req.encode())
        data = b''
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            except:
                break
        s.close()
        idx = data.find(b'\r\n\r\n')
        if idx >= 0:
            headers = data[:idx]
            body = data[idx+4:]
        else:
            headers = b''
            body = data
        return headers, body
    
    def _raw_get_with_user_defined(self, path):
        """GET with x-user-defined charset header, returns raw body."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(15)
        s.connect((self.host, self.port))
        req = (
            f'GET {path} HTTP/1.0\r\n'
            f'Host: {self.host}\r\n'
            f'Accept-Charset: x-user-defined\r\n'
            f'Connection: close\r\n\r\n'
        )
        s.sendall(req.encode())
        data = b''
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
            except:
                break
        s.close()
        idx = data.find(b'\r\n\r\n')
        if idx >= 0:
            return data[idx+4:]
        return data
    
    def get_rsa_key(self):
        """Step 1: GET /atenas.cgi?opType=6 -> returns 'e\\nn' in hex."""
        path = '/atenas.cgi?opType=6'
        headers, body = self._raw_get(path)
        text = body.decode('latin-1').strip()
        # Remove all whitespace/newlines, then split on first newline concept
        # The format is e\nn where n is the modulus (may have internal newlines)
        idx = text.find('\n')
        if idx < 0:
            print(f"RSA key response unexpected: {text[:200]}")
            return None, None
        e_hex = text[:idx].strip()
        n_hex = text[idx+1:].replace('\n', '').replace('\r', '').strip()
        print(f"RSA e (hex): {e_hex[:40]}...")
        print(f"RSA n (hex): {n_hex[:40]}...")
        return e_hex, n_hex
    
    def generate_aes_key(self):
        """Generate 32 hex chars (16 bytes / 128 bits)."""
        key_bytes = get_random_bytes(16)
        return key_bytes.hex()
    
    def aes_encrypt(self, plaintext_hex):
        """Encrypt hex string with AES-128-CBC (matches JS rijndaelEncrypt)."""
        key = bytes.fromhex(self.aes_key)
        iv = get_random_bytes(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        pt = bytes.fromhex(plaintext_hex)
        ct = cipher.encrypt(pt)
        return iv + ct
    
    def aes_decrypt(self, data):
        """Decrypt raw bytes with AES-128-CBC (matches JS rijndaelDecrypt).
        
        The first 16 bytes are the IV, rest is ciphertext.
        Returns decrypted string.
        """
        key = bytes.fromhex(self.aes_key)
        iv = data[:16]
        ct = data[16:]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        pt = cipher.decrypt(ct)
        # Remove PKCS7 padding
        try:
            pt = unpad(pt, AES.block_size)
        except:
            pass
        return pt.decode('latin-1', errors='replace')
    
    def rsa_encrypt(self, text, e_hex, n_hex):
        """RSA encrypt using PKCS#1 v1.5 (matches JS RSAEncrypt)."""
        e = int(e_hex, 16)
        n = int(n_hex, 16)
        rsa_key = RSA.construct((n, e))
        cipher = PKCS1_v1_5.new(rsa_key)
        pt = text.encode('latin-1')
        ct = cipher.encrypt(pt)
        result = ct.hex()
        return result
    
    def build_request_str(self, form_data_dict):
        """Build a URL-encoded request string (matches form field serialization)."""
        parts = []
        for key, value in form_data_dict.items():
            parts.append(f"{key}={urllib.parse.quote(str(value), safe='')}")
        return '&'.join(parts)
    
    def aes_encrypt_request(self, request_str):
        """Encrypt request string with AES, return hex result (matches Encrypt_Text)."""
        # setKey: convert hex key to bytes
        key = bytes.fromhex(self.aes_key)
        iv = get_random_bytes(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        # Pad plaintext to multiple of 16 with null bytes (\0)
        pt = request_str.encode('latin-1')
        # Match JS padding: pad with \0 to multiple of 16
        pad_len = 16 - (len(pt) % 16)
        if pad_len != 16:
            pt += b'\x00' * pad_len
        ct = cipher.encrypt(pt)
        result = (iv + ct).hex()
        return result
    
    def send_request(self, form_data, target_id=""):
        """Send encrypted request (matches sendForm). Returns decrypted body."""
        request_str = self.build_request_str(form_data)
        encrypted = self.aes_encrypt_request(request_str)
        path = f"/atenas.cgi?request={encrypted}"
        body = self._raw_get_with_user_defined(path)
        if len(body) == 0:
            print("Empty response")
            return None
        try:
            decrypted = self.aes_decrypt(body)
            return decrypted
        except Exception as e:
            print(f"Decrypt error: {e}")
            # Maybe not encrypted?
            try:
                return body.decode('latin-1')
            except:
                return None
    
    def send_form(self, opType, pgCode, lblId, extra_fields=None):
        """Send form with opType, pgCode, lblId and optional extra fields."""
        data = {
            'opType': str(opType),
            'pgCode': str(pgCode),
            'lblId': str(lblId),
        }
        if extra_fields:
            data.update(extra_fields)
        return self.send_request(data)
    
    def login(self, username=None, password=None):
        """Full login flow."""
        if not username or not password:
            print("Username and password are required")
            return False

        print("Step 1: Getting RSA public key...")
        e_hex, n_hex = self.get_rsa_key()
        if not e_hex or not n_hex:
            print("Failed to get RSA key")
            return False
        
        print("Step 2: Generating AES key...")
        self.aes_key = self.generate_aes_key()
        print(f"AES key: {self.aes_key}")
        
        print("Step 3: Building login request string...")
        # Match what the JS does:
        # getRequestStr('','frmREP',false,false) with form fields set
        form_data = {
            'opType': '0',
            'pgCode': '60',
            'lblId': '0',
            'lblLogin': username,
            'lblPass': password,
        }
        request_str = self.build_request_str(form_data)
        
        # RSA encrypt: aes_key + '\n' + request_str + '\n'
        payload = f"{self.aes_key}\n{request_str}\n"
        print(f"RSA payload: {payload[:80]}...")
        
        encrypted_rsa = self.rsa_encrypt(payload, e_hex, n_hex)
        print(f"RSA encrypted (hex): {encrypted_rsa[:60]}...")
        
        print("Step 4: Sending encrypted AES key...")
        path = f"/atenas.cgi?opType=7&{encrypted_rsa}"
        body = self._raw_get_with_user_defined(path)
        
        if len(body) == 0:
            print("Empty response from opType=7")
            return False
        
        print(f"Response body length: {len(body)} bytes")
        
        print("Step 5: Decrypting response...")
        try:
            decrypted = self.aes_decrypt(body)
            print(f"Decrypted ({len(decrypted)} chars):")
            print(decrypted[:800])
            
            if '</tr>' not in decrypted:
                print("Login FAILED - no </tr> in response")
                return False
            
            if 'lblLogin' in decrypted or 'Usuário' in decrypted or 'Usuario' in decrypted:
                print("Login FAILED - login form still present")
                return False
            
            print("LOGIN SUCCESSFUL!")
            return True
        except Exception as e:
            print(f"Decryption error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def navigate(self, opType, pgCode, lblId=0):
        """Navigate to a page (matches subComp/sendForm)."""
        return self.send_form(opType, pgCode, lblId)
    
    def get_events_page(self):
        """Navigate to events page."""
        return self.navigate(0, 0, 0)  # Unknown opType/pgCode for events


if __name__ == '__main__':
    client = REPClient()
    if client.login():
        print("\n=== Login OK ===")
