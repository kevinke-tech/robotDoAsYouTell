# Skill Manifest Contract

Generated skills are persisted in `logs/skill_manifest.json` for traceability.

## Storage Shape

```json
{
  "skills": {
    "<skill_name>": {
      "name": "<skill_name>",
      "source": "dynamic_synthesis | static_registry",
      "kind": "one_shot | background_timer | background_vision",
      "backend": "claude_agent_sdk | cursor_sdk",
      "model": "<model_name>",
      "created_at": "YYYY-MM-DDTHH:MM:SS",
      "updated_at": "YYYY-MM-DDTHH:MM:SS",
      "file": "absolute_or_project_path",
      "args_signature": { "...RUN_SPEC.args_schema..." },
      "instance_binding": "one_shot | spawning",
      "version": 1
    }
  }
}
```

## Runtime Binding View

`GET /skills` enriches each skill with:

- `manifest.instance_bindings`: runtime relationship list from runner instances:
  - `instance_id`
  - `kind`
  - `is_active`

For static skills that were not dynamically synthesized, server returns a
default manifest view:

- `source = "static_registry"`
- `version = 1`

## Lifecycle Rules

- On successful synthesize promotion, manifest is upserted.
- On skill deletion (`DELETE /skills/{name}`), manifest record is removed.
- Manifest write failures are non-fatal (skill creation still succeeds).
