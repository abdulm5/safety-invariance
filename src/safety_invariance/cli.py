from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from safety_invariance.benchmark_importers import builtin_suite, huggingface_suite, write_task_suite
from safety_invariance.calibration import calibrate_selective_precision
from safety_invariance.config import load_run_config
from safety_invariance.diagnostics import write_diagnostic_report
from safety_invariance.evaluation import load_score_bundle, with_retention, write_score_bundle
from safety_invariance.external import run_agentdojo, run_agentharm, run_toolsandbox
from safety_invariance.external_study import (
    load_external_study,
    run_external_study,
    validate_external_study,
    write_external_study_plan,
)
from safety_invariance.matrix import expand_matrix, load_collection_matrix, run_collection_matrix, validate_matrix
from safety_invariance.margin_calibration import collect_action_margins
from safety_invariance.mechanistic import analyze_mechanistic_divergence
from safety_invariance.native_report import write_native_external_report
from safety_invariance.openai_compat import load_model_profile, serve_profile
from safety_invariance.preflight import run_preflight
from safety_invariance.reporting import write_markdown_report
from safety_invariance.rescoring import rescore_run_dirs
from safety_invariance.runner import run_experiment, write_summary_csv
from safety_invariance.schemas import (
    ModelSpec,
    RunConfig,
    TransformSpec,
)
from safety_invariance.selective_audit import score_selective_audit, write_selective_audit
from safety_invariance.selective_precision import (
    analyze_selective_calibration,
    load_selective_precision_study,
    write_selective_calibration_matrix,
    write_selective_precision_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        print(f"error: {message}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="si", description="Safety Invariance experiment CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run one experiment config")
    run_parser.add_argument("--config", required=True, help="Path to JSON/YAML run config")
    run_parser.set_defaults(func=cmd_run)

    score_parser = subparsers.add_parser("score", help="Compute retention against an FP16 baseline")
    score_parser.add_argument("--run-dir", required=True, help="Run directory containing scores.json")
    score_parser.add_argument("--baseline-run-dir", help="FP16 baseline run directory containing scores.json")
    score_parser.set_defaults(func=cmd_score)

    rescore_parser = subparsers.add_parser("rescore", help="Recompute scores from existing events.jsonl artifacts")
    rescore_parser.add_argument("--runs", required=True, help="Glob for run dirs containing events.jsonl")
    rescore_parser.add_argument("--baseline-transform", default="fp16", help="Baseline transform name")
    rescore_parser.add_argument("--report", help="Optional Markdown report path to regenerate after rescoring")
    rescore_parser.set_defaults(func=cmd_rescore)

    report_parser = subparsers.add_parser("report", help="Generate a Markdown report from run dirs")
    report_parser.add_argument("--runs", required=True, help="Glob for run dirs or scores.json files")
    report_parser.add_argument("--out", required=True, help="Output Markdown path")
    report_parser.set_defaults(func=cmd_report)

    diagnose_parser = subparsers.add_parser("diagnose", help="Compare transformed runs against matching baselines")
    diagnose_parser.add_argument("--runs", required=True, help="Glob for run dirs or scores.json files")
    diagnose_parser.add_argument("--out", required=True, help="Output Markdown path")
    diagnose_parser.add_argument("--baseline-transform", default="fp16", help="Baseline transform name")
    diagnose_parser.set_defaults(func=cmd_diagnose)

    smoke_parser = subparsers.add_parser("smoke", help="Run no-GPU mock smoke experiments")
    smoke_parser.add_argument("--out", default="runs/smoke", help="Output directory for smoke runs")
    smoke_parser.set_defaults(func=cmd_smoke)

    collect_parser = subparsers.add_parser("collect", help="Run or dry-run a data-collection matrix")
    collect_parser.add_argument("--matrix", required=True, help="Path to collection matrix JSON/YAML")
    collect_parser.add_argument("--dry-run", action="store_true", help="Write plan and validate without running models")
    collect_parser.add_argument("--no-skip-existing", action="store_true", help="Re-run directories that already have scores")
    collect_parser.set_defaults(func=cmd_collect)

    validate_parser = subparsers.add_parser("validate", help="Validate a collection matrix and task suites")
    validate_parser.add_argument("--matrix", required=True, help="Path to collection matrix JSON/YAML")
    validate_parser.set_defaults(func=cmd_validate)

    preflight_parser = subparsers.add_parser("preflight", help="Check a GPU instance before running a matrix")
    preflight_parser.add_argument("--matrix", required=True, help="Path to collection matrix JSON/YAML")
    preflight_parser.add_argument("--check-hf-access", action="store_true", help="Call Hugging Face Hub model_info for target models")
    preflight_parser.set_defaults(func=cmd_preflight)

    suite_parser = subparsers.add_parser("make-suite", help="Materialize built-in or Hugging Face benchmark tasks")
    suite_parser.add_argument(
        "--source",
        required=True,
        help="utility_core, chat_safety, situational_awareness, agentharm_lite, gsm8k, mmlu, mbpp, or humaneval",
    )
    suite_parser.add_argument("--out", required=True, help="Output task-suite JSON")
    suite_parser.add_argument("--limit", type=int, default=None, help="Maximum tasks to write")
    suite_parser.add_argument("--dataset-id", help="Override Hugging Face dataset id")
    suite_parser.add_argument("--dataset-config", help="Override Hugging Face dataset config/name")
    suite_parser.add_argument("--split", default="test", help="Dataset split for Hugging Face imports")
    suite_parser.set_defaults(func=cmd_make_suite)

    calibrate_parser = subparsers.add_parser(
        "calibrate-selective",
        help="Generate selective-precision transform from baseline/candidate traces",
    )
    calibrate_parser.add_argument("--baseline-run-dir", required=True)
    calibrate_parser.add_argument("--candidate-run-dir", required=True)
    calibrate_parser.add_argument("--out", required=True)
    calibrate_parser.add_argument("--max-modules", type=int, default=4)
    calibrate_parser.set_defaults(func=cmd_calibrate_selective)

    selective_plan_parser = subparsers.add_parser(
        "selective-plan",
        help="Generate the single-block causal calibration matrix for a selective-precision study",
    )
    selective_plan_parser.add_argument("--study", required=True, help="Selective-precision study JSON/YAML")
    selective_plan_parser.add_argument("--out", help="Override generated calibration matrix path")
    selective_plan_parser.set_defaults(func=cmd_selective_plan)

    selective_analyze_parser = subparsers.add_parser(
        "selective-analyze",
        help="Rank restored blocks and generate the held-out selective-precision matrix",
    )
    selective_analyze_parser.add_argument("--study", required=True, help="Selective-precision study JSON/YAML")
    selective_analyze_parser.add_argument("--run-root", help="Override calibration run root")
    selective_analyze_parser.add_argument("--out", help="Override selection artifact path")
    selective_analyze_parser.add_argument(
        "--evaluation-matrix-out",
        help="Override generated held-out evaluation matrix path",
    )
    selective_analyze_parser.set_defaults(func=cmd_selective_analyze)

    margin_collect_parser = subparsers.add_parser(
        "selective-margin-collect",
        help="Collect preferred-vs-dispreferred completion margins for every block intervention",
    )
    margin_collect_parser.add_argument("--study", required=True, help="Selective-precision study JSON/YAML")
    margin_collect_parser.add_argument("--out", help="Override action-margin artifact path")
    margin_collect_parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Discard an existing margin artifact and recompute every transform",
    )
    margin_collect_parser.set_defaults(func=cmd_selective_margin_collect)

    selective_report_parser = subparsers.add_parser(
        "selective-report",
        help="Generate paired held-out statistics for a selective-precision study",
    )
    selective_report_parser.add_argument("--study", required=True, help="Selective-precision study JSON/YAML")
    selective_report_parser.add_argument("--run-root", help="Override held-out evaluation run root")
    selective_report_parser.add_argument("--out", help="Override Markdown report path")
    selective_report_parser.add_argument("--bootstrap-samples", type=int, default=5000)
    selective_report_parser.set_defaults(func=cmd_selective_report)

    selective_audit_parser = subparsers.add_parser(
        "selective-audit",
        help="Create a blinded FP16/quantized/intervention human-audit packet",
    )
    selective_audit_parser.add_argument("--study", required=True)
    selective_audit_parser.add_argument("--intervention-transform", required=True)
    selective_audit_parser.add_argument("--candidate-transform")
    selective_audit_parser.add_argument("--run-root")
    selective_audit_parser.add_argument("--out", required=True, help="Output Markdown packet path")
    selective_audit_parser.add_argument("--non-flip-sample", type=int, default=12)
    selective_audit_parser.add_argument("--seed", type=int)
    selective_audit_parser.set_defaults(func=cmd_selective_audit)

    selective_audit_score_parser = subparsers.add_parser(
        "selective-audit-score",
        help="Score completed blinded audit annotations and calculate agreement",
    )
    selective_audit_score_parser.add_argument("--key", required=True, help="Audit .key.json path")
    selective_audit_score_parser.add_argument(
        "--annotations",
        action="append",
        required=True,
        help="Completed annotation CSV; pass once per annotator",
    )
    selective_audit_score_parser.add_argument("--out", required=True)
    selective_audit_score_parser.set_defaults(func=cmd_selective_audit_score)

    mechanism_parser = subparsers.add_parser(
        "mechanistic-analyze",
        help="Compare FP16 and quantized hidden states, logits, and safety action margins",
    )
    mechanism_parser.add_argument("--study", required=True, help="Selective-precision study JSON/YAML")
    mechanism_parser.add_argument("--split", choices=("calibration", "evaluation"), default="calibration")
    mechanism_parser.add_argument("--out", required=True, help="Output analysis JSON")
    mechanism_parser.add_argument("--selection-artifact", help="Override causal selection artifact")
    mechanism_parser.set_defaults(func=cmd_mechanistic_analyze)

    dojo_parser = subparsers.add_parser("run-agentdojo", help="Run AgentDojo's native benchmark script")
    dojo_parser.add_argument("--model", required=True, help="AgentDojo model registry id")
    dojo_parser.add_argument("--out-dir", required=True)
    dojo_parser.add_argument("--suite")
    dojo_parser.add_argument("--attack", default="tool_knowledge")
    dojo_parser.add_argument("--defense", default="tool_filter")
    dojo_parser.add_argument("--user-task", action="append", default=[])
    dojo_parser.add_argument("--extra-arg", action="append", default=[])
    dojo_parser.add_argument("--dry-run", action="store_true")
    dojo_parser.set_defaults(func=cmd_run_agentdojo)

    sandbox_parser = subparsers.add_parser("run-toolsandbox", help="Run ToolSandbox's native CLI and capture output")
    sandbox_parser.add_argument("--agent", required=True, help="ToolSandbox agent id")
    sandbox_parser.add_argument("--out-dir", required=True)
    sandbox_parser.add_argument("--user", default="GPT_4_o_2024_05_13")
    sandbox_parser.add_argument("--scenario")
    sandbox_parser.add_argument("--extra-arg", action="append", default=[])
    sandbox_parser.add_argument("--dry-run", action="store_true")
    sandbox_parser.set_defaults(func=cmd_run_toolsandbox)

    agentharm_parser = subparsers.add_parser("run-agentharm", help="Run Inspect's native AgentHarm evaluation")
    agentharm_parser.add_argument("--model", required=True, help="Inspect model id")
    agentharm_parser.add_argument("--out-dir", required=True)
    agentharm_parser.add_argument("--task", default="agentharm", choices=("agentharm", "agentharm_benign"))
    agentharm_parser.add_argument("--split", default="test_public")
    agentharm_parser.add_argument("--refusal-judge")
    agentharm_parser.add_argument("--semantic-judge")
    agentharm_parser.add_argument("--extra-arg", action="append", default=[])
    agentharm_parser.add_argument("--dry-run", action="store_true")
    agentharm_parser.set_defaults(func=cmd_run_agentharm)

    serve_parser = subparsers.add_parser(
        "serve-openai",
        help="Serve one exact local model profile through an OpenAI-compatible endpoint",
    )
    serve_parser.add_argument("--profile", required=True, help="Model profile JSON/YAML")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--telemetry", help="Optional JSONL request telemetry path")
    serve_parser.set_defaults(func=cmd_serve_openai)

    external_plan_parser = subparsers.add_parser(
        "external-plan",
        help="Validate and materialize a native external-benchmark study plan",
    )
    external_plan_parser.add_argument("--study", required=True)
    external_plan_parser.add_argument("--check-runtime", action="store_true")
    external_plan_parser.set_defaults(func=cmd_external_plan)

    external_collect_parser = subparsers.add_parser(
        "external-collect",
        help="Run native benchmarks against exact local transformed model profiles",
    )
    external_collect_parser.add_argument("--study", required=True)
    external_collect_parser.add_argument("--profile", action="append", default=[])
    external_collect_parser.add_argument("--benchmark", action="append", default=[])
    external_collect_parser.add_argument("--dry-run", action="store_true")
    external_collect_parser.add_argument("--no-skip-existing", action="store_true")
    external_collect_parser.set_defaults(func=cmd_external_collect)

    external_report_parser = subparsers.add_parser(
        "external-report",
        help="Generate aggregate native AgentDojo/AgentHarm report from completed external runs",
    )
    external_report_parser.add_argument(
        "--root",
        action="append",
        required=True,
        help="External study output root; pass multiple times to merge roots",
    )
    external_report_parser.add_argument("--out", required=True, help="Output Markdown path")
    external_report_parser.add_argument("--json-out", help="Optional JSON artifact path")
    external_report_parser.add_argument("--baseline-profile", default="qwen25_3b_fp16")
    external_report_parser.set_defaults(func=cmd_external_report)
    return parser


def cmd_run(args: argparse.Namespace) -> int:
    config = load_run_config(args.config)
    bundle = run_experiment(config)
    print(json.dumps({"run_dir": str(config.run_dir), "utility_score": bundle.utility_score, "safety_score": bundle.safety_score}))
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    bundle = load_score_bundle(run_dir / "scores.json")
    if args.baseline_run_dir:
        baseline = load_score_bundle(Path(args.baseline_run_dir) / "scores.json")
    else:
        if bundle.transform not in {"fp16", "baseline"}:
            raise ValueError("--baseline-run-dir is required for transformed runs")
        baseline = bundle
    scored = with_retention(bundle, baseline)
    write_score_bundle(run_dir / "scores.json", scored)
    write_summary_csv(run_dir / "summary.csv", scored)
    print(json.dumps(scored.retention, sort_keys=True))
    return 0


def cmd_rescore(args: argparse.Namespace) -> int:
    result = rescore_run_dirs(
        args.runs,
        baseline_transform=args.baseline_transform,
        report_path=args.report,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    output = write_markdown_report(args.runs, args.out)
    print(str(output))
    return 0


def cmd_diagnose(args: argparse.Namespace) -> int:
    output = write_diagnostic_report(args.runs, args.out, baseline_transform=args.baseline_transform)
    print(str(output))
    return 0


def cmd_smoke(args: argparse.Namespace) -> int:
    run_smoke(Path(args.out))
    print(json.dumps({"smoke_dir": str(args.out), "report": str(Path(args.out) / "summary.md")}))
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    result = run_collection_matrix(
        args.matrix,
        dry_run=args.dry_run,
        skip_existing=not args.no_skip_existing,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    matrix = load_collection_matrix(args.matrix)
    runs = expand_matrix(matrix)
    result = validate_matrix(matrix, runs)
    print(json.dumps(result, sort_keys=True))
    return 1 if result["errors"] else 0


def cmd_preflight(args: argparse.Namespace) -> int:
    result = run_preflight(args.matrix, check_hf_access=args.check_hf_access)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["errors"] else 0


def cmd_make_suite(args: argparse.Namespace) -> int:
    hf_sources = {"gsm8k", "mmlu", "mbpp", "humaneval"}
    if args.source in hf_sources:
        suite_id, description, tasks = huggingface_suite(
            args.source,
            dataset_id=args.dataset_id,
            dataset_config=args.dataset_config,
            split=args.split,
            limit=args.limit or 100,
        )
    else:
        suite_id, description, tasks = builtin_suite(args.source, limit=args.limit)
    output = write_task_suite(args.out, suite_id, description, tasks)
    print(json.dumps({"out": str(output), "suite_id": suite_id, "task_count": len(tasks)}))
    return 0


def cmd_calibrate_selective(args: argparse.Namespace) -> int:
    payload = calibrate_selective_precision(
        baseline_run_dir=args.baseline_run_dir,
        candidate_run_dir=args.candidate_run_dir,
        out=args.out,
        max_modules=args.max_modules,
    )
    print(json.dumps({"out": args.out, "selected_modules": payload["selected_modules"]}, sort_keys=True))
    return 0


def cmd_selective_plan(args: argparse.Namespace) -> int:
    study = load_selective_precision_study(args.study)
    output = args.out or f"configs/generated/{study.name}_calibration_matrix.json"
    path = write_selective_calibration_matrix(study, output)
    print(
        json.dumps(
            {
                "study": study.name,
                "matrix_path": str(path),
                "run_count": len(study.blocks) + 2,
            },
            sort_keys=True,
        )
    )
    return 0


def cmd_selective_analyze(args: argparse.Namespace) -> int:
    study = load_selective_precision_study(args.study)
    result = analyze_selective_calibration(
        study,
        run_root=args.run_root,
        out=args.out,
        evaluation_matrix_out=args.evaluation_matrix_out,
    )
    print(
        json.dumps(
            {
                "study": study.name,
                "ranking_method": result["ranking_method"],
                "baseline_regression_count": result["baseline_regression_count"],
                "calibration_artifact_path": result["calibration_artifact_path"],
                "evaluation_matrix_path": result["evaluation_matrix_path"],
                "top_blocks": result["safety_ranking"][:10],
            },
            sort_keys=True,
        )
    )
    return 0


def cmd_selective_margin_collect(args: argparse.Namespace) -> int:
    study = load_selective_precision_study(args.study)

    def report_progress(transform: str, completed: int, total: int) -> None:
        print(
            json.dumps(
                {
                    "transform": transform,
                    "completed": completed,
                    "total": total,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    result = collect_action_margins(
        study,
        out=args.out,
        skip_existing=not args.no_skip_existing,
        on_completed=report_progress,
    )
    print(
        json.dumps(
            {
                "study": study.name,
                "artifact_path": args.out or study.margin_artifact_path,
                "complete": result["complete"],
                "completed_transforms": len(result["completed_transforms"]),
            },
            sort_keys=True,
        )
    )
    return 0


def cmd_selective_report(args: argparse.Namespace) -> int:
    study = load_selective_precision_study(args.study)
    path = write_selective_precision_report(
        study,
        run_root=args.run_root,
        out=args.out,
        bootstrap_samples=args.bootstrap_samples,
    )
    print(str(path))
    return 0


def cmd_selective_audit(args: argparse.Namespace) -> int:
    study = load_selective_precision_study(args.study)
    result = write_selective_audit(
        study,
        intervention_transform=args.intervention_transform,
        candidate_transform=args.candidate_transform,
        run_root=args.run_root,
        out=args.out,
        non_flip_sample=args.non_flip_sample,
        seed=args.seed,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def cmd_selective_audit_score(args: argparse.Namespace) -> int:
    result = score_selective_audit(
        key_path=args.key,
        annotation_paths=args.annotations,
        out=args.out,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def cmd_mechanistic_analyze(args: argparse.Namespace) -> int:
    study = load_selective_precision_study(args.study)
    result = analyze_mechanistic_divergence(
        study,
        split=args.split,
        out=args.out,
        selection_artifact=args.selection_artifact,
    )
    print(
        json.dumps(
            {
                "study": study.name,
                "split": args.split,
                "out": args.out,
                "task_count": result["task_count"],
                "causal_score_correlation": result["causal_score_correlation"],
            },
            sort_keys=True,
        )
    )
    return 0


def cmd_run_agentdojo(args: argparse.Namespace) -> int:
    result = run_agentdojo(
        model=args.model,
        out_dir=args.out_dir,
        suite=args.suite,
        attack=args.attack,
        defense=args.defense,
        user_tasks=tuple(args.user_task),
        extra_args=tuple(args.extra_arg),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def cmd_run_toolsandbox(args: argparse.Namespace) -> int:
    result = run_toolsandbox(
        agent=args.agent,
        out_dir=args.out_dir,
        user=args.user,
        scenario=args.scenario,
        extra_args=tuple(args.extra_arg),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def cmd_run_agentharm(args: argparse.Namespace) -> int:
    result = run_agentharm(
        model=args.model,
        out_dir=args.out_dir,
        task=args.task,
        split=args.split,
        refusal_judge=args.refusal_judge,
        semantic_judge=args.semantic_judge,
        extra_args=tuple(args.extra_arg),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def cmd_serve_openai(args: argparse.Namespace) -> int:
    profile = load_model_profile(args.profile)
    serve_profile(
        profile,
        host=args.host,
        port=args.port,
        telemetry_path=args.telemetry,
    )
    return 0


def cmd_external_plan(args: argparse.Namespace) -> int:
    study = load_external_study(args.study)
    validation = validate_external_study(study, check_runtime=args.check_runtime)
    path = write_external_study_plan(study)
    print(
        json.dumps(
            {
                "study": study.name,
                "run_count": len(study.profiles) * len(study.benchmarks),
                "plan_path": str(path),
                "validation": validation,
            },
            sort_keys=True,
        )
    )
    return 1 if validation["errors"] else 0


def cmd_external_collect(args: argparse.Namespace) -> int:
    study = load_external_study(args.study)
    result = run_external_study(
        study,
        dry_run=args.dry_run,
        skip_existing=not args.no_skip_existing,
        profile_names=set(args.profile) or None,
        benchmark_names=set(args.benchmark) or None,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def cmd_external_report(args: argparse.Namespace) -> int:
    path = write_native_external_report(
        args.root,
        args.out,
        baseline_profile=args.baseline_profile,
        json_out=args.json_out,
    )
    print(str(path))
    return 0


def run_smoke(out_dir: Path) -> None:
    task_paths = ("data/tasks/agentdojo_minimal.json", "data/tasks/custom_safety.json")
    fp16 = RunConfig(
        run_name="mock_fp16",
        output_dir=str(out_dir / "fp16"),
        model=ModelSpec(provider="mock", model_id="mock-safe-agent"),
        transform=TransformSpec(name="fp16", quantization="none"),
        task_paths=task_paths,
        seeds=(0,),
        mitigation={"triggered_escalation": {"enabled": True}},
        metadata={"smoke": True},
    )
    four_bit = RunConfig(
        run_name="mock_nf4_4bit",
        output_dir=str(out_dir / "nf4_4bit"),
        model=ModelSpec(provider="mock", model_id="mock-safe-agent"),
        transform=TransformSpec(name="nf4_4bit", quantization="nf4_4bit", load_in_4bit=True),
        task_paths=task_paths,
        seeds=(0,),
        mitigation={"triggered_escalation": {"enabled": True}},
        metadata={"smoke": True},
    )
    baseline = run_experiment(fp16)
    transformed = run_experiment(four_bit)
    transformed = with_retention(transformed, baseline)
    write_score_bundle(out_dir / "nf4_4bit" / "scores.json", transformed)
    write_summary_csv(out_dir / "nf4_4bit" / "summary.csv", transformed)
    baseline = with_retention(baseline, baseline)
    write_score_bundle(out_dir / "fp16" / "scores.json", baseline)
    write_summary_csv(out_dir / "fp16" / "summary.csv", baseline)
    write_markdown_report(str(out_dir / "*"), out_dir / "summary.md")


if __name__ == "__main__":
    raise SystemExit(main())
