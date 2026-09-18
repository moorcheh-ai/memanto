---
longform:
  format: scenes
  title: The Lamplighter's Archive
  draftTitle: First Draft
  sceneFolder: Draft 1
  scenes:
    - 01 - The Last Lamp on Vesper Row
    - 02 - What the Light Remembers
    - 03 - Inspector Coll
    - 04 - The Undercroft
    - 05 - A Memory Not Her Own
    - 06 - The Archivist's Bargain
    - 07 - Blackout
    - 08 - What the Dark Remembers
  ignoredFiles: []
inkswell:
  series:
    name: The Lattice Cycle
    order: 1
  goals:
    target: 90000
    deadline: 2026-09-01
    daysPerWeek: 5
  overview:
    logline: A lamplighter who tends a sleeping city's memory-lamps lights one that shows her a life she never lived — and follows it down into the sealed Archive the city has spent a generation forgetting.
    theme: What a city chooses to remember, and what it costs to be the one who carries it.
    genre: Gaslamp fantasy
    audience: Readers of cozy-but-eerie gaslamp fantasy with a quiet, competent heroine — Piranesi by way of a lamplighter's round.
    cover: Writing/The Lamplighter's Archive/cover.svg
    planningNote: Writing/The Lamplighter's Archive/The Lamplighter's Archive — Plan.md
  compile:
    version: 2
    sceneSteps:
      - id: strip-frontmatter
        options: {}
      - id: remove-comments
        options: {}
      - id: flatten-links
        options: {}
      - id: group-by-chapter
        options:
          level: 1
          sceneBreak: "* * *"
    manuscriptSteps:
      - id: trim-blank-lines
        options: {}
    separator: "\n\n"
    targetBasename: Lamplighter - manuscript
    format: md
  beats:
    template: save-the-cat
    assignments:
      opening-image:
        scenes:
          - 01 - The Last Lamp on Vesper Row
        note: Mara lights the last lamp on her route as the district sleeps — the city's memory kept safe for one more night.
        done: true
      theme-stated:
        note: 'A line from her mother: "Some things are only true while someone remembers them."'
        done: true
      setup:
        scenes:
          - 01 - The Last Lamp on Vesper Row
          - 02 - What the Light Remembers
        note: Establish the Lattice, the lamplighter's trade, and Mara's quiet, unambitious life.
        done: true
      catalyst:
        scenes:
          - 02 - What the Light Remembers
        note: A lamp shows Mara a memory that cannot be hers — a room she has never entered.
        done: true
      debate:
        scenes:
          - 03 - Inspector Coll
        note: Report the anomaly and stay safe, or keep it secret and chase it? Coll's arrival forces the question.
      break-into-2:
        scenes:
          - 04 - The Undercroft
        note: Mara descends into the sealed Undercroft to find where stray memories drain to.
      midpoint:
        scenes:
          - 05 - A Memory Not Her Own
        note: False victory — she finds the Archive, and learns it has been waiting for someone who can read it.
      all-is-lost:
        scenes:
          - 07 - Blackout
        note: The district goes dark. Every lamp on Vesper Row is wiped at once.
      dark-night-of-the-soul:
        note: The blackout took the one memory Mara had gone down to protect. If the Archive can be wiped, nothing she loves is safe in it — including the thing she buried there.
      break-into-3:
        scenes:
          - 08 - What the Dark Remembers
        note: Mara stops trying to save the row and chooses to remember it instead — reading herself into the Archive so the erased days have somewhere to live.
      finale:
        scenes:
          - 08 - What the Dark Remembers
        note: She relights Vesper Row from the Archive's own store, giving the district back its day — and keeps, awake, the one memory she'd spent years not carrying.
      final-image:
        note: Mara lights the last lamp again — but now she is the Archive's reader, and the row remembers her too.
  acts:
    - id: act-1
      title: Act I
    - id: act-2
      title: Act II
    - id: act-3
      title: Act III
  chapters:
    - id: ch-1
      title: One
      actId: act-1
      targetWords: 3000
    - id: ch-2
      title: Two
      actId: act-1
      targetWords: 1500
    - id: ch-3
      title: Three
      actId: act-2
      targetWords: 3600
    - id: ch-4
      title: Four
      actId: act-2
      targetWords: 1700
    - id: ch-5
      title: Five
      actId: act-3
      targetWords: 1500
    - id: ch-6
      title: Six
      actId: act-3
      targetWords: 1600
  plotlines:
    - id: pl-memory
      title: The Leaking Memory
      color: "#6B9BD1"
    - id: pl-bureau
      title: Coll & the Bureau
      color: "#C65D5D"
    - id: pl-grief
      title: Mara's Grief
      color: "#9B72C4"
    - id: pl-lattice
      title: The Lattice
      color: "#4FA88B"
  revisions:
    - id: rev-lamplight-stores
      text: From now on, lamplight stores memory — it doesn't merely illuminate. Treat earlier "light" references as retroactively true.
      scene: 02 - What the Light Remembers
      status: applied
      created: 2026-03-14T09:12:00.000Z
      type: continuity
      priority: high
    - id: rev-coll-knows-mara
      text: From now on, Inspector Coll already knew Mara years ago, from before the Undercroft was sealed. EDIT
      scene: 03 - Inspector Coll
      status: pending
      created: 2026-05-02T18:40:00.000Z
      type: character
      priority: med
    - id: rev-archive-sentient
      text: The Archive is sentient. Assume every reference to it implies intent, not just storage.
      scene:
      status: pending
      created: 2026-06-10T20:05:00.000Z
      type: continuity
      priority: high
    - id: rev-blackout-mechanism
      text: Why does the blackout wipe every lamp on Vesper Row at once? Seed a mechanism earlier or it's a plot hole.
      scene: 07 - Blackout
      status: pending
      created: 2026-06-18T11:20:00.000Z
      type: plot-hole
      priority: high
    - id: rev-undercroft-terms
      text: Look up period drainage/sub-cellar terminology for the Undercroft description. [RESEARCH]
      scene: 04 - The Undercroft
      status: pending
      created: 2026-06-20T08:00:00.000Z
      type: research
      priority: low
  revisionChecklist:
    story:
      structure:
        done: true
      stakes:
        done: true
      heroTransforms:
        note: Mara goes from wanting nothing to claiming the Archive — verify the turn lands by scene 5/6.
      consistent:
        note: Reconcile lamplight-stores-memory rule across early scenes.
    page:
      echoes:
        done: true
      adverbs:
        note: Sweep -ly adverbs in dialogue tags during the line pass.
  arcTracked:
    - "[[Mara Vance]]"
  styleSheet:
    entries:
      - id: s-lattice
        canonical: Lattice
        variants:
          - lattice
        kind: name
        note: The memory-network is always capitalized.
      - id: s-undercroft
        canonical: Undercroft
        variants:
          - undercroft
        kind: name
  publishing:
    metadata:
      title: The Lamplighter's Archive
      seriesTitle: The Lattice Cycle
      tagline: She lights the lamps that keep a city's memory — until one shows her a life she never lived.
      blurb: In a city that pours each day into its street-lamps, Mara Vance is content to tend her small route and want nothing. Then a lamp shows her a memory that was never hers, and the trail leads down into the sealed Archive the city has spent a generation forgetting.
      genre: Fantasy
      subgenres:
        - Gaslamp fantasy
        - Mystery
      targetReader: Readers of cozy-but-eerie gaslamp fantasy with a quiet, competent heroine.
      keywords:
        - gaslamp fantasy
        - memory magic
        - lamplighter
        - hidden archive
        - slow burn mystery
        - sentient magic
        - found family
      categories:
        main: FICTION / Fantasy / Historical
        sub:
          - FICTION / Fantasy / Gaslamp
          - FICTION / Mystery & Detective
      kuExclusive: true
      formats:
        ebook:
          enabled: true
          price: 4.99
        paperback:
          enabled: true
          price: 14.99
    checklist:
      writing:
        draft:
          done: true
          notes: First draft in progress.
      editing:
        selfEdit:
          done: true
      foundational:
        genre:
          done: true
        targetReader:
          done: true
    launch:
      releaseDate: 2026-09-01
      strategy: medium
      milestones:
        submit:
          done: false
    budget:
      items:
        - id: p-mqtp8n9n-aar6
          label: Cover art
          category: want
          estimate: 500
---

# The Lamplighter's Archive

> *Book One of [[Aszmar|The Lattice Cycle]].*

This is the **project index** — Inkswell reads the `longform` and `inkswell`
blocks above to assemble the project. You normally never edit this by hand;
the panels (Plan, Write, Track, Publish) write to it for you.

Open the **Inkswell** view (pen-tool ribbon icon, or the command
*"Open Inkswell projects"*) and this project will be listed. New here? Start
with [[_Start Here]].

## Logline

A lamplighter who tends the memory-lamps of a sleeping city lights one that
shows her a memory she never lived — and follows it down into the sealed Archive
the city has spent a generation pretending to forget.
