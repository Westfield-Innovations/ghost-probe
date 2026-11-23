# ghost-probe

The Ghost Probe checks whether a word names a real mechanism or only carries borrowed value, and gives one of three verdicts: GHOST, REAL or SPLIT. This package is its reader.

Created by Carl D. Hildebrandt · Westfield Innovations LLC

Official Ghost Probe: https://azus.ai/tools/ghost-probe/

The words of the Ghost Probe live only at that address. People read them there. Programs read them there through this reader, which holds none of the words.

It pairs with the Noun Probe (https://azus.ai/tools/noun-probe/): the Ghost Probe asks whether a word names anything at all; the Noun Probe pins a surviving word to one job.

## Install

```
pip install ghost-probe
```

It needs nothing beyond Python 3.11 or later.

## Use

```python
import ghost_probe

def my_ai(text):
    # Send `text` to the AI you already use and return its answer.
    ...

report = ghost_probe.run(
    subject="...the word, label or cause under test...",
    boundary="...the domain: what is in scope, and what is not...",
    ask=my_ai,
)
```

The report comes back with the four credit lines at its end. `ghost_probe.prompt(...)` gives the same text without calling your AI, and `ghost_probe.read(edition=1)` fixes a program to one numbered edition, whose words never change.

To see exactly what the reader reads:

```
ghost-probe            # or: python -m ghost_probe
```

## What the reader does and never does

It makes one read-only request to the official address (two when fixed to an edition: the edition and the current title block), puts the words together with your subject for your own AI, and puts the credit lines at the end of every report. It holds one reading in memory for five minutes.

It never holds the words, never sends your text, account or any identifier, never writes to disk, and never contacts any address except the official one. A proxy set for your system (`HTTPS_PROXY`) is used as usual. If the address cannot be read, it stops and runs nothing.

## Terms

Use of the Ghost Probe, through this reader or the page, is governed by the terms published at https://azus.ai/tools/ghost-probe/
