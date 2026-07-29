"""EPUB export from downloaded novel files."""

import os
import re

from ..models.novel import NovelInfo, Volume, chapter_source_filename


class EpubExporter:
    def export(
        self,
        novel_info: NovelInfo,
        volumes: list[Volume],
        base_dir: str,
        output_path: str = None,
        per_volume: bool = True,
    ) -> str | list[str]:
        """Export downloaded .txt and image files to EPUB.

        When per_volume is True, returns a list of paths (one per volume).
        Otherwise returns a single path for the combined EPUB."""
        if per_volume:
            paths = []
            for vol in volumes:
                vol_path = os.path.join(base_dir, vol.name)
                if not os.path.isdir(vol_path):
                    continue
                safe_title = self._sanitize(novel_info.title or "novel")
                safe_vol = self._sanitize(vol.name)
                vol_output = os.path.join(base_dir, f"{safe_title} - {safe_vol}.epub")
                path = self._build_epub(novel_info, [vol], base_dir, vol_output)
                if path:
                    paths.append(path)
            if not paths:
                raise ValueError("No volume directories found to export")
            return paths

        if output_path is None:
            safe_name = self._sanitize(novel_info.title or "novel")
            output_path = os.path.join(base_dir, f"{safe_name}.epub")
        return self._build_epub(novel_info, volumes, base_dir, output_path)

    def _build_epub(
        self,
        novel_info: NovelInfo,
        volumes: list[Volume],
        base_dir: str,
        output_path: str,
    ) -> str | None:
        from ebooklib import epub

        book = epub.EpubBook()
        book.set_title(novel_info.title or "Unknown Novel")
        if novel_info.author:
            book.add_author(novel_info.author)
        book.set_language("zh")
        book.add_metadata("DC", "publisher", "linodl")
        book.add_metadata("DC", "source", novel_info.catalog_url or "")

        spine = ["nav"]
        toc_items = []
        all_items = []
        all_image_names = set()

        for vol in volumes:
            vol_path = os.path.join(base_dir, vol.name)
            if not os.path.isdir(vol_path):
                continue

            illus_dir = self._find_illus_dir(vol_path)
            vol_items = []

            for ch in vol.chapters:
                if ch.is_illustration:
                    continue
                canonical_fname = f"{ch.index:03d}_{self._sanitize(ch.title)}.txt"
                fname = chapter_source_filename(ch, canonical_fname)
                fpath = os.path.join(vol_path, fname)
                if not os.path.exists(fpath):
                    continue
                with open(fpath, "r", encoding="utf-8") as f:
                    text = f.read()

                # Collect inline image references from the text
                inline_imgs = set()
                for m in re.finditer(r"\[IMG:([^\]]+)\]", text):
                    inline_imgs.add(m.group(1))

                chapter = epub.EpubHtml(
                    title=ch.title,
                    file_name=f"{self._sanitize(vol.name)}_{ch.index:03d}.xhtml",
                    lang="zh",
                )
                chapter.content = self._txt_to_html(text)
                book.add_item(chapter)
                all_items.append(chapter)
                vol_items.append(chapter)
                all_image_names.update(inline_imgs)

            if vol_items:
                toc_items.append(epub.Section(vol.name))
                toc_items.extend(vol_items)

        # Add inline images referenced in chapter text
        for vol in volumes:
            vol_path = os.path.join(base_dir, vol.name)
            illus_dir = self._find_illus_dir(vol_path)
            if not illus_dir:
                continue
            for fname in all_image_names:
                fpath = os.path.join(illus_dir, fname)
                if os.path.isfile(fpath):
                    ep_img = epub.EpubImage()
                    ep_img.file_name = f"images/{fname}"
                    ep_img.media_type = self._media_type(fname)
                    with open(fpath, "rb") as f:
                        ep_img.content = f.read()
                    book.add_item(ep_img)

        if not all_items:
            return None

        book.toc = toc_items or all_items
        book.spine = spine + all_items
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        epub.write_epub(output_path, book)
        return output_path

    def _find_illus_dir(self, vol_path):
        for name in ("插图", "鎻掑浘"):
            d = os.path.join(vol_path, name)
            if os.path.isdir(d):
                return d
        return None

    def _txt_to_html(self, text: str) -> str:
        """Convert plain text chapter content to HTML, expanding inline image markers."""
        lines = text.split("\n")
        body_lines = []
        past_header = False
        for line in lines:
            if not past_header:
                if line.startswith("=" * 50):
                    past_header = True
                continue
            body_lines.append(line)

        body = "\n".join(body_lines).strip()

        # Expand [IMG:filename] markers to <img> tags
        body = re.sub(
            r"\[IMG:([^\]]+)\]",
            r'<img src="images/\1" alt="\1" style="max-width:100%;display:block;margin:0.5em auto;"/>',
            body,
        )

        paragraphs = re.split(r"\n\s*\n", body)
        html_parts = []
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            if re.match(r"^<img\s", p):
                html_parts.append(p)
            else:
                p_escaped = (
                    p.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                html_parts.append(f"<p>{p_escaped}</p>")

        css = """
        <style>
            body { font-family: serif; line-height: 1.8; margin: 1em; }
            h1 { font-size: 1.6em; text-align: center; margin: 1em 0; }
            p { text-indent: 2em; margin: 0.5em 0; }
        </style>
        """
        return css + "\n".join(html_parts)

    @staticmethod
    def _sanitize(name):
        return re.sub(r'[<>:"/\\|?*]', "_", name)

    @staticmethod
    def _media_type(fname: str) -> str:
        if fname.lower().endswith(".png"):
            return "image/png"
        return "image/jpeg"
