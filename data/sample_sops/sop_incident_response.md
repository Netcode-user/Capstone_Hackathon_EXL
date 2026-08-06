# SOP: Production Incident Response

## Step 1: Detection and Triage
When a monitoring alert fires or a customer reports an outage, the on-call engineer
must acknowledge the page within 5 minutes and classify severity (SEV1-SEV4) based on
customer impact.

## Step 2: Incident Commander Assignment
For SEV1 and SEV2 incidents, the on-call engineer must page an Incident Commander (IC)
and open a dedicated incident channel before taking any remediation action.

## Step 3: Communication Cadence
The IC must post a status update to the #incidents channel and the public status page
every 30 minutes for the duration of a SEV1 incident, and every 60 minutes for SEV2.

## Step 4: Mitigation
Engineers apply mitigations (rollback, feature flag disable, traffic shift) only after
the IC approves the action in the incident channel, except in cases of active data loss
where immediate action is permitted and must be logged retroactively.

## Step 5: Resolution and Postmortem
Once resolved, the IC closes the incident and schedules a blameless postmortem within
3 business days. The postmortem document must be published to the engineering wiki.
