"""The Untold Game — BANNER stage entrypoint.

Generate the channel banner + write the channel description for manual upload.

Usage:
  python3 -m engine.run_banner
Then upload channel/banner.png as channel art and paste channel/description.txt
into the channel "About" in YouTube Studio.
"""
from __future__ import annotations
import os

from engine import config, paths
from engine.pipeline import banner


def main() -> None:
    banner.compose_banner(paths.channel_banner_path())
    desc_path = paths.channel_description_path()
    os.makedirs(os.path.dirname(desc_path) or ".", exist_ok=True)
    with open(desc_path, "w") as f:
        f.write(config.CHANNEL_DESCRIPTION.strip() + "\n")
    print(f"✓ banner      → {paths.channel_banner_path()}")
    print(f"✓ description → {desc_path}")
    print("Upload the banner as channel art and paste the description into 'About' in YouTube Studio.")


if __name__ == "__main__":
    main()
