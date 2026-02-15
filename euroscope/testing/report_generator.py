import argparse
import asyncio
from pathlib import Path

from euroscope.testing.behavioral_validator import BehavioralValidator


def _parse_args():
    parser = argparse.ArgumentParser(description="Generate behavioral validation report")
    parser.add_argument("--output", default="behavioral_report.md")
    return parser.parse_args()


async def _run(output_path: str):
    validator = BehavioralValidator()
    scenarios = validator.load_default_scenarios()
    results = await validator.run_suite(scenarios)
    report = validator.render_report(results)
    path = Path(output_path)
    path.write_text(report, encoding="utf-8")
    return str(path.resolve())


def main():
    args = _parse_args()
    output_path = asyncio.run(_run(args.output))
    print(output_path)


if __name__ == "__main__":
    main()
