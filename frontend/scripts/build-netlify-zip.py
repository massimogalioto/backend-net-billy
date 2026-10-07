"""Package the already generated Netlify export, with index.html at ZIP root."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


def build_zip():
    frontend = Path(__file__).resolve().parent.parent
    export = frontend / "netlify-upload"
    if not (export / "index.html").is_file():
        raise SystemExit("Generate the static export first: scripts/build-static.mjs")
    destination = frontend / "net-billy-netlify-upload.zip"
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for source in sorted(export.rglob("*")):
            if source.is_file():
                archive.write(source, source.relative_to(export).as_posix())
    with ZipFile(destination) as archive:
        assert "index.html" in archive.namelist()
        assert "cte/archivio/index.html" in archive.namelist()
        assert archive.testzip() is None
    print(destination)
    return destination


if __name__ == "__main__":
    build_zip()
