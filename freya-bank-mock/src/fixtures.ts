import fixtureData from "../../final/test-environment/test-customers.json" with { type: "json" };

export type Fixture = {
  http: number;
  response: unknown;
  delaySeconds?: number;
};

type Customer = (typeof fixtureData.customers)[number];

const customers = new Map<string, Customer>(
  fixtureData.customers.map((customer) => [customer.customerNo, customer]),
);

const cardOwners = new Map<string, string>();
for (const customer of fixtureData.customers) {
  for (const cardNumber of Object.keys(customer.services["cards.balance"] ?? {})) {
    if (cardOwners.has(cardNumber)) {
      throw new Error("Duplicate full card fixture key across customers");
    }
    cardOwners.set(cardNumber, customer.customerNo);
  }
}

function isFixture(value: unknown): value is Fixture {
  return typeof value === "object" && value !== null &&
    Object.hasOwn(value, "http") && Object.hasOwn(value, "response");
}

/** Exact fixture lookup. `selectors` are full card key, then requested week if applicable. */
export function resolveFixture(
  customerNo: string,
  service: string,
  selectors: readonly string[] = [],
): Fixture | undefined {
  const customer = customers.get(customerNo);
  if (!customer || !Object.hasOwn(customer.services, service)) return undefined;

  let node: unknown = customer.services[service as keyof typeof customer.services];
  for (const selector of selectors) {
    if (typeof node !== "object" || node === null || !Object.hasOwn(node, selector)) {
      return undefined;
    }
    node = (node as Record<string, unknown>)[selector];
  }
  return isFixture(node) ? node : undefined;
}

export function fixtureCustomers(): readonly Customer[] {
  return fixtureData.customers;
}

export function ownerOfFullCardKey(cardNumber: string): string | undefined {
  return cardOwners.get(cardNumber);
}
