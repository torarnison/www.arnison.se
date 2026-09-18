# www.arnison.se

Personal and professional website of Tor Arnison, built with [Quarto](https://quarto.org).

## How the site is put together

| File / folder | What it is |
|---|---|
| `_quarto.yml` | Site configuration: navigation, footer, fonts, pre-render scripts |
| `custom.scss` | The visual theme (blue palette, typography, layout) |
| `index.qmd` | Home page: photo, intro, email, links |
| `bio.qmd` | Bio page: free Markdown text |
| `publications.qmd` + `publications/` | Publication list, synced from ORCID |
| `cv.qmd` + `cv/cv.yml` | CV page, built from the YAML file |
| `scripts/` | The two Python scripts that build publications and CV before each render |
| `images/` | Profile photo, background illustration, favicon |
| `files/` | Put PDFs or other downloadable files here |
| `.github/workflows/publish.yml` | Renders and publishes the site automatically |

## Editing content

- **Intro text** – edit the paragraph in `index.qmd`. Links are in the `about.links` list in the same file.
- **Bio** – write in `bio.qmd`.
- **CV** – edit `cv/cv.yml`. Add entries or whole sections; the comments at the bottom show the format.
- **Publication summaries** – add an entry to `publications/summaries.yml`, keyed by DOI.
  You can also hide a work (`hide: true`) or add an extra link (e.g. a preprint).
- **Downloadable PDFs** – put the PDF in `files/papers/` and add `pdf: files/papers/<name>.pdf`
  to that publication's entry in `summaries.yml`. A "Download PDF" button appears under the
  reference. Only share versions the publisher allows (open-access articles, accepted manuscripts).
- **Profile photo** – run `python3 scripts/make_portrait.py path/to/photo.jpg` (needs Pillow:
  `pip install pillow`). It crops to 4:5, applies the site's colour grade and the oval fade, and
  writes `images/profile.webp`. Don't copy a photo over `profile.webp` by hand, or the photo will
  lose the treatment. Use `--focus 0.4` (or similar) if the face sits high or low in the frame.
- **A new page** – create `teaching.qmd` (any name), then add it to `navbar.right` in `_quarto.yml`:
  ```yaml
  - text: Teaching
    href: teaching.qmd
  ```

## Publications: how the ORCID sync works

`scripts/build_publications.py` runs before every render. It downloads all public works
from your ORCID record, fills in missing author lists and volume/issue from Crossref, merges
your summaries, and writes `publications/_generated.qmd`. (That file and `cv/_generated.qmd`
are committed as placeholders because Quarto checks that included files exist before the
scripts run; they are overwritten on every render.) A copy of the data is saved in
`publications/orcid-cache.json`, so the site still renders if ORCID is unreachable.

Anything you add to ORCID appears on the site the next time it is rendered. With the
GitHub Action below, that happens every Monday without you doing anything.

## Rendering locally

Requirements: [Quarto](https://quarto.org/docs/get-started/) and Python 3 with PyYAML
(`pip install pyyaml`).

```bash
quarto preview      # live preview in the browser while you edit
quarto render       # build the site into _site/
```

## Publishing (one-time setup)

The site is published by GitHub Actions to the `gh-pages` branch. To set it up:

1. Push this repository to `main`.
2. Create the `gh-pages` branch once (from your local clone):
   ```bash
   git checkout --orphan gh-pages
   git rm -rf .
   git commit --allow-empty -m "Initialise gh-pages"
   git push origin gh-pages
   git checkout main
   ```
3. On GitHub: **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
   branch `gh-pages`, folder `/ (root)`. Keep the custom domain `www.arnison.se`.
4. Go to **Actions**, open "Publish website" and click **Run workflow**. After a minute or
   two the site is live. From then on every push to `main`, and every Monday, republishes it.

The old `docs/` folder is no longer used and can be deleted.
