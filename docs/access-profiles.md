# Access Profiles

The project is now a personal homelab agent controller. Each server gets an
access profile that matches how painful it is to break.

## Profiles

### guarded

Use for access infrastructure such as `openvpn-server`.

- Keep SSH/VPN access stable.
- Allow collection and predefined maintenance actions only.
- Do not allow arbitrary admin commands by default.
- Do not mark as rebuildable.

### experimental

Use for intermediate repairable project boxes such as `ispy-server`.

- Allow collection, predefined maintenance actions, and logged admin
  command workflows.
- Permit config/package/service changes after a captured before-state and
  explicit approval.
- Keep destructive disk/rebuild commands behind policy guardrails.
- Permit rebuild planning and execution only after preserving useful configs.

### lab

Use for the Codex-owned disposable playground box, currently `container-host`.

- Allow the broadest agent experiments.
- Permit arbitrary logged sudo commands, installs, destructive commands, and
  rebuild planning workflows after exact approval.
- Treat Docker/root access as intentionally high power.

## Current Mapping

| Server | Profile | Rebuildable | Intent |
|---|---|---:|---|
| `openvpn-server` | `guarded` | no | Preserve remote access. |
| `ispy-server` | `experimental` | yes | Diagnose or overhaul camera setup. |
| `container-host` | `lab` | yes | Codex lab with full logged sudo authority. |

## Inventory Fields

Each inventory entry supports:

```json
{
  "access_profile": "guarded",
  "rebuildable": false
}
```

Allowed `access_profile` values are `guarded`, `experimental`, and `lab`.
Guarded servers cannot be marked rebuildable.

## Sudoers Profiles

Template sudoers files live in:

```text
server-scripts/sudoers/
```

Install them manually with `visudo -f /etc/sudoers.d/homeops-agent` after
choosing the right profile and user for the target server. Do not store sudo
passwords in the repo.

## Controller Behavior

The controller uses these profiles before broader actions:

- `guarded`: predefined action IDs only.
- `experimental`: logged admin commands after exact approval, with destructive
  policy guardrails.
- `lab`: arbitrary logged sudo commands after exact approval. This profile is
  intentionally full power.
- `rebuildable: true`: rebuild workflows may be planned from before-state
  evidence, but destructive execution requires a separate approval phrase.
