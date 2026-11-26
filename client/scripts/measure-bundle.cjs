// Attributes the built JavaScript to packages, from the production source maps.
// Run after `next build`. Usage: node scripts/measure-bundle.cjs [chunks to list, default 8]
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const root = path.resolve(__dirname, '../.next/static/chunks');
const listed = Number(process.argv[2]) || 8;
const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
const digit = new Int8Array(128).fill(-1);
for (let i = 0; i < 64; i += 1) digit[B64.charCodeAt(i)] = i;

const owner = source => {
    const at = source.lastIndexOf('node_modules/');
    if (at < 0) {
        // Prebuilt bundles keep their own source roots: pdf.js, and Next's client runtime.
        if (source.includes('/pdf.js/')) return 'pdfjs-dist';
        if (/_N_E\/(\.\.\/)+src\//.test(source)) return 'next (client runtime)';
        return /_N_E\/\.\/src\//.test(source) ? 'app (src/)' : 'other';
    }
    const parts = source.slice(at + 13).split('/');
    // Next vendors React and others under next/dist/compiled.
    if (parts[0] === 'next' && parts[2] === 'compiled') return `next/compiled/${parts[3]}`;
    return parts[0].startsWith('@') ? `${parts[0]}/${parts[1]}` : parts[0];
};

// Bytes of generated code per source: each mapping segment owns the columns up to the next one.
function attribute(code, map) {
    const bytes = new Map();
    const lines = code.split('\n');
    let source = 0;
    map.mappings.split(';').forEach((line, row) => {
        const length = (lines[row] || '').length;
        let column = 0, previous = -1, previousSource = -1;
        const close = end => { if (previous >= 0) bytes.set(previousSource, (bytes.get(previousSource) || 0) + end - previous); };
        for (const segment of line ? line.split(',') : []) {
            const fields = [];
            let value = 0, shift = 0;
            for (let i = 0; i < segment.length; i += 1) {
                const d = digit[segment.charCodeAt(i)];
                value += (d & 31) << shift;
                if (d & 32) { shift += 5; continue; }
                fields.push(value & 1 ? -(value >> 1) : value >> 1);
                value = 0; shift = 0;
            }
            column += fields[0];
            if (fields.length > 1) source += fields[1];
            close(column);
            previous = column;
            previousSource = fields.length > 1 ? source : -1;
        }
        close(length);
    });
    const packages = new Map();
    for (const [index, size] of bytes) {
        const name = index < 0 ? 'unmapped' : owner(map.sources[index] || '');
        packages.set(name, (packages.get(name) || 0) + size);
    }
    return packages;
}

const files = [];
const walk = dir => fs.readdirSync(dir, { withFileTypes: true }).forEach(entry => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (entry.name.endsWith('.js') && fs.existsSync(`${full}.map`)) files.push(full);
});
walk(root);

const kb = bytes => `${(bytes / 1024).toFixed(1).padStart(8)} KB`;
const total = new Map();
const chunks = files.map(file => {
    const code = fs.readFileSync(file, 'utf8');
    const packages = attribute(code, JSON.parse(fs.readFileSync(`${file}.map`, 'utf8')));
    for (const [name, size] of packages) total.set(name, (total.get(name) || 0) + size);
    return { file: path.relative(root, file), size: Buffer.byteLength(code), gzip: zlib.gzipSync(code).length, packages };
}).sort((a, b) => b.size - a.size);
const top = (packages, count) => [...packages].sort((a, b) => b[1] - a[1]).slice(0, count);

console.log(`${chunks.length} chunks, ${kb(chunks.reduce((sum, chunk) => sum + chunk.size, 0)).trim()} raw, ${kb(chunks.reduce((sum, chunk) => sum + chunk.gzip, 0)).trim()} gzip\n`);
console.log('Largest chunks');
for (const chunk of chunks.slice(0, listed)) {
    console.log(`${kb(chunk.size)} ${kb(chunk.gzip)} gzip  ${chunk.file}`);
    console.log(`           ${top(chunk.packages, 4).map(([name, size]) => `${name} ${(size / 1024).toFixed(0)}`).join(', ')}`);
}
console.log('\nRoute chunks over 40 KB');
for (const chunk of chunks.filter(item => item.file.startsWith('app/') && item.size > 40 * 1024)) {
    console.log(`${kb(chunk.size)} ${kb(chunk.gzip)} gzip  ${chunk.file}`);
    console.log(`           ${top(chunk.packages, 5).map(([name, size]) => `${name} ${(size / 1024).toFixed(0)}`).join(', ')}`);
}
console.log('\nPackages, all chunks');
for (const [name, size] of top(total, 25)) console.log(`${kb(size)}  ${name}`);
