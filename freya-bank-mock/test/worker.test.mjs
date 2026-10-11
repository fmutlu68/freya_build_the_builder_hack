import assert from "node:assert/strict";
import test from "node:test";
import worker from "../src/index.ts";
import { fixtureCustomers } from "../src/fixtures.ts";

const URL = "https://example.test/voice/v1/";

function request(service, data) {
  return new Request(URL + service, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ data, call: { ani: "", lang: "tr" } }),
  });
}

test("GET /health reports bank services ready", async () => {
  const response = worker.fetch(new Request("https://example.test/health"));
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), {
    status: "ok",
    bankServicesReady: true,
  });
});

test("all 617 fixture leaves return exact body and HTTP status through service routes", async () => {
  let count = 0;
  for (const customer of fixtureCustomers()) {
    for (const [service, tree] of Object.entries(customer.services)) {
      const entries = service === "cards.list" || service === "contact.email.get" || service === "statement.pdf.send"
        ? [[undefined, undefined, tree]]
        : Object.entries(tree).flatMap(([card, value]) =>
            service === "statement.week.decide" || service === "statement.week.change"
              ? Object.entries(value).map(([week, fixture]) => [card, week, fixture])
              : [[card, undefined, value]]);
      for (const [card, week, fixture] of entries) {
        const data = service === "cards.list"
          ? { customerNo: customer.customerNo, aiFlow: "CardOps" }
          : service === "contact.email.get"
          ? { customerNo: customer.customerNo, intAddressInfoType: "E" }
          : service === "statement.pdf.send"
          ? { customerNo: customer.customerNo, cardNumber: Object.keys(customer.services["cards.balance"])[0], currencyType: "TL", statementDate: "05.10.2026", emailAddress: "test@example.test" }
          : { cardNumber: card, ...(week ? { newStatementWeek: Number(week), statementDay: 1 } : {}) };
        const response = await worker.fetch(request(service, data));
        assert.equal(response.status, fixture.http, `${service} status`);
        assert.deepEqual(await response.json(), fixture.response, `${service} body`);
        count++;
      }
    }
  }
  assert.equal(count, 617);
});

test("unknown and malformed inputs do not return fixture success", async () => {
  const customer = fixtureCustomers().find((item) => item.services["cards.balance"]);
  const card = Object.keys(customer.services["cards.balance"])[0];
  const cases = [
    ["cards.list", { customerNo: "99999999" }, 404, "FB_IVR_CHANNEL_102"],
    ["cards.balance", { cardNumber: card.slice(-4) }, 404, "FB_IVR_CHANNEL_120"],
    ["statement.week.get", { cardNumber: "not-a-card" }, 404, "FB_IVR_CHANNEL_121"],
    ["statement.week.decide", { cardNumber: card, newStatementWeek: 9, statementDay: 1 }, 400, "INVALID_ARGUMENTS_ERROR"],
    ["contact.email.get", { customerNo: customer.customerNo, intAddressInfoType: "" }, 400, "INVALID_ARGUMENTS_ERROR"],
    ["statement.pdf.send", { customerNo: "99999999", cardNumber: card, currencyType: "TL", statementDate: "05.10.2026", emailAddress: "test@example.test" }, 404, "FB_IVR_CHANNEL_107"],
  ];
  for (const [service, data, status, code] of cases) {
    const response = await worker.fetch(request(service, data));
    assert.equal(response.status, status);
    const body = await response.json();
    assert.equal(body.result.returnCode, code);
    assert.equal(Object.hasOwn(body, "data"), false);
  }
  const method = worker.fetch(new Request(URL + "cards.list"));
  assert.equal(method.status, 405);
});

test("test-environment lookup ignores headers, call metadata and aiFlow", async () => {
  const customer = fixtureCustomers().find((item) => item.services["cards.balance"]);
  const card = Object.keys(customer.services["cards.balance"])[0];
  const list = await worker.fetch(new Request(URL + "cards.list", {
    method: "POST", body: JSON.stringify({ data: { customerNo: Number(customer.customerNo), aiFlow: "unused" } }),
  }));
  assert.equal(list.status, customer.services["cards.list"].http);
  assert.deepEqual(await list.json(), customer.services["cards.list"].response);
  const balance = await worker.fetch(new Request(URL + "cards.balance", {
    method: "POST", body: JSON.stringify({ data: { cardNumber: card } }),
  }));
  assert.equal(balance.status, customer.services["cards.balance"][card].http);
  assert.deepEqual(await balance.json(), customer.services["cards.balance"][card].response);
});
