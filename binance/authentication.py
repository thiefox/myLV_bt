import hmac
import hashlib
from base64 import b64encode
from Crypto.PublicKey import RSA, ECC
from Crypto.Hash import SHA256
from Crypto.Signature import pkcs1_15, eddsa

#hmac带密钥的哈希，消息接收者用密钥可以验证该消息是否被篡改
def hmac_hashing(api_secret : str, payload : str) -> str:
    m = hmac.new(api_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return m.hexdigest()

#rsa私钥签名
def rsa_signature(private_key : str, payload : str, private_key_pass=None) -> bytes:
    private_key = RSA.import_key(private_key, passphrase=private_key_pass)
    h = SHA256.new(payload.encode("utf-8"))
    signature = pkcs1_15.new(private_key).sign(h)
    return b64encode(signature)

#ed25519私钥签名
def ed25519_signature(pri_key_str : str, payload : str, private_key_pass=None) -> bytes:
    pri_key_obj = ECC.import_key(pri_key_str, passphrase=private_key_pass)
    signer = eddsa.new(pri_key_obj, "rfc8032")
    signature = signer.sign(payload.encode("utf-8"))
    return b64encode(signature)

def test():
    #载入ECC私钥
    private_key_file = "D:/src/python/myLV_bt/data/MYLV_E.pem"
    with open(private_key_file, "r") as f:
        pri_key_str = f.read()
        pri_key_obj = ECC.import_key(pri_key_str)
        pub_key_obj = pri_key_obj.public_key()
    # 载入要签名的数据
    payload = "Hello, world!"
    # 使用ECC私钥进行签名
    signer = eddsa.new(pri_key_obj, "rfc8032")
    signature = signer.sign(payload.encode("utf-8"))
    #signature = b64encode(signature)
    # 打印签名结果
    #print("Signature:", signature.decode("utf-8"))
    
    # 打印公钥
    print("Private Key:", pri_key_obj.export_key(format="PEM"))
    print("Public Key:", pub_key_obj.export_key(format="PEM"))
    # 使用公钥验证签名
    verifier = eddsa.new(pub_key_obj, "rfc8032")
    #payload = "Hello, world1"
    try:
        verifier.verify(payload.encode("utf-8"), signature)
        print("Signature is valid.")
    except (ValueError, TypeError):
        print("Signature is invalid.")
    return

#test()