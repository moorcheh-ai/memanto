# 👋 Start Here — the Inkswell sample project

Welcome. This vault is a **complete, mid-draft novel** so you can see what
Inkswell looks like in real use instead of an empty project. The book is
*[[The Lamplighter's Archive]]* — original fiction, included so the sample is
free to ship (see [licensing](#licensing)).

> [!tip] First time? Do these two things
> 1. **Enable the plugin.** Settings (⚙) → *Community plugins* → turn **off**
>    Restricted Mode → enable **Inkswell**. (A fresh vault starts in Restricted
>    Mode, so community plugins are off until you allow them.)
> 2. **Open the workspace.** Click the **pen-tip ribbon icon** on the left, or
>    run the command *"Open Inkswell projects"* (Ctrl/Cmd-P). Pick
>    **The Lamplighter's Archive** in the project selector at the top.

---

## The five-minute tour

Inkswell is one tab with a **left icon rail**, grouped into sections: **Home**,
the writing pipeline (**Plan · Write · Revise · Publish**), **Codex · Track**,
and **Search · Help** pinned at the bottom. Each stop does one job:

| Stop | What you'll see in this sample |
|------|-------------------------------|
| **Home** | The project's **hero card** — cover art, logline, theme, and a progress bar toward the 90k target — above the scene list with per-scene word counts and status colors. Click a scene to open the **Inspector** (status, POV, chapter, plotlines, characters, word target). |
| **Plan → Overview** | Novel-level planning — logline, theme, genre, audience, plus a linked **planning note** holding the synopsis, plot groundwork, and a 3-act outline. The high-level view, before anything is broken into beats or scenes. |
| **Plan → Beats** | A *Save the Cat!* beat sheet filled through the finale — early beats ticked, a couple of later ones still open. Each beat has a **+ new scene** button that creates the scene and links it to the beat. |
| **Plan → Structure** | Three views of the same scenes behind a **Tree · Board · Grid** switcher. **Tree** is the Act › Chapter › Scene **outline** — drag to reorder, with per-chapter word targets. **Board** is the same scenes as draggable status cards. **Grid** is the **Plot Grid**: a plotline × chapter matrix (The Leaking Memory, Coll & the Bureau, Mara's Grief, The Lattice) where an empty stretch is a visible pacing signal. |
| **Write** | A distraction-light Live-Preview editor that walks the manuscript in order. To-do markers (`[RESEARCH: …]`, `[NOTE: …]`, `[DIALOGUE: …]`) highlight inline — use the topbar **Insert** buttons (or `Ctrl/Cmd-Shift-T/R/D/S/N`) to drop your own, and **Log issue** to capture a fix without stopping. The right sidebar has a **Scene / Revision** switcher — **Revision** lists every marker and logged decision across the book; click one to jump. Start a **Sprint** from the Write toolbar or the status bar. |
| **Revise → Audit / Analysis** | **Audit**: the per-scene **14-point checklist** (scenes 1–2 partly audited), Story/Page project checklists, the scene-**purpose** lift-out verdict, a **scene-openings** variety strip, the **character-arc** grid (Mara is tracked from "wants nothing" to the finale), and a **style-sheet** scan. **Analysis**: readability, word-frequency, and echo reports over the prose. |
| **Revise → To-dos** | Everything left to fix in one scene-grouped worklist: every to-do marker across the manuscript (click one to jump straight to it in the editor) plus the invisible-revision **decisions** — typed & prioritized (continuity/plot-hole…) — tick one applied once you've made the change. Filter it all with one chip row. |
| **Publish → Compile / Checklist / Launch** | **Compile**: the export pipeline (groups scenes into chapters). **Checklist**: the self-publishing master checklist + the **book-metadata worksheet** (both partly filled). **Launch**: the **pre-order timeline** (release date + Medium strategy → computed milestone dates) and budget/cover/marketing/ARC trackers. |
| **Codex** | The story bible: characters, locations, a world, a concept, and a faction. Open **Mara Vance** — her **Appears in** list finds every scene that names her automatically, and clicking one opens that scene in **Write** at the first mention. Every entry is **scoped to the series** *The Lattice Cycle* (its **Scope** field), so it follows the book across the cycle but won't clutter an unrelated project. |
| **Track** | Word-goal rings, a writing-history chart, a 26-week heatmap, streaks, sprint stats, and a **By chapter** breakdown against the per-chapter targets. A **deadline** is set, so Project targets shows a **pace verdict** and the draft-milestone zone. Set today's **mood** in Goals. |
| **Search** | Full-text search across every scene's prose and synopsis. Pick the scope — this draft, the whole story, the series, or the vault — and narrow with status/POV/chapter/plotline/character filters. Click a hit to jump to it in Write, where it flashes. |

> [!tip] Too many surfaces?
> Any optional feature — Beats, Board, Plot Grid, the Revise Audit/Analysis
> tabs, the Publishing checklist/Launch planner, or the Write writing-prompts
> button — can be turned off in **Settings → Features** (or right-click a tab and
> *Hide*). It's completely lossless: hiding only stops rendering, your notes and
> stored data are untouched, and re-enabling brings everything back.

---

## How the sample maps to the data

Nothing here is magic — it's all plain Markdown you can inspect:

- **The project** is defined by the `longform:` and `inkswell:` frontmatter on
  [[The Lamplighter's Archive]] (the index note). That one block declares the
  scene order, the word target, the overview, the beat sheet, the **acts /
  chapters / plotlines** structure, the compile recipe, the series, and the
  revision log.
- **The project has two drafts.** Both index notes share the same
  `longform.title`, so Inkswell groups them into one *story* with a **draft
  switcher** at the top of the project. The main book is the first draft (its
  scenes live in `Draft 1/`); a short **Second Draft** stub lives in
  `Drafts/Second Draft/Scenes/` purely to show the feature. Story-level metadata
  (cover, logline, goals, series) is shared from the first draft — each draft
  just carries its own scene set, word counts, and Search scope.
- **Each scene** lives in [Draft 1/](Writing/The%20Lamplighter's%20Archive/Draft%201/) with flat frontmatter:
  `status`, `pov`, `chapter`, `act`, `plotlines`, `characters`, `location`,
  `targetWords`. Those fields drive the colors, the Inspector, the Outline and
  Plot Grid, and the Track tallies. The Plot Grid and Outline are pure
  projections of these — a scene joins a plotline or chapter just by naming it,
  so the views can never drift from the manuscript.
- **Codex entries** in [Codex/](Writing/Codex/) are just notes carrying a `codex:` key.
  Scenes link to them with ordinary `[[wikilinks]]` in their `characters` /
  `location` fields, and the Codex panel finds the references automatically.
  Each entry here also carries `codex-series: The Lattice Cycle`, which **scopes**
  it to that series — it shows in pickers for every book in the cycle but is hidden
  from unrelated projects. (Use `codex-project: "[[Book]]"` to scope to a single
  book, or leave both off to share an entry globally. New entries inherit the
  active project's scope automatically; folder location is just tidy storage —
  the tag is what controls visibility.)
- **Sprint and daily-word history** is *not* in these notes — it lives in the
  plugin's `data.json`. That's why it travels with this vault but wouldn't travel
  with a loose folder of chapters.

## Try editing something

The fastest way to feel the loop:

1. Go to **Write**, open scene **02 – What the Light Remembers**, and add a
   sentence. The status-bar word count for today goes up immediately.
2. Open **Track** — today's ring and the history chart reflect your new words.
3. On **Home**, change a scene's status in the Inspector and watch the color and
   the Track → Structure tally update.

> [!warning] About the dates in Track
> The seeded writing history is anchored to **June 2026**, so the *Today / Week /
> Month* rings and the current-streak read "live" around then. Opening this vault
> much later is harmless — the **history chart, heatmap, and sprint list still
> render** — but the rings reset because there are no entries for the real
> current date. Write a few words (step 1 above) and today's ring fills back in.
> Also note the seeded "today" is a **Monday**, so the Week ring starts fresh.

## Licensing

*The Lamplighter's Archive* and all Codex entries here are **original work**
created for this sample and distributed under the same license as the plugin.
No public-domain or third-party text is bundled, so there are no edition,
translation, or jurisdiction concerns — you can ship, fork, or rewrite it freely.
