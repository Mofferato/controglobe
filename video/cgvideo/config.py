"""Load config/project.yaml and resolve the project's paths."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


@dataclass
class Paths:
    root: pathlib.Path
    data: pathlib.Path
    cache: pathlib.Path
    build: pathlib.Path
    output: pathlib.Path

    @property
    def mesh(self) -> pathlib.Path:
        return self.build / "mesh.gpkg"

    @property
    def history(self) -> pathlib.Path:
        return self.build / "history.gpkg"

    @property
    def maps(self) -> pathlib.Path:
        return self.build / "maps"

    @property
    def frames(self) -> pathlib.Path:
        return self.output / "frames"

    @property
    def sequence(self) -> pathlib.Path:
        return self.output / "sequence"

    @property
    def qa(self) -> pathlib.Path:
        return self.output / "qa"


def load_config(path: str | pathlib.Path | None = None) -> dict:
    path = pathlib.Path(path) if path else ROOT / "config" / "project.yaml"
    with open(path, encoding="utf8") as fh:
        cfg = yaml.safe_load(fh)
    base = path.resolve().parent.parent
    p = cfg.get("paths", {})
    cfg["_paths"] = Paths(
        root=base,
        data=base / p.get("data", "data"),
        cache=base / p.get("cache", "cache"),
        build=base / p.get("build", "build"),
        output=base / p.get("output", "output"),
    )
    return cfg


def paths(cfg: dict) -> Paths:
    return cfg["_paths"]
