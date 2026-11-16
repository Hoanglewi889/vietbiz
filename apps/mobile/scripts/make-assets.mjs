// Draws the VietBiz mark (the italic "V" tile of the web workspace) into the source images that
// `capacitor-assets generate` turns into every iOS and Android icon and splash size.
import sharp from "sharp";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const out = join(dirname(fileURLToPath(import.meta.url)), "..", "resources");
mkdirSync(out, { recursive: true });
const ink = "#183a32", lime = "#dae9ad", paper = "#f5f6ef";
const mark = (size, scale, bg) => `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  ${bg ? `<rect width="${size}" height="${size}" fill="${bg}"/>` : ""}
  <g transform="translate(${size / 2} ${size / 2}) scale(${(size * scale) / 100})">
    <path d="M-30 -32 H-14 L2 16 L18 -32 H32 L10 32 H-8 Z" fill="${lime}" transform="skewX(-10)"/>
  </g>
</svg>`;
const splash = (dark) => `<svg xmlns="http://www.w3.org/2000/svg" width="2732" height="2732">
  <rect width="2732" height="2732" fill="${dark ? "#12302a" : paper}"/>
  <rect x="1166" y="1166" width="400" height="400" rx="96" fill="${ink}"/>
  <g transform="translate(1366 1366) scale(2.4)"><path d="M-30 -32 H-14 L2 16 L18 -32 H32 L10 32 H-8 Z" fill="${lime}" transform="skewX(-10)"/></g>
</svg>`;
await sharp(Buffer.from(mark(1024, 0.62, ink))).png().toFile(join(out, "icon-only.png"));
// Android adaptive icons: the foreground must stay inside the inner 66 % safe zone.
await sharp(Buffer.from(mark(1024, 0.4, null))).png().toFile(join(out, "icon-foreground.png"));
await sharp(Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024"><rect width="1024" height="1024" fill="${ink}"/></svg>`)).png().toFile(join(out, "icon-background.png"));
await sharp(Buffer.from(splash(false))).png().toFile(join(out, "splash.png"));
await sharp(Buffer.from(splash(true))).png().toFile(join(out, "splash-dark.png"));
console.log("resources/ ready");
