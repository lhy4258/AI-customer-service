import assert from "node:assert/strict";
import { resolveAppRole } from "../src/appRole.js";

assert.equal(resolveAppRole("development"), "customer");
assert.equal(resolveAppRole("customer"), "customer");
assert.equal(resolveAppRole("support"), "support");
assert.equal(resolveAppRole("anything-else"), "customer");

console.log("entry mode checks passed");
