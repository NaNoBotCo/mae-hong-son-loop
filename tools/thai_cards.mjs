// thai_cards.mjs — Thai share cards through the card library (shaped Thai, no PIL).
//   node tools/thai_cards.mjs jobs.json
// jobs.json: [{ out, title, sub, kicker, url, image (path), credit, accent }]
// The library: ~/Developer/claude code projects/cards (CARDS_LIB overrides). JPEG written with sips.
import { readFileSync, writeFileSync, unlinkSync, mkdirSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { homedir, tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { pathToFileURL } from 'node:url'

const lib = process.env.CARDS_LIB || join(homedir(), 'Developer/claude code projects/cards')
const { png } = await import(pathToFileURL(join(lib, 'src/node.mjs')).href)
const jobs = JSON.parse(readFileSync(process.argv[2], 'utf8'))
let n = 0
for (const j of jobs) {
  const spec = { layout: j.image ? 'photo' : 'plain', title: j.title, sub: j.sub || '', kicker: j.kicker || '', url: j.url || '',
    accent: j.accent || '#ff3b2f', font: 'prompt', lang: 'th', credit: j.credit || '' }
  if (j.image) spec.image = { bytes: new Uint8Array(readFileSync(j.image)) }
  const r = await png(spec)
  const tmp = join(tmpdir(), `thai-card-${process.pid}.png`)
  writeFileSync(tmp, r.png)
  mkdirSync(dirname(j.out), { recursive: true })
  const s = spawnSync('sips', ['-s', 'format', 'jpeg', '-s', 'formatOptions', '86', tmp, '--out', j.out], { encoding: 'utf8' })
  unlinkSync(tmp)
  if (s.status) { console.error('sips failed', j.out, s.stderr); process.exit(1) }
  n++
}
console.log(`thai cards: ${n}`)
