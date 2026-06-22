# AG Seminar @ Utrecht University

A minimal [Hugo](https://gohugo.io) website for the Algebraic Geometry Seminar at
Utrecht University. All seminar data lives in YAML files, one per block, under
`data/blocks/`. The page groups blocks into *current* / *upcoming* / *past*
automatically based on today's date.

## Adding a talk

Edit the YAML file of the relevant block in `data/blocks/` and add an entry to
its `talks:` list:

```yaml
  - date: 2026-06-16
    speaker: "Jane Doe"
    affiliation: "Some University"
    title: "A great talk"
    abstract: >-
      Abstract text, wrapped over
      multiple indented lines.
```

All fields except `date` are optional:

- `time:` and `room:` only when they differ from the block default
  (a hint like "15.30" or "BBG 1.61"),
- `note:` for anything unusual: `"No talk"`, `"cancelled"`,
  `"special lecture on the occasion of ..."`, etc.
- an entry with only `date:` and `note:` renders as a single line without
  expandable details.

## Adding a block

Create `data/blocks/<year>-<block>.yaml` (the file name does not matter, only
the fields):

```yaml
block: "Block I"
year: "2026–2027"
start: 2026-09-01
end: 2026-11-06
schedule: "Tuesdays from 13.30 to 14.30 CET"
room: "HFG 7.07"
talks: []
```

## Previewing locally

```sh
hugo server
```

and open <http://localhost:1313>.

## Deploying

**GitHub Pages**: push to `main`; `.github/workflows/deploy.yml` builds and
publishes the site (enable Pages with source "GitHub Actions" in the repository
settings once). A weekly scheduled rebuild keeps the current/past grouping
fresh between pushes.

**University web space**: build with the final URL and upload `public/`:

```sh
hugo --minify --baseURL "https://webspace.science.uu.nl/~user/agseminar/"
rsync -av public/ user@host:path/to/webspace/
```

## Data provenance

The historical data (2021 – June 2026) was scraped from the previous seminar
pages ([Soumya Sankar's](https://sites.google.com/site/soumya3sankar/organization/ag-seminar-uu)
and [Woonam Lim's](https://sites.google.com/view/woonamlim/organization/ag-seminar-at-uu))
by the one-off scripts in `scripts/`; they are kept for reference only and are
not needed to build the site.
