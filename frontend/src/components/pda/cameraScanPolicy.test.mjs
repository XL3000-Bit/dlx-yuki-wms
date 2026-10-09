import assert from "node:assert/strict";
import test from "node:test";
import {
  cameraScanKey,
  scanResultClass,
  shouldSubmitCameraScan,
} from "./cameraScanPolicy.ts";

const base = {
  value: "LOC-001",
  step: "EXPECT_LOCATION",
  online: true,
  isOpen: true,
  requestInFlight: false,
  lastAcceptedKey: null,
};

test("camera decode is eligible for the shared scan submit path", () => {
  assert.equal(shouldSubmitCameraScan(base), true);
});

test("an accepted code is not submitted twice in the same step", () => {
  assert.equal(
    shouldSubmitCameraScan({ ...base, lastAcceptedKey: cameraScanKey(base.step, base.value) }),
    false,
  );
  assert.equal(
    shouldSubmitCameraScan({ ...base, step: "EXPECT_LOT", lastAcceptedKey: cameraScanKey(base.step, base.value) }),
    true,
  );
});

test("NOT_FOUND and WRONG_LOCATION use the same failure presentation as manual input", () => {
  assert.equal(scanResultClass("NOT_FOUND"), "is-error");
  assert.equal(scanResultClass("WRONG_LOCATION"), "is-error");
  assert.equal(scanResultClass("ACCEPTED"), "is-ok");
});

test("camera state does not gate the manual submission policy", () => {
  assert.equal(shouldSubmitCameraScan(base), true);
  assert.equal(shouldSubmitCameraScan({ ...base, requestInFlight: true }), false);
});

test("offline decode can enter the shared local queue path, but quantity decode never submits", () => {
  assert.equal(shouldSubmitCameraScan({ ...base, online: false }), true);
  assert.equal(
    shouldSubmitCameraScan({ ...base, step: "EXPECT_QUANTITY_CONFIRMATION" }),
    false,
  );
});
