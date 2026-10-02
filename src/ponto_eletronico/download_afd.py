import sys
import time
import socket
import argparse
import os
from rep_client import REPClient

def strip_http_header(body):
    if not body.startswith(b"HTTP/"):
        return body
    for marker in (b"\r\n\r\n", b"\r\n\n"):
        idx = body.find(marker)
        if idx >= 0:
            return body[idx + len(marker):]
    return body

def download_afd(ip, username, password, output_filename):
    print(f"[{ip}] Iniciando comunicação com o relógio...")
    c = REPClient(host=ip)
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((ip, 80))
        s.close()
    except Exception as e:
        print(f"[{ip}] Erro de conexão: Não foi possível acessar o IP (timeout ou offline). {e}")
        return False

    c.username = username
    c.password = password
    
    print(f"[{ip}] Tentando fazer login como '{username}'...")
    e_hex, n_hex = c.get_rsa_key()
    if not e_hex or not n_hex:
        print(f"[{ip}] Falha ao obter chave RSA.")
        return False
        
    c.aes_key = c.generate_aes_key()
    form_data = {
        'opType': '0', 'pgCode': '60', 'lblId': '0',
        'lblLogin': c.username, 'lblPass': c.password,
    }
    request_str = c.build_request_str(form_data)
    payload = f"{c.aes_key}\n{request_str}\n"
    encrypted_rsa = c.rsa_encrypt(payload, e_hex, n_hex)
    
    login_body = c._raw_get_with_user_defined(f"/atenas.cgi?opType=7&{encrypted_rsa}")
    if len(login_body) == 0:
        print(f"[{ip}] Login sem corpo de resposta; seguindo com a chave AES enviada.")
    else:
        print(f"[{ip}] LOGIN OK!")
        
    def navegar_raw(op, pg, lbl=0):
        data = {'opType': str(op), 'pgCode': str(pg), 'lblId': str(lbl)}
        enc = c.aes_encrypt_request(c.build_request_str(data))
        return c._raw_get_with_user_defined(f"/atenas.cgi?request={enc}")
        
    # Preparar modo de download
    print(f"[{ip}] Preparando para exportar dados...")
    navegar_raw(4, 32, 0)
    time.sleep(0.5)
    navegar_raw(1, 255, 255)
    time.sleep(1.0)
    
    print(f"[{ip}] Solicitando Arquivo Fonte de Dados (AFD)...")
    # AFD fica em Eventos > Download de eventos > Completo.
    # Dados > Log (pgCode=31/lblId=54) baixa apenas o log do equipamento.
    data = {
        'opType': '1', 'pgCode': '32', 'lblId': '0',
        'visibleDiv': 'info',
    }
    enc = c.aes_encrypt_request(c.build_request_str(data))
    path = f"/atenas.cgi?request={enc}"
    
    try:
        body = c._raw_get_with_user_defined(path)
        body = strip_http_header(body)
        print(f"[{ip}] Lidos {len(body)} bytes completos.")
        
        if len(body) > 0:
            with open(output_filename, 'wb') as f:
                f.write(body)
            print(f"[{ip}] SUCESSO: AFD salvo em '{output_filename}'.")
            return True
        else:
            print(f"[{ip}] Erro: Resposta vazia ao tentar baixar o AFD.")
            return False
    except Exception as e:
        print(f"[{ip}] Erro ao baixar o arquivo: {e}")
        return False

DEVICES = {
    "601": {
        "ip": "192.168.15.36",
        "serial": "00004004330216717",
        "user_env": "REP_601_USER",
        "pass_env": "REP_601_PASS",
    },
    "nevine": {
        "ip": "192.168.1.35",
        "serial": "00004004330212445",
        "user_env": "REP_NEVINE_USER",
        "pass_env": "REP_NEVINE_PASS",
    },
}

def next_output_filename(serial):
    import glob
    import re

    highest = 0
    for filename in glob.glob(f"{serial}*.txt"):
        match = re.search(r"\((\d+)\)\.txt$", filename)
        if match:
            highest = max(highest, int(match.group(1)))
        elif filename == f"{serial}.txt":
            highest = max(highest, 0)
    return f"{serial} ({highest + 1}).txt"

def main():
    parser = argparse.ArgumentParser(description="Baixa AFD de um REP Henry via HTTP criptografado.")
    parser.add_argument("device", choices=DEVICES.keys(), help="Dispositivo a baixar.")
    parser.add_argument("--username", help="Usuario do REP. Tambem pode vir por variavel de ambiente.")
    parser.add_argument("--password", help="Senha do REP. Tambem pode vir por variavel de ambiente.")
    parser.add_argument("--output", help="Arquivo de saida. Se omitido, usa o proximo nome pelo serial.")
    args = parser.parse_args()

    dev = DEVICES[args.device]
    username = args.username or os.environ.get(dev["user_env"])
    password = args.password or os.environ.get(dev["pass_env"])

    if not username or not password:
        print(f"Informe --username/--password ou defina {dev['user_env']} e {dev['pass_env']}.")
        return 2

    output = args.output or next_output_filename(dev["serial"])
    return 0 if download_afd(dev["ip"], username, password, output) else 1

if __name__ == '__main__':
    raise SystemExit(main())
