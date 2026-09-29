# Reference: "Digitalizing the DMTA workflow with an electronic inventory platform" (Sygnature Discovery, 2025)

Source: Qin T. et al., *SLAS Technology* 32 (2025) 100262, technical brief. https://doi.org/10.1016/j.slast.2025.100262

Note: this is a short technical brief from a single contract research organization (CRO). The reported benefits (more ideas triaged, fewer errors, better resource allocation, high adoption) come from scientist feedback. The paper includes no quantitative before/after data.

## What they did

Sygnature needed a shared, real-time way to track compound ideas through the Design-Make-Test-Analyze (DMTA) cycle across teams and clients. Excel and PowerPoint caused fragmentation, version conflicts, and no audit trail. Instead of building or buying a dedicated tool, they **repurposed their existing chemical inventory system** (ChemInventory, a hosted service):

| Inventory concept | Reused as |
|---|---|
| Compound registration | Idea submission (structure, hypothesis, contributors) |
| Location hierarchy | Workflow stages: New Ideas → Approved / Parked → In Synthesis → *Chemist-N* → Completed → Hit → Lead |
| Moving a container between locations | Advancing an idea to the next stage |
| Substance ID (derived from structure) | Idea ID: the same molecule always gets the same ID |
| Container ID | Instance ID: separates resubmissions of the same idea for different reasons |
| Linked files and comments | Supporting documents and discussion |
| Movement audit log | Full history of an idea's progress (who, when, what) |
| Substructure and field search | Idea search |

Other points:
- **Roles:** chemists, computational chemists, and AI engineers submit ideas. Project leads prioritize them and assign synthesis. Members update stages. Clients and collaborators see progress in real time.
- **Why it worked:** low cost, scientists already knew the tool, existing support channels applied, and it was more flexible than a Kanban board because stages can nest.
- **Gaps:** weak visualization, which they address by pulling data through the API into Power BI or Tableau.
- **Future work:** compare metrics across projects, use ML to recommend resource allocation, and **tag ideas as "AI-aided" or "AI-generated"** to measure how much AI contributes.

## How it relates to the Connected Lab / DLMM paper

See [connected-lab-dlmm.md](connected-lab-dlmm.md). This paper is a concrete, low-cost example of a lab moving from Stage 1 to Stage 2. It tracks the **Design** side of the cycle and the handoff to synthesis. It does not orchestrate instruments: Make and Test are still manual steps recorded as stage moves. That leaves the gap the DLMM paper identifies, and it is the gap Gladys targets.

---

## Implications for Gladys

- **The two-ID pattern already exists in our record, so use it on purpose.** `ProtocolRevision.source_sha256` plays the role of the substance ID (the same protocol always gets the same hash), and `run_id` plays the role of the container ID (one specific execution). Any query like "every time this exact protocol ran" should group by the hash.
- **Record status as a history, not a single current value.** The movement audit log is the feature the paper values most for traceability. A list of status changes (from, to, who, when) in `RunRecord` would provide that audit trail. It would also give `Timestamps` a single source of truth, and it could enforce valid transitions, which addresses the concern that status is currently a free-standing field.
- **Tag AI provenance from day one.** Sygnature plans to tag ideas as AI-aided or AI-generated. Every Gladys protocol is AI-generated, so the record should say so, including the model and version, and whether a human edited the protocol before approval. This lets users measure what the paper wants to measure.
- **Link Make/Test runs back to the design.** A Gladys run is the Make or Test step for an idea tracked elsewhere. An optional field for external references (for example, an idea ID, compound ID, or project) connects runs to systems like this one without Gladys becoming a DMTA tracker itself.
- **Integrate with the tools labs already have.** The paper's main argument is that reusing familiar systems beats introducing new ones. Consumables and labware in a record should be able to carry inventory IDs, and records should export easily to BI tools. JSON already makes export easy.
- **Capture contributors and rationale.** Ideas carry a hypothesis and contributors, partly for intellectual-property reasons. A Gladys request could optionally carry the scientific rationale and the people involved.
