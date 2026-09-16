#!/usr/bin/env python3
"""Ship line_offsets.npy next to the chunk store (the adapter can build it, but this saves
every user a full decompression pass)."""
import sys, gzip, pathlib, numpy as np
out = pathlib.Path(sys.argv[1]); src = out/"wiki_chunks.jsonl.gz"
offs, pos = [], 0
with gzip.open(src, "rb") as f:
    for line in f:
        offs.append(pos); pos += len(line)
a = np.asarray(offs, dtype=np.int64); np.save(out/"line_offsets.npy", a)
# ship the gzip seek index too: without it the first deep read costs ~5 s (ja) to ~25 s (en)
try:
    import indexed_gzip as igzip
    f = igzip.IndexedGzipFile(str(src), spacing=64*1024*1024)
    f.build_full_index(); f.export_index(str(out/"line_offsets.gzidx")); f.close()
    print(f"  gzidx {(out/'line_offsets.gzidx').stat().st_size/1e6:.1f} MB")
except Exception as e:
    print("  gzidx skipped:", e)
print(f"{out.name}: {len(a):,} offsets, {a.nbytes/1e6:.0f} MB, uncompressed {pos/1e9:.2f} GB")
