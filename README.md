# Trace AI — Evidence-Backed Data Investigation

**Trace AI** is a lightweight AI investigation agent for data-heavy teams.

### The problem

Dashboards are good at showing **what changed**.

But teams still spend significant time figuring out:

* Why did it change?
* What evidence supports that explanation?
* What should I investigate next?

Trace explores a simple workflow:

**Signal → Evidence → Hypothesis → Next Investigation**

## Product hypothesis

> Can an AI agent reduce the distance between noticing a business signal and forming a grounded, testable explanation?

## V0

Given a structured dataset and a metric change, Trace should:

1. Identify what changed.
2. Break the change down by segment.
3. Surface supporting evidence.
4. Generate a clearly labelled hypothesis.
5. State what is **not established**.
6. Recommend the next investigation.

### Product contract

**Code calculates. AI interprets. The user decides.**

The LLM should not calculate business metrics or invent evidence.

## Example

**Signal**
Conversion fell 12%.

**Evidence**

* Mobile conversion fell 19%.
* New-user conversion fell 23%.
* Payment failures increased from 2.1% to 5.8%.

**Hypothesis**
Increased payment failures may be contributing to the decline among mobile new users.

**Not established**
The available data does not prove payment failures caused the decline.

**Next investigation**
Compare payment failures before and after the latest mobile release.

## V0 scope

* One CSV dataset
* One business metric
* Period-over-period comparison
* Segment analysis
* Python + pandas calculations
* AI explanation grounded in calculated evidence
* Simple Streamlit UI

No database. No authentication. No complex multi-agent setup.

## Product principles

**Evidence before explanation.**
Every conclusion should trace back to data.

**Facts ≠ hypotheses.**
The UI should make the distinction obvious.

**Correlation ≠ causation.**
Trace should not claim more than the data supports.

**Show uncertainty.**
If the evidence is weak, say so.

**End with action.**
The user should know what to investigate next.

## Why I'm building this

Across enterprise costing, manufacturing, AI troubleshooting, and fraud products, I kept encountering a similar problem:

**The data exists, but understanding why something happened still requires investigation.**

Trace is my exploration of how AI agents can make that investigation faster while keeping the reasoning grounded and explainable.

## Build log

### V0 — Product definition

* Defined the user problem.
* Defined Signal → Evidence → Hypothesis → Investigation.
* Added grounding and causality guardrails.
* Narrowed the MVP to one dataset and one metric.

### Next

Build a synthetic dataset with a known underlying problem and see whether Trace can correctly uncover it.

---

## Related work

**Manufacturing Cost Intelligence** — AI explainability for complex cost and WIP movements.

**Cost Processor Troubleshooting Agent** — Agent + knowledge retrieval for enterprise troubleshooting.

**Real-Time Fraud Detection** — ML-driven transaction risk scoring and decisioning.
