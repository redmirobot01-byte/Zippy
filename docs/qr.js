/* Zippy VPN — Self-contained ISO/IEC 18004 QR Code SVG Generator (ECC-L, v1..v20)
 * Zero external requests: works 100% offline and on restricted mobile networks.
 */
(function (global) {
  "use strict";

  // Total codewords, EC codewords per block, [group1Blocks, group1DataCw, group2Blocks, group2DataCw] for ECC Level L (versions 1..20)
  const VERSION_TABLE_L = [
    null,
    [26, 7, 1, 19, 0, 0],
    [44, 10, 1, 34, 0, 0],
    [70, 15, 1, 55, 0, 0],
    [100, 20, 1, 80, 0, 0],
    [134, 26, 1, 108, 0, 0],
    [172, 18, 2, 68, 0, 0],
    [196, 20, 2, 78, 0, 0],
    [242, 24, 2, 97, 0, 0],
    [292, 30, 2, 116, 0, 0],
    [346, 18, 2, 68, 2, 69],
    [404, 20, 4, 81, 0, 0],
    [466, 24, 2, 92, 2, 93],
    [532, 26, 4, 107, 0, 0],
    [581, 30, 3, 115, 1, 116],
    [655, 22, 5, 87, 1, 88],
    [733, 24, 5, 98, 1, 99],
    [815, 28, 1, 107, 5, 108],
    [901, 30, 5, 120, 1, 121],
    [991, 28, 3, 113, 4, 114],
    [1085, 28, 3, 107, 5, 108],
  ];

  const ALIGNMENT_POS = [
    [],
    [],
    [6, 18],
    [6, 22],
    [6, 26],
    [6, 30],
    [6, 34],
    [6, 22, 38],
    [6, 24, 42],
    [6, 26, 46],
    [6, 28, 50],
    [6, 30, 54],
    [6, 32, 58],
    [6, 34, 62],
    [6, 26, 46, 66],
    [6, 26, 48, 70],
    [6, 26, 50, 74],
    [6, 30, 54, 78],
    [6, 30, 56, 82],
    [6, 30, 58, 86],
    [6, 34, 62, 90],
  ];

  // GF(256) log/exp tables with polynomial 0x11d
  const GF_EXP = new Uint8Array(512);
  const GF_LOG = new Uint8Array(256);
  (function initGF() {
    let x = 1;
    for (let i = 0; i < 255; i++) {
      GF_EXP[i] = x;
      GF_LOG[x] = i;
      x <<= 1;
      if (x & 0x100) x ^= 0x11d;
    }
    for (let i = 255; i < 512; i++) GF_EXP[i] = GF_EXP[i - 255];
  })();

  function gfMul(a, b) {
    if (a === 0 || b === 0) return 0;
    return GF_EXP[GF_LOG[a] + GF_LOG[b]];
  }

  function rsGeneratorPoly(degree) {
    let poly = [1];
    for (let i = 0; i < degree; i++) {
      const next = new Array(poly.length + 1).fill(0);
      for (let j = 0; j < poly.length; j++) {
        next[j] ^= poly[j];
        next[j + 1] ^= gfMul(poly[j], GF_EXP[i]);
      }
      poly = next;
    }
    return poly;
  }

  function rsRemainder(data, ecLen) {
    const gen = rsGeneratorPoly(ecLen);
    const rem = new Uint8Array(ecLen);
    for (let i = 0; i < data.length; i++) {
      const factor = data[i] ^ rem[0];
      rem.copyWithin(0, 1);
      rem[ecLen - 1] = 0;
      for (let j = 0; j < ecLen; j++) {
        rem[j] ^= gfMul(gen[j + 1], factor);
      }
    }
    return rem;
  }

  function chooseVersion(byteLen) {
    for (let v = 1; v <= 20; v++) {
      const info = VERSION_TABLE_L[v];
      const dataCapBytes = info[2] * info[3] + info[4] * info[5];
      const headerBits = 4 + (v <= 9 ? 8 : 16);
      const maxBytes = Math.floor((dataCapBytes * 8 - headerBits) / 8);
      if (byteLen <= maxBytes) return v;
    }
    return 0;
  }

  function encodeData(bytes, version) {
    const info = VERSION_TABLE_L[version];
    const ecLen = info[1];
    const g1Blocks = info[2];
    const g1Cw = info[3];
    const g2Blocks = info[4];
    const g2Cw = info[5];
    const totalDataCw = g1Blocks * g1Cw + g2Blocks * g2Cw;

    const bits = [];
    const pushBits = (val, len) => {
      for (let i = len - 1; i >= 0; i--) bits.push((val >>> i) & 1);
    };

    // Byte mode indicator 0100
    pushBits(0b0100, 4);
    pushBits(bytes.length, version <= 9 ? 8 : 16);
    for (let i = 0; i < bytes.length; i++) pushBits(bytes[i], 8);

    const capBits = totalDataCw * 8;
    const term = Math.min(4, capBits - bits.length);
    pushBits(0, term);
    while (bits.length % 8 !== 0) bits.push(0);

    const dataCw = new Uint8Array(totalDataCw);
    for (let i = 0; i < bits.length / 8; i++) {
      let b = 0;
      for (let j = 0; j < 8; j++) b = (b << 1) | bits[i * 8 + j];
      dataCw[i] = b;
    }
    let padIdx = bits.length / 8;
    let toggle = true;
    while (padIdx < totalDataCw) {
      dataCw[padIdx++] = toggle ? 0xec : 0x11;
      toggle = !toggle;
    }

    // Split into blocks & compute Reed-Solomon EC codewords
    const dataBlocks = [];
    const ecBlocks = [];
    let offset = 0;
    for (let i = 0; i < g1Blocks; i++) {
      const blk = dataCw.slice(offset, offset + g1Cw);
      offset += g1Cw;
      dataBlocks.push(blk);
      ecBlocks.push(rsRemainder(blk, ecLen));
    }
    for (let i = 0; i < g2Blocks; i++) {
      const blk = dataCw.slice(offset, offset + g2Cw);
      offset += g2Cw;
      dataBlocks.push(blk);
      ecBlocks.push(rsRemainder(blk, ecLen));
    }

    // Interleave data and EC blocks
    const result = [];
    const maxDataLen = Math.max(g1Cw, g2Cw);
    for (let i = 0; i < maxDataLen; i++) {
      for (let b = 0; b < dataBlocks.length; b++) {
        if (i < dataBlocks[b].length) result.push(dataBlocks[b][i]);
      }
    }
    for (let i = 0; i < ecLen; i++) {
      for (let b = 0; b < ecBlocks.length; b++) {
        result.push(ecBlocks[b][i]);
      }
    }
    return result;
  }

  function buildBaseMatrix(version) {
    const size = version * 4 + 17;
    const modules = Array.from({ length: size }, () => new Uint8Array(size));
    const isFunc = Array.from({ length: size }, () => new Uint8Array(size));

    const setFunc = (x, y, dark) => {
      if (x < 0 || y < 0 || x >= size || y >= size) return;
      modules[y][x] = dark ? 1 : 0;
      isFunc[y][x] = 1;
    };

    const drawFinder = (cx, cy) => {
      for (let dy = -4; dy <= 4; dy++) {
        for (let dx = -4; dx <= 4; dx++) {
          const dist = Math.max(Math.abs(dx), Math.abs(dy));
          setFunc(cx + dx, cy + dy, dist !== 2 && dist !== 4);
        }
      }
    };

    const drawAlignment = (cx, cy) => {
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          setFunc(cx + dx, cy + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
        }
      }
    };

    // Timing patterns
    for (let i = 0; i < size; i++) {
      setFunc(6, i, i % 2 === 0);
      setFunc(i, 6, i % 2 === 0);
    }

    // Three finder patterns
    drawFinder(3, 3);
    drawFinder(size - 4, 3);
    drawFinder(3, size - 4);

    // Alignment patterns
    const pos = ALIGNMENT_POS[version];
    for (let i = 0; i < pos.length; i++) {
      for (let j = 0; j < pos.length; j++) {
        if (
          (i === 0 && j === 0) ||
          (i === 0 && j === pos.length - 1) ||
          (i === pos.length - 1 && j === 0)
        ) {
          continue;
        }
        drawAlignment(pos[i], pos[j]);
      }
    }

    // Reserve format bits
    for (let i = 0; i <= 8; i++) {
      if (i !== 6) {
        setFunc(8, i, false);
        setFunc(i, 8, false);
      }
    }
    for (let i = 0; i < 8; i++) {
      setFunc(size - 1 - i, 8, false);
      setFunc(8, size - 1 - i, false);
    }
    setFunc(8, size - 8, true); // Dark module

    // Version info for v >= 7
    if (version >= 7) {
      let rem = version;
      for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
      const bits = (version << 12) | rem;
      for (let i = 0; i < 18; i++) {
        const bit = ((bits >>> i) & 1) !== 0;
        const a = size - 11 + (i % 3);
        const b = Math.floor(i / 3);
        setFunc(a, b, bit);
        setFunc(b, a, bit);
      }
    }

    return { size, modules, isFunc };
  }

  function drawFormatBits(modules, isFunc, size, mask) {
    // ECC Level L format indicator = 01
    const data = (0b01 << 3) | mask;
    let rem = data;
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
    const bits = ((data << 10) | rem) ^ 0x5412;
    const bit = (i) => ((bits >>> i) & 1) ? 1 : 0;

    for (let i = 0; i <= 5; i++) modules[i][8] = bit(i);
    modules[7][8] = bit(6);
    modules[8][8] = bit(7);
    modules[8][7] = bit(8);
    for (let i = 9; i < 15; i++) modules[8][14 - i] = bit(i);

    for (let i = 0; i < 8; i++) modules[8][size - 1 - i] = bit(i);
    for (let i = 8; i < 15; i++) modules[size - 15 + i][8] = bit(i);
    modules[size - 8][8] = 1;
    void isFunc;
  }

  function placeCodewords(modules, isFunc, size, codewords) {
    let bitIdx = 0;
    const totalBits = codewords.length * 8;
    for (let right = size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5;
      for (let vert = 0; vert < size; vert++) {
        for (let j = 0; j < 2; j++) {
          const x = right - j;
          const upward = ((right + 1) & 2) === 0;
          const y = upward ? size - 1 - vert : vert;
          if (!isFunc[y][x] && bitIdx < totalBits) {
            const cw = codewords[bitIdx >>> 3];
            modules[y][x] = (cw >>> (7 - (bitIdx & 7))) & 1;
            bitIdx++;
          }
        }
      }
    }
  }

  function maskBit(mask, x, y) {
    switch (mask) {
      case 0: return (x + y) % 2 === 0;
      case 1: return y % 2 === 0;
      case 2: return x % 3 === 0;
      case 3: return (x + y) % 3 === 0;
      case 4: return (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0;
      case 5: return ((x * y) % 2) + ((x * y) % 3) === 0;
      case 6: return (((x * y) % 2) + ((x * y) % 3)) % 2 === 0;
      case 7: return (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
      default: return false;
    }
  }

  function cloneGrid(grid) {
    return grid.map((row) => new Uint8Array(row));
  }

  function penaltyScore(m, size) {
    let score = 0;
    // Rule 1: runs of >= 5
    for (let y = 0; y < size; y++) {
      let run = 1;
      for (let x = 1; x < size; x++) {
        if (m[y][x] === m[y][x - 1]) {
          run++;
          if (run === 5) score += 3;
          else if (run > 5) score += 1;
        } else run = 1;
      }
    }
    for (let x = 0; x < size; x++) {
      let run = 1;
      for (let y = 1; y < size; y++) {
        if (m[y][x] === m[y - 1][x]) {
          run++;
          if (run === 5) score += 3;
          else if (run > 5) score += 1;
        } else run = 1;
      }
    }
    // Rule 2: 2x2 blocks
    for (let y = 0; y < size - 1; y++) {
      for (let x = 0; x < size - 1; x++) {
        const c = m[y][x];
        if (c === m[y][x + 1] && c === m[y + 1][x] && c === m[y + 1][x + 1]) {
          score += 3;
        }
      }
    }
    return score;
  }

  function renderQrSvg(text, quietZone) {
    const border = typeof quietZone === "number" ? quietZone : 3;
    const bytes = new TextEncoder().encode(String(text || ""));
    const version = chooseVersion(bytes.length);
    if (!version) return null;

    const codewords = encodeData(bytes, version);
    const base = buildBaseMatrix(version);
    placeCodewords(base.modules, base.isFunc, base.size, codewords);

    let bestGrid = null;
    let bestScore = Infinity;
    for (let mask = 0; mask < 8; mask++) {
      const grid = cloneGrid(base.modules);
      for (let y = 0; y < base.size; y++) {
        for (let x = 0; x < base.size; x++) {
          if (!base.isFunc[y][x] && maskBit(mask, x, y)) {
            grid[y][x] ^= 1;
          }
        }
      }
      drawFormatBits(grid, base.isFunc, base.size, mask);
      const sc = penaltyScore(grid, base.size);
      if (sc < bestScore) {
        bestScore = sc;
        bestGrid = grid;
      }
    }

    const total = base.size + border * 2;
    const parts = [];
    for (let y = 0; y < base.size; y++) {
      for (let x = 0; x < base.size; x++) {
        if (bestGrid[y][x]) {
          parts.push(`M${x + border},${y + border}h1v1h-1z`);
        }
      }
    }

    return (
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${total} ${total}" ` +
      `shape-rendering="crispEdges" role="img" aria-label="QR kod">` +
      `<rect width="100%" height="100%" fill="#ffffff"/>` +
      `<path d="${parts.join("")}" fill="#090d16"/></svg>`
    );
  }

  global.ZippyQR = { renderSvg: renderQrSvg };
})(window);
