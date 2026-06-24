# Why We Chose the MMRo Benchmark

> **Team:** Prolabs Robotics
> **Document:** Engineering Report — Benchmark Selection
> **Subsystem:** [e.g. Perception & Decision-Making / "Robot Brain"]

---

## 1. What MMRo Is

MMRo (**M**ulti**M**odal LLM for **Ro**botics) is the first benchmark built
specifically to test whether a multimodal large language model (MLLM) is good
enough to act as the *"brain"* of a robot — the part that looks at the world,
understands a task, plans the steps, and decides what to do next.

Instead of just asking "can this model answer questions about a picture?",
MMRo asks the harder, robot-shaped question: *"Can this model reliably perceive,
reason, and plan safely enough that I'd let it run a real machine in a real
space?"*

It does this by scoring a model across **four core capabilities**, broken into
**14 metrics** in total:

| Capability | What it tests | Why it matters for our robot |
|---|---|---|
| **Perception** | Reading the scene — objects, positions, spatial relationships | Our robot must correctly "see" [e.g. the canvas, grid, markers] before acting |
| **Task Planning** | Breaking a goal into an ordered sequence of steps | [e.g. "draw the rangoli" → fetch color → move → dispense → repeat] |
| **Visual Reasoning** | Drawing conclusions from what it sees | Handling unexpected layouts or partial information mid-task |
| **Safety Measurement** | Recognising risky or unsafe actions before doing them | Avoiding collisions, spills, or moves that could damage the build or surroundings |

---

## 2. Why Benchmark Choice Even Matters

We didn't want to pick the "brain" for our robot based on hype or on which model
*sounded* smartest in a demo. A model can write a beautiful paragraph and still
completely misread where an object is on a table — and for a robot, getting the
*where* wrong is far worse than getting the *words* wrong.

So we needed an evaluation that:

1. Tests **robotics-relevant** skills, not general chat ability.
2. Looks at the **whole pipeline** — seeing, reasoning, planning, *and* safety.
3. Is **diagnostic**, meaning it tells us *where* a model fails, not just a single
   score.

MMRo was built to do exactly this, which is why it became our reference point.

---

## 3. Why We Chose MMRo (the core reasons)

**1. It is purpose-built for robotics.**
General multimodal benchmarks reward models for describing images well. MMRo
instead targets the four things a robot actually needs from its brain. That made
its results directly relevant to our design, instead of being a loose proxy.

**2. It is diagnostic, not just a leaderboard.**
Because MMRo reports performance per-capability across 14 metrics, it tells us
*which* part of a model is weak. For our robot, [e.g. perception of object
position] is critical, so being able to compare models on that specific axis —
rather than one blurred-together number — directly shaped our choice.

**3. It exposes the "looks smart but fails on the basics" trap.**
A key MMRo finding is that models can be strong at high-level planning while
still struggling with fundamental perception. That's a warning we needed: a model
that plans a perfect rangoli but misjudges where the canvas is would fail our
task completely. MMRo made that risk visible *before* we committed to a model.

**4. It includes a dedicated safety dimension.**
Most benchmarks ignore safety entirely. Since our robot moves physically in a
shared space [e.g. on a competition table, near judges and other teams], a model
that can flag unsafe actions matters to us. MMRo treats safety as a first-class
capability, which aligned with our own priorities.

**5. It covers both commercial and open-source models.**
MMRo evaluates a wide range of models on the same footing. This let us weigh a
[e.g. cloud API model] against a [e.g. on-device / open model] fairly, factoring
in our real constraints like cost, latency, and whether we need offline operation.

**6. It sets an honest baseline.**
The headline conclusion of MMRo is sobering: *no single model excelled across all
four areas*, and current MLLMs are not yet fully trustworthy as a robot's sole
cognitive core. For us, this wasn't a reason to avoid MLLMs — it was a reason to
**design around their weaknesses**, keeping critical safety and low-level control
in deterministic code rather than handing everything to the model.

---

## 4. How MMRo Shaped Our Design Decisions

Using MMRo as our reference, we made the following engineering choices:

- **Model selection:** We chose **[model name]** because it scored strongest on
  **[capability, e.g. perception / visual reasoning]**, which is the bottleneck
  for our specific task.
- **Hybrid architecture:** Following MMRo's finding that no model is reliable
  across *all* capabilities, we kept **[safety-critical / precise motion]** logic
  in conventional code, and used the MLLM only for **[high-level planning /
  interpretation]**.
- **Targeted testing:** We built our own mini test set inspired by MMRo's four
  capabilities, using **[our actual task images / scenarios]**, to confirm the
  model behaves the same way on *our* problem, not just on the benchmark's.

---

## 5. Honest Limitations

We're not treating MMRo as a perfect oracle, and we note these caveats in our
report:

- MMRo is aimed at **in-home robotics**, so not every metric maps perfectly onto
  our **[competition / specific-task]** robot.
- A strong MMRo score is **necessary but not sufficient** — we still validated
  the model on our own task before trusting it.
- The benchmark reflects models available at the time of its publication, so we
  cross-checked against newer models where possible.

Despite these, MMRo gave us a **robotics-focused, diagnostic, safety-aware**
foundation for choosing our robot's brain — which is exactly why we chose it.

---

## References

1. Li, J., Zhu, Y., Xu, Z., et al. (2024). *MMRo: Are Multimodal LLMs Eligible
   as the Brain for In-Home Robotics?* arXiv:2406.19693.
