---
name: setup-obsidian-research
description: Configure the target Obsidian vault, preferred note language, output folder, image count, and reading-view style for Obsidian Research.
---

Find existing Obsidian vaults on the user's device. Ask the user to choose if more than one is plausible, and ask for the preferred output language if they have not provided one. Default to `zh-CN` only when no preference is known; the language may be changed later or overridden in an individual research request. Ask for an output folder only if the user has a preference; otherwise use `Research`.

Resolve `../../scripts/settings.py` relative to this skill folder. Run `python3 PATH_TO_SETTINGS set --vault VAULT_PATH --language LANGUAGE --folder FOLDER --max-images 6 --install-style`. This stores the preferences in the selected vault's `.obsidian-research.json` and installs the bundled Reading View CSS snippet in that vault. Verify by running the script's `show` command and checking the target vault's `.obsidian/appearance.json` lists `obsidian-research` under `enabledCssSnippets`. Tell the user which vault, language, and folder are configured.

Do not change another vault. Preserve other Obsidian appearance settings. The CSS affects only notes whose frontmatter contains `cssclasses: [obsidian-research]`.
