# Dispatch Priority and Readiness

## Business objective

Dispatch intelligence lets warehouse operators see when a source container is needed without opening every FC task. It keeps outbound urgency separate from inventory-aging priority and provides a conservative indication of whether the inventory can be dispatched.

## Field definitions

- **Earliest Outbound**: earliest scheduled date among valid remaining outbound allocations for a source container.
- **Days Remaining**: calendar-day difference between Earliest Outbound and the backend warehouse business date.
- **Dispatch Priority**: outbound urgency derived only from Days Remaining.
- **Dispatch Readiness**: operational availability derived from outbound status, remaining allocation, and inventory capacity.
- **Warehouse Days**: non-negative calendar days since the source inventory inbound date. Existing inventory-aging colors remain unchanged.

## Earliest outbound calculation

The relationship is:

```text
Container -> InventoryLot -> OutboundInventoryAllocation -> OutboundOrder
```

The value is:

```text
MIN(OutboundOrder.schedule_pickup_at)
```

The grouped query excludes:

- `CANCELED` orders;
- `COMPLETED` orders;
- allocations whose allocated pallet quantity is fully completed;
- orders without `schedule_pickup_at`.

The value is derived on every request. Imports and manual schedule/allocation/status changes therefore cannot leave a stale container value. Excel headers such as Outbound Date, Ship Date, Scheduled Outbound, 出库日期, and 最早出库时间 map only to `OutboundOrder.schedule_pickup_at`; they never write a container-derived field.

## Dispatch priority rules

| Days Remaining | Priority |
| --- | --- |
| `<= 0` | CRITICAL |
| `1–2` | HIGH |
| `3–5` | MEDIUM |
| `> 5` or unscheduled | NORMAL |

The thresholds use the configured Business Today and business-local outbound date, not exact elapsed hours. The frontend renders the returned date-only value and does not recalculate priority.

## Business timezone

- `BUSINESS_TIMEZONE` defaults to `America/Los_Angeles` and is loaded through the existing backend settings system.
- **Business Today** is the calendar date of the current instant after conversion to `BUSINESS_TIMEZONE`. It does not depend on the operating-system timezone or PostgreSQL session timezone.
- A timezone-aware outbound timestamp is converted to the business timezone before its date is used for display, Days Remaining, or Dispatch Priority.
- A naive datetime from API input, `datetime-local`, FBA scheduling, or Excel import is interpreted as local wall time in `BUSINESS_TIMEZONE`; it is never assumed to be UTC.
- Days Remaining is `business outbound date - Business Today`.
- Operational date filters use a timezone-aware half-open range `[local midnight, next local midnight)`. Each midnight is constructed independently, so 23-hour and 25-hour DST days are handled correctly.
- PostgreSQL `timestamptz` stores an instant. That instant is kept for `MIN(schedule_pickup_at)` ordering; conversion to a business date happens only when deriving operational date values.
- Inventory aging, warehouse days, inbound/FBA aging, and PostgreSQL FBA workbench aging use the same Python-supplied Business Today. They do not use SQL `current_date`.

## Dispatch readiness rules

State precedence is conservative:

1. `BLOCKED`: an active outbound exception exists.
2. `COMPLETED`: the outbound is completed or all allocated pallet quantity is completed.
3. `NOT_READY`: canceled work, missing inventory, missing/zero allocation, or insufficient inventory capacity for the remaining allocation.
4. `PARTIAL`: some, but not all, allocated quantity is completed.
5. `READY`: inventory capacity covers a valid remaining allocation and no blocking state applies.

Canceled orders do not contribute pending urgency or readiness. Released/rolled-back quantities stop contributing once no valid remaining allocation exists.

## Pages

- **Container Tracking**: earliest outbound, remaining days, warehouse days, priority filters, date presets/custom range, server sorting, and a Dispatch Overview drawer with readiness and related OB links.
- **FBA Workbench**: dispatch priority/date/days columns alongside the existing inventory-aging priority.
- **Outbound Workbench**: Remaining Source shows inbound date, warehouse days, earliest outbound, and priority, with urgent sources first.

Dispatch indicators use consistent colors and tooltips. Empty or unscheduled values display `--`; Container Tracking provides explicit list/detail errors, filter-empty text, and a NOT_READY explanation.

## Acceptance criteria

- Multiple active orders return their minimum scheduled outbound date.
- Canceled, completed, unscheduled, and fully completed allocations do not create urgency.
- Priority thresholds match the table above.
- Exception and terminal states cannot be overwritten by READY.
- Partial completion, insufficient inventory, missing allocation, and cancellation return conservative readiness states.
- Container lists use one aggregate query rather than one outbound query per row.
- Schedule changes require existing outbound-write permission, reject completed/canceled orders, and write an audit record.
- Invalid imported dates produce an `INVALID_DATE` validation issue before confirmation.

## Known limitations

- Per-warehouse timezones are not supported. All warehouses currently use the single configured `BUSINESS_TIMEZONE`.
- Readiness is pallet-based because pallet quantity is the common operational measure in the current workflows. Carton, weight, and CBM shortages remain protected by allocation validation but do not independently change the displayed readiness state.
- The current frontend has no unit-test runner. Component behavior is validated by TypeScript compilation and the production build; adding a lightweight test framework should be handled separately rather than introducing a new dependency during this acceptance pass.
