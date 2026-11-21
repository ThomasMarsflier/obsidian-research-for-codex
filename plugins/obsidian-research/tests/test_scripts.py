import importlib.util
import json
import sys
import tempfile
import unittest
import struct
import zlib
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crawl = load_script("crawl")
writer = load_script("write_note")
settings = load_script("settings")
images = load_script("download_image")


class CrawlTests(unittest.TestCase):
    def test_extracts_title_body_and_links_without_scripts(self):
        parser = crawl.PageParser("https://example.org/a")
        parser.feed("<title>Article</title><nav>Menu</nav><article><h1>Hello</h1><p>World</p><a href='/b'>Next</a><script>ignore me</script></article>")
        title, text, links, images = parser.result()
        self.assertEqual(title, "Article")
        self.assertIn("Hello\nWorld", text)
        self.assertNotIn("Menu", text)
        self.assertNotIn("ignore me", text)
        self.assertEqual(links, ["https://example.org/b"])
        self.assertEqual(images, [])

    def test_rejects_private_ip_and_cross_host(self):
        with patch.object(crawl.socket, "getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 0))]):
            with self.assertRaisesRegex(ValueError, "Private"):
                crawl.validate_url("http://localhost/")
        with self.assertRaisesRegex(ValueError, "Cross-host"):
            crawl.validate_url("https://other.org/", "example.org")

    def test_redirect_cannot_enter_robots_disallowed_path(self):
        handler = crawl.SameHostRedirect("example.org")
        class Robots:
            def can_fetch(self, agent, url):
                return not url.endswith("/private")
        handler.robots = Robots()
        with patch.object(crawl.socket, "getaddrinfo", return_value=[(None, None, None, None, ("93.184.215.14", 0))]):
            with self.assertRaisesRegex(ValueError, "robots"):
                handler.redirect_request(None, None, 302, "Found", {}, "https://example.org/private")

    def test_extracts_image_leads(self):
        parser = crawl.PageParser("https://example.org/story")
        parser.feed("<meta property='og:image' content='/cover.jpg'><article><img alt='Chart' src='/small.jpg' srcset='/small.jpg 400w, /large.jpg 1600w'></article>")
        _, _, _, images_found = parser.result()
        self.assertEqual(images_found[0]["url"], "https://example.org/cover.jpg")
        self.assertEqual(images_found[1]["url"], "https://example.org/large.jpg")
        self.assertEqual(images_found[1]["alt"], "Chart")


class WriterTests(unittest.TestCase):
    def test_creates_new_note_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            (vault / ".obsidian").mkdir()
            first = writer.write_note(vault, "Research", "A/B", "# First")
            second = writer.write_note(vault, "Research", "A/B", "# Second")
            self.assertEqual(first.name, "A B.md")
            self.assertEqual(second.name, "A B (2).md")
            self.assertEqual(first.read_text(), "# First\n")
            self.assertEqual(second.read_text(), "# Second\n")

    def test_rejects_escape_and_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            vault.mkdir()
            (vault / ".obsidian").mkdir()
            with self.assertRaises(ValueError):
                writer.write_note(vault, "../outside", "A", "text")
            (vault / "link").symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                writer.write_note(vault, "link", "A", "text")


class SettingsTests(unittest.TestCase):
    def test_presets_language_and_preserves_appearance(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            (vault / ".obsidian").mkdir()
            appearance = vault / ".obsidian" / "appearance.json"
            appearance.write_text('{"theme":"moonstone","enabledCssSnippets":["existing"]}')
            result = settings.configure(vault, "en-GB", "Research/Longform", 4, install_style=True)
            self.assertEqual(result["language"], "en-GB")
            self.assertEqual(settings.read_settings(vault)["folder"], "Research/Longform")
            after = json.loads(appearance.read_text())
            self.assertEqual(after["theme"], "moonstone")
            self.assertEqual(after["enabledCssSnippets"], ["existing", "obsidian-research"])
            self.assertTrue((vault / ".obsidian" / "snippets" / "obsidian-research.css").exists())


class ImageTests(unittest.TestCase):
    def test_reads_png_and_jpeg_dimensions(self):
        png = b"\x89PNG\r\n\x1a\n" + bytes(8) + (1600).to_bytes(4, "big") + (900).to_bytes(4, "big")
        self.assertEqual(images.dimensions(png, "image/png"), (1600, 900))
        jpeg = b"\xff\xd8\xff\xc0\x00\x11\x08\x03\x84\x06\x40" + bytes(10)
        self.assertEqual(images.dimensions(jpeg, "image/jpeg"), (1600, 900))

    def test_downloads_hd_image_with_attribution(self):
        width, height = 1600, 900
        def chunk(tag, payload):
            return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff)
        pixels = (b"\x00" + b"\xff\xff\xff\xff" * width) * height
        data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")
        class Headers:
            def get_content_type(self): return "image/png"
        class Response:
            headers = Headers()
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def geturl(self): return "https://example.org/image.png"
            def read(self, limit): return data
        class Opener:
            def open(self, *args, **kwargs): return Response()
        class Robots:
            def can_fetch(self, *args): return True
        with tempfile.TemporaryDirectory() as temporary:
            vault = Path(temporary)
            (vault / ".obsidian").mkdir()
            with patch.object(images, "validate_url", side_effect=lambda url, expected_host=None: url), patch.object(images, "robots_for", return_value=Robots()), patch.object(images, "build_opener", return_value=Opener()):
                result = images.download_image(vault, "Research/_assets/topic", "https://example.org/image.png", "https://example.org/story", "CC BY 4.0", "Example", "A chart")
            saved = Path(result["path"])
            self.assertTrue(saved.exists())
            self.assertEqual((result["width"], result["height"]), (width, height))
            metadata = json.loads(saved.with_suffix(".png.json").read_text())
            self.assertEqual(metadata["license"], "CC BY 4.0")


if __name__ == "__main__":
    unittest.main()
