"""Expose existing history files without relying on Glob following symlinks."""
import json
from pathlib import Path


def history_access_note(workspace, node_dir):
    root = Path(workspace).resolve() / "history"
    archives = sorted(p.resolve() for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if not archives:
        return ""
    lines = ["# Complete archived-history file index", "",
             "These are original artifacts, not summaries. Read the proposals and matching results in full as instructed."]
    count = 0
    for archive in archives:
        proposals = sorted(archive.glob("explore_b*/attempt_*/proposal.md"))
        lines += ["", f"## {archive.name}: {len(proposals)} proposals", f"Archive directory: {archive}"]
        for proposal in proposals:
            count += 1
            lines.append(f"- Proposal: {proposal}")
            for relative in ("eval/score.json", "error.txt", "artifact/program.py"):
                f = proposal.parent / relative
                if f.is_file():
                    lines.append(f"  {relative}: {f}")
    target = Path(node_dir).resolve() / "agent_log/history-files.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n")
    audit = {"archives": [str(p) for p in archives], "proposal_count": count,
             "index": str(target), "policy": "full original history; explicit resolved paths"}
    target.with_suffix(".json").write_text(json.dumps(audit, indent=2) + "\n")
    return ("\n\n## Linked-history filesystem compatibility\n"
            f"There ARE {len(archives)} completed archive(s), containing {count} historical proposals. "
            "Glob/Grep recursive searches do not reliably descend through directory symlinks. "
            "A 'No files found' result for history/** does NOT mean history is empty. "
            f"First Read this complete file index: {target}. "
            "Use its explicit resolved paths to Read every historical proposal and matching score/error "
            "as the original prompt requires. These archives are within your existing read permissions. "
            "This index only lists paths; it does not summarize or replace history. "
            "The problem statement documents installed packages; do not search outside the permitted "
            "branch/history directories for package sources.\n")
