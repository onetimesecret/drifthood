// src/lib/crypto.js

/**
 * Client-side cryptographic operations for the drift detector.
 * Zero dependencies — uses Web Crypto API (SubtleCrypto) exclusively.
 *
 * Key derivation model:
 *   HKDF(token, salt=extid, info="auth") → authKey (for Bearer header)
 *   HKDF(token, salt=extid, info="enc")  → encKey  (for AES-GCM encryption)
 *
 * The raw token never crosses the network after initial receipt from server.
 * Derived authKey replaces it in Authorization headers.
 *
 * HKDF follows RFC 5869 (extract-then-expand with HMAC-SHA256).
 * SubtleCrypto's HKDF matches Python's stdlib hmac-based implementation
 * when given identical inputs:
 *   - IKM: raw token bytes (decoded from base64url)
 *   - salt: UTF-8 encoded extid string
 *   - info: UTF-8 encoded "auth" or "enc"
 *   - hash: SHA-256
 */


// ---------------------------------------------------------------------------
// Base64url helpers (no padding, URL-safe alphabet)
//
// Python's secrets.token_urlsafe(32) produces base64url-encoded strings
// representing 32 raw bytes. These helpers handle that encoding.
// ---------------------------------------------------------------------------

/**
 * Decode a base64url string (no padding) to Uint8Array.
 * Converts URL-safe chars (+→-, /→_) back to standard base64 before decoding.
 */
function base64urlDecode(str) {
  // Restore standard base64 alphabet and add padding
  const base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Encode Uint8Array to base64url string (no padding).
 */
function base64urlEncode(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

/**
 * Encode Uint8Array to standard base64 string.
 * Used for encrypted blob storage where URL-safety is not needed.
 */
function base64Encode(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Decode standard base64 string to Uint8Array.
 */
function base64Decode(str) {
  const binary = atob(str);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}


// ---------------------------------------------------------------------------
// Key derivation
// ---------------------------------------------------------------------------

/**
 * Derive auth and encryption keys from a raw token + session extid.
 *
 * Uses HKDF (RFC 5869) with SHA-256. The token's raw bytes are the input
 * keying material; the extid (as UTF-8 bytes) is the salt. Two separate
 * info strings ("auth", "enc") produce independent derived keys.
 *
 * @param {string} token - Raw token from server (base64url-encoded, 32 bytes)
 * @param {string} extid - Session extid (UUIDv7 string, used as HKDF salt)
 * @returns {Promise<{authKey: string, encKey: CryptoKey}>}
 *   authKey: base64url-encoded 32-byte derived key (for Bearer header)
 *   encKey:  CryptoKey handle for AES-GCM encrypt/decrypt
 */
export async function deriveKeys(token, extid) {
  // Decode token from base64url to the original 32 raw bytes
  const tokenBytes = base64urlDecode(token);

  // Import raw bytes as HKDF key material (not directly usable for
  // encrypt/sign — only for deriveBits/deriveKey)
  const keyMaterial = await crypto.subtle.importKey(
    'raw', tokenBytes, 'HKDF', false, ['deriveBits', 'deriveKey']
  );

  // Salt is the session's public identifier, UTF-8 encoded.
  // Using extid as salt binds derived keys to a specific session.
  const salt = new TextEncoder().encode(extid);

  // --- Auth key ---
  // HKDF(token, salt=extid, info="auth") → 256 bits → base64url string
  // This replaces the raw token in Authorization: Bearer headers.
  const authBits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt, info: new TextEncoder().encode('auth') },
    keyMaterial,
    256
  );
  const authKey = base64urlEncode(new Uint8Array(authBits));

  // --- Encryption key ---
  // HKDF(token, salt=extid, info="enc") → AES-GCM-256 CryptoKey
  // Non-extractable: the raw key bytes cannot be read from JS.
  const encKey = await crypto.subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt, info: new TextEncoder().encode('enc') },
    keyMaterial,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt']
  );

  return { authKey, encKey };
}


// ---------------------------------------------------------------------------
// Encryption (AES-GCM)
// ---------------------------------------------------------------------------

/**
 * Encrypt a plaintext string using AES-GCM with a random 96-bit IV.
 *
 * The entity's extid is bound as Additional Authenticated Data (AAD),
 * which means a ciphertext encrypted for one entity cannot be replayed
 * against a different entity — decryption will fail if the extid doesn't
 * match.
 *
 * @param {CryptoKey} encKey - AES-GCM key from deriveKeys()
 * @param {string} plaintext - String to encrypt (typically JSON)
 * @param {string} entityExtid - Entity's extid, bound as AAD
 * @returns {Promise<{ciphertext: string, iv: string, hash: string}>}
 *   ciphertext: base64-encoded encrypted bytes (includes GCM auth tag)
 *   iv:         base64-encoded 96-bit nonce
 *   hash:       hex SHA-256 of plaintext (for dedup / integrity checks)
 */
export async function encryptBlob(encKey, plaintext, entityExtid) {
  const plaintextBytes = new TextEncoder().encode(plaintext);
  const ad = new TextEncoder().encode(entityExtid);

  // 96-bit IV is the standard size for AES-GCM. Each encryption uses
  // a fresh random IV — never reuse an IV with the same key.
  const iv = crypto.getRandomValues(new Uint8Array(12));

  const ciphertextBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv, additionalData: ad },
    encKey,
    plaintextBytes
  );

  // Hash the plaintext so the server can detect duplicates without
  // being able to read the content.
  const hash = await hashBlob(plaintext);

  return {
    ciphertext: base64Encode(new Uint8Array(ciphertextBuffer)),
    iv: base64Encode(iv),
    hash,
  };
}

/**
 * Decrypt an AES-GCM encrypted blob.
 *
 * @param {CryptoKey} encKey - AES-GCM key from deriveKeys()
 * @param {string} ciphertext - base64-encoded ciphertext (from encryptBlob)
 * @param {string} iv - base64-encoded 96-bit nonce (from encryptBlob)
 * @param {string} entityExtid - Entity's extid (must match what was used during encryption)
 * @returns {Promise<string>} Decrypted plaintext string
 * @throws {DOMException} If the key, IV, or AAD don't match (authentication failure)
 */
export async function decryptBlob(encKey, ciphertext, iv, entityExtid) {
  const ciphertextBytes = base64Decode(ciphertext);
  const ivBytes = base64Decode(iv);
  const ad = new TextEncoder().encode(entityExtid);

  const plaintextBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: ivBytes, additionalData: ad },
    encKey,
    ciphertextBytes
  );

  return new TextDecoder().decode(plaintextBuffer);
}


// ---------------------------------------------------------------------------
// Hashing
// ---------------------------------------------------------------------------

/**
 * SHA-256 hash of a string, returned as lowercase hex.
 *
 * Used for content dedup: the server can compare hashes to detect
 * identical blobs without access to plaintext.
 *
 * @param {string} plaintext - String to hash
 * @returns {Promise<string>} 64-character hex-encoded SHA-256 digest
 */
export async function hashBlob(plaintext) {
  const data = new TextEncoder().encode(plaintext);
  const hashBuffer = await crypto.subtle.digest('SHA-256', data);
  const hashArray = new Uint8Array(hashBuffer);
  return Array.from(hashArray)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}
