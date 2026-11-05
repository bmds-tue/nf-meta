import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// The version of the [project] table in pyproject.toml (not e.g. ruff's target-version)
const pyprojectPath = path.join(__dirname, '../../../../../', 'pyproject.toml');
const content = fs.readFileSync(pyprojectPath, 'utf-8');
const project = content.match(/^\[project\]\s*$([\s\S]*?)(?=^\[)/m);
const match = project?.[1].match(/^version\s*=\s*"([^"]+)"/m);
if (!match) {
    throw new Error(`No version in the [project] table of ${pyprojectPath}`);
}

const outputPath = path.join(__dirname, '../src/version.ts');
fs.writeFileSync(outputPath, `export const APP_VERSION = '${match[1]}';\n`);
