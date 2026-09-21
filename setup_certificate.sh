#!/bin/bash
# LocalCodeSigner Certificate Setup for macOS
# Automatically handles standard user, sudo execution, LibreSSL and OpenSSL 3.x

set -e

# 1. Determine target user and home directory (handles sudo properly)
if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
    TARGET_USER="$SUDO_USER"
    TARGET_HOME=$(eval echo "~$SUDO_USER")
    RUN_AS_USER="sudo -u $TARGET_USER"
else
    TARGET_USER="$(id -un)"
    TARGET_HOME="$HOME"
    RUN_AS_USER=""
fi

# 2. Locate user's login keychain
KEYCHAIN=""
if [ -n "$RUN_AS_USER" ]; then
    KEYCHAIN=$($RUN_AS_USER security login-keychain 2>/dev/null | tr -d ' "\t\r\n')
else
    KEYCHAIN=$(security login-keychain 2>/dev/null | tr -d ' "\t\r\n')
fi

if [ -z "$KEYCHAIN" ] || [ ! -f "$KEYCHAIN" ]; then
    if [ -f "$TARGET_HOME/Library/Keychains/login.keychain-db" ]; then
        KEYCHAIN="$TARGET_HOME/Library/Keychains/login.keychain-db"
    elif [ -f "$TARGET_HOME/Library/Keychains/login.keychain" ]; then
        KEYCHAIN="$TARGET_HOME/Library/Keychains/login.keychain"
    fi
fi

echo "🔑 Checking for 'LocalCodeSigner' certificate in Keychain..."
CERT_EXISTS=0
if [ -n "$KEYCHAIN" ]; then
    if [ -n "$RUN_AS_USER" ]; then
        $RUN_AS_USER security find-certificate -c "LocalCodeSigner" "$KEYCHAIN" >/dev/null 2>&1 && CERT_EXISTS=1
    else
        security find-certificate -c "LocalCodeSigner" "$KEYCHAIN" >/dev/null 2>&1 && CERT_EXISTS=1
    fi
else
    security find-certificate -c "LocalCodeSigner" >/dev/null 2>&1 && CERT_EXISTS=1
fi

if [ $CERT_EXISTS -eq 1 ]; then
    echo "✅ Certificate 'LocalCodeSigner' already exists in Keychain."
    exit 0
fi

echo "⚙️ Creating and installing 'LocalCodeSigner' certificate..."
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

# Generate private key and certificate
openssl req -new -x509 -nodes -days 3650 -config "$CONF" -keyout "$KEY" -out "$CRT" 2>/dev/null

# Export PKCS12: Standard export first (macOS LibreSSL default), fallback to -legacy (OpenSSL 3.x)
if ! openssl pkcs12 -export -out "$P12" -inkey "$KEY" -in "$CRT" -passout pass:123456 2>/dev/null; then
    openssl pkcs12 -export -legacy -out "$P12" -inkey "$KEY" -in "$CRT" -passout pass:123456 2>/dev/null
fi

# Import into Keychain
if [ -n "$KEYCHAIN" ]; then
    if [ -n "$RUN_AS_USER" ]; then
        $RUN_AS_USER security import "$P12" -k "$KEYCHAIN" -P 123456 -T /usr/bin/codesign 2>/dev/null || \
        $RUN_AS_USER security import "$P12" -P 123456 -T /usr/bin/codesign 2>/dev/null
    else
        security import "$P12" -k "$KEYCHAIN" -P 123456 -T /usr/bin/codesign 2>/dev/null || \
        security import "$P12" -P 123456 -T /usr/bin/codesign 2>/dev/null
    fi
else
    security import "$P12" -P 123456 -T /usr/bin/codesign 2>/dev/null
fi

# Clean up temp files safely using python
python3 -c "import os; [os.remove(p) for p in ['$CONF', '$KEY', '$CRT', '$P12'] if os.path.exists(p)]" 2>/dev/null || true

echo "🎉 Successfully installed 'LocalCodeSigner' certificate into Keychain!"
