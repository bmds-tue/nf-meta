import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Read pyproject.toml
const pyprojectPath = path.join(__dirname, '../../../../../', 'pyproject.toml');
const content = fs.readFileSync(pyprojectPath, 'utf-8');

// Extract version
const match = content.match(/version\s*=\s*"([^"]+)"/);
const version = match ? match[1] : '0.0.0';

// Write to a constant file
const outputPath = path.join(__dirname, '../src/version.ts');
fs.writeFileSync(outputPath, `export const APP_VERSION = '${version}';\n`);