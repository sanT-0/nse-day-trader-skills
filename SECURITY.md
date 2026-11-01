# Security policy

## Supported versions

Security fixes are applied to the latest release on the `main` branch.

## Reporting

Please open a private GitHub security advisory for credential exposure,
unsafe order-execution behavior, path traversal or dependency compromise.
For ordinary calculation/data bugs, open a normal issue with secrets removed.

## Credentials and broker safety

- This project does not need any broker token for its supported manual workflow.
- Never paste broker credentials, OTPs, access tokens, PAN or account data
  into an issue, prompt, log or state file.
- `nse-trader-broker` only writes portable JSON/Markdown. It does not import a
  broker SDK or call a broker endpoint.
- The optional SDK sample inside a generated ticket is inert text. Users who
  run it themselves assume responsibility for credentials and orders.
- CI never executes live market tests or broker calls.

## Market-data caveat

Market-data endpoints are untrusted external input. Scripts parse only the
expected data fields and degrade with an explicit error; returned text is not
executed as code.
