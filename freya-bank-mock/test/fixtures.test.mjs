import assert from "node:assert/strict";
import test from "node:test";
import { fixtureCustomers, resolveFixture } from "../src/fixtures.ts";

function* leaves(node, selectors = []) {
  if (node && typeof node === "object" && Object.hasOwn(node, "http") && Object.hasOwn(node, "response")) {
    yield { selectors, fixture: node };
    return;
  }
  for (const [key, value] of Object.entries(node)) {
    yield* leaves(value, [...selectors, key]);
  }
}

test("every source fixture leaf resolves to the same response and HTTP status", () => {
  const customers = fixtureCustomers();
  assert.equal(customers.length, 34);
  let count = 0;
  let delayed = 0;
  for (const customer of customers) {
    for (const [service, tree] of Object.entries(customer.services)) {
      for (const { selectors, fixture } of leaves(tree)) {
        const selected = resolveFixture(customer.customerNo, service, selectors);
        assert.deepEqual(selected, fixture);
        assert.equal(selected.http, fixture.http);
        assert.deepEqual(selected.response, fixture.response);
        if (Object.hasOwn(selected, "delaySeconds")) delayed++;
        count++;
      }
    }
  }
  assert.equal(count, 617);
  assert.equal(delayed, 1);
});

test("unknown customer, service, full card key, or requested week never falls back", () => {
  const customer = fixtureCustomers().find((item) => item.services["cards.balance"]);
  assert.ok(customer);
  const card = Object.keys(customer.services["cards.balance"])[0];
  assert.equal(resolveFixture("not-a-customer", "cards.list"), undefined);
  assert.equal(resolveFixture(customer.customerNo, "unknown-service"), undefined);
  assert.equal(resolveFixture(customer.customerNo, "cards.balance", ["wrong-full-card-key"]), undefined);
  assert.equal(resolveFixture(customer.customerNo, "cards.balance", [card.slice(-4)]), undefined);
  assert.equal(resolveFixture(customer.customerNo, "statement.week.decide", [card, "999"]), undefined);
});
