# SOP: Enterprise Customer Onboarding

## Step 1: Contract Handoff
Once a deal closes, Sales must hand off the signed contract and account plan to
Customer Success within 24 hours via the CRM handoff form.

## Step 2: Kickoff Call Scheduling
Customer Success schedules a kickoff call with the customer's technical point of
contact within 5 business days of handoff, and sends a pre-read agenda 48 hours prior.

## Step 3: Environment Provisioning
The onboarding engineer provisions the customer's production environment using the
standard Terraform onboarding module, and must not manually create cloud resources
outside of Terraform, since that breaks drift detection and auditability.

## Step 4: Data Migration
Historical data is migrated using the approved migration toolkit and validated against
the customer's source system record counts before going live. Discrepancies over 1%
must be resolved before cutover.

## Step 5: Go-Live and Handoff to Support
After a successful validation window of 5 business days with no critical issues, the
account is handed off from onboarding to standard Support, and the customer receives
their permanent Slack Connect channel.
