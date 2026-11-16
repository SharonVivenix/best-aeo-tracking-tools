# Contributing

This repo files AEO tools by the tap they read and ships a log reader for the tap most of them skip. The two most useful contributions are a corrected fact with a vendor link, and a new AI user agent with a link to the vendor's crawler documentation.

## Change the data, then regenerate

1. Edit [tools.yaml](tools.yaml). One entry per tool, entry plan facts only.
2. Set `taps` to what the vendor says it measures: `crawl`, `fanout`, `answer`, `click`. If the public pages do not say, leave the tap out.
3. Never type the Blind to column or the coverage table. `render_table.py` derives both from `taps`.
4. Run `python render_table.py --write`, then `python render_table.py --check`.
5. Open a pull request with the vendor link.

## Add a user agent

Agents live in [aeolog/agents.py](aeolog/agents.py). Each one needs a token, a vendor, an engine id and a purpose of `training`, `search` or `user`. Link the vendor page that documents the purpose. Tokens that only exist in `robots.txt`, such as `Google-Extended`, do not belong in the registry because they never appear in a log.

## Accepted

* Price, plan, prompt or engine changes with a source link.
* A published capture method for a tool marked `Not published`.
* A new referrer host for an AI assistant.
* Parsers for other log formats, with a test.

## Not accepted

* Affiliate or tracking links.
* Review scores and star ratings.
* Dependencies in `aeolog`. It stays standard library only and must run on Python 3.10.

## Code

```bash
pip install pyyaml
python render_table.py --check
python -m unittest discover -s tests -v
python examples/make_sample.py
```

If you change the sample generator, rerun it and keep the four planted problems, because the tests look for each one.
