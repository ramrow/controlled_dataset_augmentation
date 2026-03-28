#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import hashlib
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BEDROCK_PROVIDER = "bedrock"
BEDROCK_MODEL = "arn:aws:bedrock:us-west-2:567316078106:inference-profile/us.anthropic.claude-opus-4-6-v1"

PROMPT_SUFFIX = (
    "Generate the target OpenFOAM file so it is complete, functional, and logically consistent with the requirement. "
    "Use technically sound parameter choices and maintain internal consistency across physical models, dimensions, and numerics."
)


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                raise ValueError(f"Parse error {path}:{i}: {e}")
    return rows


def append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def stable_bucket(key: str, chunk_count: int) -> int:
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(h[:12], 16) % chunk_count


def grouped_prompts(rows):
    groups = defaultdict(list)
    for r in rows:
        up = r.get("user_prompt", "")
        groups[up].append(r)
    return groups


def extract_requirement(row):
    req = row.get("user_requirement")
    if isinstance(req, str) and req.strip():
        return req.strip()
    up = row.get("user_prompt", "")
    m = re.search(r"User requirement:\s*(.*)", up, flags=re.IGNORECASE | re.DOTALL)
    if m:
        txt = m.group(1)
        txt = txt.split("Generate the target OpenFOAM file", 1)[0].strip()
        return txt
    return ""


def adjust_first_velocity(req: str, delta: float):
    pats = [
        r"uniform\s*\(\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s+([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s+([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*\)\s*m/s",
        r"velocity\s+of\s*\(\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s+([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s+([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*\)",
    ]
    for p in pats:
        m = re.search(p, req, flags=re.IGNORECASE)
        if m:
            x = float(m.group(1))
            nx = x + delta
            repl = m.group(0).replace(m.group(1), f"{nx:.6g}", 1)
            return req[:m.start()] + repl + req[m.end():], {"parameter": "velocity", "old": x, "new": nx, "unit": "m/s"}

    p2 = r"velocity\s*(?:is|=|of)?\s*([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*m/s"
    m = re.search(p2, req, flags=re.IGNORECASE)
    if m:
        x = float(m.group(1))
        nx = x + delta
        repl = m.group(0).replace(m.group(1), f"{nx:.6g}", 1)
        return req[:m.start()] + repl + req[m.end():], {"parameter": "velocity", "old": x, "new": nx, "unit": "m/s"}

    return None, None


def adjust_viscosity(req: str, frac: float):
    p = r"(viscosity|kinematic viscosity|dynamic viscosity)[^\n\r]{0,80}?([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)"
    m = re.search(p, req, flags=re.IGNORECASE)
    if m:
        old = float(m.group(2))
        new = old * (1.0 + frac)
        repl = m.group(0).replace(m.group(2), f"{new:.6g}", 1)
        return req[:m.start()] + repl + req[m.end():], {"parameter": "viscosity", "old": old, "new": new, "scale": 1.0 + frac}
    return None, None


def adjust_density(req: str, frac: float):
    p = r"(density|rho)[^\n\r]{0,80}?([+-]?\d*\.?\d+(?:[eE][+-]?\d+)?)"
    m = re.search(p, req, flags=re.IGNORECASE)
    if m:
        old = float(m.group(2))
        new = old * (1.0 + frac)
        repl = m.group(0).replace(m.group(2), f"{new:.6g}", 1)
        return req[:m.start()] + repl + req[m.end():], {"parameter": "density", "old": old, "new": new, "scale": 1.0 + frac}
    return None, None


def build_variants(base_req: str, stages):
    variants = []
    if "velocity" in stages:
        for d in [0.5, 1.0, 1.5]:
            nr, meta = adjust_first_velocity(base_req, d)
            if nr:
                variants.append((f"vel_plus_{str(d).replace('.', 'p')}", nr, meta))

    if "viscosity" in stages:
        for frac in [-0.10, 0.10, 0.20]:
            nr, meta = adjust_viscosity(base_req, frac)
            if nr:
                tag = f"mu_{'m' if frac < 0 else 'p'}{int(abs(frac)*100)}pct"
                variants.append((tag, nr, meta))

    if "density" in stages:
        for frac in [-0.10, 0.10, 0.20]:
            nr, meta = adjust_density(base_req, frac)
            if nr:
                tag = f"rho_{'m' if frac < 0 else 'p'}{int(abs(frac)*100)}pct"
                variants.append((tag, nr, meta))

    seen = set()
    uniq = []
    for tag, req, meta in variants:
        if req not in seen:
            seen.add(req)
            uniq.append((tag, req, meta))
    return uniq


def run_foam_agent(foam_agent_dir: Path, openfoam_path: str, output_dir: Path, requirement_path: Path, timeout_sec: int):
    cmd = [
        "python", str(foam_agent_dir / "foambench_main.py"),
        "--openfoam_path", openfoam_path,
        "--output", str(output_dir),
        "--prompt_path", str(requirement_path),
    ]
    proc = subprocess.run(cmd, cwd=str(foam_agent_dir.parent), capture_output=True, text=True, timeout=timeout_sec)
    return proc.returncode, proc.stdout[-8000:], proc.stderr[-8000:]


def find_case_root(run_out: Path) -> Path:
    if not run_out.exists():
        return run_out
    direct = [(run_out / d).exists() for d in ["0", "constant", "system"]]
    if any(direct):
        return run_out
    subs = [p for p in run_out.iterdir() if p.is_dir()]
    for p in subs:
        if (p / "0").exists() or (p / "constant").exists() or (p / "system").exists():
            return p
    return run_out


def collect_generated_files(case_root: Path):
    """Collect only direct file entries from 0/, system/, and constant/.
    Excludes nested subdirectories (including constant/polyMesh) and time directories.
    """
    rows = []
    for sd in ["0", "system", "constant"]:
        base = case_root / sd
        if not base.exists() or not base.is_dir():
            continue
        for fp in base.iterdir():
            if fp.is_file():
                rel = f"{sd}/{fp.name}"
                rows.append((rel, fp))
    return rows


def expected_relpaths_from_group(grp_rows):
    expected = set()
    for r in grp_rows:
        fn = r.get("file_name")
        fd = r.get("folder_name")
        if isinstance(fn, str) and isinstance(fd, str):
            if fd in {".", "./", ""}:
                expected.add(fn)
            else:
                expected.add(f"{fd}/{fn}")
    return expected


def scope_expected_relpaths(expected_relpaths: set) -> set:
    """Keep only direct files in 0/, system/, and constant/."""
    scoped = set()
    for rel in expected_relpaths:
        if not isinstance(rel, str) or "/" not in rel:
            continue
        parts = rel.split("/")
        if len(parts) == 2 and parts[0] in {"0", "system", "constant"}:
            scoped.add(rel)
    return scoped


def case_success(case_root: Path, expected_relpaths: set):
    logs = list(case_root.glob("log*"))
    for lp in logs:
        try:
            txt = lp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "FOAM FATAL" in txt or "ERROR:" in txt:
            return False, f"fatal in {lp.name}"

    has_time = False
    for d in case_root.iterdir() if case_root.exists() else []:
        if d.is_dir() and d.name != "0":
            try:
                if float(d.name) > 0:
                    has_time = True
                    break
            except Exception:
                pass
    if not has_time:
        return False, "no positive time directory"

    generated = {rel for rel, _ in collect_generated_files(case_root)}
    missing_expected = sorted(list(expected_relpaths - generated))
    if missing_expected:
        return False, f"missing expected files: {missing_expected[:5]}"

    return True, "ok"


def main():
    ap = argparse.ArgumentParser(description="Controlled augmentation ladder with chunked parallel execution and immediate save")
    ap.add_argument("--input", default="foamgpt_train.jsonl", help="Input JSONL")
    ap.add_argument("--split", default="train")
    ap.add_argument("--openfoam-path", required=True)
    ap.add_argument("--foam-agent-dir", default="Foam-Agent")
    ap.add_argument("--work-dir", default="ladder_runs")
    ap.add_argument("--out-dir", default="ladder_outputs")
    ap.add_argument("--chunk-index", type=int, default=0)
    ap.add_argument("--chunk-count", type=int, default=6)
    ap.add_argument("--stages", default="velocity,viscosity,density")
    ap.add_argument("--timeout-sec", type=int, default=1800)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    input_path = root / args.input
    foam_agent_dir = (root / args.foam_agent_dir).resolve()
    work_dir = (root / args.work_dir / f"{args.split}_chunk{args.chunk_index}").resolve()
    out_dir = (root / args.out_dir).resolve()

    stages = {s.strip().lower() for s in args.stages.split(",") if s.strip()}

    rows = load_jsonl(input_path)
    groups = grouped_prompts(rows)

    accepted_cases_path = out_dir / f"accepted_cases_{args.split}_chunk{args.chunk_index}.jsonl"
    accepted_rows_path = out_dir / f"accepted_rows_{args.split}_chunk{args.chunk_index}.jsonl"
    failed_path = out_dir / f"failed_{args.split}_chunk{args.chunk_index}.jsonl"
    progress_path = out_dir / f"progress_{args.split}_chunk{args.chunk_index}.jsonl"

    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)

    for gidx, (user_prompt, grp_rows) in enumerate(groups.items()):
        rep = grp_rows[0]
        case_name = rep.get("case_name", f"case_{gidx}")
        bucket_key = f"{case_name}::{hashlib.md5(user_prompt.encode('utf-8')).hexdigest()}"
        if stable_bucket(bucket_key, args.chunk_count) != args.chunk_index:
            continue

        expected_relpaths = scope_expected_relpaths(expected_relpaths_from_group(grp_rows))

        base_req = extract_requirement(rep)
        if not base_req:
            append_jsonl(failed_path, {
                "time": datetime.utcnow().isoformat(),
                "case_name": case_name,
                "reason": "missing_base_requirement",
            })
            continue

        variants = build_variants(base_req, stages)
        if not variants:
            append_jsonl(progress_path, {
                "time": datetime.utcnow().isoformat(),
                "case_name": case_name,
                "status": "no_variants_for_selected_stages",
            })
            continue

        for tag, new_req, meta in variants:
            var_id = f"{case_name}__{tag}"
            var_dir = work_dir / var_id
            req_path = var_dir / "user_requirement.txt"
            run_out = var_dir / "run"
            var_dir.mkdir(parents=True, exist_ok=True)
            req_path.write_text(new_req, encoding="utf-8")

            rc, so, se = run_foam_agent(
                foam_agent_dir=foam_agent_dir,
                openfoam_path=args.openfoam_path,
                output_dir=run_out,
                requirement_path=req_path,
                timeout_sec=args.timeout_sec,
            )

            case_root = find_case_root(run_out)
            ok, reason = case_success(case_root, expected_relpaths)

            unsupported = ("unsupported_openfoam10_requirement" in so) or ("unsupported_openfoam10_requirement" in se)
            if unsupported:
                ok = False
                reason = "unsupported_openfoam10_requirement"

            case_record = {
                "time": datetime.utcnow().isoformat(),
                "case_name": case_name,
                "variant_id": var_id,
                "chunk_index": args.chunk_index,
                "meta": meta,
                "user_requirement": new_req,
                "user_prompt": f"user_requirement: {new_req}\n {PROMPT_SUFFIX}",
                "source_user_prompt": user_prompt,
                "model_provider": BEDROCK_PROVIDER,
                "model_version": BEDROCK_MODEL,
                "run_output_dir": str(run_out),
                "case_root": str(case_root),
                "return_code": rc,
                "success": bool(ok and rc == 0),
                "reason": reason,
            }

            if ok and rc == 0:
                append_jsonl(accepted_cases_path, case_record)

                generated_files = collect_generated_files(case_root)
                for rel, fp in generated_files:
                    try:
                        content = fp.read_text(encoding="utf-8", errors="ignore")
                    except Exception:
                        continue

                    row = dict(rep)
                    row["case_name"] = case_name
                    row["folder_name"] = "." if rel == "Allrun" else rel.rsplit("/", 1)[0]
                    row["file_name"] = rel if rel == "Allrun" else rel.rsplit("/", 1)[1]
                    row["file_content"] = content
                    row["user_requirement"] = new_req
                    row["user_prompt"] = f"user_requirement: {new_req}\n {PROMPT_SUFFIX}"
                    row["variant_id"] = var_id
                    row["parameter_change"] = meta
                    row["source_user_prompt"] = user_prompt
                    row["model_provider"] = BEDROCK_PROVIDER
                    row["model_version"] = BEDROCK_MODEL
                    row["generated_from_case_root"] = str(case_root)

                    append_jsonl(accepted_rows_path, row)
            else:
                case_record["stdout_tail"] = so
                case_record["stderr_tail"] = se
                append_jsonl(failed_path, case_record)

            append_jsonl(progress_path, {
                "time": datetime.utcnow().isoformat(),
                "case_name": case_name,
                "variant_id": var_id,
                "status": "done",
                "success": bool(ok and rc == 0),
                "reason": reason,
            })


if __name__ == "__main__":
    main()
