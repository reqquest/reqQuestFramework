# Project glossary

> Starting file (fictional domain: a meeting-room booking system) — replace the examples with your project's terms. It arrives with the first toolkit install; after that it belongs to the project, and `adopt`, `check` and `upgrade` never touch it. The glossary rules (one glossary from two files, definitions flowing glossary → requirements) are described in the base [`glossary.md`](glossary.md).

| Term | Definition |
|---|---|
| **Booking** | A time slot assigned to one room and one employee, which prevents another booking of the same room in the same slot. |
| **Booking conflict** | An attempt to create two bookings of the same room with overlapping time slots. |
| **Long booking** | A booking that lasts longer than 4 hours — it is subject to an additional approval rule, see `REQQF-POL-BOOKING-001` in the starter kit's example requirements. |
