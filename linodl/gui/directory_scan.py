"""Filesystem helpers used by GUI panels."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DirectoryInfo:
    name: str
    text_count: int
    image_count: int = 0


def scan_download_directories(output_dir: str, include_images: bool = False) -> list[DirectoryInfo]:
    if not os.path.isdir(output_dir):
        raise NotADirectoryError(output_dir)

    directories = []
    for name in sorted(os.listdir(output_dir)):
        path = os.path.join(output_dir, name)
        if not os.path.isdir(path):
            continue

        text_count = len([
            filename for filename in os.listdir(path)
            if filename.endswith(".txt")
        ])
        image_count = 0
        if include_images:
            image_dir = os.path.join(path, "插图")
            image_count = len(os.listdir(image_dir)) if os.path.isdir(image_dir) else 0
        directories.append(DirectoryInfo(name, text_count, image_count))

    return directories
