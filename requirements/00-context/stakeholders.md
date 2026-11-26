# Stakeholders

> Example file (fictional domain: a meeting-room booking system) — replace it with the real list of your project's stakeholders.

The "Function" column describes the stakeholder's part in the business process. The last column, "Role", gives the role keys from `roles.yaml` (a copy of the example [`roles.example.yaml`](roles.example.yaml)) that the stakeholder holds: one or several. A stakeholder without a role is allowed. From the `catalog` level every role from `roles.yaml` must appear here (rule V8).

| Stakeholder | Function | Interest | Role |
|---|---|---|---|
| Employee | End user | Fast, error-free room booking | |
| Reception | Current process owner | Relief from managing bookings by hand | |
| IT department | System operator | Maintainability, no emergency escalations | `role-tech-lead`, `role-architect` |
| Office administrator | Handles exceptions (long bookings, conflicts) | Visibility and control over exceptions — see `REQQF-POL-BOOKING-001` (the starter kit's example requirements) | `role-product-owner` |
