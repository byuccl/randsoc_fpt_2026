"""Shared plotting helpers for the RandSoC figure scripts."""

from contextlib import contextmanager
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # pylint: disable=wrong-import-position

# Output formats written by figure(); overridden from each script's --formats.
FORMATS = ["png"]
DPI = 150


def parse_formats(spec: str) -> list[str]:
    """Turn a '--formats png,pdf' string into a list of extensions."""
    fmts = [f.strip().lstrip(".").lower() for f in spec.split(",")]
    fmts = [f for f in fmts if f]
    if not fmts:
        raise ValueError("no output format given")
    return fmts


def add_common_args(parser, csv_help: str) -> None:
    """Add the --csv / --out-dir / --formats arguments shared by every script."""
    parser.add_argument("--csv", type=Path, required=True, help=csv_help)
    parser.add_argument(
        "--out-dir", type=Path, default=Path("images"),
        help="Directory the figures are written to (default: images)",
    )
    parser.add_argument(
        "--formats", default="png",
        help="Comma-separated output formats, e.g. png or png,pdf (default: png)",
    )


@contextmanager
def figure(out_stem, figsize=(8, 4), subplot_kw=None, savefig_kw=None):
    """Create a single-axes figure, yield (fig, ax), then save it as its own file.

    ``out_stem`` is the output path without an extension; one file is written
    per entry in FORMATS. ``subplot_kw`` is forwarded to plt.subplots (e.g.
    ``dict(polar=True)``); ``savefig_kw`` to ``fig.savefig`` (e.g.
    ``dict(bbox_inches="tight")``).
    """
    fig, ax = plt.subplots(figsize=figsize, subplot_kw=subplot_kw)
    yield fig, ax
    fig.tight_layout()
    out_stem = Path(out_stem)
    for fmt in FORMATS:
        path = out_stem.with_name(f"{out_stem.name}.{fmt}")
        fig.savefig(path, dpi=DPI, **(savefig_kw or {}))
        print(f"Saved {path}")
    plt.close(fig)
