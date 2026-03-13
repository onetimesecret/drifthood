// ── Version and example endpoint sets ──

export const DD_VERSION = '0.5.0';

export const EXAMPLES = {
  'mixed': [
    {m:'GET',  l:'status-query',  p:'/api/v1/status', b:'',                              ct:'query'},
    {m:'POST', l:'share-form',    p:'/api/v1/share',  b:'secret=hello&ttl=3600',         ct:'application/x-www-form-urlencoded'},
    {m:'POST', l:'share-json',    p:'/api/v2/share',  b:'{"secret":"hello","ttl":3600}',  ct:'application/json'},
  ],
  'query-only': [
    {m:'GET', l:'v1-status', p:'/api/v1/status',      b:'', ct:'query'},
    {m:'GET', l:'v2-status', p:'/api/v2/status',      b:'', ct:'query'},
    {m:'GET', l:'v1-404',    p:'/api/v1/nonexistent', b:'', ct:'query'},
  ],
  'form-only': [
    {m:'POST', l:'v1-share',      p:'/api/v1/share',    b:'secret=test&ttl=3600',                    ct:'application/x-www-form-urlencoded'},
    {m:'POST', l:'v1-generate',   p:'/api/v1/generate', b:'ttl=3600',                                ct:'application/x-www-form-urlencoded'},
    {m:'POST', l:'v1-share-pass', p:'/api/v1/share',    b:'secret=test&ttl=3600&passphrase=abcdefgh', ct:'application/x-www-form-urlencoded'},
  ],
  'json-only': [
    {m:'POST', l:'v2-share',      p:'/api/v2/share',    b:'{"secret":"test","ttl":3600}',                          ct:'application/json'},
    {m:'POST', l:'v2-generate',   p:'/api/v2/generate', b:'{"ttl":3600}',                                          ct:'application/json'},
    {m:'POST', l:'v2-share-pass', p:'/api/v2/share',    b:'{"secret":"test","ttl":3600,"passphrase":"abcdefgh"}',   ct:'application/json'},
  ],
};
