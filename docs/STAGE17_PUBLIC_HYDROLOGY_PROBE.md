# Stage 17 public hydrology source probe

## Scope

This probe checks reachability and metadata for official public pages identified in the Stage 17 physical-data source inventory．It targets the Onga River Office，the official station list，candidate Onga and Nishikawa station pages，the national hydrology database root，and the JMA tide table．

A second targeted probe inspects the official `river.go.jp` public application's own metadata and water-level API．The API base path and route templates were recovered from the JavaScript bundle served by that official application，rather than inferred from a third-party service．

The probes are diagnostic only．They do not assign a station to M，N，O，or G，do not write an observation into the solver，and do not approve any physical source．

## Public-page probe

For each target，the workflow records the requested and final URL，HTTP status，content type，received byte count，SHA-256，page title，encoding，script URLs，link count，and strings that may indicate official data endpoints or observation identifiers．Static JavaScript resources linked from the pages are downloaded within size and count limits and scanned for candidate endpoint strings．

## Official application API probe

The official application bundle identifies an API base under the same `river.go.jp` origin and provides templates for current and past water-level retrieval．The targeted probe therefore records:

- `setting.json`，`miniSetting.json`，the official current-time resource，and common master metadata
- the official application time used for a reproducible request
- current and past endpoint attempts for 祇園橋，唐熊，and 中間
- padded and unpadded observation-code forms because the public application converts query values to numbers internally
- HTTP status，content type，payload SHA-256，JSON parsing result，key inventory，and whether the expected station and river names occur in the response

Every raw public response is preserved in the workflow artifact．The report does not promote a successful payload to an approved time series．

## Interpretation

A successful HTTP or JSON response proves only that the official public resource was reachable during the workflow run．It does not establish that a complete historical archive，discharge，rating curve，quality flag，coordinate，or vertical datum is available．Those properties require a separate metadata and data-content audit．

The station pages for 祇園橋，唐熊，and 中間 carry official observation identifiers．The probe preserves those identifiers but does not infer hydraulic compatibility with numerical boundaries．The standalone 立屋敷 page is treated separately because it is served by the Onga River Office rather than the same single-page application route．

A current water-level value is especially unsuitable as a direct solver input because a physical run requires a period-specific time series，quality information，vertical datum，and an approved mapping from the observation point to the numerical boundary．

## Failure handling

The workflow requires the core Onga Office pages，the official station list，the 立屋敷 page，the JMA tide table，and the official application current-time resource to be reachable．Dynamic station or historical endpoint failures are preserved as diagnostics．A failed or partial probe is not permission to substitute an unverified third-party source．

## Safeguards

- Approved water geometry and metric mesh are not modified．
- No physical value is assigned．
- No source candidate is approved．
- No external office contact is performed．
- No public-simulator connection is added．
- JMA astronomical tide remains a secondary reference rather than an observed M-boundary substitute．
