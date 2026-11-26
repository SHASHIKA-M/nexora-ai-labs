// Frontend build: bundles the ES-module source into a single minified asset.
// esbuild is the only build dependency; it is installed by `npm install`.
import { build } from 'esbuild';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const entry = path.join(root, 'frontend', 'src', 'main.js');
const outDir = path.join(root, 'frontend', 'public', 'assets');

fs.mkdirSync(outDir, { recursive: true });

const result = await build({
  entryPoints: [entry],
  outfile: path.join(outDir, 'app.js'),
  bundle: true,
  minify: true,
  sourcemap: false,
  target: ['es2020'],
  format: 'iife',
  logLevel: 'silent',
  metafile: true,
});

// Ship the stylesheet next to the bundle so the browser can fetch it.
fs.copyFileSync(path.join(root, 'frontend', 'src', 'styles.css'), path.join(outDir, 'styles.css'));

const output = Object.values(result.metafile.outputs)[0];
const bytes = fs.statSync(path.join(outDir, 'app.js')).size;
const cssBytes = fs.statSync(path.join(outDir, 'styles.css')).size;
console.log(`Built frontend bundle: ${path.relative(root, path.join(outDir, 'app.js'))}`);
console.log(`  modules inlined: ${Object.keys(result.metafile.inputs).length}`);
console.log(`  bundle size:     ${(bytes / 1024).toFixed(1)} KB (js) + ${(cssBytes / 1024).toFixed(1)} KB (css)`);
void output;
