# Security policy

## Supported versions

The current 1.x release line is supported. Older versions are not
patched — install the current release.

## What this tool touches

seller-profit-truth reads one local sales file (JSON or CSV) and
prints a report. It writes no files, opens no network connections,
collects no telemetry, and sends nothing anywhere. Your sales
figures never leave your machine.

If you attach a sales file to a public bug report, replace real
product names and round or alter the figures first — margins on a
real listing are commercially sensitive even in a "small" tool's
tracker.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository:
**Security tab → Report a vulnerability**. Please do not open a
public issue for a suspected vulnerability.

## Correctness issues

A report whose numbers disagree with the fee rates actually in force
(or with hand-worked arithmetic from the stated rates) is treated as
a correctness bug: open an issue with the input file (sanitized —
replace real product names and alter the figures first), the rates
used, and your hand-working. Any change to an encoded fee figure
needs its platform source and check date in the change description.
