from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DesktopAssets:
    index_file: Path

    @property
    def url(self) -> str:
        return self.index_file.as_uri()

    @classmethod
    def resolve(cls, project_root: Path | None = None) -> "DesktopAssets":
        root = project_root or Path(__file__).resolve().parents[2]
        index_file = (root / "frontend" / "dist" / "index.html").resolve()
        if not index_file.is_file():
            raise FileNotFoundError(
                "React desktop assets are missing. Run: cd frontend; npm install; npm run build"
            )
        return cls(index_file=index_file)
