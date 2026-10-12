# Property Membership Rollout

Property authorization is delivered in two stages so existing owners and managers are not locked out.

## Stage 1: schema and reconciliation

Deploy migration `0053_property_membership` and the membership admin while leaving
`PROPERTY_MEMBERSHIP_ENFORCEMENT` unset or false. Existing email-based access remains available during this stage, while all newly created owner properties and manager invitations also create explicit memberships.

Before enforcement:

1. Export a dry-run inventory containing property IDs, current owner/manager email fields, candidate user IDs, roles, and any linked intake IDs. Do not create memberships from email equality automatically.
2. Have an authorized operator verify each property-to-user mapping. Ambiguous, duplicate, edited, or unmatched identities remain unresolved.
3. Insert only approved `(property_id, user_id, role)` rows in a transaction and retain an audit copy of the approved mapping.
4. Confirm every active owner and manager has the expected memberships and that unresolved properties are documented.
5. Test owner, manager, assistant, admin, resident, private-media, and reporting access in a non-production environment with enforcement enabled.

Rollback for Stage 1: leave enforcement disabled. Membership rows are additive and do not change legacy access.

Known Stage 1 risk: while enforcement is false, a logged-in owner or manager whose email matches a legacy property email field still receives that property's legacy authorization even without a membership row. Invitation signup identity is still bound to the invited email, but the legacy email authorization path remains until the reviewed Stage 2 switch. Keep Stage 1 short, audit email changes, and do not treat schema deployment alone as completing the authorization repair.

## Stage 2: authorization enforcement

After reconciliation and access verification, set `PROPERTY_MEMBERSHIP_ENFORCEMENT=true` in a reviewed release. This makes owner and manager access fail closed unless an explicit membership exists.

Release checks:

- Re-run the reconciliation inventory and require zero unexplained active-user gaps.
- Apply migrations before enabling enforcement.
- Run system, migration, focused authorization/media/Stripe, and broader tests.
- Verify representative owner and manager accounts in the target environment without changing their data.

Rollback for Stage 2: set `PROPERTY_MEMBERSHIP_ENFORCEMENT=false` and restart the service. Do not delete membership rows; investigate and correct the missing or incorrect mappings before re-enabling enforcement.
