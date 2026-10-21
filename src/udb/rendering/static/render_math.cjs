// Turn the \( ... \) and \[ ... \] formulas of an HTML file into static SVG.
// The result needs no JavaScript and no network to display.
//
// Usage:
//   MJ_ROOT=/folder/with/node_modules node render_math.cjs input.html output.html
//
// Needs `npm install mathjax-full` inside MJ_ROOT (udb does it on first use).
const fs = require('fs');
const root = process.env.MJ_ROOT;
if (!root) { console.error('MJ_ROOT is not set'); process.exit(2); }
const req = (p) => require(`${root}/node_modules/mathjax-full/js/${p}`);

const { mathjax } = req('mathjax.js');
const { TeX } = req('input/tex.js');
const { SVG } = req('output/svg.js');
const { liteAdaptor } = req('adaptors/liteAdaptor.js');
const { RegisterHTMLHandler } = req('handlers/html.js');
const { AllPackages } = req('input/tex/AllPackages.js');

const [, , inPath, outPath] = process.argv;
const src = fs.readFileSync(inPath, 'utf8');

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);
const tex = new TeX({ packages: AllPackages });
const svg = new SVG({ fontCache: 'none' });
const doc = mathjax.document('', { InputJax: tex, OutputJax: svg });

const unescapeHtml = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
let errors = 0;
const render = (code, display) => {
  const node = doc.convert(unescapeHtml(code).trim(), { display });
  const html = adaptor.outerHTML(node);
  if (html.includes('data-mjx-error') || html.includes('merror')) {
    errors += 1;
    console.error('TeX error in:', code.slice(0, 120));
  }
  return html;
};

// Only formulas in the body are touched; <head> (styles, scripts) stays as is.
const idx = src.indexOf('<body');
const head = src.slice(0, idx);
let body = src.slice(idx);
let n = 0;
body = body.replace(/\\\[([\s\S]*?)\\\]/g, (_, c) => { n++; return render(c, true); });
body = body.replace(/\\\(([\s\S]*?)\\\)/g, (_, c) => { n++; return render(c, false); });

const css = adaptor.textContent(svg.styleSheet(doc));
fs.writeFileSync(outPath, head.replace('</head>', `<style>${css}</style>\n</head>`) + body);
console.log(JSON.stringify({ formulas: n, errors }));
if (errors) process.exit(1);
