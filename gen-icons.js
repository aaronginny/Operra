// Generates icon-192.png and icon-512.png using pure Node.js (no dependencies)
// Navy background (#0B2447) with gold "D" letter rendered via pixel-level drawing

const fs = require("fs");
const zlib = require("zlib");

function makePNG(size) {
  const navy = [11, 36, 71];
  const gold = [180, 140, 60];

  // Create pixel buffer (RGBA)
  const pixels = new Uint8Array(size * size * 4);

  // Corner radius
  const r = Math.round(size * 0.2);

  // Fill with navy + rounded corners (transparent outside)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const idx = (y * size + x) * 4;
      // Check if inside rounded rect
      let inside = true;
      if (x < r && y < r) inside = Math.hypot(x - r, y - r) <= r;
      else if (x > size - 1 - r && y < r) inside = Math.hypot(x - (size - 1 - r), y - r) <= r;
      else if (x < r && y > size - 1 - r) inside = Math.hypot(x - r, y - (size - 1 - r)) <= r;
      else if (x > size - 1 - r && y > size - 1 - r) inside = Math.hypot(x - (size - 1 - r), y - (size - 1 - r)) <= r;

      if (inside) {
        pixels[idx] = navy[0];
        pixels[idx + 1] = navy[1];
        pixels[idx + 2] = navy[2];
        pixels[idx + 3] = 255;
      } else {
        pixels[idx + 3] = 0; // transparent
      }
    }
  }

  // Draw "D" letter using a simple bitmap approach
  // Define the D shape as bezier-sampled fill
  const cx = size / 2;
  const fontSize = size * 0.58;
  const baseline = size * 0.68;

  // D glyph: left vertical bar + right curved part
  // Left stem
  const stemX = cx - fontSize * 0.28;
  const stemW = fontSize * 0.14;
  const topY = baseline - fontSize * 0.78;
  const botY = baseline;

  // Draw every pixel and test if inside the D glyph
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const idx = (y * size + x) * 4;
      if (pixels[idx + 3] === 0) continue; // skip transparent (outside rounded corners)

      const fy = y; // pixel y
      const fx = x; // pixel x

      // Is this pixel inside the "D" shape?
      let inD = false;

      if (fy >= topY && fy <= botY) {
        const t = (fy - topY) / (botY - topY); // 0..1 top to bottom
        // Left stem
        if (fx >= stemX && fx <= stemX + stemW) {
          inD = true;
        }
        // Right bulge: ellipse
        // Center of ellipse shifts slightly: widest at middle
        const bulgeDepth = fontSize * 0.38 * Math.sin(Math.PI * t);
        const bulgeRight = stemX + stemW + bulgeDepth;
        const innerEdge = stemX + stemW;
        if (fx > innerEdge && fx <= bulgeRight && fy >= topY && fy <= botY) {
          // Check it's within the outer arc
          const midY = (topY + botY) / 2;
          const halfH = (botY - topY) / 2;
          const normY = (fy - midY) / halfH; // -1..1
          // Outer ellipse at this y: x extent = stemX+stemW to stemX+stemW+maxBulge*sin
          const maxBulge = fontSize * 0.38;
          const outerX = stemX + stemW + maxBulge * Math.sqrt(1 - normY * normY);
          if (fx <= outerX) inD = true;
        }
        // Top/bottom horizontal bars (serifs)
        const barH = fontSize * 0.1;
        if ((fy <= topY + barH || fy >= botY - barH) && fx >= stemX && fx <= stemX + stemW + fontSize * 0.15) {
          inD = true;
        }
      }

      if (inD) {
        pixels[idx] = gold[0];
        pixels[idx + 1] = gold[1];
        pixels[idx + 2] = gold[2];
        pixels[idx + 3] = 255;
      }
    }
  }

  // Encode as PNG
  return encodePNG(pixels, size, size);
}

function encodePNG(pixels, width, height) {
  // PNG signature
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

  // IHDR chunk
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;  // bit depth
  ihdr[9] = 6;  // color type RGBA
  ihdr[10] = 0; // compression
  ihdr[11] = 0; // filter
  ihdr[12] = 0; // interlace
  const ihdrChunk = makeChunk("IHDR", ihdr);

  // IDAT chunk: filter + compress
  const raw = Buffer.alloc(height * (1 + width * 4));
  for (let y = 0; y < height; y++) {
    raw[y * (1 + width * 4)] = 0; // filter type None
    for (let x = 0; x < width; x++) {
      const src = (y * width + x) * 4;
      const dst = y * (1 + width * 4) + 1 + x * 4;
      raw[dst] = pixels[src];
      raw[dst + 1] = pixels[src + 1];
      raw[dst + 2] = pixels[src + 2];
      raw[dst + 3] = pixels[src + 3];
    }
  }
  const compressed = zlib.deflateSync(raw, { level: 6 });
  const idatChunk = makeChunk("IDAT", compressed);

  // IEND chunk
  const iendChunk = makeChunk("IEND", Buffer.alloc(0));

  return Buffer.concat([sig, ihdrChunk, idatChunk, iendChunk]);
}

function makeChunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeB = Buffer.from(type, "ascii");
  const crcBuf = Buffer.concat([typeB, data]);
  const crcVal = crc32(crcBuf);
  const crcOut = Buffer.alloc(4);
  crcOut.writeInt32BE(crcVal, 0);
  return Buffer.concat([len, typeB, data, crcOut]);
}

function crc32(buf) {
  const table = makeCRCTable();
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) {
    c = table[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  }
  return (c ^ 0xFFFFFFFF) | 0;
}

let _crcTable = null;
function makeCRCTable() {
  if (_crcTable) return _crcTable;
  _crcTable = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) {
      c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    }
    _crcTable[n] = c;
  }
  return _crcTable;
}

fs.writeFileSync("client/public/icon-192.png", makePNG(192));
console.log("icon-192.png written");
fs.writeFileSync("client/public/icon-512.png", makePNG(512));
console.log("icon-512.png written");
