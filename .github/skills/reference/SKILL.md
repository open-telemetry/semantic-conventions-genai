---
name: reference
description: 'Use when implementing or evaluating reference coverage for a semantic-conventions changeset involving GenAI spans, attributes, entities, metrics, or events across Python libraries.'
---

# Reference Scenarios Skill

Use this skill to add or update reference implementations under `reference/scenarios/<library>/` when conventions change.

## Workflow

1. **Find libraries**: Check which scenarios under `reference/scenarios/` support the changed operation(s).
2. **Update `scenario.py` and `README.md`**:
   - Wrap real library calls in spans. Call or patch private methods if needed to instrument the library only when it's not possible to do so through the public API.
   - Set attributes inline using only real values from SDK inputs, outputs, errors, or library state.
   - If the library cannot provide a value, do not fake it, leave it unset.
   - Update `reference/scenarios/<library>/README.md` operation table and status.
3. **Run and test**:
   ```bash
   cd reference
   uv run run-scenario <library>       # run scenario and update data.json
   uv run run-scenario --all           # run all scenarios
   uv run update-reports               # update report tables in README.md
   ```
4. **Regenerate docs** (from repo root):
   ```bash
   make generate-all
   ```

---

## Scenario README (`reference/scenarios/<library>/README.md`)

When adding or updating a reference scenario, update its `README.md`:
- **Libraries only**: Scenarios are for libraries and SDKs only. Do NOT add application examples.
- **Short description**: 1-2 sentences explaining what the library is (e.g. model-call boundary, agent framework) and what it owns vs delegates.
- **Operations table**: List relevant operations and their status:

```markdown
| Operation | Should be instrumented here | Status |
| --- | --- | --- |
| inference (`chat`) | Yes - calls model directly | ✅ Implemented |
| execute_tool | No - app runs tools | ➖ Not instrumentable |
| retrieval | Yes - Vector Stores search | ❌ Not implemented |
```

---

## Good vs Bad Patterns

### 1. Where values come from

**Good**: Read values from SDK arguments or response objects:
```python
# 'model' is an SDK parameter; response fields come from the SDK object
with tracer.start_as_current_span("chat", attributes={"gen_ai.request.model": model}) as span:
    response = client.chat.completions.create(model=model, messages=messages)
    span.set_attribute("gen_ai.response.id", response.id)
    span.set_attribute("gen_ai.usage.output_tokens", response.usage.completion_tokens)
```

**Bad**: Hardcoding values or using fake test data:
```python
# Bad: hardcoded value not returned by SDK
span.set_attribute("gen_ai.agent.name", "my-agent")

# Bad: reading from test config instead of SDK request/response
span.set_attribute("gen_ai.response.model", test_config["expected_model"])
```

### 2. Set attributes inline

**Good**: Set attributes right next to the SDK call:
```python
with tracer.start_as_current_span("invoke_agent") as span:
    result = agent.invoke(prompt)
    span.set_attribute("gen_ai.agent.id", agent.id)
```

**Bad**: Hiding attribute logic in helper functions:
```python
with tracer.start_as_current_span("invoke_agent") as span:
    result = agent.invoke(prompt)
    _set_attributes(span, agent, result)  # Hides where values come from
```

### 3. Span boundaries

**Good**: Span wraps the specific library call representing the operation:
```python
with tracer.start_as_current_span("chat") as span:
    response = client.chat.completions.create(model=model, messages=messages)
```

**Bad**: Span wraps scenario setup, multiple calls, or application loops:
```python
# Bad: wraps multiple separate calls and setup code
with tracer.start_as_current_span("chat"):
    setup_environment()
    resp1 = client.chat.completions.create(...)
    resp2 = client.chat.completions.create(...)

# Bad: wraps custom application logic instead of instrumenting library API
with tracer.start_as_current_span("invoke_agent"):
    for step in app_steps:
        process_step(step)
```

