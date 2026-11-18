# Security policy

## Reporting a vulnerability

Please report security problems privately, not in a public issue or pull request.

Use GitHub's private reporting: open the repository's **Security** tab and choose **Report a vulnerability**
(<https://github.com/keazzyyx/sf-hospitality-permits/security/advisories/new>). Only the maintainer sees the report.

Include what you can of:

- what is affected (the public conditions search, the API, the web app, the ingest scripts, a dependency);
- how to reproduce it, with the URL, request or input that shows it;
- what an attacker could do with it.

You will get an acknowledgement within 7 days and a fix or a decision within 30 days for anything confirmed. Once
it is fixed, the advisory is published and you are credited unless you ask not to be.

## What is in scope

- **SF Conditions Search** (<https://sf-conditions-search.vercel.app>) and the code that builds it
  (`apps/showcase`, `tools/conditions-search`, `scripts/validation/build_public_conditions_site.py`), including
  anything that would let the site load code or data from outside its own origin, or publish a private contact
  that the build is meant to withhold.
- **The API and web app** (`apps/api`, `apps/web`): authentication, access to another user's memos or plans,
  injection, and secrets in the code or its history.
- **The ingest code** (`packages/precedent`): anything that could make it run untrusted content as code.

## What is not in scope

- The public records themselves (Planning, Entertainment Commission, ABC, DataSF): report errors in a condition
  through the "Wrong or missing? Tell me" link on its result card.
- The answers the rules engine or the memo gives. They are not legal advice; a wrong answer is a bug, not a
  vulnerability. Open an issue.
- Findings that need a compromised device or browser, denial of service by volume, and missing headers with no
  shown impact.

## Supported versions

Only the `main` branch and the live site built from it are supported. There are no released versions.
