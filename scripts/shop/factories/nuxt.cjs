// Nuxt payload.js (JSONP) со стандартного входа → JSON на выход (для lago.py)
const vm = require('vm');
let src = '';
process.stdin.on('data', (c) => (src += c));
process.stdin.on('end', () => {
  let out;
  vm.runInNewContext(src, { __NUXT_JSONP__: (p, o) => { out = o; } }, { timeout: 5000 });
  process.stdout.write(JSON.stringify(out || null));
});
