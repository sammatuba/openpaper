const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname,'../public/vendor/textfold');
const upstream = JSON.parse(fs.readFileSync(path.join(root,'UPSTREAM.json'),'utf8'));
assert.equal(upstream.commit,'92ad625ab6887bf0060374c1fd86a558513baed2');
for (const [name,record] of Object.entries(upstream.files)) {
    const hash = crypto.createHash('sha256').update(fs.readFileSync(path.join(root,name))).digest('hex');
    assert.equal(hash,record.sha256,`${name}: unexpected change to pinned upstream asset`);
}
assert.match(fs.readFileSync(path.join(root,'LICENSE'),'utf8'),/Apache License/);
assert.match(fs.readFileSync(path.join(root,'NOTICE'),'utf8'),/Copyright 2026 Xia Chen/);
assert.match(fs.readFileSync(path.join(root,'reader.js'),'utf8'),/window\.__reader =/);
console.log('Pinned upstream Textfold assets, integration patch, license and notice verified');
