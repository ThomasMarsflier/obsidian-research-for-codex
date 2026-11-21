# Obsidian Research for Codex

A desktop-only Codex plugin that researches a user-provided topic or public URL and creates an Obsidian Markdown note with citations and a separate analysis section.

## What it does

- Uses Codex's available web search and reading tools to find and compare sources for a topic.
- Includes a bounded public HTML crawler for a supplied URL: same host, robots.txt checks, public-network targets only, at most 20 pages and depth 2.
- Finds and stores permitted high-resolution images with creator, source, license, dimensions, and local Obsidian embeds.
- Lets you preset the note language, folder, and image count per vault. Codex compares translated material back against the source and corrects material drift.
- Writes a new note into a selected Obsidian vault without overwriting an existing note.
- Uses an editorial Markdown layout and a scoped Reading View style, while keeping sourced findings, the assistant's analysis, and unresolved questions distinct.

The crawler does not handle login-protected pages, paywalls, JavaScript-only content, PDFs, or sites that prohibit automated access. The image downloader accepts PNG, JPEG, and WebP files only after the research workflow verifies reuse rights. Web search availability depends on the Codex environment. The plugin does not claim exhaustive coverage of the web.

## Install

This repository is a Codex plugin package. In a supported Codex desktop environment, add this repository as a plugin marketplace source:

```sh
codex plugin marketplace add ThomasMarsflier/obsidian-research-for-codex
```

Then install **Obsidian Research** from the marketplace in the desktop app. Restart the app if it does not appear immediately. Run its setup skill to select a vault and preset the output language. Setup installs a CSS snippet that affects only notes tagged with the plugin's `cssclasses` frontmatter. The plugin needs local execution and write access to the Obsidian vault you choose. No separate API key is required by the bundled scripts.

Example prompt:

> Research the latest evidence on a topic, compare sources, and save a cited note with your own analysis to my Obsidian vault.

You can also provide a public URL and override the preset language or folder in a request. The skill asks for a vault when it cannot choose safely.

## Development

The plugin package lives in [`plugins/obsidian-research`](plugins/obsidian-research). It uses Python 3.9+ and the standard library. Run:

```sh
python3 -m unittest discover -s plugins/obsidian-research/tests -v
python3 package.py
python3 /path/to/quick_validate.py plugins/obsidian-research/skills/research-to-obsidian
```

The final command uses the `quick_validate.py` bundled with Codex's `skill-creator` skill. The ZIP release contains only the plugin package, with `plugin.json` at its root.

## Publishing

The GitHub release distributes the plugin package. Public listing in the shared OpenAI Plugin Directory is a separate process requiring a verified developer identity, ZIP upload, automated checks, review, and an explicit publish action. This plugin is marked **Desktop only** because it writes local Obsidian files.

## Privacy and support

See [Privacy](PRIVACY.md) and [Support](SUPPORT.md).

## License

MIT. See [LICENSE](LICENSE).
