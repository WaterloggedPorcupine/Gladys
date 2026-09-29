# Reference: "The Connected Lab" (HighRes × Involve Data, 2026)

Source: joint whitepaper by HighRes (maker of the Cellario OS orchestration platform) and Involve Data (data strategy consultancy). It is the first paper in a series; planned follow-ups cover orchestration ("The Missing Layer") and building an enforceable data semantic hierarchy.

Note: this is a vendor and consultancy paper written to sell assessment engagements. Treat its framing as a useful industry vocabulary, not as neutral research. Its claims about where "most organizations sit" are the authors' experience, not measured data.

## Core thesis

Life-science orgs have invested heavily at the top of the stack (cloud, ELN, LIMS, AI) and at the bottom (instruments, robotics). The connections between them are left to individual teams, so data moves through manual export, brittle scripts, and copy-paste. The paper says this is an **architecture** problem, not a tooling, vendor, or culture problem.

**Why now:** AI is compressing the Design and Analyze halves of the Design-Make-Test-Analyze (DMTA, "lab in the loop") cycle. That moves the bottleneck to **Make and Test**, the physical lab. An AI strategy can only move as fast as the lab that feeds it.

## The Digital Lab Maturity Model (DLMM): four layers

| Layer | What it is |
|---|---|
| 1. Instruments & Hardware | Liquid handlers, plate readers, robotics, sample storage, work cells |
| 2. **Orchestration** | Turns scientific intent into executed work on instruments, and raw output into structured, contextualized data with provenance. Covers workflow execution, scheduling, instrument integration, error handling and recovery, and **data contracts** (how output is captured, named, and handed off) |
| 3. **Data Fabric** | Storage, governance, schema, lineage, integration: ELN, LIMS, lake or warehouse, MDM, FAIR |
| 4. Analytics & AI | Models, dashboards, decisions |

Layers 2 and 3 form "the flexible middle", which the paper calls the leverage point. Most orgs think in two layers (IT stack and lab) and treat the middle as glue. In an immature lab, orchestration "is labor distributed across scripts, shared drives, scientist habit, and hope."

**Game board:** enterprise IT is largely fixed, the physical lab is semi-fixed (including CRO work), and strategy lives in the middle. The goal is to standardize architecture and data semantics, not every tool. A large org may run three ELNs, and that is acceptable.

### Failure modes (conflating layers)
- Orchestration treated as part of the data fabric: the LIMS gets overloaded with workflow logic.
- Orchestration treated as part of the instruments: one orchestration island per vendor, with no way to combine them.
- AI reads directly from instruments: it gets raw output with no context or provenance. The paper names this as a structural reason AI pilots stall.
- Data fabric asked to produce decisions: the analytics layer never matures.

### Data swamp vs data lake
Industrial IoT's first wave failed because organizations collected data before deciding what the data meant. What fixed it was an enforced **semantic hierarchy**, an organization-wide model of what each data point means, so data is comparable by construction. Standards bodies (Allotrope, Pistoia) have not produced a universal standard. The pragmatic path is a semantic model that is consistent inside one organization, not one that is interoperable across the industry.

## Maturity ladder

1. **Disconnected**: data moves by hand, and no orchestration layer exists.
2. **Integrated**: a few end-to-end workflows exist, each built as its own project, and the patterns don't generalize. The cost of each new integration never goes down.
3. **Connected**: the four layers are run as one system with a named owner for the middle. New workflows need no new plumbing, instrument-data contracts exist, and AI reads from the fabric rather than from instruments.
4. **Adaptive**: new instruments are integrated against existing contracts in days. AI is a standard part of workflow design.

The authors say most large organizations sit at Stage 1–2, and the leverage is in moving to Stage 3. Their example pharma profile: Instruments at 2, Orchestration at **1**, Data Fabric at 2, Analytics at 3. Orchestration is the weakest layer.

## Five diagnostic questions
1. Can we unify our data, and would it survive an acquisition? (semantic hierarchy)
2. Where does the connective middle live, and who owns it?
3. Are our AI initiatives honest about what they assume of the orchestration and data fabric layers?
4. Can we show, with evidence, what a workflow costs and its turnaround time (TAT), before and after automation?
5. Are capital decisions evaluated against the architecture?

## Executive pain points (useful language for positioning)
- "I cannot get a holistic picture from our data." (fragmentation across sites and acquisitions)
- "Our TAT is too slow and I can't prove the investment paid off."
- "I don't know what this really costs to run." (hidden time: searching, reformatting, re-runs, manual protocols)
- "I can't make the call because I don't have the data I need." (broken provenance)
- "We spent a fortune on the lab and it's not paying off."

---

## Implications for Gladys

Gladys (scientist request → reviewable robot protocol) sits squarely in the **orchestration** layer, and specifically at its front edge: turning scientific intent into executable work. In DLMM terms, that is the layer the paper calls weakest and most valuable. Suggestions, mapped to the current package layout:

- **`records/` is the data contract.** Every run Gladys produces should emit a structured record: the original request, the generated protocol and its version, labware and deck layout, parameters, who reviewed and approved it, and the execution outcome. This is the provenance chain the paper says decisions depend on. Design it so a data fabric (ELN/LIMS/lake) can ingest it directly, without having to become one.
- **Adopt a semantic model early.** Consistent naming for samples, plates, wells, reagents, and assays in generated protocols and records avoids building a small data swamp. Keep the model internally consistent and easy to map to other systems; don't wait for Allotrope.
- **`platforms/` should avoid the "orchestration island" failure.** Opentrons comes first, but the intent-to-protocol representation and the record format should be platform-neutral, with Opentrons as one backend.
- **`validity/` is the trust layer.** Checks that a protocol matches the request and is physically valid support the "can the data be trusted?" pain point. Validation results belong in the record too.
- **Capture TAT and cost signals.** Timestamps for request, protocol ready, approval, run start, and run end, plus reagent and tip usage, let users answer diagnostic question 4 with evidence instead of estimates.
- **Positioning:** the DMTA-bottleneck argument is a ready-made pitch. AI is speeding up Design and Analyze; Gladys speeds up the step from Design into Make/Test. It also helps Stage 1–2 labs, whose scripts written by scientist habit are exactly what Gladys replaces.
- **Stay in lane.** Per the failure modes, Gladys shouldn't grow LIMS or analytics features. Its job is to hand clean, contextualized output to those layers.
