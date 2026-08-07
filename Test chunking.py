"""
scripts/test_chunking.py

Standalone sanity check for the new chunking module against the project's
real sample SOPs in data/sample_sops/*.md. Run this AFTER dropping
chunking.py into backend/app/.

Usage:
    python scripts/test_chunking.py
    python scripts/test_chunking.py --strategy recursive --chunk-size 300 --overlap 40
"""

import argparse
import glob
import os
import sys

# Make backend/app importable when run from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend", "app"))

from chunking import chunk_text  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default="markdown_aware",
                         choices=["fixed", "recursive", "markdown_aware"])
    parser.add_argument("--chunk-size", type=int, default=400)
    parser.add_argument("--overlap", type=int, default=60)
    parser.add_argument("--sops-dir", default="data/sample_sops")
    args = parser.parse_args()

    sop_files = sorted(glob.glob(os.path.join(args.sops_dir, "*.md")))
    if not sop_files:
        print(f"No SOP markdown files found in {args.sops_dir}/ "
              f"(run this from the repo root)")
        return

    total_chunks = 0
    for path in sop_files:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()

        sop_id = os.path.splitext(os.path.basename(path))[0]
        chunks = chunk_text(
            text,
            strategy=args.strategy,
            chunk_size=args.chunk_size,
            chunk_overlap=args.overlap,
            base_metadata={"sop_id": sop_id},
        )
        total_chunks += len(chunks)

        print(f"\n=== {path} -> {len(chunks)} chunks (strategy={args.strategy}) ===")
        for c in chunks:
            section = c.metadata.get("section", "")
            preview = c.text.replace("\n", " ")[:80]
            print(f"  [{c.index}] ~{c.token_count} tok | section={section!r} | {preview!r}...")

    print(f"\nTotal: {len(sop_files)} SOP file(s) -> {total_chunks} chunk(s)")


if __name__ == "__main__":
    main()
