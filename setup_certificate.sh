#!/bin/bash
set -e

echo "🔑 Kiểm tra chứng thư số LocalCodeSigner trong Keychain..."
if security find-certificate -c "LocalCodeSigner" ~/Library/Keychains/login.keychain-db >/dev/null 2>&1; then
    echo "✅ Chứng thư số LocalCodeSigner đã tồn tại trong Keychain."
    exit 0
fi

echo "⚙️ Đang tạo và cài đặt chứng thư số LocalCodeSigner..."
CONF="/tmp/cert_local_codesigner.conf"
KEY="/tmp/cert_local_codesigner.key"
CRT="/tmp/cert_local_codesigner.crt"
P12="/tmp/cert_local_codesigner.p12"

cat << 'EOF' > "$CONF"
[ req ]
default_bits        = 2048
distinguished_name  = req_distinguished_name
prompt              = no
x509_extensions     = v3_req

[ req_distinguished_name ]
CN                  = LocalCodeSigner

[ v3_req ]
keyUsage            = critical, digitalSignature
extendedKeyUsage    = codeSigning
EOF

openssl req -new -x509 -nodes -days 3650 -config "$CONF" -keyout "$KEY" -out "$CRT" 2>/dev/null
openssl pkcs12 -export -legacy -out "$P12" -inkey "$KEY" -in "$CRT" -passout pass:123456 2>/dev/null
security import "$P12" -k ~/Library/Keychains/login.keychain-db -P 123456 -T /usr/bin/codesign 2>/dev/null || security import "$P12" -P 123456 -T /usr/bin/codesign 2>/dev/null

rm -f "$CONF" "$KEY" "$CRT" "$P12"
echo "🎉 Đã cài đặt chứng thư số LocalCodeSigner vào Keychain thành công!"
