import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const assets = new URL('./', import.meta.url);
for (const [source, destination] of [
  ['wiscomper-hero.svg', 'wiscomper-hero.png'],
  ['visualization-flow.svg', 'wiscomper-workflow.png'],
]) {
  const result = await sharp(fileURLToPath(new URL(source, assets)), { density: 108 })
    .png({ compressionLevel: 9 })
    .toFile(fileURLToPath(new URL(destination, assets)));
  console.log(`${destination}: ${result.width} × ${result.height}, ${result.size} bytes`);
}
