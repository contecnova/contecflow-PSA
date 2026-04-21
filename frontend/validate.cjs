#!/usr/bin/env node
/**
 * Contecflow v22 — Validador JSX con Babel (CommonJS)
 * Ejecutar: node validate.cjs
 */
const parser = require('@babel/parser');
const fs     = require('fs');
const path   = require('path');

const pagesDir = path.join(__dirname, 'src', 'pages');
const files = fs.readdirSync(pagesDir)
  .filter(f => f.endsWith('.jsx') || f.endsWith('.js'))
  .sort();

let errors = 0;

console.log(`\n Validando ${files.length} archivos JSX...\n`);

for (const file of files) {
  const code = fs.readFileSync(path.join(pagesDir, file), 'utf8');
  try {
    parser.parse(code, { sourceType: 'module', plugins: ['jsx'] });
  } catch(e) {
    errors++;
    console.error(`  ❌ ${file}:${e.loc?.line}:${e.loc?.column}`);
    console.error(`     ${e.message.split('\n')[0]}`);
    const lines = code.split('\n');
    const errLine = (e.loc?.line || 1) - 1;
    for (let i = Math.max(0, errLine-1); i <= Math.min(lines.length-1, errLine+1); i++) {
      const marker = i === errLine ? '>>>' : '   ';
      console.error(`     ${marker} ${i+1}| ${lines[i]}`);
    }
    console.error('');
  }
}

if (errors === 0) {
  console.log(` ✅ ${files.length}/${files.length} archivos JSX correctos\n`);
} else {
  console.error(` ❌ ${errors} archivo(s) con errores de sintaxis\n`);
  process.exit(1);
}
