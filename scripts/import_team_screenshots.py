"""Produce a review-only JSON draft; never writes a saved team or current roster."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from champion_assistant.data.references import ReferenceCatalog
from champion_assistant.data.storage import save_json
from champion_assistant.teams import TeamRules
from champion_assistant.team_import import ScreenshotImporter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ability', required=True)
    parser.add_argument('--status', required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/team-import/draft.json')
    args = parser.parse_args()
    result = ScreenshotImporter(TeamRules(ReferenceCatalog(ROOT/'pokemon'))).run(args.ability, args.status, print)
    save_json(args.output, result)
    print(f'已输出待核对草稿：{args.output}')
    print(result['notice'])


if __name__ == '__main__':
    main()
