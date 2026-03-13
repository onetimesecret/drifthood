# Inspiration for Drift Detector


### > What valuable functionality does SwaggerUI have that we could borrow from? What are some other tools we could look at to better understand the problem space?

Good question. Let me think about this in terms of what actually matters for drift detection rather than just listing features.

#### **SwaggerUI's relevant mechanics:**

The "Try it out" execution model is the closest analog to what you're building. The interesting parts: it pre-populates parameters from the spec with correct types and constraints (enums become dropdowns, required fields are marked), it shows curl equivalents of what it's about to send (useful for debugging why two hosts diverge), and it renders response schemas alongside actual responses so you can see whether the *drift* is from the spec or just between hosts. The authentication model is also worth studying: it has a global "Authorize" button that applies credentials to all subsequent requests, with per-endpoint override capability. You already have something similar with base auth + per-request auth fields.

What you'd actually want to steal: the parameter-level granularity. SwaggerUI doesn't treat the request body as a single text blob. Each field is its own input, typed from the schema. That matters for drift detection because you could diff at the field level on the *request* side too, catching cases where a parameter that exists in v1 got renamed in v2.

#### **Other tools worth examining for the problem space:**

Hurl (hurl.dev) takes a different angle. Plain-text files that describe HTTP requests with inline assertions. The interesting bit: it chains requests, so you can capture a value from response A and feed it into request B. For secrets API testing that's directly relevant since you create a secret, then retrieve it, then verify it's gone after burn. Right now your tool treats each endpoint as independent.

Portman (from Apideck) generates Postman collections from OpenAPI specs with automatic contract tests. The part that matters: it auto-generates validation tests from the schema, checking response shapes against what the spec promises. That's a different axis from your host-to-host diffing. You're comparing A-vs-B for the same request; Portman compares response-vs-spec. Both are drift, just different reference frames.

Schemathesis does property-based/fuzz testing against OpenAPI specs. It generates weird edge-case inputs automatically from the schema. The failure modes it finds (like "this endpoint returns 500 when you send an empty string for a required field") are exactly the kind of behavioral drift between versions that wouldn't show up with happy-path example values from the spec.

Dredd (from Apiary, now largely abandoned but the concepts are solid) validated API implementations against API Blueprint/OpenAPI specs. Its "transaction" model is interesting: it treated each endpoint+example combination as a transaction with hooks for setup/teardown. The hooks concept maps to your problem: before testing "retrieve secret," you need to have created one.

#### **The gap your tool sits in:**

Most of these tools test one host against a spec (contract testing) or generate tests from a spec. Your tool tests one host against another host, which is a less-explored space. The closest thing in production use is probably shadow traffic / traffic replay systems (like Diffy from Twitter, now archived, or Istio's traffic mirroring). Diffy in particular had the same architecture: send the same request to two backends, diff the responses, with noise reduction for expected differences. It ran as a proxy rather than a UI-driven tool, but the diffing logic and ignore-path mechanics are the same problem.

The chain-of-requests gap is probably the most impactful thing missing from the current tool for your actual use case of testing secrets lifecycle across versions.


### > What can we learn from existing tools like Hurl, Portman, Schemathesis, Dredd, SwaggerUI that would improve Drift Detector?

Here's what each tool brings to the table, filtered for what actually matters to Drift Detector's specific problem (one spec, two hosts, compare responses).

**Hurl** is a plain-text HTTP request runner. The interesting bit is its assertion chain model: you declare expected response properties inline (`status == 200`, `jsonpath "$.count" >= 1`, `header "Content-Type" contains "json"`). For Drift Detector, the relevant idea isn't the assertions themselves but how Hurl treats **response capture**: you can extract a value from response A and feed it into request B (`variable: key`). Right now Drift Detector treats each endpoint as independent. But real API workflows are sequential: you create a secret, get back a key, then retrieve using that key. Without response chaining, you can't test the retrieval endpoints at all because you don't have valid keys to substitute into `{key}`. That's the single biggest functional gap.

**Portman** sits between OpenAPI and Postman, auto-generating test suites from specs. Its contract testing approach is relevant: it generates variation tests from the schema (required fields missing, wrong types, boundary values) and checks that the API conforms. Drift Detector doesn't need contract validation per se, but Portman's **variation generation** is interesting for drift detection. If you send a malformed request to both hosts and they return _different_ error responses (different status codes, different error shapes), that's drift too. Currently you only test the happy path shape defined in the spec. Generating negative cases automatically from the schema would increase surface area without manual work.

**Schemathesis** is the most directly relevant. It does property-based/fuzz testing against OpenAPI specs. Two things matter here. First, it has **stateful testing** via OpenAPI links: it chains operations using the spec's `links` or by inferring that a 201 response body feeds into a subsequent GET. That's the same chaining problem Hurl solves, but Schemathesis derives it from the spec itself rather than requiring manual wiring. Second, Schemathesis generates **random valid payloads** from schemas. For drift detection, this is powerful: instead of sending one hand-crafted body to both hosts, you send N randomly-generated-but-schema-valid bodies and diff every pair of responses. A rename that only manifests under certain field combinations would surface.

**Dredd** validates that a running API matches its spec. The relevant pattern is how it handles **response schema validation**: it doesn't just check status codes, it validates response body structure against the spec's response schemas. Drift Detector currently diffs response A vs response B with DeepDiff but doesn't check whether _either_ response actually matches the declared schema. That's a third axis: Host A drifted from spec, Host B matches spec, and the diff shows them disagreeing. Knowing _which_ host is spec-compliant and which drifted tells you the direction of the regression.

**SwaggerUI** you've already mined for the field-level input model. The remaining useful pattern is **authentication flow handling**: SwaggerUI lets you configure auth once (API key, OAuth token, basic auth) and it gets injected into every request. Drift Detector presumably needs auth headers for both hosts, and those hosts might use different tokens. A per-host auth configuration that auto-injects into every request would reduce friction.

Ranked by impact on Drift Detector's core job:

1. **Response chaining** (Schemathesis/Hurl pattern) — unlocks testing endpoints that depend on prior responses. Without it, a large chunk of CRUD APIs is untestable.

2. **Random payload generation from schema** (Schemathesis) — multiplies test coverage without manual effort, catches drift that only appears with certain field combinations.

3. **Spec-conformance as a third comparison axis** (Dredd) — when responses differ, knowing which one matches the spec tells you which host regressed.

4. **Negative/variation test generation** (Portman) — error handling drift is real and currently invisible.

5. **Per-host auth injection** (SwaggerUI) — quality of life, reduces setup friction per test run.

The first one is the structural limitation. Everything else improves coverage or ergonomics, but without chaining, you're restricted to endpoints that don't depend on runtime values from other endpoints.


---

You click Run, expect fresh data, and get back what looks like the same stale response.

  The structural reason is straightforward: runGroup() does clear ep.result = null and makes a fresh API
   call — so if the response truly changed, the UI should update. If it didn't, the actual bug is
  either:

  1. The run didn't actually fire for that endpoint (group name mismatch, or the endpoint was filtered
  out)
  2. The API call returned the same stale data (upstream caching, SSL cert issue causing fallback,
  connection reuse)
  3. The result object changed but the component didn't re-render (Svelte reactivity issue with mutating
   the same object reference)

  Since "Clean runs" + "Run Group" fixed it, that points strongly at #3 — a reactivity problem. Setting
  ep.result = null then ep.result = newResult on the same object may not trigger Svelte 5's fine-grained
   reactivity if the proxy doesn't detect the intermediate null. The clean run forces a full reset via
  clearResults() which replaces every endpoint's state, guaranteeing a reactive update.

The problem: restore() doesn't distinguish between "load this configuration to run again" and "display
  these historical results as if they're current." It treats saved results identically to live results
— same state field, same rendering, no timestamp, no provenance. So when init() auto-loads the most
recent testrun on page load, stale results appear indistinguishable from a run you just triggered.

It is a structural  problem. On every page load, init() (line 93) automatically loads the most recent
testrun from the DB — including its stale results — and restores them into live state. Then autosave
starts, which means those stale results get re-persisted on a 60-second loop, creating a
self-reinforcing cycle of stale data.

The result: you restart a server, open DriftDetector, and it looks like you just ran everything — but
you're seeing data from the last autosave. There's no visual indicator that these results are from 20
minutes ago, or 2 days ago.

Here's how well-known tools in this space handle the same problem, and the tradeoffs:

1. Postman / Insomnia model: Results are ephemeral, never restored
On open, the response panel is empty. You must click Send. Saved "examples" are explicitly labeled as
historical snapshots, never injected into the live workspace. Tradeoff: you lose continuity between
sessions, but you never mistake old data for current.

2. Playwright / Vitest model: Results invalidated on input change
When the source code changes, previous test results are grayed out or cleared. A re-run is required.
The runner knows "this result was produced from different inputs than what's configured now."
Tradeoff: needs a staleness signal (hash of inputs vs. hash at capture time).

3. Grafana / Datadog model: Timestamp is always visible, auto-refresh is the norm
Every panel shows when data was last fetched. Stale data gets a visible age indicator. Many panels
auto-refresh on an interval. Tradeoff: requires bandwidth for polling, but staleness is never
ambiguous.

For DriftDetector, I'd look at a combination of 2 and 3, applied as three concrete changes:

A. Restore configuration, not results. When restore() loads a saved testrun, restore the endpoints,
environments, ignore paths — but set ep.state = 'idle' and ep.result = null. The saved results still
exist in the DB for review via the sidebar, but the active workspace starts clean. This is the single
highest-impact change: it eliminates the entire class of "looking at stale data without knowing it."

B. Capture a timestamp per result, show it. The backend already returns elapsed_ms; add a captured_at
ISO timestamp to each hit() response. Display it subtly in the result card (e.g., "3m ago" or "2h
ago"). When it crosses a threshold — say 5 minutes — the result fades or gets a "stale" badge. This
gives situational awareness even within a single session.

C. Invalidate results when environments change. If the user changes Host B's URL or auth, all existing
  results were produced against a different target. Clear them, or at minimum mark them stale. This is
the "inputs changed, outputs are suspect" signal from the Playwright model.

The autosave mechanism can continue as-is — it's useful for crash recovery. The key insight is that
saving state and restoring results into the active workspace are different operations, and conflating
them is what creates the "sticky" behavior.

Want me to implement these, or do you want to adjust the approach first?

---

Related links

https://buildwithfern.com/#docs
