# 🌸 CryptoMiko: HODL Tycoon

A complete, single-file, kawaii-anime **crypto idle-tycoon** for the browser.
From one cracked laptop in a bedroom to an interplanetary blockchain empire —
one adorable Miko Operator at a time.

## ▶️ How to play

Open **`index.html`** in any modern browser. That's it — no build step, no
server, no external assets. Your progress autosaves to `localStorage` and
resumes exactly where you left off, including offline earnings while the tab
was closed.

> Tip: for the full experience (audio needs a user gesture), just tap anything
> once after loading.

## 🎮 What's inside

| System | Inspired by | How it works here |
|---|---|---|
| Tap-to-earn rigs, bulk buy x1/x10/x25/MAX, milestone multipliers | AdVenture Capitalist | 10 rigs on Genesis Chain, cost curve 1.12ⁿ |
| Shared regenerating **⚡ Energy** buys every rig | AdVenture Communist | one resource-allocation puzzle across all coin tracks |
| 3-stage internal bottleneck: **Hash / Bandwidth / Cold Wallet** | Idle Miner Tycoon | color-coded green/yellow/red indicator per rig |
| **Miko Operators** (managers) + timed burst abilities + Whale Accountant upgrades | AdCap managers/accountants | accountants cost Diamond Hands and are wiped on prestige |
| **Diamond Hands ◈** prestige (`sqrt(lifetime/K)`), +2%/◈ forever, prestige shop | AdCap Angel Investors | spending ◈ lowers your bonus — real decisions |
| Offline earnings, capped 2h → 24h via research; unmanaged rigs earn nothing | Idle Miner Tycoon | Miko-chan is free on rig #1 so new players never bounce |
| **Blockchain Lab** research tree paid with 🔬 shards from achievements only | Idle Miner Tycoon | 4 branches: Profit / Automation / Offline / Energy |
| Daily tasks, chain milestones, 100+ achievement wall, **Energy Sprint** optimization puzzle | — | there is always at least one active decision available |
| **Pump Events**: simulated 60h live events, Meme Reactor, "Pump the Chart" tap frenzy, exclusive skin | live-ops tycoons | deterministic epoch schedule, no backend needed |
| Collectible Operator **skins** with stat bonuses (Mystery Wallet gacha, gems earned in-game only) | AdCap outfits | no real-money anything |
| Golden Candle 📈 | AdCap golden angel | rare flying tap bonus: ×7 boost, energy, or gems |

Chains 2–5 (StakeShiba, MoonOre, NeoYen, QuantumCoin) are visible on the
Chains tab with live unlock progress, shipped as locked coming-soon economies.

## 💾 Saves

- Versioned JSON in `localStorage` (`cryptomiko_save_v1`) with a migration stub
- Autosave every 10s + on every purchase + on tab hide/close
- Export/Import as a Base64 string from ⚙️ Settings
- Full wipe requires typing `RESET`

## 🧪 Testing

Headless Playwright suite (22 checks: economy math, bottleneck clamping,
prestige formula, save/reload with backdated timestamp → offline cap payout,
big-number formatting, event minigame) was run against the file with Chromium.
The game loop is fixed-tick and wall-clock based, so simulation stays accurate
in throttled background tabs.

## 🛠️ Tech

Single self-contained HTML file: inline CSS, inline vanilla JS, inline SVG art
(all characters and rigs are hand-built vectors — zero external requests),
Web Audio API synth for all SFX plus a generative lo-fi music loop, and a
mantissa/exponent big-number class so numbers never hit `Infinity`
(K, M, B, T, Qa, Qi, Sx … suffixes, AdCap style).
