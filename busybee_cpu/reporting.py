from __future__ import annotations

from pathlib import Path
from typing import Any


def write_report(path: str | Path, results: dict[str, dict[str, Any]]) -> None:
    lines = [
        "# BusyBee CPU Policy Report",
        "",
        "This report evaluates a non-generative CPU action policy: TF-IDF features plus linear classifiers for action selection and argument-template selection.",
        "Concrete arguments are filled by deterministic resolvers before schema and safety checks.",
        "",
    ]
    for name, metrics in results.items():
        lines += [f"## {name}", ""]
        for key, value in metrics.items():
            if key == "groups":
                continue
            lines.append(f"- {key}: {value:.4f}" if isinstance(value, float) else f"- {key}: {value}")
        lines += ["", "### Grouped Metrics", ""]
        for group, group_metrics in metrics.get("groups", {}).items():
            lines.append(f"#### {group} (n={group_metrics.get('n', 0)})")
            for key, value in group_metrics.items():
                if key == "n":
                    continue
                lines.append(f"- {key}: {value:.4f}")
            lines.append("")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
