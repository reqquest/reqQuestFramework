---
id: REQQF-FR-BOOKING-002
title: Booking creation API
short_title: booking-api
type: FR
status: approved
owner: role-tech-lead
version: "1.1"
last_updated: 2026-11-22
tags: [example, booking]
category: BOOKING
traces_to: [REQQF-BR-BOOKING-001]
---

# REQQF-FR-BOOKING-002 — Booking creation API

> Example interface requirement (fictional domain) — an integration contract as a functional requirement with an embedded OpenAPI fragment. The fragment convention is described in [`conventions.md`](https://github.com/reqquest/reqQuestFramework/blob/main/docs/framework/conventions.md), section 9.

## Description

The system shall provide clients (the web application and external calendars) with an operation that creates a room booking. The client gives the room and the start and end of the time slot. The meaning and rules of a booking are described in [`REQQF-FR-BOOKING-001-room-booking`](REQQF-FR-BOOKING-001-room-booking.md); this requirement sets how the client calls it.

## Acceptance criteria

- A valid request creates the booking and returns it with an assigned identifier (`201`).
- A request whose slot overlaps an existing booking of that room returns the error `409` with the identifier of the conflicting booking in the field `conflictingBookingId`.
- A slot end earlier than its start returns the error `400`.

## Structure

```yaml openapi id=REQQF-FR-BOOKING-002.create-booking
paths:
  /bookings:
    post:
      operationId: createBooking
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/BookingRequest'
      responses:
        201:
          description: Booking created.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Booking'
        400:
          description: Invalid time slot.
        409:
          description: The slot overlaps an existing booking.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BookingConflict'
components:
  schemas:
    BookingRequest:
      type: object
      required: [roomId, start, end]
      properties:
        roomId:
          type: string
        start:
          type: string
          format: date-time
        end:
          type: string
          format: date-time
    Booking:
      allOf:
        - $ref: '#/components/schemas/BookingRequest'
        - type: object
          required: [id]
          properties:
            id:
              type: string
    BookingConflict:
      type: object
      required: [conflictingBookingId]
      properties:
        conflictingBookingId:
          type: string
```

## Related

- Derives from: [`REQQF-BR-BOOKING-001-self-service-booking`](../../business/REQQF-BR-BOOKING-001-self-service-booking.md)
- Booking behaviour: [`REQQF-FR-BOOKING-001-room-booking`](REQQF-FR-BOOKING-001-room-booking.md)
