# Marker annotation — DATASET2 Task 1.5

Interactive labeling of 200 silence markers for the wearer-POV gating corpus, used to
validate the behavioural proxy against human judgement (Cohen's kappa).

**This repo is private and generated.** Edit the app in the thesis repo
(`analysis/annotate_ui.py`) and re-run `orchestration/publish_annotation_app.py`.

## For annotators

Open the app URL, type your name as the **Annotator ID**, and label each card `1` or
`0`. Read the rules in the collapsible panel first — kappa only means something if
everyone applies the same criterion.

Keyboard: `1` trigger · `0` not a trigger · `←` `→` navigate · `Enter` next.

Your work saves automatically after every card, and is restored if the app restarts, so
you can stop and come back. There is also a download button in the sidebar.

Each annotator's labels are written to `annotations/dataset2_annotation_sheet_<id>.csv`.
Label independently — **do not compare answers with the other annotator**, or the
agreement statistic becomes meaningless.

## Deploying

1. https://share.streamlit.io → **Create app** → pick this repo, branch `main`,
   main file `streamlit_app.py`.
2. **Advanced settings → Secrets**, paste:

   ```toml
   [github]
   token  = "github_pat_..."
   repo   = "OWNER/REPO"
   branch = "main"
   ```

   Use a fine-grained token scoped to this repository only, with
   **Contents: Read and write**. Without it the app still runs, but progress lives only
   in the browser session and is lost on restart.
3. Deploy, then share the URL.

## Data

Transcript excerpts are from the ICSI Meeting Corpus, CC BY 4.0
(https://groups.inf.ed.ac.uk/ami/icsi/).
