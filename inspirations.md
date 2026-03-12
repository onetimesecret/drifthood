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
