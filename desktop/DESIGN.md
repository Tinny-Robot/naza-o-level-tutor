# O-Level AI Tutor - Design System (ADTC 2026)

Premium dark-mode desktop learning UI for Nigerian teens (14-19). Inspired by Cursor, Linear, Spotify, and ChatGPT Desktop - original product language for offline O-Level tutoring.

**Stitch project:** [628528694332230301](https://stitch.withgoogle.com/projects/628528694332230301)  
Account used for generation: `handanfoun@gmail.com`

## Emotional goals

Students should feel excited, curious, motivated, and productive - like an AI companion, not an LMS. First 5 seconds: “Whoa, this is cool.”

## Color tokens

| Token | Hex | Use |
|-------|-----|-----|
| Primary Electric Blue | `#3B82F6` | CTAs, active nav, rings |
| Secondary Royal Purple | `#7C3AED` | General mode, accents |
| Accent Cyan | `#22D3EE` | Offline badges, highlights |
| Success Emerald | `#10B981` | Correct / streak |
| Warning Amber | `#F59E0B` | Achievements |
| Error Soft Red | `#F87171` | Wrong answers |
| Background | `#0B0F19` | App canvas |
| Panel | `#121826` | Sidebar |
| Card | `#1A2234` | Elevated surfaces |
| Text | `#F8FAFC` | Primary text |
| Muted | `#94A3B8` | Secondary text |

## Typography

- **Display / headings:** Sora (geometric, confident)
- **Body:** Hanken Grotesk
- **Code:** JetBrains Mono

Do not use Inter, Roboto, or Arial as the brand face.

## Layout shell

- Left sidebar (~260px): logo, nav, offline pill
- Top command bar: search / Cmd+K affordance, streak, offline
- Center workspace: routed pages
- AI Tutor optional right sources panel (~300px)

## Motion

- Page transitions: soft fade + 12px rise (Framer Motion)
- Staggered cards on Home / Achievements
- Hover lift on cards (+3px)
- Quiz answer selection feedback
- Respect `prefers-reduced-motion`

Avoid noisy parallax or childish confetti. Celebrations stay premium (badge unlock, XP tint).

## Screens

| Route | Purpose |
|-------|---------|
| `/` | Learning hub: plan, recommend, weak topics, streak |
| `/tutor` | Chat + sole Lesson Mode experience + citations/images |
| `/practice` | Adaptive WAEC/NECO practice (not timed) |
| `/exams` | CBT Mock Exams (WAEC/NECO/JAMB-style) |
| `/progress` | Mastery analytics (no XP gamification) |

Settings live in a CommandBar modal. Achievements / Profile / standalone Lesson / Revision nav removed.

## Stitch exports

HTML snapshots live in `desktop/stitch/` (home, lesson, quiz, revision, progress, achievements, ai-tutor).

## Implementation notes

- Vite + React + TypeScript
- Tutor is live-local via FastAPI (`POST http://127.0.0.1:8010/chat` → `GenerationPipeline.ask`); client-side typewriter reveal of the real answer
- Offline-first messaging throughout; only HTTP to `127.0.0.1` / `localhost` - no cloud AI in the UI
