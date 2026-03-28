import argparse
import json
from pathlib import Path
from collections import defaultdict


def load_jsonl(path: Path):
    rows = []
    with path.open('r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                raise ValueError(f"Parse error in {path} line {i}: {e}")
    return rows


def main():
    ap = argparse.ArgumentParser(description='Group rows by identical user_prompt')
    ap.add_argument('--input', nargs='+', required=True, help='Input jsonl file(s)')
    ap.add_argument('--out-dir', default='grouped_by_user_prompt', help='Output directory')
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    overall = {}

    for inp in args.input:
        p = Path(inp)
        rows = load_jsonl(p)

        groups = defaultdict(list)
        missing = 0
        for idx, r in enumerate(rows):
            up = r.get('user_prompt')
            if not isinstance(up, str):
                missing += 1
                up = '__MISSING_USER_PROMPT__'
            groups[up].append(idx)

        # Build compact group records
        group_records = []
        for gid, (prompt, idxs) in enumerate(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))):
            sample = rows[idxs[0]]
            group_records.append({
                'group_id': gid,
                'user_prompt': prompt,
                'count': len(idxs),
                'row_indices': idxs,
                'sample_case_name': sample.get('case_name'),
                'sample_file_name': sample.get('file_name'),
            })

        # Write outputs
        base = p.stem
        out_json = out_dir / f'{base}_groups.json'
        out_csv = out_dir / f'{base}_groups.csv'
        out_summary = out_dir / f'{base}_summary.json'

        out_json.write_text(json.dumps(group_records, ensure_ascii=False, indent=2), encoding='utf-8')

        # simple csv
        with out_csv.open('w', encoding='utf-8', newline='') as f:
            f.write('group_id,count,sample_case_name,sample_file_name\n')
            for g in group_records:
                f.write(f"{g['group_id']},{g['count']},\"{str(g['sample_case_name']).replace('"','""')}\",\"{str(g['sample_file_name']).replace('"','""')}\"\n")

        summary = {
            'file': str(p),
            'total_rows': len(rows),
            'unique_user_prompts': len(groups),
            'duplicate_prompt_rows': sum(len(v) for v in groups.values() if len(v) > 1),
            'largest_group_size': max((len(v) for v in groups.values()), default=0),
            'missing_user_prompt_rows': missing,
            'outputs': {
                'groups_json': str(out_json),
                'groups_csv': str(out_csv),
            }
        }
        out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        overall[base] = summary

    overall_path = out_dir / 'overall_summary.json'
    overall_path.write_text(json.dumps(overall, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(overall, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
