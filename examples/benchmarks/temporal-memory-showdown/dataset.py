"""Synthetic long-horizon dataset with explicit temporal contradictions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryRecord:
    record_id: str
    session: int
    memory_type: str
    text: str


@dataclass(frozen=True)
class QueryCase:
    query_id: str
    category: str
    query: str
    required: tuple[tuple[str, ...], ...]
    forbidden: tuple[tuple[str, ...], ...] = ()


RECORDS: tuple[MemoryRecord, ...] = (
    MemoryRecord(
        "M001",
        1,
        "fact",
        "Asteria's greenhouse module is GH-7. The initial crop is Genovese basil.",
    ),
    MemoryRecord(
        "M002",
        1,
        "event",
        "The original launch window is August 14, 2026, from Kiruna.",
    ),
    MemoryRecord(
        "M003",
        1,
        "relationship",
        "Elena Park is mission commander. Dr. Amara Okafor owns plant science.",
    ),
    MemoryRecord(
        "M004",
        1,
        "instruction",
        "Operational alerts go to Slack channel #asteria-ops.",
    ),
    MemoryRecord(
        "M005",
        2,
        "decision",
        "The baseline nutrient recipe is N-17 with a target root-zone pH of 6.2.",
    ),
    MemoryRecord(
        "M006",
        2,
        "fact",
        "The greenhouse thermal ceiling is 24 C. Backup oxygen lasts 18 hours.",
    ),
    MemoryRecord(
        "M007",
        2,
        "decision",
        "Helios Agritech is the approved seed vendor under purchase order PO-81.",
    ),
    MemoryRecord(
        "M008",
        3,
        "instruction",
        "Emergency valve recovery uses procedure V1: isolate line B, then cycle pump 2.",
    ),
    MemoryRecord(
        "M009",
        3,
        "fact",
        "The original landing site is Malapert Ridge. The mission call sign is Aurora.",
    ),
    MemoryRecord(
        "M010",
        3,
        "decision",
        "Telemetry is retained for 90 days. The approved program cap is USD 420,000.",
    ),
    MemoryRecord(
        "M011",
        4,
        "decision",
        "Crop plan revision C-2 replaces basil with dwarf radish for the flight trial.",
    ),
    MemoryRecord(
        "M012",
        4,
        "observation",
        "Dwarf radish completed germination testing in GH-7 with no mold detected.",
    ),
    MemoryRecord(
        "M013",
        4,
        "instruction",
        "Do not load Genovese basil seed into the flight cassette after revision C-2.",
    ),
    MemoryRecord(
        "M014",
        5,
        "decision",
        "Launch review L-3 moves the launch from August 14 to September 2, 2026.",
    ),
    MemoryRecord(
        "M015",
        5,
        "relationship",
        "Priya Nair replaces Elena Park as mission commander. Elena remains an adviser.",
    ),
    MemoryRecord(
        "M016",
        5,
        "instruction",
        "The current operations channel is Matrix room #asteria-flight, not Slack.",
    ),
    MemoryRecord(
        "M017",
        6,
        "decision",
        "Nutrient protocol N-21 supersedes N-17 and lowers target root-zone pH to 5.9.",
    ),
    MemoryRecord(
        "M018",
        6,
        "instruction",
        "The 24 C thermal ceiling is revoked. Hold GH-7 at or below 22 C.",
    ),
    MemoryRecord(
        "M019",
        6,
        "fact",
        "Battery pack BX-9 supplies the greenhouse controller during transfer.",
    ),
    MemoryRecord(
        "M020",
        7,
        "decision",
        "Site review S-4 selects Shackleton rim and rejects Malapert Ridge.",
    ),
    MemoryRecord(
        "M021",
        7,
        "decision",
        "The finance board reduces the program cap from USD 420,000 to USD 390,000.",
    ),
    MemoryRecord(
        "M022",
        7,
        "event",
        "Helios Agritech lot H-44 is recalled after contamination screening.",
    ),
    MemoryRecord(
        "M023",
        8,
        "decision",
        "Nova Seedworks becomes the approved vendor under replacement order PO-96.",
    ),
    MemoryRecord(
        "M024",
        8,
        "instruction",
        "Procedure V3 supersedes V1: isolate line C, vent for 30 seconds, then cycle pump 1.",
    ),
    MemoryRecord(
        "M025",
        8,
        "instruction",
        "Never use valve procedure V1 during flight operations.",
    ),
    MemoryRecord(
        "M026",
        9,
        "decision",
        "Security review shortens telemetry retention from 90 days to 30 days.",
    ),
    MemoryRecord(
        "M027",
        9,
        "decision",
        "The mission call sign changes from Aurora to Lumen for all current traffic.",
    ),
    MemoryRecord(
        "M028",
        9,
        "commitment",
        "Dr. Okafor will deliver the final radish growth report before August 20.",
    ),
    MemoryRecord(
        "M029",
        10,
        "fact",
        "Final readiness confirms GH-7, dwarf radish, N-21, and the 22 C ceiling.",
    ),
    MemoryRecord(
        "M030",
        10,
        "fact",
        "Final command brief lists Priya Nair, Shackleton rim, and call sign Lumen.",
    ),
    MemoryRecord(
        "M031",
        10,
        "instruction",
        "Send current alerts only to Matrix room #asteria-flight.",
    ),
    MemoryRecord(
        "M032",
        10,
        "fact",
        "Final logistics lists Nova Seedworks PO-96 and battery pack BX-9.",
    ),
)


QUERIES: tuple[QueryCase, ...] = (
    QueryCase(
        "Q01",
        "current-state",
        "What crop is currently approved for the Asteria flight trial?",
        (("dwarf radish", "radish"),),
        (("genovese basil", "basil"),),
    ),
    QueryCase(
        "Q02",
        "current-state",
        "What is the current launch date?",
        (("september 2", "september 2, 2026"),),
        (("august 14",),),
    ),
    QueryCase(
        "Q03",
        "current-state",
        "Who is the current mission commander?",
        (("priya nair",),),
        (("elena park",),),
    ),
    QueryCase(
        "Q04",
        "current-state",
        "Where should current operational alerts be sent?",
        (("matrix",), ("#asteria-flight", "asteria-flight")),
        (("slack", "#asteria-ops", "asteria-ops"),),
    ),
    QueryCase(
        "Q05",
        "current-state",
        "Which nutrient protocol and pH target are active?",
        (("n-21",), ("5.9",)),
        (("n-17",), ("6.2",)),
    ),
    QueryCase(
        "Q06",
        "current-state",
        "What is the active greenhouse thermal ceiling?",
        (("22 c", "22c", "22 degrees"),),
        (("24 c", "24c", "24 degrees"),),
    ),
    QueryCase(
        "Q07",
        "current-state",
        "Which landing site is selected now?",
        (("shackleton rim", "shackleton"),),
        (("malapert ridge", "malapert"),),
    ),
    QueryCase(
        "Q08",
        "current-state",
        "What is the current approved program cap?",
        (("390,000", "390000", "390k"),),
        (("420,000", "420000", "420k"),),
    ),
    QueryCase(
        "Q09",
        "current-state",
        "Which seed vendor and purchase order are currently approved?",
        (("nova seedworks",), ("po-96",)),
        (("helios agritech", "po-81"),),
    ),
    QueryCase(
        "Q10",
        "current-state",
        "Which emergency valve procedure is active?",
        (("v3",), ("line c",), ("pump 1",)),
        (("v1", "line b", "pump 2"),),
    ),
    QueryCase(
        "Q11",
        "current-state",
        "What are the current telemetry retention period and mission call sign?",
        (("30 days",), ("lumen",)),
        (("90 days",), ("aurora",)),
    ),
    QueryCase(
        "Q12",
        "historical",
        "What crop was approved before revision C-2?",
        (("genovese basil", "basil"),),
        (("dwarf radish",),),
    ),
    QueryCase(
        "Q13",
        "historical",
        "Who was mission commander before Priya Nair?",
        (("elena park",),),
        (("priya nair",),),
    ),
    QueryCase(
        "Q14",
        "historical",
        "What was the original landing site?",
        (("malapert ridge", "malapert"),),
        (("shackleton rim",),),
    ),
    QueryCase(
        "Q15",
        "historical",
        "Which valve procedure was used before V3?",
        (("v1",), ("line b",), ("pump 2",)),
        (("line c", "pump 1"),),
    ),
    QueryCase(
        "Q16",
        "multi-hop",
        "Prepare the current command brief: commander, landing site, and call sign.",
        (("priya nair",), ("shackleton rim", "shackleton"), ("lumen",)),
        (("elena park",), ("malapert ridge",), ("aurora",)),
    ),
    QueryCase(
        "Q17",
        "multi-hop",
        "Prepare the current greenhouse brief: module, crop, nutrient protocol, and temperature limit.",
        (("gh-7",), ("dwarf radish", "radish"), ("n-21",), ("22 c", "22c")),
        (("basil",), ("n-17",), ("24 c", "24c")),
    ),
    QueryCase(
        "Q18",
        "multi-hop",
        "Prepare current logistics: vendor, order, and transfer battery.",
        (("nova seedworks",), ("po-96",), ("bx-9",)),
        (("helios agritech", "po-81"),),
    ),
)


def validate_dataset() -> None:
    record_ids = [record.record_id for record in RECORDS]
    query_ids = [query.query_id for query in QUERIES]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("Duplicate memory record id")
    if len(query_ids) != len(set(query_ids)):
        raise ValueError("Duplicate query id")
    if any(record.session < 1 for record in RECORDS):
        raise ValueError("Sessions must be positive")
    if any(not query.required for query in QUERIES):
        raise ValueError("Every query needs at least one required concept")


validate_dataset()
