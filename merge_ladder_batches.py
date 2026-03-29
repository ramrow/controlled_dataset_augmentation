#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')


def dedupe_rows(rows):
    seen = set()
    out = []
    for r in rows:
        key = (
            r.get('case_name'),
            r.get('folder_name'),
            r.get('file_name'),
            r.get('user_requirement'),
            r.get('variant_id'),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description='Merge ladder batch outputs into single files')
    ap.add_argument('--out-dir', default='ladder_outputs')
    ap.add_argument('--split', default='train')
    ap.add_argument('--chunk-count', type=int, default=6)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    out_dir = (root / args.out_dir).resolve()

    all_rows = []
    all_cases = []
    all_failed = []
    all_progress = []

    for i in range(args.chunk_count):
        all_rows.extend(load_jsonl(out_dir / f'accepted_rows_{args.split}_chunk{i}.jsonl'))
        all_cases.extend(load_jsonl(out_dir / f'accepted_cases_{args.split}_chunk{i}.jsonl'))
        all_failed.extend(load_jsonl(out_dir / f'failed_{args.split}_chunk{i}.jsonl'))
        all_progress.extend(load_jsonl(out_dir / f'progress_{args.split}_chunk{i}.jsonl'))

    all_rows = dedupe_rows(all_rows)

    rows_out = out_dir / f'accepted_rows_{args.split}_merged.jsonl'
    cases_out = out_dir / f'accepted_cases_{args.split}_merged.jsonl'
    failed_out = out_dir / f'failed_{args.split}_merged.jsonl'
    progress_out = out_dir / f'progress_{args.split}_merged.jsonl'

    append_jsonl(rows_out, all_rows)
    append_jsonl(cases_out, all_cases)
    append_jsonl(failed_out, all_failed)
    append_jsonl(progress_out, all_progress)

    summary = {
        'split': args.split,
        'chunk_count': args.chunk_count,
        'accepted_rows_merged': len(all_rows),
        'accepted_cases_merged': len(all_cases),
        'failed_merged': len(all_failed),
        'progress_merged': len(all_progress),
        'outputs': {
            'rows': str(rows_out),
            'cases': str(cases_out),
            'failed': str(failed_out),
            'progress': str(progress_out),
        }
    }

    summary_path = out_dir / f'merge_summary_{args.split}.json'
    summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
