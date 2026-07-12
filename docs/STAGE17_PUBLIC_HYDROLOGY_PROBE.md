# Stage 17 public hydrology source probe

## Scope

This probe checks reachability and static metadata for official public pages identified in the Stage 17 physical-data source inventory．It targets the Onga River Office，the official station list，candidate Onga and Nishikawa station pages，the national hydrology database root，and the JMA tide table．

The probe is diagnostic only．It does not assign a station to M，N，O，or G，does not download a value into the solver，and does not approve any physical source．

## Recorded information

For each target，the workflow records the requested and final URL，HTTP status，content type，received byte count，SHA-256，page title，encoding，script URLs，link count，and strings that may indicate official data endpoints or observation identifiers．Static JavaScript resources linked from the pages are also downloaded within size and count limits and scanned for candidate endpoint strings．

## Interpretation

A successful HTTP response proves only that the public page was reachable during the workflow run．It does not establish that historical data，discharge，rating curves，quality flags，coordinates，or vertical datums are available．Those properties require a separate metadata and data-content audit．

The station pages for 祇園橋，唐熊，and 中間 carry official observation identifiers in their query parameters．The probe preserves those identifiers but does not infer hydraulic compatibility with the numerical boundaries．The standalone 立屋敷 page is treated separately．

## Failure handling

The workflow requires the core Onga Office pages，the official station list，the 立屋敷 page，and the JMA tide table to be reachable．Dynamic river.go.jp station pages and the historical database are recorded even when JavaScript，access control，or encoding prevents complete static parsing．A failed or partial probe is diagnostic evidence，not permission to substitute an unverified third-party source．

## Safeguards

- Approved water geometry and metric mesh are not modified．
- No physical value is assigned．
- No external office contact is performed．
- No public-simulator connection is added．
- JMA astronomical tide remains a secondary reference rather than an observed M-boundary substitute．
