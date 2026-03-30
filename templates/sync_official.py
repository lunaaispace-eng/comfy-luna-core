"""Sync official workflow templates from Comfy-Org/workflow_templates.

Downloads blueprint JSON files from the official repository into
templates/official/ for the workflow registry to index.

Usage:
    python -m luna_core.templates.sync_official
"""

import json
import logging
import os
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger("luna_core.templates.sync")

REPO = "Comfy-Org/workflow_templates"
BRANCH = "main"
INDEX_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/blueprints/index.json"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/blueprints"
OUTPUT_DIR = Path(__file__).parent / "official"


def fetch_json(url: str) -> dict:
    """Fetch JSON from a URL."""
    req = Request(url, headers={"User-Agent": "comfy-luna-core"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def sync(output_dir: Path = OUTPUT_DIR) -> int:
    """Download official workflow blueprints.

    Returns:
        Number of workflows downloaded.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fetch the index
    try:
        index = fetch_json(INDEX_URL)
    except (URLError, json.JSONDecodeError) as e:
        logger.error("Could not fetch template index: %s", e)
        return 0

    # Save the index itself
    index_path = output_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    # Extract blueprint entries from the index
    # Index is an array of modules, each with a "blueprints" array
    blueprint_names = set()
    if isinstance(index, list):
        for module in index:
            if isinstance(module, dict):
                for bp in module.get("blueprints", []):
                    name = bp.get("name", "")
                    if name:
                        blueprint_names.add(name)
    elif isinstance(index, dict):
        for bp in index.get("blueprints", index.get("templates", [])):
            name = bp.get("name", "") if isinstance(bp, dict) else ""
            if name:
                blueprint_names.add(name)

    # Download each blueprint workflow JSON
    downloaded = 0
    for name in sorted(blueprint_names):
        filename = f"{name}.json"
        url = f"{RAW_BASE}/{filename}"

        try:
            req = Request(url, headers={"User-Agent": "comfy-luna-core"})
            with urlopen(req, timeout=30) as resp:
                data = resp.read()
            (output_dir / filename).write_bytes(data)
            downloaded += 1
            logger.debug("Downloaded: %s", filename)
        except URLError:
            logger.debug("Could not download: %s", filename)

    logger.info("Synced %d official workflow templates", downloaded)
    return downloaded


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = sync()
    print(f"Downloaded {count} official workflow templates to {OUTPUT_DIR}")
