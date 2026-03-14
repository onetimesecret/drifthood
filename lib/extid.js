/**
 * Generate a UUIDv7 (RFC 9562) — time-ordered with millisecond precision.
 *
 * Used as external identifiers so primary keys and tokens never
 * appear in URLs, UI, or API communication.
 */
export function uuidv7() {
  const timestamp = Date.now();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);

  // Bytes 0-5: 48-bit timestamp (big-endian)
  bytes[0] = Math.floor(timestamp / 0x10000000000) & 0xFF;
  bytes[1] = Math.floor(timestamp / 0x100000000) & 0xFF;
  bytes[2] = Math.floor(timestamp / 0x1000000) & 0xFF;
  bytes[3] = Math.floor(timestamp / 0x10000) & 0xFF;
  bytes[4] = Math.floor(timestamp / 0x100) & 0xFF;
  bytes[5] = timestamp & 0xFF;

  // Byte 6: version 7 (high nibble) + random (low nibble)
  bytes[6] = (bytes[6] & 0x0F) | 0x70;

  // Byte 8: variant 10 (high 2 bits) + random (low 6 bits)
  bytes[8] = (bytes[8] & 0x3F) | 0x80;

  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
